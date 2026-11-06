import asyncio
import json
import os
import uuid

from dotenv import set_key
from websockets.asyncio.client import connect

from meeting import (
    finish_meeting,
    mark_present,
    parse_meeting_command,
    stand_in_message,
    start_meeting,
)

# Importing post_message also loads .env.
from post_message import ENV_PATH, invite_agent, post_message
from quiz import clean_text
from quiz_flow import handle_quiz, load_team

quiz_lock = asyncio.Lock()
background_tasks = set()


def run_in_background(coroutine) -> None:
    """Start a task and keep a reference so it isn't cleaned up early."""
    task = asyncio.create_task(coroutine)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


def connection_id() -> str:
    """Reuse one ID, so a reconnect counts as the same connection."""
    existing = os.environ.get("BRB_CONNECTION_ID")
    if existing:
        return existing
    new_id = str(uuid.uuid4())
    set_key(ENV_PATH, "BRB_CONNECTION_ID", new_id)
    return new_id


async def run_meeting(room_id: str, seconds: int) -> None:
    """Wait for the roll call to end, then bring in Doppels for anyone absent."""
    await asyncio.sleep(seconds)
    present, absent = finish_meeting(room_id, load_team())
    names = ", ".join(member["name"] for member in present) or "nobody"
    await asyncio.to_thread(post_message, room_id, f"Roll call closed. Present: {names}.")

    for member in absent:
        await asyncio.to_thread(invite_agent, room_id, member["doppel"])
        await asyncio.to_thread(
            post_message, room_id, f"{member['name']} is away. Their Doppel is standing in."
        )
        await asyncio.to_thread(post_message, room_id, stand_in_message(member))


async def handle_message(data: dict) -> None:
    payload = data.get("payload", {})
    text = payload.get("body") or ""
    name = payload.get("sender_name") or "there"
    addressed = bool(payload.get("addressed"))
    # `name` stays the username for lookups. `real_name` is for what people read.
    real_name = load_team().get(name, {}).get("name", name)

    # The lock handles one quiz step at a time. The thread keeps pings flowing.
    async with quiz_lock:
        reply = await asyncio.to_thread(
            handle_quiz, payload.get("sender") or name, name, text, addressed
        )

    if reply is None:
        room_id = data["room_id"]
        command = clean_text(text).lower()
        seconds = parse_meeting_command(command)

        if mark_present(room_id, name, command):
            reply = f"Got it, {real_name} is here."
        elif not addressed:
            return
        elif seconds is not None:
            if start_meeting(room_id):
                reply = f"Meeting starting! Reply `here` within {seconds} seconds."
                run_in_background(run_meeting(room_id, seconds))
            else:
                reply = "A roll call is already running here."
        elif "help" in text.lower():
            reply = "Commands: `start quiz`, `quit`, `meeting`, `meeting 30`."
        else:
            reply = f"Hi {real_name}, I'm BRB, your team's meeting manager."

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
                run_in_background(handle_message(data))
            elif event == "refused":
                print("Refused:", data)
            else:
                print("Event:", event)


if __name__ == "__main__":
    asyncio.run(listen())