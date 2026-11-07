"""Mirror the approvals ledger into a Switch room document, one per room.

Switch only writes a room document for a caller tied to exactly one room, and
BRB's main connection listens to every room. So for each write BRB opens a
short connection that claims just that room, writes, and closes it.
"""

import asyncio
import json
import os
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

from away import now
from ledger import load_ledger

ROOT = Path(__file__).resolve().parent.parent
DOCS_PATH = ROOT / "data" / "room_docs.json"
DOC_NAME = "brb-approvals-ledger"
STATUS = {"pending": "Waiting", "approved": "Approved", "rejected": "Rejected"}
# One sync at a time, so two quick changes never create two documents.
sync_lock = asyncio.Lock()


def render_ledger(items: list[dict], room_id: str) -> str:
    """The document text: every request raised in this room, newest first."""
    mine = [item for item in items if item["room_id"] == room_id]
    lines = [
        "# BRB approvals ledger",
        "",
        f"Updated {now().strftime('%d %b, %I:%M %p %Z')}. Only BRB edits this.",
        "To decide, tag BRB: `approve 2` or `reject 2 your reason`.",
        "",
    ]
    if not mine:
        return "\n".join(lines + ["Nothing has been raised in this room yet.", ""])
    lines += ["| # | For | Request | Status | Reason |", "|---|---|---|---|---|"]
    for item in sorted(mine, key=lambda i: i["id"], reverse=True):
        cells = [str(item["id"]), item["name"], item["text"], STATUS[item["status"]], item["reason"] or ""]
        lines.append("| " + " | ".join(cell.replace("|", "/") for cell in cells) + " |")
    return "\n".join(lines + [""])


def load_doc_ids() -> dict:
    if not DOCS_PATH.exists():
        return {}
    return json.loads(DOCS_PATH.read_text(encoding="utf-8"))


def save_doc_ids(ids: dict) -> None:
    DOCS_PATH.parent.mkdir(exist_ok=True)
    DOCS_PATH.write_text(json.dumps(ids, indent=2), encoding="utf-8")


def call_op(connection_id: str, name: str, body: dict) -> httpx.Response:
    agent = os.environ["BRB_AGENT_ID"]
    return httpx.post(
        f"{os.environ['SWITCH_URL']}/agents/{agent}/ops/{name}",
        headers={
            "Authorization": f"Bearer {os.environ['BRB_API_KEY']}",
            "X-Switch-Connection-Id": connection_id,
        },
        json=body,
        timeout=30,
    )


def write_doc(connection_id: str, doc_id: str | None, content: str) -> str:
    """Update the room's ledger document, or create it. Return its id."""
    if doc_id:
        response = call_op(connection_id, "update_room_document", {"document_id": doc_id, "content": content})
        if response.is_success:
            return doc_id
        # Someone deleted it from the room. Make a new one.
    response = call_op(
        connection_id,
        "create_room_document",
        {
            "name": DOC_NAME,
            "description": "Requests Doppels raised here and what each owner decided.",
            "instructions": "BRB's record of approvals. Read it, but never edit it.",
            "content": content,
        },
    )
    response.raise_for_status()
    return response.json()["result"]["document_id"]


async def sync_room(room_id: str, doc_id: str | None, content: str) -> str:
    """Claim just this room for a moment, write the document, then let go."""
    connection_id = f"brb-ledger-{room_id}"
    base = os.environ["SWITCH_URL"].replace("http", "ws", 1)
    url = (
        f"{base}/agents/{os.environ['BRB_AGENT_ID']}/connection/ws"
        f"?connection_id={connection_id}&scope=single&rooms={room_id}"
    )
    headers = {"Authorization": f"Bearer {os.environ['BRB_API_KEY']}"}
    async with connect(url, additional_headers=headers) as socket:
        # The first frame confirms the connection is open and holds the room.
        await asyncio.wait_for(socket.recv(), timeout=10)
        return await asyncio.to_thread(write_doc, connection_id, doc_id, content)


async def sync_ledger_docs() -> None:
    """Refresh the ledger document in every room that has ledger items."""
    async with sync_lock:
        items = load_ledger()
        ids = load_doc_ids()
        for room_id in sorted({item["room_id"] for item in items}):
            try:
                ids[room_id] = await sync_room(room_id, ids.get(room_id), render_ledger(items, room_id))
            except Exception as error:  # The ledger file stays the record either way.
                print(f"Ledger document for {room_id}: {error}")
        save_doc_ids(ids)
