"""One-time BRB setup against a Switch server. Safe to run again.

    uv run brb/setup.py [--name brb]

Needs SWITCH_URL and SWITCH_REGISTRATION_KEY in .env. If they're missing it
reads them from a local Switch Console server on this computer, or asks. It
registers the BRB agent, then lets anyone in a room talk to BRB. Use --name
when the server already has an agent called brb.
"""

import argparse
import os
from getpass import getpass
from pathlib import Path

import httpx
from dotenv import set_key

# Importing register loads .env. Its main block won't run.
from register import ENV_PATH, register_agent


def remember(name: str, value: str) -> None:
    set_key(ENV_PATH, name, value)
    os.environ[name] = value


def local_console_settings(run_dir: Path) -> dict[str, str]:
    """Address and key of a server Switch Console runs on this computer."""
    env_file = run_dir / "switch-core.env"
    if not env_file.exists():
        return {}
    values = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()
    if not {"SERVER_PORT", "AGENT_REGISTRATION_TOKEN"} <= values.keys():
        return {}
    host = values.get("SERVER_HOST", "127.0.0.1")
    return {
        "SWITCH_URL": f"http://{host}:{values['SERVER_PORT']}",
        "SWITCH_REGISTRATION_KEY": values["AGENT_REGISTRATION_TOKEN"],
    }


def console_run_dir() -> Path:
    """Where Switch Console keeps its local server's settings (Windows)."""
    return Path(os.environ.get("APPDATA", "")) / "switchdash" / "local-switch-server" / "native" / "run"


def ask_for_missing() -> None:
    if not os.environ.get("SWITCH_URL"):
        found = local_console_settings(console_run_dir())
        if found:
            print(f"Found a local Switch Console server at {found['SWITCH_URL']}.")
            for key, value in found.items():
                remember(key, value)
    if not os.environ.get("SWITCH_URL"):
        url = input("Switch API URL (e.g. https://api.example.com): ").strip().rstrip("/")
        remember("SWITCH_URL", url)
    if not os.environ.get("SWITCH_REGISTRATION_KEY"):
        print("The registration key is AGENT_REGISTRATION_TOKEN on a self-hosted server,")
        print("or a key from the Gateway's API keys page.")
        remember("SWITCH_REGISTRATION_KEY", getpass("Registration key (hidden): ").strip())


def ensure_agent(env_prefix: str, name: str, description: str) -> None:
    """Register an agent once. Its key is shown only once, so save it at once."""
    if os.environ.get(f"{env_prefix}_API_KEY"):
        print(f"{name}: already registered")
        return
    agent = register_agent(os.environ["SWITCH_URL"], os.environ["SWITCH_REGISTRATION_KEY"], name, description)
    remember(f"{env_prefix}_AGENT_ID", agent["id"])
    remember(f"{env_prefix}_API_KEY", agent["api_key"])
    print(f"{name}: registered")


def open_brb_to_everyone() -> None:
    """BRB answers anyone in its rooms. A helper agent with the same owner sets it."""
    response = httpx.post(
        f"{os.environ['SWITCH_URL']}/agents/{os.environ['SETUP_AGENT_ID']}/ops/update_agent_detail",
        headers={"Authorization": f"Bearer {os.environ['SETUP_API_KEY']}"},
        json={"agent_id": os.environ["BRB_AGENT_ID"], "addressing": "anyone"},
        timeout=30,
    )
    response.raise_for_status()
    print("BRB: anyone in a room can talk to it")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default="brb", help="agent name for BRB on this server")
    name = parser.parse_args().name

    ask_for_missing()
    remember("BRB_NAME", name)
    ensure_agent("BRB", name,"Runs the BRB quiz, meeting checks and ledger.")
    ensure_agent("SETUP", f"{name}.setup", "One-off helper that sets BRB's addressing.")
    open_brb_to_everyone()
    print(f"\nDone. Start BRB with: uv run brb/listener.py  (in chat it is @{name})")


if __name__ == "__main__":
    main()
