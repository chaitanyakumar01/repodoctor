import os
import requests
import sys
import json
import time
import uuid
import sseclient

def run_test_flow(url, expect_success, create_pr=False):
    print(f"Testing flow for: {url}")
    res = requests.post("http://localhost:8000/api/runs", json={"repo_url": url})
    if res.status_code != 200:
        print(f"FAILED to start run: {res.text}")
        return False
    run_id = res.json()["run_id"]
    print(f"Run started: {run_id}")
    
    response = requests.get(f"http://localhost:8000/api/runs/{run_id}/events", stream=True)
    client = sseclient.SSEClient(response)
    
    for event in client.events():
        data = json.loads(event.data)
        if data['type'] == 'status':
            print(f"[*] {data['data']['message']}")
        elif data['type'] in ['done', 'error']:
            print(f"[!] {data['type']}: {data['data']['message']}")
            break
            
    res = requests.get(f"http://localhost:8000/api/runs/{run_id}")
    state = res.json()
    print(f"Final state success: {state['success']}")
    print(f"Diff:\n{state['diff']}")
    
    if expect_success and not state['success']:
        print(f"FAILED: Expected success but got false")
        return False
    if not expect_success and state['success']:
        print(f"FAILED: Expected failure but got success")
        return False
        
    if create_pr and state['success']:
        print("Creating PR...")
        pr_res = requests.post(f"http://localhost:8000/api/runs/{run_id}/create-pr")
        if pr_res.status_code == 200:
            print(f"PR Created: {pr_res.json()['pr_url']}")
            return pr_res.json()['pr_url']
        else:
            print(f"Failed to create PR: {pr_res.text}")
            return False
            
    return True

def main():
    demo_url = os.getenv("DEMO_REPO_URL", "https://github.com/chaitanyakumar01/repodoctor-demo")
    should_create_pr = os.getenv("CREATE_PR", "0") == "1"
    print(f"Test 1: Normal flow (should fix code): {demo_url}")
    run_test_flow(demo_url, expect_success=True, create_pr=should_create_pr)
    
    print("\nTest 2: Invalid URL (should fail cloning)")
    run_test_flow("https://github.com/chaitanyakumar01/doesnotexist123", expect_success=False)

if __name__ == "__main__":
    main()

