import pytest
from pathlib import Path
import tempfile
import os
import shutil

os.environ["GEMINI_API_KEY"] = "dummy"

from backend.agent import RepoDoctorAgent
from backend.sandbox import validate_repo_url
from backend.main import create_pr, runs, RunState
from fastapi import HTTPException
import asyncio

@pytest.fixture
def agent():
    with tempfile.TemporaryDirectory() as d:
        repo_path = Path(d)
        (repo_path / "src" / "contests").mkdir(parents=True)
        yield RepoDoctorAgent(repo_path)

@pytest.mark.parametrize("path", [
    "shopping.py",
    "pkg/module.py",
    "src/contests/x.py",
    "latest_utils.py",
    "contest_data.py"
])
def test_file_guard_allowed(agent, path):
    assert "Successfully" in agent._tool_write_file(path, "")

@pytest.mark.parametrize("path", [
    "tests/test_a.py",
    "conftest.py",
    "test_x.py",
    "foo_test.py",
    "test/test_b.py"
])
def test_file_guard_blocked(agent, path):
    assert "Error" in agent._tool_write_file(path, "")

@pytest.mark.parametrize("path", [
    "../x",
    "/etc/passwd",
])
def test_path_traversal_read_rejected(agent, path):
    assert "Error" in agent._tool_read_file(path)

@pytest.mark.parametrize("path,is_symlink", [
    ("../x", False),
    ("/etc/passwd", False),
    ("evil_sibling", False),
    ("symlink_file", True),
    ("symlink_dir/secret", True)
])
def test_path_traversal_write_rejected(agent, path, is_symlink):
    with tempfile.TemporaryDirectory() as outside_d:
        outside_path = Path(outside_d)
        
        if path == "evil_sibling":
            sibling_dir = agent.repo_path.parent / (agent.repo_path.name + "_evil")
            sibling_dir.mkdir(exist_ok=True)
            rel_path = f"../{sibling_dir.name}/x"
            assert "Error" in agent._tool_write_file(rel_path, "")
            shutil.rmtree(sibling_dir, ignore_errors=True)
            return

        if is_symlink:
            outside_file = outside_path / "secret.txt"
            outside_file.write_text("secret")
            if "dir" in path:
                sym_dir = agent.repo_path / "symlink_dir"
                sym_dir.symlink_to(outside_path, target_is_directory=True)
                assert "Error" in agent._tool_write_file(path, "hacked")
            else:
                sym_file = agent.repo_path / "symlink_file"
                sym_file.symlink_to(outside_file)
                assert "Error" in agent._tool_write_file(path, "hacked")
            return
            
        assert "Error" in agent._tool_write_file(path, "")

@pytest.mark.parametrize("url", [
    "file:///etc",
    "/tmp/x",
    "http://github.com/a/b",
    "https://github.com.evil.com/a/b",
    "https://evil.com/github.com/a/b",
    "https://github.com/a"
])
def test_url_validation_rejected(url):
    # Ensure REPODOCTOR_ALLOW_LOCAL is unset for strict test
    if "REPODOCTOR_ALLOW_LOCAL" in os.environ:
        del os.environ["REPODOCTOR_ALLOW_LOCAL"]
    
    with pytest.raises(ValueError, match="Invalid URL"):
        validate_repo_url(url)

def test_url_validation_allowed():
    validate_repo_url("https://github.com/owner/repo")
    validate_repo_url("https://github.com/owner/repo/pull/1")

def test_edit_file_success(agent):
    file_path = "shopping.py"
    agent._tool_write_file(file_path, "def x():\n    pass\n")
    res = agent._tool_edit_file(file_path, "def x():", "def y():")
    assert "Successfully" in res
    assert agent._tool_read_file(file_path) == "1: def y():\n2:     pass"

def test_edit_file_zero_matches(agent):
    file_path = "shopping.py"
    agent._tool_write_file(file_path, "def x():\n    pass\n")
    res = agent._tool_edit_file(file_path, "def z():", "def y():")
    assert "Error: old_str not found in file." in res

def test_edit_file_multiple_matches(agent):
    file_path = "shopping.py"
    agent._tool_write_file(file_path, "pass\npass\n")
    res = agent._tool_edit_file(file_path, "pass", "fail")
    assert "Error: old_str matches" in res

@pytest.mark.parametrize("path", [
    "tests/test_a.py",
    "conftest.py"
])
def test_edit_file_guard_blocked(agent, path):
    res = agent._tool_edit_file(path, "a", "b")
    assert "Error" in res

@pytest.mark.parametrize("path", [
    "../x",
    "/etc/passwd",
])
def test_path_traversal_edit_rejected(agent, path):
    assert "Error" in agent._tool_edit_file(path, "a", "b")

@pytest.mark.asyncio
async def test_create_pr_fails_when_agent_failed():
    run_id = "test_run_fail"
    runs[run_id] = RunState(
        run_id=run_id,
        repo_url="https://github.com/a/b",
        status="done",
        success=False, # AGENT FAILED TO FIX
        summary="Failed to fix",
    )
    
    with pytest.raises(HTTPException) as exc:
        await create_pr(run_id)
        
    assert exc.value.status_code == 400
    assert "cannot create PR" in str(exc.value.detail)

def test_mock_agent_flow():
    os.environ["LLM_PROVIDER"] = "mock"
    import tempfile
    import shutil
    from backend.agent import run_agent
    
    with tempfile.TemporaryDirectory() as d:
        repo_path = Path(d)
        shutil.copytree("demo_repo", repo_path, dirs_exist_ok=True)
        
        res = run_agent(repo_path)
        
        assert res.success is True
        assert res.files_changed == ["shopping.py"]
        
        # Diff should have 3 hunks (3 '@@ ' occurrences)
        hunk_count = res.diff.count("@@ -")
        assert hunk_count == 3
        assert "[MOCK RUN]" in res.summary
