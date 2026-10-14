# RepoDoctor 🩺

RepoDoctor is an autonomous AI agent that diagnoses and repairs failing tests in Python repositories. It safely clones your repository, executes tests in an isolated Docker container, inspects failures, writes targeted code fixes, verifies that the tests pass, and prepares a GitHub Pull Request for your final review and approval.

---

## Prerequisites

Before running RepoDoctor, ensure your system has the following:

1. **Operating System & Shell**:
   - **macOS & Linux**: Supported natively. `run.sh` runs out-of-the-box in bash or zsh.
   - **Windows**: Windows users must run RepoDoctor inside **WSL2** (Windows Subsystem for Linux 2) with **Docker Desktop for Windows** (ensure *"Use the WSL 2 based engine"* and your WSL distro integration are enabled in Docker Desktop Settings).
2. **Docker Desktop / Docker Engine** (Must be installed and actively running)
   - Download: [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
   - Ensure the Docker daemon is running (whale icon in your menu bar / taskbar is steady).
3. **Python 3.10 or newer**
   - Verify in your terminal with: `python3 --version`
4. **An LLM API Key (Free Gemini Key Recommended)**
   - **Google Gemini (Free)**: Obtain a free API key at [Google AI Studio](https://aistudio.google.com).
   - *Or* **Anthropic Claude**: Obtain a key at [Anthropic Console](https://console.anthropic.com).
5. **GitHub Personal Access Token (Fine-Grained)**
   - Generate a fine-grained token at: [https://github.com/settings/tokens?type=beta](https://github.com/settings/tokens?type=beta)
   - **Repository access**: Select *"Only select repositories"* and choose your target repository.
   - **Permissions required**:
     - `Contents`: **Read and Write** (needed to create fix branches and commit code)
     - `Pull requests`: **Read and Write** (needed to open the Pull Request)

---

## Quick Start Setup (Using `run.sh`)

RepoDoctor includes an automated launcher (`run.sh`) that verifies prerequisites, provisions a virtual environment, installs dependencies, validates keys, and boots the application.

### Step 1: Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in your keys:
```ini
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_actual_gemini_api_key_here
GITHUB_TOKEN=your_actual_github_token_here
```
*(Leave `MODEL_NAME` blank to let RepoDoctor automatically select the latest stable Gemini Flash model).*

### Step 2: Start RepoDoctor

Run the runner script:
```bash
./run.sh
```

What `run.sh` does automatically:
1. Validates that Docker is installed and the daemon is responding.
2. Creates an isolated Python virtual environment (`.venv`) if one does not exist.
3. Upgrades pip and installs all required dependencies from `requirements.txt`.
4. Checks that `.env` exists and validates that all required keys for your chosen provider are populated (without ever displaying secret values).
5. Launches the Uvicorn web server bound to `127.0.0.1:8000`.

### Step 3: Open the Web UI

Open your web browser and navigate to:
```
http://127.0.0.1:8000
```

---

## How to Use the UI

1. **Enter Repository URL**: In the input field, paste the full HTTPS URL of your target GitHub repository (for example, `https://github.com/your-username/repodoctor-demo`).
2. **Start Diagnosis**: Click **Fix My Repo**.
3. **Real-Time Live Feed**:
   - The UI displays an interactive progress bar: `Cloning` &rarr; `Running Tests` &rarr; `Fixing Code` &rarr; `Done`.
   - Live logs stream via Server-Sent Events (SSE), detailing test outputs, agent tool executions, and file edits.
4. **Review Diffs & Badges**:
   - Once complete, you will see test status badges (**Before: Failing** and **After: Passing**).
   - An explanation summary describes what bugs were found and how they were resolved.
   - A unified syntax-highlighted diff displays the exact file changes proposed by the AI.
5. **Approve & Open PR**:
   - If satisfied with the proposed changes, click **Approve & Create PR**.
   - RepoDoctor pushes a dedicated branch (`repodoctor/fix-<id>`) and creates a Pull Request on GitHub. A clickable link to the PR appears directly in the UI.

---

## What is Mock Mode?

RepoDoctor includes an offline simulation mode designed for testing and demonstration:

```ini
LLM_PROVIDER=mock
```

- **How it works**: In mock mode, RepoDoctor replays a pre-defined, deterministic diagnostic sequence specifically matching the bundled `demo_repo` (resolving the 3 planted bugs in `shopping.py`) without making any external calls to Google Gemini or Anthropic.
- **Important Disclosure**: **Mock mode must NEVER be presented as a live AI run.** It is solely intended for offline integration testing, UI demonstrations, and validating your Docker execution pipeline without consuming API quota or requiring network access to LLM services.

---

## Safety & Security Architecture

RepoDoctor is designed from the ground up with defensive engineering principles to ensure untrusted code cannot harm your machine:

1. **Strict Docker Sandboxing**:
   - Untrusted repository code and test suites are **never** executed directly on your host operating system.
   - All tests run inside an isolated Docker container (`python:3.11-slim`) with strict cgroups resource limits:
     - Memory capped at `512MB`.
     - CPU capped at `1.0` cores.
     - Hard execution timeout capped at `120 seconds`.
2. **Branch Protection (Never Touches Default Branch)**:
   - RepoDoctor **never** commits or pushes directly to `main`, `master`, or your default branch.
   - Fixes are committed to an isolated branch with a unique identifier: `repodoctor/fix-<short-id>`.
3. **Human-in-the-Loop Approval**:
   - No code is committed to GitHub and no Pull Request is opened automatically.
   - The user must explicitly inspect the unified diff in the UI and click **Approve & Create PR**.
4. **Fails Closed**:
   - If tests cannot be made to pass within 5 iteration attempts or within a 10-minute timeout, the agent halts and reports failure. No Pull Request can be created for broken code.
5. **Path Traversal & Test-File Protection**:
   - The agent is strictly prevented from editing test files (`test_*.py`, `conftest.py`, `*_test.py`). It must fix the underlying implementation code, not alter the tests.
   - File read and write tools validate paths to ensure the agent cannot read or overwrite files outside the repository root directory.

---

## Troubleshooting

### 1. Docker is not running / `Docker daemon is not running`
- **Symptom**: `run.sh` halts with `Error: Docker is installed, but the Docker daemon is not running.`
- **Resolution**: Open the Docker Desktop application on your computer. Wait until the status in the bottom tray or top menu bar shows "Engine running" (green). Then re-run `./run.sh`.

### 2. `docker: command not found` on macOS
- **Symptom**: Terminal reports `docker: command not found`.
- **Resolution**:
  - Ensure Docker Desktop is installed in `/Applications/Docker.app`.
  - Open Docker Desktop &rarr; **Settings** (gear icon) &rarr; **Advanced**.
  - Under **Choose how to manage Docker CLI tools**, select **System** (creates `/usr/local/bin/docker`) or **User** (creates `~/.docker/bin/docker`), and ensure that directory is in your terminal `$PATH`.

### 3. Rate Limit Errors (HTTP 429) on Free Tier
- **Symptom**: UI logs show `Rate limited, retrying in Xs...` or terminal indicates API quota exceeded.
- **Resolution**: The free tier of Google Gemini provides generous capabilities but enforces per-minute and per-day request quotas. RepoDoctor includes automated exponential backoff retry. If your daily quota is fully exhausted:
  - Wait for your daily quota to refresh, or
  - Switch to an Anthropic API key by setting `LLM_PROVIDER=anthropic` in `.env`, or
  - Switch to `LLM_PROVIDER=mock` for testing.

### 4. GitHub Token Errors (`Bad credentials` or `Push access denied`)
- **Symptom**: Creating a PR fails with authentication or permission errors.
- **Resolution**:
  - Verify your token has not expired.
  - Check that the token has access to the specific repository you are targeting.
  - Ensure both `Contents: Read & write` and `Pull requests: Read & write` permissions are checked.
  - If using a personal repository, ensure your GitHub user has push permissions to it.

---

## Known Limitations

We believe in complete transparency about RepoDoctor's current architectural boundaries:

1. **Python + Pytest Repositories Only**: RepoDoctor currently supports Python projects that use `pytest`. Other languages (JavaScript, Go, Rust, Java) and other Python test runners (`unittest`, `nose`) are not supported in this version.
2. **Fixes Failing Tests Only**: RepoDoctor is engineered specifically to restore failing test suites to green. It does not implement new application features, refactor passing code, or generate missing unit test suites.
3. **Tested Primarily on Bundled Demo Suite**: While designed to handle standard Python dependency setups (`requirements.txt`, `pyproject.toml`, `setup.py`), complex enterprise monorepos requiring external system libraries, proprietary databases, or specialized Docker containers may need custom container configurations.
4. **Free-Tier LLM Quotas**: When utilizing the free tier of Google Gemini, running multiple successive diagnosis loops can quickly exhaust daily quota limits.
5. **Sandbox Network Connectivity**: The Docker sandbox currently retains outbound network access so that `pip install` can fetch dependencies defined in the repository.
6. **In-Memory Run State**: Job runs and real-time event histories are stored in process memory. If the Uvicorn server is restarted, active run histories are reset.
7. **No API Authentication (Localhost Only)**: The FastAPI backend does not include user authentication or role-based access control. RepoDoctor is strictly designed to run on `localhost` (`127.0.0.1`). Do not expose the port to the public internet without an authenticating reverse proxy or VPN.
