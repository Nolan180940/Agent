"""
Terminal / shell tools — Git Bash, PowerShell, CMD.

Provides the agent with full shell access on Windows.
"""
import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from tools.base import tool


# ── Shell discovery ─────────────────────────────────────────────────────────

def _find_git_bash() -> Optional[str]:
    """Locate Git Bash executable on the system."""
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        r"C:\Git\bin\bash.exe",
    ]
    # Also check PATH
    for p in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(p) / "bash.exe"
        if candidate.exists():
            return str(candidate)
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _find_powershell() -> str:
    """Return the best available PowerShell executable."""
    # Prefer pwsh (PowerShell 7+) over powershell (Windows PowerShell 5.1)
    for exe in ["pwsh.exe", "powershell.exe"]:
        for p in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(p) / exe
            if candidate.exists():
                return str(candidate)
    return "powershell.exe"  # fallback


async def _run_shell(
    command: str,
    shell: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
    env: Optional[dict] = None,
) -> str:
    """Run a command in the given shell and return stdout+stderr."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=merged_env,
        executable=shell,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return f"⚠️ Command timed out after {timeout}s"

    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()

    parts = []
    if out:
        parts.append(out)
    if err:
        parts.append(f"[stderr]\n{err}")
    if not parts:
        parts.append(f"(exit code {proc.returncode})")
    return "\n".join(parts)


# ── Tools ───────────────────────────────────────────────────────────────────

@tool(category="terminal")
async def run_powershell(
    command: str,
    cwd: str = "",
    timeout_seconds: int = 60,
) -> str:
    """
    Run a PowerShell command and return the output.

    Args:
        command: PowerShell command(s) to execute.
        cwd: Optional working directory (default: current).
        timeout_seconds: Max execution time in seconds.

    Returns:
        stdout + stderr output.
    """
    ps = _find_powershell()
    cwd_path = cwd or None
    return await _run_shell(command, shell=ps, cwd=cwd_path, timeout=timeout_seconds)


@tool(category="terminal")
async def run_git_bash(
    command: str,
    cwd: str = "",
    timeout_seconds: int = 60,
) -> str:
    """
    Run a command in Git Bash (bash on Windows) and return the output.

    Useful for git operations, shell scripts, and Unix-style commands.

    Args:
        command: Bash command(s) to execute.
        cwd: Optional working directory.
        timeout_seconds: Max execution time in seconds.

    Returns:
        stdout + stderr output.
    """
    bash = _find_git_bash()
    if bash is None:
        return "Git Bash not found. Install Git for Windows from https://git-scm.com"
    cwd_path = cwd or None
    return await _run_shell(command, shell=bash, cwd=cwd_path, timeout=timeout_seconds)


@tool(category="terminal")
async def run_cmd(
    command: str,
    cwd: str = "",
    timeout_seconds: int = 60,
) -> str:
    """
    Run a command in Windows CMD (cmd.exe) and return the output.

    Args:
        command: CMD command(s) to execute.
        cwd: Optional working directory.
        timeout_seconds: Max execution time in seconds.

    Returns:
        stdout + stderr output.
    """
    cwd_path = cwd or None
    return await _run_shell(command, shell="cmd.exe", cwd=cwd_path, timeout=timeout_seconds)


@tool(category="terminal")
async def run_shell_command(
    command: str,
    shell: str = "powershell",
    cwd: str = "",
    timeout_seconds: int = 60,
) -> str:
    """
    Run a command in the specified shell (powershell, git-bash, or cmd).

    Args:
        command: The command to execute.
        shell: Which shell to use — "powershell", "git-bash", or "cmd".
        cwd: Optional working directory.
        timeout_seconds: Max execution time in seconds.

    Returns:
        stdout + stderr output.
    """
    shell_map = {
        "powershell": _find_powershell(),
        "git-bash": _find_git_bash(),
        "cmd": "cmd.exe",
    }
    shell_lower = shell.lower()
    if shell_lower not in shell_map:
        return f"Unknown shell '{shell}'. Use: powershell, git-bash, or cmd."

    exe = shell_map[shell_lower]
    if exe is None:
        return f"{shell} not found on this system."

    cwd_path = cwd or None
    return await _run_shell(command, shell=exe, cwd=cwd_path, timeout=timeout_seconds)
