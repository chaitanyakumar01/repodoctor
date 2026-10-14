import os
import time
from typing import List, Callable, Dict, Any, Tuple
from dataclasses import dataclass

from backend.config import MODEL_NAME

@dataclass
class ToolCall:
    id: str
    name: str
    input: dict

class LLMProvider:
    def __init__(self, emit_cb: Callable[[str, dict], None]):
        self.emit = emit_cb

    def generate(self, system: str, tools: List[dict], messages: List[Any]) -> Tuple[str, List[ToolCall], Any]:
        raise NotImplementedError

    def format_tool_results(self, results: List[Dict[str, str]]) -> Any:
        raise NotImplementedError

def with_retry(emit: Callable, func, *args, **kwargs):
    max_tries = 5
    for attempt in range(1, max_tries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "503" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                if attempt == max_tries:
                    raise
                wait_sec = 2 ** attempt
                emit("status", {"message": f"Rate limited, retrying in {wait_sec}s..."})
                time.sleep(wait_sec)
            else:
                raise

class AnthropicProvider(LLMProvider):
    def __init__(self, emit_cb: Callable[[str, dict], None]):
        super().__init__(emit_cb)
        from anthropic import Anthropic
        from backend.config import ANTHROPIC_API_KEY
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def generate(self, system: str, tools: List[dict], messages: List[Any]) -> Tuple[str, List[ToolCall], Any]:
        def _call():
            return self.client.messages.create(
                model=MODEL_NAME,
                max_tokens=2048,
                system=system,
                tools=tools,
                messages=messages
            )
        
        response = with_retry(self.emit, _call)
        
        text_content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_content += block.text + "\n"
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))
                
        assistant_message = {
            "role": "assistant",
            "content": response.content
        }
        return text_content.strip(), tool_calls, assistant_message

    def format_tool_results(self, results: List[Dict[str, str]]) -> Any:
        content = []
        for res in results:
            content.append({
                "type": "tool_result",
                "tool_use_id": res["id"],
                "content": res["content"]
            })
        return {"role": "user", "content": content}

class GeminiProvider(LLMProvider):
    def __init__(self, emit_cb: Callable[[str, dict], None]):
        super().__init__(emit_cb)
        from google import genai
        from backend.config import GEMINI_API_KEY
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def generate(self, system: str, tools: List[dict], messages: List[Any]) -> Tuple[str, List[ToolCall], Any]:
        from google.genai import types
        gemini_tools = []
        for t in tools:
            gemini_tools.append(
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=t.get("input_schema")
                )
            )
        tool_config = types.Tool(function_declarations=gemini_tools)
        
        gemini_messages = []
        for msg in messages:
            if isinstance(msg, types.Content):
                gemini_messages.append(msg)
            elif isinstance(msg, dict):
                role = "model" if msg.get("role") == "assistant" else "user"
                content = msg.get("content")
                gemini_messages.append(types.Content(role=role, parts=[types.Part.from_text(text=str(content))]))
                    
        def _call():
            return self.client.models.generate_content(
                model=MODEL_NAME,
                contents=gemini_messages,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    tools=[tool_config],
                    temperature=0.0
                )
            )
            
        response = with_retry(self.emit, _call)
        
        text_content = ""
        tool_calls = []
        assistant_parts = []
        
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                assistant_parts.append(part)
                if part.text:
                    text_content += part.text + "\n"
                elif part.function_call:
                    fc = part.function_call
                    # Extract args
                    args = dict(fc.args) if fc.args else {}
                    # For Gemini, id isn't explicitly provided, use name + index
                    call_id = f"{fc.name}_{len(tool_calls)}"
                    tool_calls.append(ToolCall(id=call_id, name=fc.name, input=args))

        assistant_message = types.Content(role="model", parts=assistant_parts)
        return text_content.strip(), tool_calls, assistant_message

    def format_tool_results(self, results: List[Dict[str, str]]) -> Any:
        from google.genai import types
        parts = []
        for res in results:
            parts.append(
                types.Part.from_function_response(
                    name=res["name"],
                    response={"result": res["content"]}
                )
            )
        return types.Content(role="user", parts=parts)

class MockProvider(LLMProvider):
    def __init__(self, emit_cb: Callable[[str, dict], None]):
        super().__init__(emit_cb)
        self.step = 0

    def generate(self, system: str, tools: List[dict], messages: List[Any]) -> Tuple[str, List[ToolCall], Any]:
        text_content = ""
        tool_calls = []
        
        if self.step == 0:
            tool_calls.append(ToolCall(id="call_0", name="list_files", input={}))
        elif self.step == 1:
            tool_calls.append(ToolCall(id="call_1", name="read_file", input={"path": "tests/test_shopping.py"}))
        elif self.step == 2:
            tool_calls.append(ToolCall(id="call_2", name="read_file", input={"path": "shopping.py"}))
        elif self.step == 3:
            tool_calls.append(ToolCall(id="call_3_1", name="edit_file", input={"path": "shopping.py", "old_str": "total -= discount_percent", "new_str": "total -= total * (discount_percent / 100.0)"}))
            tool_calls.append(ToolCall(id="call_3_2", name="edit_file", input={"path": "shopping.py", "old_str": "max(self.items, key=lambda item: item.price)", "new_str": "max(self.items, key=lambda item: item.price, default=None)"}))
            tool_calls.append(ToolCall(id="call_3_3", name="edit_file", input={"path": "shopping.py", "old_str": "start = (page) * page_size", "new_str": "start = (page - 1) * page_size"}))
        elif self.step == 4:
            tool_calls.append(ToolCall(id="call_4", name="run_tests", input={}))
        elif self.step == 5:
            text_content = "[MOCK RUN] Fixed the 3 bugs in shopping.py."
            
        self.step += 1
        return text_content, tool_calls, {"role": "assistant", "content": "mock"}

    def format_tool_results(self, results: List[Dict[str, str]]) -> Any:
        return {"role": "user", "content": "mock"}

def get_provider(emit_cb: Callable[[str, dict], None]) -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider == "anthropic":
        return AnthropicProvider(emit_cb)
    elif provider == "mock":
        return MockProvider(emit_cb)
    return GeminiProvider(emit_cb)
