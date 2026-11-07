import asyncio

import listener
import meeting
import onboarding

TEAM = {"alzz_secondary": {"name": "Aliva", "folder": "Aliva", "doppel": "doppel.aliva"}}


def test_pick_bridge_prefers_the_default_that_can_make_channels():
    bridges = [
        {"id": "a", "status": "active", "can_create_channels": False, "is_default": True},
        {"id": "b", "status": "active", "can_create_channels": True, "is_default": False},
        {"id": "c", "status": "active", "can_create_channels": True, "is_default": True},
    ]
    assert onboarding.pick_bridge(bridges) == "c"
    assert onboarding.pick_bridge(bridges[:2]) == "b"
    assert onboarding.pick_bridge([{"id": "x", "status": "error", "can_create_channels": True}]) is None


def test_private_room_is_made_once_and_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "ONBOARDING_PATH", tmp_path / "onboarding.json")
    calls = []

    def fake_op(name, body):
        calls.append((name, body))
        if name == "list_bridges":
            return [{"id": "discord", "status": "active", "can_create_channels": True}]
        return {"id": "private-1"}

    monkeypatch.setattr(onboarding, "call_op", fake_op)
    assert onboarding.open_private_room("alzz_secondary", "Aliva", "team-room") == "private-1"
    assert onboarding.open_private_room("alzz_secondary", "Aliva", "other-room") == "private-1"
    create = [body for name, body in calls if name == "create_room"]
    assert len(create) == 1
    assert create[0]["channel_type"] == "direct" and create[0]["user_names"] == ["alzz_secondary"]
    assert onboarding.origin_of("private-1") == "other-room"
    assert onboarding.origin_of("team-room") is None


def test_onboard_me_starts_the_quiz_privately_and_shares_only_the_card(tmp_path, monkeypatch):
    posts = []
    monkeypatch.setattr(onboarding, "ONBOARDING_PATH", tmp_path / "onboarding.json")
    monkeypatch.setattr(listener, "post_message", lambda room, text: posts.append((room, text)))
    monkeypatch.setattr(listener, "load_team", lambda: TEAM)

    def fake_open(username, real_name, origin):
        onboarding.save_rooms({username: {"room_id": "private-1", "origin": origin}})
        return "private-1"

    monkeypatch.setattr(listener, "open_private_room", fake_open)
    def fake_quiz(sender_id, name, text, addressed):
        if text == "start quiz":
            return "Question 1 of 10"
        if text == "a":
            return "**Welcome Aliva!** Aliva is The Midnight Shipper."
        return None

    monkeypatch.setattr(listener, "handle_quiz", fake_quiz)
    meeting.active_meetings.clear()

    def message(room, body, addressed):
        return {"room_id": room, "payload": {"sender_name": "alzz_secondary", "sender": "u2", "body": body, "addressed": addressed}}

    async def scenario():
        await listener.handle_message(message("team-room", "<@&1> onboard me", True))
        await listener.handle_message(message("private-1", "a", False))

    asyncio.run(scenario())
    assert posts[0] == ("team-room", "Opening a private room for you, Aliva. Look for it in your channel list.")
    assert posts[1][0] == "private-1" and "Question 1 of 10" in posts[1][1]
    # The finished card goes to the private room and back to the team room.
    assert ("private-1", "**Welcome Aliva!** Aliva is The Midnight Shipper.") in posts
    assert ("team-room", "**Welcome Aliva!** Aliva is The Midnight Shipper.") in posts


def test_a_failed_room_falls_back_to_the_public_quiz(tmp_path, monkeypatch):
    posts = []
    monkeypatch.setattr(onboarding, "ONBOARDING_PATH", tmp_path / "onboarding.json")
    monkeypatch.setattr(listener, "post_message", lambda room, text: posts.append((room, text)))

    def broken(*args):
        raise RuntimeError("no bridge")

    monkeypatch.setattr(listener, "open_private_room", broken)
    asyncio.run(listener.start_onboarding("u2", "alzz_secondary", "Aliva", "team-room"))
    assert posts == [("team-room", "I couldn't open a private room, Aliva. Say `start quiz` here instead.")]
