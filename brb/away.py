"""Away notices: `away until 11pm`, `away for 2h`, `away` and `back`.

Plain logic, so it's easy to test. The listener does the posting.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AWAY_PATH = ROOT / "data" / "away.json"

UNTIL = re.compile(r"until\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)
FOR = re.compile(r"for\s+(\d+)\s*(h|hr|hrs|hours?|m|mins?|minutes?)\b", re.I)


def team_zone() -> timezone:
    """The team's clock. IST unless BRB_UTC_OFFSET says otherwise, like -04:00."""
    offset = os.environ.get("BRB_UTC_OFFSET", "+05:30")
    sign = -1 if offset.startswith("-") else 1
    hours, minutes = offset.lstrip("+-").split(":")
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    return timezone(sign * delta, os.environ.get("BRB_ZONE_LABEL", "IST"))


def now() -> datetime:
    return datetime.now(team_zone())


def load_away() -> dict:
    if not AWAY_PATH.exists():
        return {}
    return json.loads(AWAY_PATH.read_text(encoding="utf-8"))


def save_away(away: dict) -> None:
    AWAY_PATH.parent.mkdir(exist_ok=True)
    AWAY_PATH.write_text(json.dumps(away, indent=2), encoding="utf-8")


def parse_until(text: str, current: datetime) -> datetime | None:
    """Return when the person is back, or None if no time was given."""
    if match := FOR.search(text):
        amount, unit = int(match.group(1)), match.group(2).lower()
        step = timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
        return current + step
    if match := UNTIL.search(text):
        hour, minute, half = int(match.group(1)), int(match.group(2) or 0), match.group(3)
        if half:
            if not 1 <= hour <= 12:
                raise ValueError
            hour = hour % 12 + (12 if half.lower() == "pm" else 0)
        end = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # "until 9am" said at night means tomorrow morning.
        return end if end > current else end + timedelta(days=1)
    if text.strip().lower() == "away":
        return None
    raise ValueError


def describe(until: str | None) -> str:
    if until is None:
        return "until they say they're back"
    end = datetime.fromisoformat(until).astimezone(team_zone())
    return "until " + end.strftime("%I:%M %p").lstrip("0") + f" {end.tzname()}"


def away_entry(username: str, current: datetime | None = None) -> dict | None:
    """The person's away record, or None. A record past its end time is cleared."""
    away = load_away()
    entry = away.get(username)
    if entry is None:
        return None
    if entry["until"] and datetime.fromisoformat(entry["until"]) <= (current or now()):
        del away[username]
        save_away(away)
        return None
    return entry


def set_back(username: str) -> bool:
    """Clear an away record. Return True if there was one."""
    away = load_away()
    if away.pop(username, None) is None:
        return False
    save_away(away)
    return True


def handle_away_command(
    username: str, command: str, team: dict, current: datetime | None = None
) -> tuple[str, str] | None:
    """Return (reply, change) for `away ...` or `back`, else None.

    change is "away", "back" or "" (nothing changed), so the listener knows
    whether to bring in or brief the Doppel.
    """
    words = command.split()
    if not words or words[0].lower() not in ("away", "back"):
        return None
    member = team.get(username)
    if member is None:
        return f"{username}, you aren't in brb/team.json yet.", ""

    if words[0].lower() == "back":
        if not set_back(username):
            return f"{member['name']}, you weren't marked away.", ""
        return f"Welcome back, {member['name']}! Your Doppel will catch you up.", "back"

    current = current or now()
    try:
        until = parse_until(command, current)
    except ValueError:
        return "Try `away until 11pm`, `away for 2h` or just `away`.", ""

    away = load_away()
    away[username] = {"until": until.isoformat() if until else None, "since": current.isoformat()}
    save_away(away)
    when = describe(away[username]["until"])
    return f"Got it, {member['name']} is away {when}. Their Doppel will stand in.", "away"


def mentioned_away_members(text: str, sender: str, team: dict) -> list[tuple[str, dict]]:
    """Away teammates someone tagged, as (username, member). Never the sender."""
    lowered = (text or "").lower()
    found = []
    for username, member in team.items():
        if username == sender:
            continue
        handles = (f"@{username.lower()}", f"@{member['name'].lower()}")
        if any(re.search(re.escape(handle) + r"\b", lowered) for handle in handles):
            if away_entry(username):
                found.append((username, member))
    return found


def ask_doppel_message(member: dict, sender_name: str, text: str, until: str | None) -> str:
    """Wake the Doppel for a teammate's question. It must start with the @mention."""
    return (
        f"@{member['doppel']} {sender_name} tagged {member['name']}, who is away "
        f"{describe(until)}. Their message: \"{text.strip()}\". Answer for "
        f"{member['name']} from your own folder and stay within your mandate."
    )


def back_message(member: dict) -> str:
    return (
        f"@{member['doppel']} {member['name']} is back. Give them a short catch-up: "
        "check every room you're in, then say what happened, what you agreed to, "
        "and what is waiting for their approval."
    )
