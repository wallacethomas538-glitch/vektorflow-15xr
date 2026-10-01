"""Optional isolated execution substrate for VektorFlow.

Borrowed/adapted infrastructure pattern: disposable container execution.
No host filesystem is mounted and networking is disabled by default.
Execution is disabled unless VF_DOCKER_ENABLED=true.
"""
from __future__ import annotations
import asyncio, os, shlex
from typing import Any, Dict

class SandboxUnavailable(RuntimeError):
    pass

def sandbox_status() -> Dict[str, Any]:
    return {
        "enabled": os.getenv("VF_DOCKER_ENABLED","false").lower() == "true",
        "image": os.getenv("VF_DOCKER_IMAGE","python:3.12-alpine"),
        "network": "none",
        "filesystem": "isolated",
        "max_seconds": int(os.getenv("VF_DOCKER_TIMEOUT","60")),
    }

async def run_python(code: str, *, timeout: int | None=None) -> Dict[str, Any]:
    if os.getenv("VF_DOCKER_ENABLED","false").lower() != "true":
        raise SandboxUnavailable("Docker sandbox is disabled. Set VF_DOCKER_ENABLED=true after Docker is available and approved.")
    if not code.strip():
        raise ValueError("code is required")
    image = os.getenv("VF_DOCKER_IMAGE","python:3.12-alpine")
    seconds = max(1, min(int(timeout or os.getenv("VF_DOCKER_TIMEOUT","60")), 300))
    cmd = [
        "docker","run","--rm","--network","none",
        "--cpus",os.getenv("VF_DOCKER_CPUS","1"),
        "--memory",os.getenv("VF_DOCKER_MEMORY","512m"),
        "--pids-limit",os.getenv("VF_DOCKER_PIDS","128"),
        "--read-only","--tmpfs","/tmp:rw,noexec,nosuid,size=64m",
        image,"python","-c",code,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"status":"timeout","timeout_seconds":seconds}
    return {
        "status":"completed" if proc.returncode == 0 else "failed",
        "returncode":proc.returncode,
        "stdout":out.decode("utf-8","replace")[-20000:],
        "stderr":err.decode("utf-8","replace")[-10000:],
        "sandbox":sandbox_status(),
    }
