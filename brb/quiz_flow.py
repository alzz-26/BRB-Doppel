import json
from pathlib import Path

from persona_writer import write_style
from quiz import (
    ARCHETYPES,
    QUESTIONS,
    build_card,
    build_persona,
    choose_archetype,
    clean_text,
    format_question,
    parse_answer,
    style_picks,
)

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "quiz_state.json"
TEAM_PATH = ROOT / "brb" / "team.json"
CANCEL_COMMANDS = {"cancel", "cancel quiz", "quit", "quit quiz", "stop", "stop quiz"}

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_team() -> dict:
    return json.loads(TEAM_PATH.read_text(encoding="utf-8"))


def write_persona(folder: str, name: str, answers: list[str], username: str) -> None:
    doppel_folder = ROOT / "doppels" / folder
    archetype = ARCHETYPES[choose_archetype(answers)]
    style = write_style(name, archetype["title"], archetype["style"], style_picks(answers), doppel_folder)
    path = doppel_folder / "AGENTS.md"
    persona = build_persona(name, answers, style, username, load_team())
    # Unix line endings: the Doppel may read this file on a Linux server.
    path.write_text(persona, encoding="utf-8", newline="\n")


def handle_quiz(sender_id: str, sender_name: str, text: str, addressed: bool) -> str | None:
    """Return BRB's reply, or None if this message isn't part of a quiz."""
    state = load_state()
    entry = state.get(sender_id)
    command = clean_text(text).lower()

    if entry is None:
        if not (addressed and command == "start quiz"):
            return None
        member = load_team().get(sender_name)
        if member is None:
            return f"{sender_name}, you aren't in brb/team.json yet."
        state[sender_id] = {"name": member["name"], "folder": member["folder"], "answers": []}
        save_state(state)
        return f"Let's build {member['name']}'s Doppel. Reply A, B, C or D.\n\n{format_question(0)}"

    if command in CANCEL_COMMANDS:
        del state[sender_id]
        save_state(state)
        return "Quiz cancelled."

    answer = parse_answer(text)
    if answer is None:
        return "Please reply with A, B, C or D, or say quit." if addressed else None

    entry["answers"].append(answer)
    done = len(entry["answers"])
    if done < len(QUESTIONS):
        save_state(state)  # Save each answer as soon as we have it.
        return format_question(done)

    write_persona(entry["folder"], entry["name"], entry["answers"], sender_name)
    card = build_card(entry["name"], entry["answers"])
    del state[sender_id]
    save_state(state)
    return card
