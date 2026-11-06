import asyncio
import json
import os
import uuid

from dotenv import set_key
from websockets.asyncio.client import connect

# Importing post_message also loads .env.
from post_message import ENV_PATH, post_message


def connection_id() -> str:
    """Reuse one ID, so a reconnect counts as the same connection."""
    existing = os.environ.get("BRB_CONNECTION_ID")
    if existing:
        return existing
    new_id = str(uuid.uuid4())
    set_key(ENV_PATH, "BRB_CONNECTION_ID", new_id)
    return new_id


async def handle_message(data: dict) -> None:
    payload = data.get("payload", {})
    # We see every room message, but only act when BRB is tagged.
    if not payload.get("addressed"):
        return
    print(f"{payload.get('sender_name')}: {payload.get('body')}")
    if "help" in (payload.get("body") or "").lower():
        reply = f"Hi {payload.get('sender_name')}, I'm BRB, your team's meeting manager. What can I help you with ?"
    else:
        reply = f"Hi {payload.get('sender_name')}, I'm BRB, your team's meeting manager."
    # post_message is blocking, so run it off the heartbeat loop.
    await asyncio.to_thread(post_message, data["room_id"], reply)


async def listen() -> None:
    base = os.environ["SWITCH_URL"].replace("http://", "ws://", 1)
    agent_id = os.environ["BRB_AGENT_ID"]
    url = (
        f"{base}/agents/{agent_id}/connection/ws"
        f"?connection_id={connection_id()}&scope=all&filter=all"
    )
    headers = {"Authorization": f"Bearer {os.environ['BRB_API_KEY']}"}
    cursor = 0

    async with connect(url, additional_headers=headers) as socket:
        print("BRB is listening. Press Ctrl+C to stop.")
        async for raw in socket:
            frame = json.loads(raw)
            event = frame.get("event")
            data = frame.get("data", {})

            if event == "ping":
                await socket.send(json.dumps({"type": "pong", "cursor": cursor}))
            elif event == "message":
                cursor = data.get("sequence", cursor)
                await handle_message(data)
            elif event == "refused":
                print("Refused:", data)
            else:
                print("Event:", event)


if __name__ == "__main__":
    asyncio.run(listen())