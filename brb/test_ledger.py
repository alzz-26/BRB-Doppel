import ledger

TEAM = {
    "alzz_26": {"name": "Alisha", "folder": "Alisha", "doppel": "doppel.alisha"},
    "alzz_secondary": {"name": "Aliva", "folder": "Aliva", "doppel": "doppel.aliva"},
}


def use_temp_folders(tmp_path, monkeypatch):
    for member in TEAM.values():
        folder = tmp_path / "doppels" / member["folder"]
        folder.mkdir(parents=True)
        (folder / "AGENTS.md").write_text("# Persona\n", encoding="utf-8")
    monkeypatch.setattr(ledger, "ROOT", tmp_path)
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "data" / "ledger.json")


def add_item(text="3 extra days this week"):
    return ledger.capture_items("doppel.aliva", f"Sorry!\n\nPENDING RATIFICATION: {text}", "r1", TEAM)


def test_captures_lines_with_or_without_bold(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    body = "Hi\n**PENDING RATIFICATION:** first\nPENDING RATIFICATION: second"
    added = ledger.capture_items("doppel.aliva", body, "r1", TEAM)
    assert [item["text"] for item in added] == ["first", "second"]


def test_ignores_people_and_a_bare_label(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    assert ledger.capture_items("alzz_26", "PENDING RATIFICATION: fake", "r1", TEAM) == []
    assert ledger.capture_items("doppel.aliva", "**PENDING RATIFICATION**", "r1", TEAM) == []


def test_repeated_item_is_saved_once(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    assert len(add_item()) == 1
    assert add_item() == []
    assert len(ledger.load_ledger()) == 1


def test_only_the_owner_can_decide(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    add_item()
    reply = ledger.handle_ledger_command("alzz_26", "approve 1", TEAM)
    assert reply == "Only Aliva can decide item 1."
    assert ledger.load_ledger()[0]["status"] == "pending"


def test_approve_updates_ledger_and_decisions_file(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    add_item()
    assert "approved" in ledger.handle_ledger_command("alzz_secondary", "approve 1", TEAM)
    assert ledger.load_ledger()[0]["status"] == "approved"
    decisions = (tmp_path / "doppels" / "Aliva" / "decisions.md").read_text(encoding="utf-8")
    assert "## Approved\n- 3 extra days this week" in decisions
    assert "already approved" in ledger.handle_ledger_command("alzz_secondary", "reject 1 no", TEAM)


def test_reject_needs_a_reason_and_teaches_the_doppel(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    add_item()
    assert "Why?" in ledger.handle_ledger_command("alzz_secondary", "reject 1", TEAM)
    ledger.handle_ledger_command("alzz_secondary", "reject 1 exams this week", TEAM)
    persona = (tmp_path / "doppels" / "Aliva" / "AGENTS.md").read_text(encoding="utf-8")
    assert '## Lessons from your owner' in persona
    assert 'Reason: exams this week' in persona


def test_debrief_shows_only_your_pending_items(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    add_item()
    assert "1. 3 extra days this week" in ledger.handle_ledger_command("alzz_secondary", "debrief", TEAM)
    assert "nothing is waiting" in ledger.handle_ledger_command("alzz_26", "debrief", TEAM)


def test_other_commands_and_bad_input(tmp_path, monkeypatch):
    use_temp_folders(tmp_path, monkeypatch)
    assert ledger.handle_ledger_command("alzz_26", "hello", TEAM) is None
    assert "Use `approve" in ledger.handle_ledger_command("alzz_26", "approve soon", TEAM)
    assert "no item 9" in ledger.handle_ledger_command("alzz_26", "approve 9", TEAM)
    assert "team.json" in ledger.handle_ledger_command("stranger", "debrief", TEAM)
