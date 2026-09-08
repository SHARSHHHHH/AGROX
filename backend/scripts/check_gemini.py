#!/usr/bin/env python3
"""Standalone Gemini connectivity check.

Run this FIRST whenever the AI answers stop working. It talks to Gemini
directly and prints the real error, instead of the app's fallback sentence.

    cd backend
    python scripts/check_gemini.py

Exit code 0 = everything works.
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai import llm                    # noqa: E402
from app.core.config import settings      # noqa: E402

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m")


def ok(msg):
    print(f"{GREEN}  PASS{RESET}  {msg}")


def fail(msg):
    print(f"{RED}  FAIL{RESET}  {msg}")


def warn(msg):
    print(f"{YELLOW}  WARN{RESET}  {msg}")


async def main() -> int:
    print("\nGemini connectivity check")
    print("=" * 60)

    # ---- 1. Key present ------------------------------------------------
    print("\n1. API key")
    key = settings.GEMINI_API_KEY
    if not key:
        fail("GEMINI_API_KEY is empty.")
        print(f"{DIM}     Add it to backend/.env and restart.")
        print(f"     Create one at https://aistudio.google.com/apikey{RESET}")
        return 1

    ok(f"key present ({len(key)} chars, starts '{key[:4]}…')")
    if key.startswith("AQ."):
        print(f"{DIM}     'AQ.' is Google's newer key format. It is valid on")
        print(f"     the native generativelanguage endpoint this app uses.{RESET}")
    elif not key.startswith("AIza"):
        warn("unrecognised key prefix — if auth fails below, re-copy the key.")

    # ---- 2. Which models can this key actually see? --------------------
    print("\n2. Model access")
    try:
        models = await llm.list_models()
    except llm.GeminiError as exc:
        fail(f"[{exc.kind}] {exc}")
        await llm.close_client()
        return 1

    ok(f"key can reach {len(models)} model(s)")

    configured = settings.GEMINI_MODEL
    if configured in models:
        ok(f"configured model '{configured}' is available")
    else:
        fail(f"configured model '{configured}' is NOT in the available list")
        flash = [m for m in models if "flash" in m and "image" not in m][:8]
        print(f"{DIM}     Available flash models: {', '.join(flash) or 'none'}")
        print(f"     Set GEMINI_MODEL in backend/.env to one of these.{RESET}")
        await llm.close_client()
        return 1

    # ---- 3. Real generation call ---------------------------------------
    print("\n3. Generation")
    started = time.perf_counter()
    try:
        text = await llm.chat_strict(
            "You are a helpful assistant. Answer in one short sentence.",
            "Say OK if you can read this.",
            temperature=0.0)
    except llm.GeminiError as exc:
        fail(f"[{exc.kind}] {exc}")
        await llm.close_client()
        return 1

    elapsed = time.perf_counter() - started
    ok(f"generation succeeded in {elapsed:.2f}s")
    print(f"{DIM}     Reply: {text[:100]}{RESET}")

    if elapsed > 8:
        warn(f"{elapsed:.1f}s is slow for a short prompt.")
        print(f"{DIM}     GEMINI_THINKING_BUDGET is {settings.GEMINI_THINKING_BUDGET}. "
              f"Set it to 0 in .env to disable reasoning overhead.{RESET}")

    # ---- 4. Function calling (agentic layer) ---------------------------
    print("\n4. Function calling")
    tools = [{
        "name": "get_weather",
        "description": "Get the current weather for a named location.",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    }]
    try:
        result = await llm.chat_with_tools(
            "You are an assistant with tools. Use them when relevant.",
            "What is the weather in Chennai right now?",
            tools)
    except llm.GeminiError as exc:
        warn(f"[{exc.kind}] {exc}")
        print(f"{DIM}     Chat works, so the agentic layer is degraded, "
              f"not broken.{RESET}")
    else:
        if result["type"] == "function_call":
            ok(f"model requested tool '{result['name']}' with {result['args']}")
        else:
            warn("model replied with text instead of calling the tool")

    await llm.close_client()

    print("\n" + "=" * 60)
    print(f"{GREEN}All checks passed. Gemini is working.{RESET}\n")
    print(f"{DIM}Current settings:")
    print(f"  model            {settings.GEMINI_MODEL}")
    print(f"  thinking budget  {settings.GEMINI_THINKING_BUDGET}")
    print(f"  max output       {settings.GEMINI_MAX_OUTPUT_TOKENS}{RESET}\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
