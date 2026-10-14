const startBtn = document.getElementById('start-btn');
const urlInput = document.getElementById('repo-url');
const errorMsg = document.getElementById('error-message');
const progressSection = document.getElementById('progress-section');
const logPanel = document.getElementById('log-panel');
const resultSection = document.getElementById('result-section');
const summaryBox = document.getElementById('summary-box');
const diffBox = document.getElementById('diff-box');
const approveBtn = document.getElementById('approve-btn');
const prLink = document.getElementById('pr-link');
const badgeBefore = document.getElementById('badge-before');
const badgeAfter = document.getElementById('badge-after');

let currentRunId = null;

function setStep(step) {
    ['cloning', 'testing', 'fixing', 'done'].forEach(s => {
        document.getElementById(`step-${s}`).className = '';
    });
    const el = document.getElementById(`step-${step}`);
    if (el) el.className = 'active';
}

function appendLog(html) {
    const div = document.createElement('div');
    div.innerHTML = html;
    logPanel.appendChild(div);
    logPanel.scrollTop = logPanel.scrollHeight;
}

startBtn.addEventListener('click', async () => {
    const url = urlInput.value.trim();
    if (!url) return;
    
    startBtn.disabled = true;
    errorMsg.classList.add('hidden');
    progressSection.classList.remove('hidden');
    resultSection.classList.add('hidden');
    logPanel.innerHTML = '';
    
    try {
        const res = await fetch('/api/runs', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({repo_url: url})
        });
        
        if (!res.ok) throw new Error((await res.json()).detail || 'Failed to start run');
        
        const data = await res.json();
        currentRunId = data.run_id;
        connectSSE(currentRunId);
        
    } catch (e) {
        errorMsg.textContent = e.message;
        errorMsg.classList.remove('hidden');
        startBtn.disabled = false;
        progressSection.classList.add('hidden');
    }
});

function connectSSE(runId) {
    const evs = new EventSource(`/api/runs/${runId}/events`);
    
    evs.onmessage = (e) => {
        const event = JSON.parse(e.data);
        
        if (event.type === 'status') {
            appendLog(`<span class="log-status">[*] ${event.data.message}</span>`);
            if (event.data.message.includes('Cloning')) setStep('cloning');
            if (event.data.message.includes('initial tests')) setStep('testing');
            if (event.data.message.includes('Agent loop started')) setStep('fixing');
        } 
        else if (event.type === 'tool_call') {
            appendLog(`<span class="log-tool">[TOOL] ${event.data.tool}</span>`);
        }
        else if (event.type === 'tool_result') {
            let res = event.data.result.substring(0, 100).replace(/\n/g, ' ');
            if (event.data.result.length > 100) res += '...';
            appendLog(`<span class="log-result">[RESULT] ${res}</span>`);
        }
        else if (event.type === 'agent_message') {
            appendLog(`<div class="log-agent">[AGENT] ${event.data.message}</div>`);
        }
        else if (event.type === 'error') {
            appendLog(`<span class="log-error">[!] ${event.data.message}</span>`);
            evs.close();
            startBtn.disabled = false;
            fetchResults(runId);
        }
        else if (event.type === 'done') {
            setStep('done');
            evs.close();
            startBtn.disabled = false;
            fetchResults(runId);
        }
    };
    
    evs.onerror = () => {
        evs.close();
        startBtn.disabled = false;
    };
}

async function fetchResults(runId) {
    const res = await fetch(`/api/runs/${runId}`);
    const data = await res.json();
    
    if (data.status === 'error') {
        errorMsg.textContent = data.error_message || 'An error occurred during execution.';
        errorMsg.classList.remove('hidden');
        return;
    }
    
    resultSection.classList.remove('hidden');
    
    if (data.test_before) {
        badgeBefore.className = `badge ${data.test_before.passed ? 'badge-green' : 'badge-red'}`;
        badgeBefore.textContent = `Before: ${data.test_before.passed ? 'Passing' : 'Failing'}`;
    }
    if (data.test_after) {
        badgeAfter.className = `badge ${data.test_after.passed ? 'badge-green' : 'badge-red'}`;
        badgeAfter.textContent = `After: ${data.test_after.passed ? 'Passing' : 'Failing'}`;
    }
    
    const rawHtml = marked.parse(data.summary);
    const cleanHtml = DOMPurify.sanitize(rawHtml);
    summaryBox.innerHTML = `<strong>Summary:</strong><br/>${cleanHtml}`;
    
    diffBox.textContent = data.diff || 'No changes made.';
    if (window.hljs) hljs.highlightElement(diffBox);
    
    if (data.test_before && data.test_before.passed) {
        approveBtn.style.display = 'none';
        summaryBox.innerHTML += `<br/><br/><strong>No fixes needed as tests already pass!</strong>`;
    } else if (data.success) {
        approveBtn.style.display = 'block';
        approveBtn.disabled = false;
        approveBtn.onclick = () => createPR(runId);
        prLink.classList.add('hidden');
    } else {
        approveBtn.style.display = 'none';
        summaryBox.innerHTML += `<br/><br/><strong style="color:#ef4444;">Agent failed to fix the tests.</strong>`;
    }
}

async function createPR(runId) {
    approveBtn.disabled = true;
    approveBtn.textContent = 'Creating PR...';
    try {
        const res = await fetch(`/api/runs/${runId}/create-pr`, { method: 'POST' });
        if (!res.ok) throw new Error((await res.json()).detail || 'Failed to create PR');
        const data = await res.json();
        
        approveBtn.style.display = 'none';
        prLink.classList.remove('hidden');
        prLink.innerHTML = `
            <div style="margin-top: 10px;">
                <p>✅ PR Created Successfully: <strong>${data.pr_url}</strong></p>
                <a href="${data.pr_url}" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 10px 20px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin-top: 10px;">
                    View PR on GitHub
                </a>
            </div>
        `;
    } catch (e) {
        prLink.classList.remove('hidden');
        prLink.innerHTML = `<p style="color: #ef4444; font-weight: bold;">❌ Failed to create PR: ${e.message}</p>`;
        approveBtn.disabled = false;
        approveBtn.textContent = 'Approve & Create PR';
    }
}
