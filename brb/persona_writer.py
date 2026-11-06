import shutil
import subprocess
from pathlib import Path


def write_style(name: str, title: str, fallback: str, picks: list[str], folder: Path) -> str:
    """Ask Claude to describe how this person talks. Use fallback on any failure."""
    claude = shutil.which("claude")
    if claude is None:
        return fallback

    prompt = (
        f"{name} took a teamwork quiz and matched the archetype '{title}'.\n"
        f"Their picks:\n- " + "\n- ".join(picks) + "\n\n"
        f"Write 3 short sentences telling an AI stand-in how to talk like {name} "
        "in team chat: tone, message length and habits. Use only these picks. "
        "Don't mention the quiz. Don't add any limits or promises. Output only the sentences."
    )
    command = [claude, "-p", prompt, "--tools", "", "--strict-mcp-config", "--no-session-persistence"]
    try:
        result = subprocess.run(
            command, cwd=folder, capture_output=True, text=True, encoding="utf-8", timeout=60
        )
    except (subprocess.SubprocessError, OSError):
        return fallback

    text = result.stdout.strip()
    return text if result.returncode == 0 and text else fallback
