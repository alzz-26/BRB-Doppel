import asyncio
import os

os.environ.setdefault("SWITCH_URL", "http://test")
import ledger
import listener
import meeting


def test_roll_call_invites_only_absent_doppels(monkeypatch):
    posts, invites = [], []
    team = {
        "alzz_26": {"name": "Alisha", "folder": "Alisha", "doppel": "doppel.alisha"},
        "alzz_secondary": {"name": "Aliva", "folder": "Aliva", "doppel": "doppel.aliva"},
    }
    monkeypatch.setattr(listener, "post_message", lambda room, text: posts.append(text))
    monkeypatch.setattr(listener, "invite_agent", lambda room, agent: invites.append(agent))
    monkeypatch.setattr(listener, "load_team", lambda: team)
    monkeypatch.setattr(listener, "handle_quiz", lambda *args: None)
    meeting.active_meetings.clear()

    def message(sender, body, addressed):
        return {"room_id": "r1", "payload": {"sender_name": sender, "body": body, "addressed": addressed}}

    async def scenario():
        await listener.handle_message(message("alzz_26", "<@&1> meeting 1", True))
        await listener.handle_message(message("alzz_26", "here", False))
        await asyncio.gather(*list(listener.background_tasks))

    asyncio.run(scenario())
    assert invites == ["doppel.aliva"]
    assert posts[0].startswith("Meeting starting")
    assert any("Present: Alisha" in post for post in posts)
    assert posts[-1].startswith("@doppel.aliva ")


def test_doppel_line_is_logged_and_owner_can_approve(monkeypatch, tmp_path):
    posts = []
    team = {"alzz_secondary": {"name": "Aliva", "folder": "Aliva", "doppel": "doppel.aliva"}}
    (tmp_path / "doppels" / "Aliva").mkdir(parents=True)
    monkeypatch.setattr(ledger, "ROOT", tmp_path)
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "data" / "ledger.json")
    monkeypatch.setattr(listener, "post_message", lambda room, text: posts.append(text))
    monkeypatch.setattr(listener, "load_team", lambda: team)
    monkeypatch.setattr(listener, "handle_quiz", lambda *args: None)

    def message(sender, body, addressed):
        return {"room_id": "r1", "payload": {"sender_name": sender, "body": body, "addressed": addressed}}

    async def scenario():
        await listener.handle_message(message("doppel.aliva", "PENDING RATIFICATION: 3 days", False))
        await listener.handle_message(message("alzz_secondary", "<@&1> Debrief", True))
        await listener.handle_message(message("alzz_secondary", "<@&1> approve 1", True))

    asyncio.run(scenario())
    assert posts[0] == "Logged #1 for Aliva's approval."
    assert "1. 3 days" in posts[1]
    assert posts[2] == "Item 1 approved: 3 days"
