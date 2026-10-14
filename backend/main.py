import uuid
import shutil
import asyncio
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.sandbox import clone_repo
from backend.agent import run_agent
from backend.models import AgentEvent, TestResult
from backend.github_pr import create_fix_pr

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunState(BaseModel):
    run_id: str
    repo_url: str
    status: str
    events: list[AgentEvent] = []
    success: bool = False
    summary: str = ""
    diff: str = ""
    new_file_contents: Dict[str, str] = {}
    test_before: Optional[Dict[str, Any]] = None
    test_after: Optional[Dict[str, Any]] = None
    pr_url: Optional[str] = None
    error_message: Optional[str] = None

runs: Dict[str, RunState] = {}
run_queues: Dict[str, asyncio.Queue] = {}

class RunRequest(BaseModel):
    repo_url: str

def background_run_wrapper(run_id: str, repo_url: str, loop: asyncio.AbstractEventLoop):
    state = runs[run_id]
    q = run_queues[run_id]
    
    def emit(event: AgentEvent):
        state.events.append(event)
        asyncio.run_coroutine_threadsafe(q.put(event), loop)

    try:
        emit(AgentEvent(type="status", data={"message": "Cloning repository..."}))
        state.status = "cloning"
        repo_path = clone_repo(repo_url)
        
        try:
            state.status = "testing"
            result = run_agent(repo_path, event_callback=emit)
            
            state.status = "done"
            state.success = result.success
            state.summary = result.summary
            state.diff = result.diff
            state.new_file_contents = result.new_file_contents
            if result.test_before:
                state.test_before = result.test_before.model_dump()
            if result.test_after:
                state.test_after = result.test_after.model_dump()
                
            emit(AgentEvent(type="done", data={"message": "Run finished naturally."}))
        finally:
            shutil.rmtree(repo_path, ignore_errors=True)
            
    except Exception as e:
        state.status = "error"
        state.error_message = str(e)
        emit(AgentEvent(type="error", data={"message": str(e)}))

@app.post("/api/runs")
async def start_run(req: RunRequest, bg_tasks: BackgroundTasks):
    run_id = uuid.uuid4().hex
    runs[run_id] = RunState(run_id=run_id, repo_url=req.repo_url, status="queued")
    run_queues[run_id] = asyncio.Queue()
    
    loop = asyncio.get_running_loop()
    bg_tasks.add_task(background_run_wrapper, run_id, req.repo_url, loop)
    return {"run_id": run_id}

@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str):
    if run_id not in runs:
        raise HTTPException(404, "Run not found")
        
    q = run_queues[run_id]
    state = runs[run_id]
    
    async def event_generator():
        yielded_count = len(state.events)
        for i in range(yielded_count):
            yield f"data: {state.events[i].model_dump_json()}\n\n"
            
        if state.status in ["done", "error"]:
            return
            
        for _ in range(yielded_count):
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break
            
        while True:
            ev = await q.get()
            yield f"data: {ev.model_dump_json()}\n\n"
            if ev.type in ["done", "error"]:
                break
                
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    if run_id not in runs:
        raise HTTPException(404, "Run not found")
    return runs[run_id]

@app.post("/api/runs/{run_id}/create-pr")
async def create_pr(run_id: str):
    state = runs.get(run_id)
    if not state:
        raise HTTPException(404, "Run not found")
    if state.status != "done":
        raise HTTPException(400, "Run is not finished")
    if not state.success:
        raise HTTPException(400, "Tests did not pass, cannot create PR")
    if not state.test_before or not state.test_after:
        raise HTTPException(400, "Missing test results, cannot create PR")
    if state.pr_url:
        return {"pr_url": state.pr_url}
        
    if not state.test_before or not state.test_after:
        raise HTTPException(500, "Test results are missing")

    try:
        pr_url = create_fix_pr(
            repo_url=state.repo_url,
            diff_files=state.new_file_contents,
            summary=state.summary,
            test_before=TestResult(**state.test_before),
            test_after=TestResult(**state.test_after)
        )
        state.pr_url = pr_url
        return {"pr_url": pr_url}
    except Exception as e:
        raise HTTPException(500, str(e))

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
