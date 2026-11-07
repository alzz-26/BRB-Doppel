import asyncio
import os
from datetime import datetime, timedelta

os.environ.setdefault("SWITCH_URL", "http://test")
import away
import listener
import meeting

TEAM = {
    "alzz_26": {"name": "Alisha", "folder": "Alisha", "doppel": "doppel.alisha"},
    "alzz_secondary": {"name": "Aliva", "folder": "Aliva", "doppel": "doppel.aliva"},
}
# 6:00 PM in the team's zone (IST by default).
SIX_PM = datetime(2026, 11, 7, 18, 0, tzinfo=away.team_zone())


def use_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(away, "AWAY_PATH", tmp_path / "data" / "away.json")


def test_parse_until_handles_clock_times_and_durations():
    assert away.parse_until("away until 11pm", SIX_PM) == SIX_PM.replace(hour=23)
    assert away.parse_until("away until 11:30 pm", SIX_PM) == SIX_PM.replace(hour=23, minute=30)
    assert away.parse_until("away until 21:15", SIX_PM) == SIX_PM.replace(hour=21, minute=15)
    assert away.parse_until("away for 2h", SIX_PM) == SIX_PM + timedelta(hours=2)
    assert away.parse_until("away for 45 minutes", SIX_PM) == SIX_PM + timedelta(minutes=45)
    assert away.parse_until("away", SIX_PM) is None


def test_a_time_already_passed_means_tomorrow():
    tomorrow_nine = SIX_PM.replace(hour=9) + timedelta(days=1)
    assert away.parse_until("away until 9am", SIX_PM) == tomorrow_nine


def test_away_then_back(tmp_path, monkeypatch):
    use_temp_file(tmp_path, monkeypatch)
    reply, change = away.handle_away_command("alzz_26", "away until 11pm", TEAM, SIX_PM)
    assert (reply, change) == ("Got it, Alisha is away until 11:00 PM IST. Their Doppel will stand in.", "away")
    assert away.away_entry("alzz_26", SIX_PM) is not None

    reply, change = away.handle_away_command("alzz_26", "back", TEAM)
    assert change == "back" and "Welcome back, Alisha" in reply
    assert away.away_entry("alzz_26", SIX_PM) is None
    assert away.handle_away_command("alzz_26", "back", TEAM)[1] == ""


def test_bad_time_and_strangers_change_nothing(tmp_path, monkeypatch):
    use_temp_file(tmp_path, monkeypatch)
    assert away.handle_away_command("alzz_26", "away until lunch", TEAM, SIX_PM)[1] == ""
    assert away.handle_away_command("alzz_26", "away until 13pm", TEAM, SIX_PM)[1] == ""
    assert away.handle_away_command("bob", "away", TEAM, SIX_PM)[1] == ""
    assert away.handle_away_command("alzz_26", "meeting", TEAM, SIX_PM) is None
    assert away.load_away() == {}


def test_away_ends_by_itself(tmp_path, monkeypatch):
    use_temp_file(tmp_path, monkeypatch)
    away.handle_away_command("alzz_26", "away for 1h", TEAM, SIX_PM)
    assert away.away_entry("alzz_26", SIX_PM + timedelta(minutes=59)) is not None
    assert away.away_entry("alzz_26", SIX_PM + timedelta(hours=2)) is None
    assert away.load_away() == {}


def test_only_tags_of_away_teammates_count(tmp_path, monkeypatch):
    use_temp_file(tmp_path, monkeypatch)
    away.handle_away_command("alzz_26", "away", TEAM, SIX_PM)
    found = away.mentioned_away_members("@alzz_26 can you send the hashcodes?", "alzz_secondary", TEAM)
    assert [username for username, _ in found] == ["alzz_26"]
    assert away.mentioned_away_members("@Alisha ping", "alzz_secondary", TEAM)
    # No @, someone who isn't away, or your own name: no Doppel.
    assert not away.mentioned_away_members("alzz_26 said hi", "alzz_secondary", TEAM)
    assert not away.mentioned_away_members("@alzz_secondary hi", "alzz_26", TEAM)
    assert not away.mentioned_away_members("@alzz_26 note to self", "alzz_26", TEAM)


def fake_switch(monkeypatch, tmp_path):
    posts, invites = [], []
    use_temp_file(tmp_path, monkeypatch)
    monkeypatch.setattr(listener, "post_message", lambda room, text: posts.append(text))
    monkeypatch.setattr(listener, "invite_agent", lambda room, agent: invites.append(agent))
    monkeypatch.setattr(listener, "load_team", lambda: TEAM)
    monkeypatch.setattr(listener, "handle_quiz", lambda *args: None)
    meeting.active_meetings.clear()
    return posts, invites


def message(sender, body, addressed):
    return {"room_id": "r1", "payload": {"sender_name": sender, "body": body, "addressed": addressed}}


def test_tagging_an_away_teammate_wakes_their_doppel(monkeypatch, tmp_path):
    posts, invites = fake_switch(monkeypatch, tmp_path)

    async def scenario():
        await listener.handle_message(message("alzz_26", "<@&1> away for 2h", True))
        await listener.handle_message(message("alzz_secondary", "@alzz_26 send the hashcodes?", False))

    asyncio.run(scenario())
    assert posts[0].startswith("Got it, Alisha is away until")
    assert invites == ["doppel.alisha", "doppel.alisha"]
    assert posts[-1].startswith("@doppel.alisha Aliva tagged Alisha, who is away")
    assert "send the hashcodes?" in posts[-1]


def test_back_brings_a_catch_up_and_here_also_counts(monkeypatch, tmp_path):
    posts, invites = fake_switch(monkeypatch, tmp_path)

    async def scenario():
        await listener.handle_message(message("alzz_26", "<@&1> away", True))
        await listener.handle_message(message("alzz_26", "<@&1> back", True))
        await listener.handle_message(message("alzz_26", "<@&1> away", True))
        await listener.handle_message(message("alzz_26", "<@&1> meeting 1", True))
        await listener.handle_message(message("alzz_26", "here", False))
        await asyncio.gather(*list(listener.background_tasks))

    asyncio.run(scenario())
    assert any(post.startswith("Welcome back, Alisha") for post in posts)
    assert any(post.startswith("@doppel.alisha Alisha is back.") for post in posts)
    # Saying "here" at a roll call clears the away note too.
    assert away.load_away() == {}


def test_brb_ignores_its_own_posts(monkeypatch, tmp_path):
    posts, invites = fake_switch(monkeypatch, tmp_path)
    away.handle_away_command("alzz_26", "away", TEAM)

    asyncio.run(listener.handle_message(message("brb", "@alzz_26 is away", False)))
    assert posts == [] and invites == []
