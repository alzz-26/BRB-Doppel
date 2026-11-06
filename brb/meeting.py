"""Roll call for a meeting. Plain logic, so it's easy to test."""

DEFAULT_SECONDS = 60

# room_id -> the sender names who said "here". In memory is fine here:
# a roll call lasts seconds, so it doesn't need to survive a restart.
active_meetings: dict[str, set[str]] = {}


def parse_meeting_command(command: str) -> int | None:
    """Return the roll-call length for "meeting" or "meeting 30", else None."""
    words = command.split()
    if not words or words[0] != "meeting" or len(words) > 2:
        return None
    if len(words) == 1:
        return DEFAULT_SECONDS
    return int(words[1]) if words[1].isdigit() and int(words[1]) > 0 else None


def start_meeting(room_id: str) -> bool:
    """Open a roll call. Return False if one is already running in this room."""
    if room_id in active_meetings:
        return False
    active_meetings[room_id] = set()
    return True


def mark_present(room_id: str, sender_name: str, command: str) -> bool:
    """Record "here" during a roll call. Return True if it was recorded."""
    if room_id not in active_meetings or command != "here":
        return False
    active_meetings[room_id].add(sender_name)
    return True


def finish_meeting(room_id: str, team: dict) -> tuple[list[dict], list[dict]]:
    """Close the roll call and return (present members, absent members)."""
    responded = active_meetings.pop(room_id, set())
    present = [member for key, member in team.items() if key in responded]
    absent = [member for key, member in team.items() if key not in responded]
    return present, absent


def stand_in_message(member: dict) -> str:
    """The message that wakes a Doppel. It must start with the @mention."""
    return (
        f"@{member['doppel']} {member['name']} is away from this meeting, so please "
        f"stand in. Introduce yourself as {member['name']}'s Doppel in one line. "
        "Answer from your own folder and stay within your mandate."
    )
