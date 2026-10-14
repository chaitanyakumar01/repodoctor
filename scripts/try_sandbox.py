#!/usr/bin/env python3
import sys
import shutil
import tempfile
from pathlib import Path

# Add the parent directory to sys.path so we can import backend module
sys.path.append(str(Path(__file__).parent.parent))

from backend.sandbox import clone_repo, run_tests

def main():
    if len(sys.argv) != 2:
        print("Usage: python try_sandbox.py <github_https_url>")
        sys.exit(1)
        
    url = sys.argv[1]
    repo_path = None
    
    try:
        if Path(url).exists() and Path(url).is_dir():
            print(f"Using local directory {url}")
            repo_path = Path(tempfile.mkdtemp(prefix="repodoctor_"))
            shutil.copytree(url, repo_path, dirs_exist_ok=True)
        else:
            print(f"Cloning {url} ...")
            repo_path = clone_repo(url)
            print(f"Cloned into {repo_path}")
        
        print("Running tests in Docker sandbox...")
        result = run_tests(repo_path)
        
        print("\n=== TEST RESULT ===")
        print(f"Passed: {result.passed}")
        print(f"Exit Code: {result.exit_code}")
        print(f"Duration: {result.duration_seconds:.2f}s")
        print(f"Failed Tests: {result.failed_tests}")
        
        print("\n--- STDOUT ---")
        print(result.stdout)
        print("\n--- STDERR ---")
        print(result.stderr)
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        if repo_path and repo_path.exists():
            print(f"\nCleaning up {repo_path} ...")
            shutil.rmtree(repo_path, ignore_errors=True)

if __name__ == "__main__":
    main()
