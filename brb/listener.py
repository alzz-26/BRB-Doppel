import asyncio
import json
import os
import uuid

from dotenv import set_key
from websockets.asyncio.client import connect
from quiz_flow import handle_quiz

# Importing post_message also loads .env.
from post_message import ENV_PATH, post_message

quiz_lock = asyncio.Lock()
background_tasks = set()

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
    text = payload.get("body") or ""
    name = payload.get("sender_name") or "there"
    addressed = bool(payload.get("addressed"))

    # The lock handles one quiz step at a time. The thread keeps pings flowing.
    async with quiz_lock:
        reply = await asyncio.to_thread(
            handle_quiz, payload.get("sender") or name, name, text, addressed
        )

    if reply is None:
        if not addressed:
            return
        if "help" in text.lower():
            reply = "Commands: `start quiz`, `cancel quiz`."
        else:
            reply = f"Hi {name}, I'm BRB, your team's meeting manager."

    print(f"{name}: {text}")
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
                # Run in the background so this loop can keep answering pings.
                task = asyncio.create_task(handle_message(data))
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
            elif event == "refused":
                print("Refused:", data)
            else:
                print("Event:", event)


if __name__ == "__main__":
    asyncio.run(listen())