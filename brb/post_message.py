import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)


def post_message(room_id: str, content: str) -> dict:
    """Post a message into a room as BRB."""
    url = f"{os.environ['SWITCH_URL']}/agents/{os.environ['BRB_AGENT_ID']}/message"
    response = httpx.post(
        url,
        # This is BRB's own badge, not the bootstrap key.
        headers={"Authorization": f"Bearer {os.environ['BRB_API_KEY']}"},
        json={"room_id": room_id, "content": content},
        timeout=30,
    )
    if response.is_error:
        print(response.status_code, response.text)
    response.raise_for_status()
    return response.json()


def invite_agent(room_id: str, agent_name: str) -> dict:
    """Bring another agent into a room that BRB is already in."""
    url = (
        f"{os.environ['SWITCH_URL']}/agents/{os.environ['BRB_AGENT_ID']}"
        "/ops/invite_agent_to_room"
    )
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {os.environ['BRB_API_KEY']}"},
        json={"room_id": room_id, "agent_name": agent_name},
        timeout=30,
    )
    if response.is_error:
        print(response.status_code, response.text)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    print(post_message(os.environ["SWITCH_ROOM_ID"], "BRB is online"))