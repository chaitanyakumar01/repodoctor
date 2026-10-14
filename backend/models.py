from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class TestResult(BaseModel):
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    failed_tests: List[str]
    duration_seconds: float

class AgentEvent(BaseModel):
    type: str
    data: Dict[str, Any]

class AgentResult(BaseModel):
    success: bool
    summary: str
    diff: str
    files_changed: List[str]
    new_file_contents: Dict[str, str] = {}
    attempts: int
    events: List[AgentEvent]
    test_before: Optional[TestResult] = None
    test_after: Optional[TestResult] = None
