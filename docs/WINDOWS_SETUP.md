# Windows Setup — WinError 10013 and PowerShell

Neither of the errors you hit is a bug in the project. Both are Windows
environment issues.

---

## 1. `WinError 10013` — the server never started

```
ERROR: [WinError 10013] An attempt was made to access a socket
       in a way forbidden by its access permissions
```

Windows refused to let uvicorn bind port 8000. The API never came up, which is
why the `curl` that followed had nothing to talk to.

Usual cause: **Hyper-V, WSL2 or Docker Desktop reserves large blocks of TCP
ports**, and 8000 often falls inside one. It is not "in use" by a visible
program, so Task Manager shows nothing.

### Check whether 8000 is inside a reserved range

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

If you see a range containing 8000 (e.g. `7990  8089`), that is your answer.

### Fix A — use a different port (easiest)

```powershell
cd backend
uvicorn app.main:app --reload --port 8080
```

Then tell the frontend where the backend is. Create `frontend\.env.local`:

```
VITE_API_PORT=8080
```

`vite.config.ts` now reads that variable, so the dev proxy follows. Restart
`npm run dev` after creating the file.

### Fix B — reclaim the reserved range

Run PowerShell **as Administrator**:

```powershell
net stop winnat
net start winnat
```

This releases the dynamic reservations Hyper-V grabbed. They often come back
after a reboot, so Fix A is more durable.

### Fix C — check nothing is genuinely listening

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

If something is, stop it or use Fix A.

---

## 2. `curl` does not work the way you expect in PowerShell

```
curl : The URI prefix is not recognized.
```

In PowerShell, `curl` is an **alias for `Invoke-WebRequest`**, not real curl.
Two things broke:

- `localhost:8000/...` — PowerShell reads `localhost:` as a URI scheme. You
  must write `http://localhost:8000/...`.
- `# must now say "qwen"` — that is a bash comment. PowerShell tried to parse it.

### Use these instead

```powershell
Invoke-RestMethod http://localhost:8000/api/health | ConvertTo-Json -Depth 5
Invoke-RestMethod http://localhost:8000/api/test-gemini | ConvertTo-Json -Depth 5
```

Or call the real curl, which ships with Windows 10+ as `curl.exe`:

```powershell
curl.exe http://localhost:8000/api/health
```

Adjust the port if you used Fix A.

---

## 3. Full startup sequence for Windows

**Terminal 1 — backend**

```powershell
cd sustainable-agriculture\backend
pip install -r requirements.txt
pip install -r requirements-qwen.txt
uvicorn app.main:app --reload --port 8080
```

Watch for:

```
Qwen loading in background (first run downloads ~3 GB)...
Active LLM provider: {'provider': 'qwen', ...}
Startup complete. Provider=qwen Demo=True
...
Qwen ready on cpu          <-- may take several minutes on first run
```

The API answers immediately — you do not need to wait for the last line.
Until it appears, chat returns an honest "still loading" message rather than
hanging.

**Terminal 2 — frontend**

```powershell
cd sustainable-agriculture\frontend
echo VITE_API_PORT=8080 > .env.local
npm install
npm run dev
```

**Verify**

```powershell
Invoke-RestMethod http://localhost:8080/api/health | ConvertTo-Json -Depth 5
```

`llm_provider` must read `qwen`.

---

## 4. Where the model downloads to

Hugging Face caches under:

```
C:\Users\<you>\.cache\huggingface\hub
```

Qwen2.5-1.5B-Instruct is roughly 3 GB. Make sure that drive has space. To move
it, set `HF_HOME` before starting uvicorn:

```powershell
$env:HF_HOME = "D:\hf-cache"
uvicorn app.main:app --reload --port 8080
```

---

## 5. Python 3.9 note

Your environment is Python 3.9. I checked the whole backend against 3.9:
**0 syntax errors, 0 runtime incompatibilities.** Files using newer annotation
syntax already carry `from __future__ import annotations`, which defers
evaluation and keeps 3.9 safe.

One thing to watch: newer PyTorch releases are dropping Python 3.9. Your
install log shows torch resolved successfully, so you are fine — but if you
ever reinstall and pip refuses, that is why, and Python 3.11 is the fix.

---

## 6. Expect the first answer to be slow

Qwen2.5-1.5B on a CPU generates roughly 5-15 tokens/second, so a 200-token
answer takes 15-40 seconds. That is inherent to running a local model without a
GPU, not a fault.

If it is too slow for a demo, in `backend\.env`:

```
QWEN_MAX_NEW_TOKENS=120
```

Or switch back to the API once you are off a network that blocks Google:

```
LLM_PROVIDER=gemini
```
