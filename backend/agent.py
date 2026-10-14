import os
import time
import difflib
from pathlib import Path
from typing import List, Callable, Dict, Any

from backend.config import MODEL_NAME, MAX_ATTEMPTS, MAX_TIME_MINUTES
from backend.models import AgentResult, AgentEvent, TestResult
from backend.sandbox import run_tests
from backend.llm import get_provider, ToolCall

SYSTEM_PROMPT = """You are a careful senior engineer fixing failing tests in a Python repository.
Your task is to fix the failing tests.
- First, read the failing test output, then read the failing test and the source file it exercises.
- Prefer fixing the SOURCE code. Never edit or delete tests to make them pass, never skip tests, never add pytest.mark.skip.
- Make the smallest possible change. Prefer using `edit_file` for existing files. Use `write_file` ONLY for creating completely new files.
- After each edit, call run_tests to verify your fix.
- When tests pass, stop and give a short summary: root cause, what changed, and why it is correct.
"""

TOOLS = [
    {
        "name": "list_files",
        "description": "Returns a directory tree of the repository (max depth 3, ignores git/pycache/venv/node_modules). Use this to find where files are located.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to list (default: '.')",
                    "default": "."
                }
            }
        }
    },
    {
        "name": "read_file",
        "description": "Reads the contents of a file with line numbers. Max 400 lines returned.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file to read"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Overwrites a file with new content. Cannot modify test files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "The complete new content of the file"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "edit_file",
        "description": "Replaces exactly one unique match of old_str with new_str in a file. Cannot modify test files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file to edit"
                },
                "old_str": {
                    "type": "string",
                    "description": "The exact string to be replaced. Must be unique in the file."
                },
                "new_str": {
                    "type": "string",
                    "description": "The new string to replace it with."
                }
            },
            "required": ["path", "old_str", "new_str"]
        }
    },
    {
        "name": "run_tests",
        "description": "Runs the test suite inside the sandbox and returns the results summary. Call this after edits to verify.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]

class RepoDoctorAgent:
    def __init__(self, repo_path: Path, event_callback: Callable[[AgentEvent], None] = None):
        self.repo_path = repo_path.resolve()
        self.event_callback = event_callback or (lambda x: None)
        self.provider = get_provider(self.emit)
        self.original_files: Dict[str, str] = {}
        self.run_tests_count = 0
        self.tool_calls_count = 0
        self.start_time = time.time()
        self.events: List[AgentEvent] = []
        self.messages: List[Any] = []

    def emit(self, type_: str, data: dict):
        event = AgentEvent(type=type_, data=data)
        self.events.append(event)
        self.event_callback(event)

    def tree(self, dir_path: Path, root_path: Path, max_depth: int, current_depth: int = 0) -> str:
        if current_depth > max_depth:
            return ""
        ignore = {".git", "__pycache__", "venv", "node_modules", ".pytest_cache"}
        output = []
        try:
            items = sorted(list(dir_path.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
            for item in items:
                if item.name in ignore:
                    continue
                indent = "  " * current_depth
                if item.is_dir():
                    output.append(f"{indent}- {item.name}/")
                    sub_tree = self.tree(item, root_path, max_depth, current_depth + 1)
                    if sub_tree:
                        output.append(sub_tree)
                else:
                    output.append(f"{indent}- {item.name}")
        except Exception:
            pass
        return "\n".join(output)

    def _tool_list_files(self, path: str = ".") -> str:
        raw_target = self.repo_path / path
        if raw_target.is_symlink():
            return "Error: path traversal not allowed."
        target = raw_target.resolve()
        if not target.is_relative_to(self.repo_path):
            return "Error: path traversal not allowed."
        if not target.exists():
            return f"Error: path {path} does not exist."
        
        result = self.tree(target, target, 3)
        return result or "Directory is empty."

    def _tool_read_file(self, path: str) -> str:
        raw_target = self.repo_path / path
        if raw_target.is_symlink():
            return "Error: path traversal not allowed."
        target = raw_target.resolve()
        if not target.is_relative_to(self.repo_path):
            return "Error: path traversal not allowed."
        if not target.is_file():
            return f"Error: {path} is not a file."
        try:
            with open(target, "r") as f:
                lines = f.readlines()
            
            truncated = ""
            if len(lines) > 400:
                lines = lines[:400]
                truncated = "\n... [TRUNCATED to 400 lines] ..."
                
            out = []
            for i, line in enumerate(lines, 1):
                out.append(f"{i}: {line.rstrip()}")
            return "\n".join(out) + truncated
        except Exception as e:
            return f"Error reading file: {e}"

    def _tool_write_file(self, path: str, content: str) -> str:
        raw_target = self.repo_path / path
        if raw_target.is_symlink():
            return "Error: path traversal not allowed."
        target = raw_target.resolve()
        if not target.is_relative_to(self.repo_path):
            return "Error: path traversal not allowed."
        
        rel_path_obj = target.relative_to(self.repo_path)
        parts = rel_path_obj.parts
        name = target.name
        rel_path = rel_path_obj.as_posix()
        if "tests" in parts or "test" in parts or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
            return "Error: You are not allowed to modify tests to make them pass. You must fix the source code instead."
            
        try:
            if rel_path not in self.original_files:
                if target.exists():
                    with open(target, "r") as f:
                        self.original_files[rel_path] = f.read()
                else:
                    self.original_files[rel_path] = ""
                    
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w") as f:
                f.write(content)
            return f"Successfully wrote to {path}."
        except Exception as e:
            return f"Error writing file: {e}"

    def _tool_edit_file(self, path: str, old_str: str, new_str: str) -> str:
        raw_target = self.repo_path / path
        if raw_target.is_symlink():
            return "Error: path traversal not allowed."
        target = raw_target.resolve()
        if not target.is_relative_to(self.repo_path):
            return "Error: path traversal not allowed."
        if not target.exists():
            return f"Error: path {path} does not exist."
            
        rel_path_obj = target.relative_to(self.repo_path)
        parts = rel_path_obj.parts
        name = target.name
        rel_path = rel_path_obj.as_posix()
        if "tests" in parts or "test" in parts or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
            return "Error: You are not allowed to modify tests to make them pass. You must fix the source code instead."
            
        try:
            with open(target, "r") as f:
                content = f.read()
                
            if rel_path not in self.original_files:
                self.original_files[rel_path] = content
                
            count = content.count(old_str)
            if count == 0:
                return "Error: old_str not found in file."
            elif count > 1:
                return f"Error: old_str matches {count} times. The match must be unique."
                
            new_content = content.replace(old_str, new_str, 1)
            with open(target, "w") as f:
                f.write(new_content)
                
            return f"Successfully edited {path}."
        except Exception as e:
            return f"Error editing file: {e}"

    def _tool_run_tests(self) -> str:
        self.run_tests_count += 1
        if self.run_tests_count > MAX_ATTEMPTS:
            return "Error: Maximum number of test runs reached. Do not call run_tests again, just summarize your changes and stop."
            
        self.emit("status", {"message": f"Running tests (Attempt {self.run_tests_count}/{MAX_ATTEMPTS})..."})
        result = run_tests(self.repo_path)
        self.last_test_result = result
        
        status = "PASSED" if result.passed else "FAILED"
        out = f"Tests {status} (Exit Code: {result.exit_code})\n"
        if result.failed_tests:
            out += f"Failed Tests: {', '.join(result.failed_tests)}\n"
        out += f"\n--- STDOUT ---\n{result.stdout}\n"
        if result.stderr:
            out += f"\n--- STDERR ---\n{result.stderr}\n"
        
        return out

    def execute_tool(self, tool_call) -> str:
        self.tool_calls_count += 1
        name = tool_call.name
        args = tool_call.input
        self.emit("tool_call", {"tool": name, "args": args})
        
        try:
            if name == "list_files":
                res = self._tool_list_files(args.get("path", "."))
            elif name == "read_file":
                res = self._tool_read_file(args.get("path"))
            elif name == "write_file":
                res = self._tool_write_file(args.get("path"), args.get("content"))
            elif name == "edit_file":
                res = self._tool_edit_file(args.get("path"), args.get("old_str"), args.get("new_str"))
            elif name == "run_tests":
                res = self._tool_run_tests()
            else:
                res = f"Error: Unknown tool {name}"
        except Exception as e:
            res = f"Error executing tool {name}: {e}"
            
        self.emit("tool_result", {"tool": name, "result": res})
        return res

    def get_diff(self) -> str:
        diffs = []
        for rel_path, orig_content in self.original_files.items():
            target = self.repo_path / rel_path
            if target.exists():
                with open(target, "r") as f:
                    new_content = f.read()
            else:
                new_content = ""
                
            orig_lines = orig_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            d = list(difflib.unified_diff(orig_lines, new_lines, fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", n=2))
            if d:
                diffs.append("".join(d))
        return "\n".join(diffs)

    def run(self, initial_test_output: str) -> AgentResult:
        self.emit("status", {"message": "Agent loop started"})
        
        self.messages.append({
            "role": "user", 
            "content": f"Here is the failing test output:\n<test_output>\n{initial_test_output}\n</test_output>\nPlease fix the issue and summarize."
        })
        
        success = False
        summary = ""
        
        while True:
            if time.time() - self.start_time > MAX_TIME_MINUTES * 60:
                self.emit("error", {"message": "Timeout reached."})
                summary += "\nAgent stopped due to timeout."
                break
            if self.tool_calls_count >= 25:
                self.emit("error", {"message": "Max tool calls reached."})
                summary += "\nAgent stopped due to max tool calls limit."
                break

            text_content, tool_calls, assistant_message = self.provider.generate(
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages
            )
            
            self.messages.append(assistant_message)
            
            if text_content:
                self.emit("agent_message", {"message": text_content})
                summary = text_content
            
            if not tool_calls:
                # No more tools used -> assume done
                success = (self.run_tests_count > 0)
                self.emit("done", {"message": "Agent finished naturally."})
                break
                
            tool_results = []
            for tc in tool_calls:
                res_str = self.execute_tool(tc)
                tool_results.append({
                    "id": tc.id,
                    "name": tc.name,
                    "content": res_str
                })
                
            self.messages.append(self.provider.format_tool_results(tool_results))
            
        final_diff = self.get_diff()
        
        new_contents = {}
        for rel_path in self.original_files.keys():
            target = self.repo_path / rel_path
            if target.exists():
                with open(target, "r") as f:
                    new_contents[rel_path] = f.read()
                    
        return AgentResult(
            success=success,
            summary=summary,
            diff=final_diff,
            files_changed=list(self.original_files.keys()),
            new_file_contents=new_contents,
            attempts=self.run_tests_count,
            events=self.events,
            test_before=None,
            test_after=getattr(self, 'last_test_result', None)
        )

def run_agent(repo_path: Path, event_callback: Callable[[AgentEvent], None] = None) -> AgentResult:
    if event_callback:
        event_callback(AgentEvent(type="status", data={"message": "Running initial tests..."}))
        
    initial_res = run_tests(repo_path)
    if initial_res.passed:
        if event_callback:
            event_callback(AgentEvent(type="status", data={"message": "Tests already pass, nothing to fix."}))
        return AgentResult(
            success=True,
            summary="Tests already pass. No fixes needed.",
            diff="",
            files_changed=[],
            attempts=0,
            events=[]
        )
        
    out = f"Initial Tests FAILED (Exit Code: {initial_res.exit_code})\n"
    if initial_res.failed_tests:
        out += f"Failed Tests: {', '.join(initial_res.failed_tests)}\n"
    out += f"\n--- STDOUT ---\n{initial_res.stdout}\n"
    if initial_res.stderr:
        out += f"\n--- STDERR ---\n{initial_res.stderr}\n"
        
    agent = RepoDoctorAgent(repo_path, event_callback)
    res = agent.run(out)
    res.test_before = initial_res
    if not res.test_after:
        res.test_after = initial_res
    return res
