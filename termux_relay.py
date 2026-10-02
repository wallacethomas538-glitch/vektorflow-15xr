#!/usr/bin/env python3
"""VektorFlow Termux relay.

Run this as a background Termux service (for example through Termux:Boot).
It polls the VektorFlow Second Brain relay API over outbound HTTPS, so Render
never needs an inbound connection to the phone.

It does NOT execute arbitrary commands from the model. It maps jobs to a small
allowlisted set of local developer executors.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid

import requests

BASE_URL = os.environ["VEKTORFLOW_URL"].rstrip("/")
TOKEN = os.environ["TERMUX_RELAY_TOKEN"]
POLL_SECONDS = max(2, int(os.getenv("TERMUX_POLL_SECONDS", "5")))
RELAY_ID = os.getenv("TERMUX_RELAY_ID", f"termux-{uuid.uuid4().hex[:10]}")
ROOT = os.path.expanduser(os.getenv("VEKTORFLOW_REPO_DIR", "~/vektorflow-15xr"))

def build_command(target: str, instruction: str, edit_requested: bool):
    if target == "hermes":
        return ["hermes", "chat", "-q", instruction, "--format", "stream-json"]
    if target == "codex":
        return ["codex", "exec"] + (["--full-auto"] if edit_requested else []) + [instruction]
    if target == "opencode":
        return ["opencode", "run"] + (["--auto"] if edit_requested else []) + [instruction]
    raise ValueError(f"Unsupported executor: {target}")

EXECUTORS = {"hermes": "hermes", "codex": "codex", "opencode": "opencode"}

session = requests.Session()
session.headers.update({"X-Termux-Relay-Token": TOKEN})

def run_executor(target: str, instruction: str, working_dir: str, timeout: int, action: str = ""):
    if target not in EXECUTORS:
        raise ValueError(f"Unsupported executor: {target}")
    cwd = os.path.expanduser(working_dir or ROOT)
    if not os.path.isdir(cwd):
        cwd = ROOT
    proc = subprocess.run(
        EXECUTORS[target] + [instruction],
        cwd=cwd, text=True, capture_output=True,
        timeout=max(10, min(timeout, 900)),
    )
    return proc.returncode, proc.stdout[-50000:], proc.stderr[-20000:]

def heartbeat():
    payload = {
        "relay_id": RELAY_ID, "hostname": socket.gethostname(), "version": "1.0",
        "status": "online", "executors": list(EXECUTORS),
    }
    session.post(f"{BASE_URL}/api/second-brain/relay/heartbeat", json=payload, timeout=15).raise_for_status()

def poll():
    response = session.get(f"{BASE_URL}/api/second-brain/relay/jobs/next", timeout=20)
    response.raise_for_status()
    return response.json().get("job")

def report(job_id, status, stdout="", stderr="", exit_code=None, result=None):
    session.post(
        f"{BASE_URL}/api/second-brain/relay/jobs/result",
        json={"job_id": job_id, "status": status, "stdout": stdout, "stderr": stderr,
              "exit_code": exit_code, "result": result or {}},
        timeout=20,
    ).raise_for_status()

def main():
    print(f"VektorFlow Termux relay {RELAY_ID} -> {BASE_URL}")
    while True:
        try:
            heartbeat()
            job = poll()
            if job:
                try:
                    code, stdout, stderr = run_executor(
                        job["target"], job["instruction"], job.get("working_dir") or ROOT,
                        int(job.get("timeout_seconds") or 300), job.get("action") or "",
                    )
                    report(job["id"], "completed" if code == 0 else "failed",
                           stdout, stderr, code, {"target": job["target"], "action": job["action"]})
                except subprocess.TimeoutExpired as exc:
                    report(job["id"], "failed", str(exc.stdout or ""), str(exc.stderr or ""),
                           None, {"error": "timeout"})
                except Exception as exc:
                    report(job["id"], "failed", "", str(exc), None, {"error": type(exc).__name__})
            time.sleep(POLL_SECONDS)
        except Exception as exc:
            print(f"relay error: {exc}", flush=True)
            time.sleep(min(POLL_SECONDS * 3, 30))

if __name__ == "__main__":
    main()
