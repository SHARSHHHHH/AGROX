#!/usr/bin/env python3
"""Diagnose why the app is not working. Run this FIRST when something breaks.

    cd backend
    python scripts/doctor.py
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GREEN, RED, YELLOW, DIM, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"
ok = lambda m: print(f"{GREEN}  PASS{RESET}  {m}")
bad = lambda m: print(f"{RED}  FAIL{RESET}  {m}")
warn = lambda m: print(f"{YELLOW}  WARN{RESET}  {m}")


def port_open(port, host="127.0.0.1"):
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    print("\nAgri Advisor doctor")
    print("=" * 58)
    problems = 0

    # --- 1. is the backend listening anywhere? ---
    print("\n1. Backend process")
    found = [p for p in (8000, 8080, 8001, 5000) if port_open(p)]
    if found:
        ok(f"something is listening on port(s): {found}")
    else:
        bad("nothing is listening on 8000, 8080, 8001 or 5000")
        print(f"{DIM}     The frontend's ECONNREFUSED means exactly this.")
        print(f"     Start it:  cd backend && uvicorn app.main:app --reload{RESET}")
        problems += 1

    # --- 2. frontend proxy target ---
    print("\n2. Frontend proxy target")
    env_local = os.path.join(os.path.dirname(os.getcwd()), "frontend", ".env.local")
    if os.path.exists(env_local):
        content = open(env_local, encoding="utf-8").read().strip()
        ok(f"frontend/.env.local exists: {content}")
        for line in content.splitlines():
            if line.startswith("VITE_API_PORT="):
                want = int(line.split("=", 1)[1].strip())
                if found and want not in found:
                    bad(f"proxy points at {want} but the backend is on {found}")
                    problems += 1
    else:
        if found and 8000 not in found:
            bad(f"no .env.local, so the proxy defaults to 8000, "
                f"but the backend is on {found}")
            print(f"{DIM}     Fix: echo VITE_API_PORT={found[0]} > frontend/.env.local{RESET}")
            problems += 1
        else:
            ok("no .env.local needed (proxy default 8000 matches)")

    # --- 3. database ---
    print("\n3. Database")
    try:
        from app.core.config import settings
        from app.database.db import SessionLocal
        from app.models.models import Farm, SensorReading, User

        db = SessionLocal()
        users = db.query(User).count()
        readings = db.query(SensorReading).count()
        farms = db.query(Farm).count()
        db.close()

        path = settings.DATABASE_URL.replace("sqlite:///", "")
        ok(f"database at {path}")
        if users:
            ok(f"{users} user(s), {farms} farm(s), {readings} sensor reading(s)")
        else:
            warn("no users — seed has not run. Start the backend once.")
    except Exception as exc:
        bad(f"database error: {type(exc).__name__}: {exc}")
        problems += 1

    # --- 4. configuration ---
    print("\n4. Configuration")
    try:
        from app.core.config import settings
        ok(f"LLM provider    : {settings.LLM_PROVIDER}")
        ok(f"Vision provider : {settings.VISION_PROVIDER}")
        if settings.DATA_GOV_API_KEY:
            ok(f"data.gov.in key : set ({len(settings.DATA_GOV_API_KEY)} chars)")
        else:
            warn("DATA_GOV_API_KEY is empty — mandi prices will be unavailable")
        if settings.LLM_PROVIDER == "qwen":
            try:
                import torch  # noqa: F401
                import transformers  # noqa: F401
                ok("torch + transformers installed")
            except ImportError:
                warn("LLM_PROVIDER=qwen but torch/transformers are missing")
                print(f"{DIM}     pip install -r requirements-qwen.txt{RESET}")
    except Exception as exc:
        bad(f"config error: {exc}")
        problems += 1

    print("\n" + "=" * 58)
    if problems:
        print(f"{RED}{problems} problem(s) found — see above.{RESET}\n")
    else:
        print(f"{GREEN}No problems found.{RESET}")
        print(f"{DIM}If the UI is still blank, hard-refresh the browser "
              f"(Ctrl+Shift+R).{RESET}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
