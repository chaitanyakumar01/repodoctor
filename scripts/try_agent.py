#!/usr/bin/env python3
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.sandbox import clone_repo
from backend.agent import run_agent

def main():
    if len(sys.argv) != 2:
        print("Usage: python try_agent.py <github_https_url_or_local_path>")
        sys.exit(1)
        
    url = sys.argv[1]
    
    if Path(url).exists() and Path(url).is_dir():
        print(f"Using local directory {url}")
        repo_path = Path(tempfile.mkdtemp(prefix="repodoctor_"))
        shutil.copytree(url, repo_path, dirs_exist_ok=True)
    else:
        print(f"Cloning {url} ...")
        try:
            repo_path = clone_repo(url)
        except Exception as e:
            print(f"Failed to clone: {e}")
            sys.exit(1)
            
    print(f"Working directory: {repo_path}")
    
    def on_event(event):
        if event.type == "status":
            print(f"[*] {event.data['message']}")
        elif event.type == "tool_call":
            print(f"[TOOL ->] {event.data['tool']} {event.data['args']}")
        elif event.type == "tool_result":
            res = str(event.data['result'])
            if len(res) > 200:
                res = res[:200] + "... [truncated]"
            print(f"[<- RESULT] {res}")
        elif event.type == "agent_message":
            print(f"\n[AGENT]: {event.data['message']}\n")
        elif event.type == "error":
            print(f"[!] ERROR: {event.data['message']}")
        elif event.type == "done":
            pass
            
    try:
        result = run_agent(repo_path, event_callback=on_event)
        print("\n" + "="*40)
        print("AGENT RUN COMPLETE")
        print("="*40)
        print(f"Success:       {result.success}")
        print(f"Attempts:      {result.attempts}")
        print(f"Files Changed: {result.files_changed}")
        print(f"Summary:\n{result.summary}")
        print("\nDiff:")
        print(result.diff)
        
    finally:
        print(f"\nCleaning up {repo_path} ...")
        shutil.rmtree(repo_path, ignore_errors=True)

if __name__ == "__main__":
    main()
