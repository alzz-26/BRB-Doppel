"""Add a teammate to BRB and create their Doppel's folder, for any provider.

    uv run brb/setup_doppel.py --username alzz_26 --name Alisha --provider claude

--username is their username in the chat app (Discord). Run it again to add
missing files: it never overwrites a persona or a status someone already wrote.
"""

import argparse
import json
from pathlib import Path

from doppel_files import PROVIDERS, provider_files, scope_section, starter_persona, starter_status

ROOT = Path(__file__).resolve().parent.parent
TEAM_PATH = ROOT / "brb" / "team.json"


def write_new(path: Path, content: str, overwrite: bool = False) -> bool:
    """Write the file unless it exists. Unix line endings for Linux servers."""
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def setup_doppel(username: str, name: str, provider: str, doppel: str, folder: str) -> list[str]:
    """Add the member to team.json and fill their folder. Return what changed."""
    changes = []
    team = json.loads(TEAM_PATH.read_text(encoding="utf-8")) if TEAM_PATH.exists() else {}
    member = {"name": name, "folder": folder, "doppel": doppel}
    if team.get(username) != member:
        team[username] = member
        TEAM_PATH.write_text(json.dumps(team, indent=2) + "\n", encoding="utf-8", newline="\n")
        changes.append(f"team.json: {username} is {name}, Doppel {doppel}")

    base = ROOT / "doppels" / folder
    persona_path = base / "AGENTS.md"
    if write_new(persona_path, starter_persona(name)):
        changes.append(f"doppels/{folder}/AGENTS.md")
    else:
        persona = persona_path.read_text(encoding="utf-8")
        if "## Scope" not in persona:
            # Personas from before the scope rules moved out of CLAUDE.md.
            write_new(persona_path, persona.rstrip() + "\n" + scope_section(name), overwrite=True)
            changes.append(f"doppels/{folder}/AGENTS.md: added scope rules")
    if write_new(base / "status.md", starter_status(name)):
        changes.append(f"doppels/{folder}/status.md")
    # Provider files only point at AGENTS.md, so keeping them current is safe.
    for relative, content in provider_files(provider, doppel).items():
        write_new(base / relative, content, overwrite=True)
        changes.append(f"doppels/{folder}/{relative}")
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", required=True, help="their chat username, like alzz_26")
    parser.add_argument("--name", required=True, help="the name people call them, like Alisha")
    parser.add_argument("--provider", default="claude", choices=PROVIDERS)
    parser.add_argument("--doppel", help="agent name to register (default doppel.<name>)")
    args = parser.parse_args()

    doppel = args.doppel or f"doppel.{args.name.lower()}"
    for change in setup_doppel(args.username, args.name, args.provider, doppel, args.name):
        print("  wrote", change)

    folder = (ROOT / "doppels" / args.name).resolve()
    print(f"""
Next, in Switch Console, signed in as {args.name}:
  1. Your Agents > new agent. Provider: {args.provider}. Name: {doppel}.
  2. Directory: {folder}
  3. Who can talk to it: custom rule with {args.name}, their teammates, and the agent brb.
  4. In the chat app: `@brb start quiz` to give the Doppel its persona.""")


if __name__ == "__main__":
    main()
