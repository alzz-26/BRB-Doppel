"""Private onboarding: `@brb onboard me` opens a room with just you and BRB.

The quiz runs there, so answers and mandate limits stay private. Only the
welcome card goes back to the room you asked from.
"""

import json
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ONBOARDING_PATH = ROOT / "data" / "onboarding.json"
ONBOARD_COMMANDS = {"onboard", "onboard me", "private quiz"}


def load_rooms() -> dict:
    if not ONBOARDING_PATH.exists():
        return {}
    return json.loads(ONBOARDING_PATH.read_text(encoding="utf-8"))


def save_rooms(rooms: dict) -> None:
    ONBOARDING_PATH.parent.mkdir(exist_ok=True)
    ONBOARDING_PATH.write_text(json.dumps(rooms, indent=2), encoding="utf-8")


def pick_bridge(bridges: list[dict]) -> str | None:
    """The chat app to open the room in: the default one, else any that can."""
    usable = [b for b in bridges if b.get("status") == "active" and b.get("can_create_channels")]
    for bridge in usable:
        if bridge.get("is_default"):
            return bridge["id"]
    return usable[0]["id"] if usable else None


def call_op(name: str, body: dict) -> dict:
    response = httpx.post(
        f"{os.environ['SWITCH_URL']}/agents/{os.environ['BRB_AGENT_ID']}/ops/{name}",
        headers={"Authorization": f"Bearer {os.environ['BRB_API_KEY']}"},
        json=body,
        timeout=60,
    )
    if response.is_error:
        print(name, response.status_code, response.text)
    response.raise_for_status()
    return response.json()["result"]


def open_private_room(username: str, real_name: str, origin_room: str) -> str:
    """Create a private room for this person. Return its room id.

    Always a fresh room: deleting the channel in Discord doesn't close the
    Switch room, so an old room may have no channel left to post in.
    """
    rooms = load_rooms()
    bridge = pick_bridge(call_op("list_bridges", {}))
    if bridge is None:
        raise RuntimeError("No connected chat app can create channels.")
    room = call_op(
        "create_room",
        {
            "name": f"BRB onboarding - {real_name}",
            "description": f"Private room for {real_name} and BRB: the quiz and debriefs.",
            "agent_names": [os.environ.get("BRB_NAME", "brb")],
            "user_names": [username],
            "channel_type": "direct",
            "bridge_id": bridge,
        },
    )
    rooms[username] = {"room_id": room["id"], "origin": origin_room}
    save_rooms(rooms)
    return room["id"]


def origin_of(room_id: str) -> str | None:
    """If room_id is someone's private room, the room they onboarded from."""
    for entry in load_rooms().values():
        if entry["room_id"] == room_id:
            return entry["origin"]
    return None


def welcome_text(real_name: str, first_question: str) -> str:
    return (
        f"Hi {real_name}! Only you and BRB are in this room, so your answers stay "
        f"private. The team will only see your welcome card.\n\n{first_question}"
    )
