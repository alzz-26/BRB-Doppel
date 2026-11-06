import meeting

TEAM = {
    "alzz_26": {"name": "Alisha", "folder": "Alisha", "doppel": "doppel.alisha"},
    "alzz_secondary": {"name": "Aliva", "folder": "Aliva", "doppel": "doppel.aliva"},
}


def setup_function():
    meeting.active_meetings.clear()


def test_parse_meeting_command():
    assert meeting.parse_meeting_command("meeting") == 60
    assert meeting.parse_meeting_command("meeting 20") == 20
    assert meeting.parse_meeting_command("meeting soon") is None
    assert meeting.parse_meeting_command("meeting 0") is None
    assert meeting.parse_meeting_command("hello") is None
    assert meeting.parse_meeting_command("") is None


def test_only_one_roll_call_per_room():
    assert meeting.start_meeting("r1") is True
    assert meeting.start_meeting("r1") is False
    assert meeting.start_meeting("r2") is True


def test_people_who_say_here_are_present():
    meeting.start_meeting("r1")
    assert meeting.mark_present("r1", "alzz_26", "here") is True
    present, absent = meeting.finish_meeting("r1", TEAM)
    assert [member["name"] for member in present] == ["Alisha"]
    assert [member["name"] for member in absent] == ["Aliva"]
    assert "r1" not in meeting.active_meetings


def test_here_is_ignored_without_a_roll_call():
    assert meeting.mark_present("r1", "alzz_26", "here") is False
    meeting.start_meeting("r1")
    assert meeting.mark_present("r1", "alzz_26", "here i am") is False


def test_stand_in_message_starts_with_the_mention():
    assert meeting.stand_in_message(TEAM["alzz_secondary"]).startswith("@doppel.aliva ")
