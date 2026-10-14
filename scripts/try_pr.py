#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.github_pr import create_fix_pr
from backend.models import TestResult

def main():
    if len(sys.argv) != 2:
        print("Usage: python try_pr.py <github_https_url>")
        print("Ensure GITHUB_TOKEN is set in your environment.")
        sys.exit(1)
        
    repo_url = sys.argv[1]
    
    # Mock data to test the PR creation
    diff_files = {
        "repodoctor_test_file.txt": "This file was created by RepoDoctor to test the PR flow.\n"
    }
    
    summary = "Fixed a failing test by adding missing logic."
    
    test_before = TestResult(
        passed=False,
        exit_code=1,
        stdout="pytest output before",
        stderr="",
        failed_tests=["test_add"],
        duration_seconds=1.5
    )
    
    test_after = TestResult(
        passed=True,
        exit_code=0,
        stdout="pytest output after",
        stderr="",
        failed_tests=[],
        duration_seconds=1.0
    )
    
    try:
        print(f"Attempting to create PR for {repo_url} ...")
        pr_url = create_fix_pr(
            repo_url=repo_url,
            diff_files=diff_files,
            summary=summary,
            test_before=test_before,
            test_after=test_after
        )
        print(f"\nSUCCESS! PR created at: {pr_url}")
    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    main()
