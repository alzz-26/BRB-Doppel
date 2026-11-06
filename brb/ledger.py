"""The approvals ledger: one record of what each Doppel put up for approval."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "data" / "ledger.json"

# Matches "PENDING RATIFICATION: 3 extra days", with or without ** around the label.
PENDING_LINE = re.compile(r"^[\s*_]*PENDING RATIFICATION[\s*_]*:[\s*_]*(.+?)[\s*_]*$", re.I | re.M)


def load_ledger() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def save_ledger(items: list[dict]) -> None:
    LEDGER_PATH.parent.mkdir(exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def owner_of_doppel(doppel_name: str, team: dict) -> tuple[str, dict] | None:
    """Return (username, member) for a Doppel, or None if the sender isn't one."""
    for username, member in team.items():
        if member.get("doppel") == doppel_name:
            return username, member
    return None


def capture_items(doppel_name: str, body: str, room_id: str, team: dict) -> list[dict]:
    """Save each PENDING RATIFICATION line from a Doppel and return the new items."""
    found = owner_of_doppel(doppel_name, team)
    if found is None:
        return []
    username, member = found

    items = load_ledger()
    added = []
    for text in PENDING_LINE.findall(body or ""):
        repeat = any(
            item["owner"] == username
            and item["status"] == "pending"
            and item["text"].lower() == text.lower()
            for item in items
        )
        if repeat:
            continue
        item = {
            "id": len(items) + 1,
            "owner": username,
            "name": member["name"],
            "folder": member["folder"],
            "text": text,
            "room_id": room_id,
            "status": "pending",
            "created_at": now(),
            "decided_at": None,
            "reason": None,
        }
        items.append(item)
        added.append(item)

    if added:
        save_ledger(items)
        write_decisions(username, member, items)
    return added


def write_decisions(username: str, member: dict, items: list[dict]) -> None:
    """Give the Doppel a read-only copy. status.md stays the owner's own file."""
    lines = [f"# Decisions for {member['name']}", ""]
    for status in ("pending", "approved", "rejected"):
        lines.append(f"## {status.title()}")
        mine = [i for i in items if i["owner"] == username and i["status"] == status]
        for item in mine or [None]:
            if item is None:
                lines.append("- None")
            elif item["reason"]:
                lines.append(f"- {item['text']} (reason: {item['reason']})")
            else:
                lines.append(f"- {item['text']}")
        lines.append("")
    path = ROOT / "doppels" / member["folder"] / "decisions.md"
    path.write_text("\n".join(lines), encoding="utf-8")


def add_lesson(member: dict, text: str, reason: str) -> None:
    """Teach the Doppel from a rejection by adding to its persona."""
    path = ROOT / "doppels" / member["folder"] / "AGENTS.md"
    persona = path.read_text(encoding="utf-8").rstrip()
    if "## Lessons from your owner" not in persona:
        persona += "\n\n## Lessons from your owner\n"
    persona += f"\n- {member['name']} rejected \"{text}\". Reason: {reason}"
    path.write_text(persona + "\n", encoding="utf-8")


def debrief(username: str, member: dict) -> str:
    pending = [i for i in load_ledger() if i["owner"] == username and i["status"] == "pending"]
    if not pending:
        return f"{member['name']}, nothing is waiting for your approval."
    lines = [f"**{member['name']}, {len(pending)} item(s) need your decision:**"]
    lines += [f"{item['id']}. {item['text']}" for item in pending]
    first = pending[0]["id"]
    lines.append(f"\nTag BRB and reply `approve {first}` or `reject {first} your reason`.")
    return "\n".join(lines)


def decide(username: str, member: dict, command: str) -> str:
    """Handle "approve 1" or "reject 1 reason". The owner check happens here."""
    match = re.fullmatch(r"(approve|reject)\s+(\d+)(?:\s+(.+))?", command, re.I | re.S)
    action, item_id, reason = match.group(1).lower(), int(match.group(2)), match.group(3)

    items = load_ledger()
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        return f"There's no item {item_id}."
    if item["owner"] != username:
        return f"Only {item['name']} can decide item {item_id}."
    if item["status"] != "pending":
        return f"Item {item_id} is already {item['status']}."
    if action == "reject" and not reason:
        return f"Why? Reply `@brb reject {item_id} your reason`, so your Doppel can learn."

    item["status"] = "approved" if action == "approve" else "rejected"
    item["reason"] = reason
    item["decided_at"] = now()
    save_ledger(items)
    write_decisions(username, member, items)

    if action == "approve":
        return f"Item {item_id} approved: {item['text']}"
    add_lesson(member, item["text"], reason)
    return f"Item {item_id} rejected. Your Doppel has learned from this."


def handle_ledger_command(username: str, command: str, team: dict) -> str | None:
    """Return BRB's reply for debrief, approve or reject, else None."""
    words = command.split()
    if not words or words[0].lower() not in ("debrief", "approve", "reject"):
        return None
    member = team.get(username)
    if member is None:
        return f"{username}, you aren't in brb/team.json yet."
    if words[0].lower() == "debrief":
        return debrief(username, member)
    if len(words) < 2 or not words[1].isdigit():
        return "Use `approve 1` or `reject 1 your reason`."
    return decide(username, member, command)
