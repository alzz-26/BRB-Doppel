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

from away import (
    ask_doppel_message,
    away_entry,
    back_message,
    handle_away_command,
    mentioned_away_members,
    set_back,
)
from ledger import capture_items, handle_ledger_command, owner_of_doppel

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


async def bring_in(room_id: str, doppel: str) -> None:
    """Invite a Doppel. Switch refuses if it's already here, which is fine."""
    try:
        await asyncio.to_thread(invite_agent, room_id, doppel)
    except Exception as error:  # Already in the room, most often.
        print(f"Invite {doppel}: {error}")


async def ask_doppels_for_away(room_id: str, sender: str, real_name: str, text: str, team: dict) -> None:
    """Someone tagged a teammate who is away. Their Doppel answers instead."""
    for username, member in mentioned_away_members(text, sender, team):
        entry = away_entry(username) or {"until": None}
        await bring_in(room_id, member["doppel"])
        message = ask_doppel_message(member, real_name, text, entry["until"])
        await asyncio.to_thread(post_message, room_id, message)


async def after_away_change(room_id: str, member: dict, change: str) -> None:
    """Away: the Doppel joins this room. Back: the Doppel gives a catch-up."""
    await bring_in(room_id, member["doppel"])
    if change == "back":
        await asyncio.to_thread(post_message, room_id, back_message(member))


async def ledger_command(name: str, text: str, team: dict) -> str | None:
    """Keep the words' original case, so a rejection reason reads as typed."""
    async with quiz_lock:
        return await asyncio.to_thread(handle_ledger_command, name, clean_text(text), team)


async def handle_message(data: dict) -> None:
    payload = data.get("payload", {})
    text = payload.get("body") or ""
    name = payload.get("sender_name") or "there"
    addressed = bool(payload.get("addressed"))
    team = load_team()
    # `name` stays the username for lookups. `real_name` is for what people read.
    real_name = team.get(name, {}).get("name", name)

    # A Doppel's message can hold items for approval. BRB records them.
    async with quiz_lock:
        new_items = await asyncio.to_thread(capture_items, name, text, data["room_id"], team)
    if new_items:
        logged = ", ".join(f"#{item['id']}" for item in new_items)
        owner = new_items[0]["name"]
        note = f"Logged {logged} for {owner}'s approval."
        await asyncio.to_thread(post_message, data["room_id"], note)
        return

    # Doppels only report to the ledger. BRB never holds a conversation with them.
    if owner_of_doppel(name, team):
        return

    # The lock handles one quiz step at a time. The thread keeps pings flowing.
    async with quiz_lock:
        reply = await asyncio.to_thread(
            handle_quiz, payload.get("sender") or name, name, text, addressed
        )

    follow_up = None
    if reply is None:
        room_id = data["room_id"]
        command = clean_text(text).lower()
        seconds = parse_meeting_command(command)

        if mark_present(room_id, name, command):
            set_back(name)  # Answering a roll call means you're back.
            reply = f"Got it, {real_name} is here."
        elif not addressed:
            # BRB never reacts to its own posts.
            if name.lower() != "brb":
                await ask_doppels_for_away(room_id, name, real_name, text, team)
            return
        elif (ledger_reply := await ledger_command(name, text, team)) is not None:
            reply = ledger_reply
        elif (away_result := handle_away_command(name, command, team)) is not None:
            reply, change = away_result
            if change:
                follow_up = after_away_change(room_id, team[name], change)
        elif seconds is not None:
            if start_meeting(room_id):
                reply = f"Meeting starting! Reply `here` within {seconds} seconds."
                run_in_background(run_meeting(room_id, seconds))
            else:
                reply = "A roll call is already running here."
        elif "help" in text.lower():
            reply = (
                "Commands: `start quiz`, `quit`, `meeting`, `meeting 30`, "
                "`away until 11pm`, `away for 2h`, `back`, "
                "`debrief`, `approve 1`, `reject 1 reason`."
            )
        else:
            reply = f"Hi {real_name}, I'm BRB, your team's meeting manager."

    print(f"{name}: {text}")
    # post_message is blocking, so run it off the heartbeat loop.
    await asyncio.to_thread(post_message, data["room_id"], reply)
    if follow_up is not None:
        await follow_up

async def listen() -> None:
    # "http" becomes "ws" and "https" becomes "wss".
    base = os.environ["SWITCH_URL"].replace("http", "ws", 1)
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