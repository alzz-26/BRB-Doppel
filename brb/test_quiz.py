import json
import subprocess

import persona_writer
import quiz_flow
from quiz import QUESTIONS, build_mandate, choose_archetype, clean_text, parse_answer


def use_temp_folders(tmp_path, monkeypatch):
    team = tmp_path / "team.json"
    team.write_text(json.dumps({"Aliva": {"name": "Aliva", "folder": "Aliva"}}))
    (tmp_path / "doppels" / "Aliva").mkdir(parents=True)
    monkeypatch.setattr(quiz_flow, "ROOT", tmp_path)
    monkeypatch.setattr(quiz_flow, "STATE_PATH", tmp_path / "data" / "state.json")
    monkeypatch.setattr(quiz_flow, "TEAM_PATH", team)
    # Never call the real Claude in tests: it's slow and uses your limit.
    monkeypatch.setattr(quiz_flow, "write_style", lambda *args: "Test style.")


def test_writer_falls_back_when_claude_fails(tmp_path, monkeypatch):
    def broken_run(*args, **kwargs):
        raise subprocess.TimeoutExpired("claude", 60)

    monkeypatch.setattr(persona_writer.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(persona_writer.subprocess, "run", broken_run)
    assert persona_writer.write_style("A", "T", "Fallback", ["x"], tmp_path) == "Fallback"


def test_parse_answer_accepts_only_a_single_letter():
    assert parse_answer("a") == "A"
    assert parse_answer("<@&123> B.") == "B"
    assert parse_answer("@brb d") == "D"
    assert parse_answer("about") is None
    assert parse_answer("E") is None
    assert parse_answer(None) is None


def test_clean_text_removes_mentions():
    assert clean_text("<@&156> start quiz").lower() == "start quiz"


def test_majority_archetype_and_mandate():
    answers = ["A", "A", "A", "B", "C", "D", "A", "B", "C", "D"]
    assert choose_archetype(answers) == "shipper"
    assert build_mandate(answers)["extra_work"] == "None"
    assert build_mandate(answers)["sharing"] == "Anything in its folder"


def test_full_quiz_writes_persona_and_clears_state(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    assert "Question 1" in quiz_flow.handle_quiz("u1", "Aliva", "<@&1> start quiz", True)
    for index in range(len(QUESTIONS) - 1):
        assert f"Question {index + 2}" in quiz_flow.handle_quiz("u1", "Aliva", "a", False)
    card = quiz_flow.handle_quiz("u1", "Aliva", "a", False)
    assert "The Midnight Shipper" in card
    persona = (tmp_path / "doppels" / "Aliva" / "AGENTS.md").read_text(encoding="utf-8")
    assert "PENDING RATIFICATION: what was asked" in persona
    assert "Your owner's Discord username is `Aliva`" in persona
    assert "- `Aliva` is Aliva" in persona
    assert quiz_flow.load_state() == {}


def test_other_messages_are_ignored(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    assert quiz_flow.handle_quiz("u1", "Aliva", "hello", False) is None
    quiz_flow.handle_quiz("u1", "Aliva", "start quiz", True)
    assert quiz_flow.handle_quiz("u1", "Aliva", "just chatting", False) is None
    assert "Please reply" in quiz_flow.handle_quiz("u1", "Aliva", "hmm", True)
    assert quiz_flow.handle_quiz("u2", "Bob", "A", False) is None
    assert "cancelled" in quiz_flow.handle_quiz("u1", "Aliva", "cancel quiz", True)


def test_unknown_person_cannot_start(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    assert "team.json" in quiz_flow.handle_quiz("u9", "Stranger", "start quiz", True)

def test_quit_works_with_or_without_a_tag(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    for message, addressed in [("quit", False), ("<@&1> stop", True), ("cancel quiz", False)]:
        quiz_flow.handle_quiz("u1", "Aliva", "start quiz", True)
        assert "cancelled" in quiz_flow.handle_quiz("u1", "Aliva", message, addressed)
        assert quiz_flow.load_state() == {}