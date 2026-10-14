# RepoDoctor Specification

## Overview
RepoDoctor is an AI-powered agent designed to automatically fix failing tests in a given GitHub repository. It takes a repository URL, runs its test suite (specifically `pytest` for Python projects in the MVP), and if there are test failures, it utilizes the Anthropic Claude API to automatically identify, fix the code, and submit a Pull Request.

## Scope (MVP)
- **Target Language:** Python only.
- **Testing Framework:** `pytest` only.
- **Goal:** Fixing FAILING TESTS only.

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, Uvicorn
- **LLM Integration:** Anthropic Claude API (via the official `anthropic` Python SDK, utilizing Tool Use).
  - Model configured via `MODEL_NAME` env var.
  - Authentication via `ANTHROPIC_API_KEY` env var.
- **GitHub Integration:** PyGithub (Authentication via `GITHUB_TOKEN` env var).
- **Execution Sandbox:** Docker (All untrusted repository code execution and testing occurs exclusively inside Docker containers).
- **Frontend:** Single-page application (HTML/Vanilla JS) with live log streaming via Server-Sent Events (SSE).

## Hard Rules
1. **Branching:** Never push to the default branch. Always create a new branch named `repodoctor/fix-<short-id>`.
2. **Security & Sandboxing:** Never run cloned repository code on the host machine. Execution must happen solely within Docker, complete with timeouts and resource limits.
3. **Execution Limits:** Maximum 5 fix attempts per run. Maximum 10 minutes total execution time per run.
4. **PR Condition:** If tests are not passing at the end of the attempts, do NOT open a Pull Request. Instead, return a detailed report of the attempts.
5. **Secret Management:** Never log, print, or expose secrets (tokens, API keys) anywhere.
6. **Code Quality:** Keep code simple, fully typed, include docstrings, and avoid over-engineering.

## Folder Structure
```text
repodoctor/
├── backend/
│   ├── main.py            # FastAPI app, routes (including SSE endpoint)
│   ├── sandbox.py         # Clone repo, Docker run management, test execution
│   ├── agent.py           # LLM agent loop and Claude tool implementations
│   ├── github_pr.py       # Branching, committing, pushing, PR creation
│   ├── models.py          # Pydantic schemas for API and internal data
│   └── config.py          # Environment variables and limits configuration
├── frontend/
│   ├── index.html         # SPA markup
│   ├── app.js             # Vanilla JS for SSE stream rendering
│   └── style.css          # Styling (vibrant, modern)
├── demo_repo/             # Sample repository with a planted bug for testing
├── SPEC.md                # Project Specification and Plan
├── README.md              # Project documentation
└── .env.example           # Example environment variables
```

## API Endpoints

### `POST /api/jobs`
- **Description:** Submits a new repository to be processed by RepoDoctor.
- **Request Body:** `{"repo_url": "https://github.com/user/repo"}`
- **Response:** `{"job_id": "uuid-string", "status": "queued"}`

### `GET /api/jobs/{job_id}/stream`
- **Description:** Streams live logs and progress updates for a specific job using Server-Sent Events (SSE).
- **Response:** SSE text/event-stream format.

### `GET /api/jobs/{job_id}`
- **Description:** Gets the final report of the job, including whether a PR was opened, link to PR, or failure reasons.
- **Response:** `{"job_id": "uuid", "status": "completed|failed", "pr_url": "...", "report": "..."}`

## Data Flow
1. **Trigger:** User enters a GitHub repository URL on the Frontend.
2. **API Call:** Frontend sends a `POST` request to `/api/jobs` and receives a `job_id`.
3. **Stream Connection:** Frontend opens an SSE connection to `/api/jobs/{job_id}/stream`.
4. **Initialization:**
   - Backend pulls the repository to a temporary workspace.
   - Sets up the Docker sandbox environment.
5. **Testing (Baseline):**
   - Sandbox runs `pytest`.
   - If tests pass, terminate the job (nothing to fix).
   - If tests fail, collect the test logs and proceed to the Agent Loop.
6. **Agent Loop (Max 5 attempts):**
   - Provide Claude with test failure logs and tools to view/edit files.
   - Agent views files, proposes fixes, and uses tools to apply changes.
   - Sandbox re-runs `pytest`.
   - If tests pass -> break loop and proceed to PR creation.
   - If tests fail -> feedback to agent, increment attempt counter.
7. **Resolution:**
   - **Success:** Agent fixed the code. `github_pr.py` commits changes to `repodoctor/fix-<id>`, pushes, and opens a PR. Returns PR URL.
   - **Failure:** Reached 5 attempts or 10-minute timeout. Generates a report of what was tried. No PR is opened.
8. **Cleanup:** Destroy the temporary Docker container and workspace.

## Phase-by-Phase Checklist

### Phase 1: Setup & Scaffolding
- [ ] Initialize Python virtual environment.
- [ ] Create folder structure.
- [ ] Define `models.py` (Pydantic models) and `config.py` (Env vars, limits).
- [ ] Set up empty files (`main.py`, `sandbox.py`, etc.).
- [ ] Define `.env.example`.

### Phase 2: Sandbox Environment (`sandbox.py`)
- [ ] Implement secure repository cloning.
- [ ] Set up Docker Python container execution (bind mounts or volume mounts).
- [ ] Implement function to run `pytest` inside the container with strict timeouts.
- [ ] Capture and parse standard output/error from test runs.

### Phase 3: GitHub Integration (`github_pr.py`)
- [ ] Set up PyGithub client.
- [ ] Implement function to branch from default.
- [ ] Implement function to commit modified files.
- [ ] Implement function to push branch.
- [ ] Implement function to open a Pull Request with a descriptive title and body.

### Phase 4: Agent Core (`agent.py`)
- [ ] Integrate Anthropic SDK (`anthropic`).
- [ ] Define Tool usage for Claude (e.g., `read_file`, `write_file`, `replace_code`).
- [ ] Implement the agent loop (max 5 iterations, max 10 mins).
- [ ] Handle communication of test logs to Claude and applying Claude's fixes to the workspace.

### Phase 5: API & Orchestration (`main.py`)
- [ ] Set up FastAPI and basic endpoints.
- [ ] Integrate background tasks to handle job execution asynchronously without blocking the API.
- [ ] Implement SSE endpoint to broadcast real-time logs from `sandbox`, `agent`, and `github_pr` modules.

### Phase 6: Frontend Development (`frontend/`)
- [ ] Build basic HTML layout.
- [ ] Implement Vanilla JS to interact with `POST /api/jobs`.
- [ ] Implement Vanilla JS EventSource to consume the SSE log stream.
- [ ] Ensure modern, vibrant styling in `style.css`.

### Phase 7: Testing & Refinement
- [ ] Create `demo_repo/` with intentionally failing Python test.
- [ ] Run end-to-end tests against `demo_repo/`.
- [ ] Verify security rules (Docker limits, secret masking, branch creation limits).
- [ ] Finalize documentation in `README.md`.
