import time
import shutil
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from typing import List

from backend.models import TestResult
from backend.config import SANDBOX_MEM_LIMIT, SANDBOX_CPU_LIMIT, SANDBOX_TIMEOUT_SEC

import os

def validate_repo_url(url: str):
    allow_local = os.environ.get("REPODOCTOR_ALLOW_LOCAL") == "1"
    if allow_local and url.startswith(("/", "file://")):
        return
        
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise ValueError("Invalid URL: Only https://github.com/<owner>/<repo> URLs are allowed.")
    
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 2:
        raise ValueError("Invalid URL: Only https://github.com/<owner>/<repo> URLs are allowed.")

def clone_repo(url: str) -> Path:
    """
    Shallow clones a GitHub HTTPS URL into a unique temporary directory.
    Validates that the URL is a github.com HTTPS URL.
    """
    validate_repo_url(url)
    
    if url.startswith(("/", "file://")):
        path = url.replace("file://", "")
        temp_dir = Path(tempfile.mkdtemp(prefix="repodoctor_"))
        shutil.copytree(path, temp_dir, dirs_exist_ok=True)
        return temp_dir
    
    temp_dir = Path(tempfile.mkdtemp(prefix="repodoctor_"))
    
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", url, str(temp_dir)],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Git clone failed: {e.stderr}")
    
    return temp_dir

def truncate_log(log: str, max_chars: int = 8000) -> str:
    """Truncates string to the last max_chars characters."""
    if len(log) > max_chars:
        return "... [TRUNCATED] ...\n" + log[-max_chars:]
    return log

def parse_failed_tests(stdout: str) -> List[str]:
    """Parses pytest output to extract failed test IDs."""
    failed_tests = []
    for line in stdout.splitlines():
        if line.startswith("FAILED ") or line.startswith("ERROR "):
            parts = line.split(" ", 1)
            if len(parts) > 1:
                test_id = parts[1].split(" - ")[0].strip()
                failed_tests.append(test_id)
    return failed_tests

def test_parse_failed_tests():
    # Test with FAILED lines
    out_failed = "FAILED tests/test_shopping.py::test_cart - AssertionError\nFAILED tests/test_shopping.py::test_checkout"
    assert parse_failed_tests(out_failed) == ["tests/test_shopping.py::test_cart", "tests/test_shopping.py::test_checkout"]
    
    # Test with ERROR line (collection error)
    out_error = "ERROR tests/test_bad.py - SyntaxError: invalid syntax"
    assert parse_failed_tests(out_error) == ["tests/test_bad.py"]
    
    # Test with all passed
    out_passed = "PASSED tests/test_good.py::test_ok"
    assert parse_failed_tests(out_passed) == []

def run_tests(repo_path: Path) -> TestResult:
    """
    Runs tests inside a Docker container (python:3.11-slim).
    Installs dependencies, then runs pytest.
    """
    start_time = time.time()
    
    script = """
set -e
if [ -f requirements.txt ]; then
    pip install --no-cache-dir -r requirements.txt
elif [ -f pyproject.toml ] || [ -f setup.py ]; then
    pip install --no-cache-dir -e .
fi
pip install --no-cache-dir pytest
set +e
python -m pytest --maxfail=10 -q --tb=short -rfE -p no:cacheprovider
exit $?
"""
    
    command = [
        "docker", "run", "--rm",
        "-v", f"{repo_path.absolute()}:/workspace",
        "-w", "/workspace",
        "--memory", SANDBOX_MEM_LIMIT,
        "--cpus", SANDBOX_CPU_LIMIT,
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "python:3.11-slim",
        "bash", "-c", script
    ]
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=SANDBOX_TIMEOUT_SEC
        )
        exit_code = result.returncode
        stdout = truncate_log(result.stdout)
        stderr = truncate_log(result.stderr)
        
    except subprocess.TimeoutExpired as e:
        exit_code = 124 # Timeout exit code
        stdout = truncate_log(e.stdout.decode('utf-8', errors='replace') if e.stdout else "")
        stderr = f"Timeout Error: Execution exceeded {SANDBOX_TIMEOUT_SEC} seconds."
    
    duration = time.time() - start_time
    passed = (exit_code == 0)
    failed_tests = parse_failed_tests(stdout) if not passed else []
    
    return TestResult(
        passed=passed,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        failed_tests=failed_tests,
        duration_seconds=duration
    )
