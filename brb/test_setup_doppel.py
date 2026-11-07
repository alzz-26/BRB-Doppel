import json

import pytest

import doppel_files
import setup_doppel


def use_temp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_doppel, "ROOT", tmp_path)
    monkeypatch.setattr(setup_doppel, "TEAM_PATH", tmp_path / "team.json")


def test_claude_gets_a_pointer_and_its_safety_settings(tmp_path, monkeypatch):
    use_temp_root(tmp_path, monkeypatch)
    setup_doppel.setup_doppel("alzz_26", "Alisha", "claude", "doppel.alisha", "Alisha")
    folder = tmp_path / "doppels" / "Alisha"
    assert "## Scope" in (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert (folder / "CLAUDE.md").read_text(encoding="utf-8").endswith("@AGENTS.md\n")
    settings = json.loads((folder / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings == {"disableClaudeAiConnectors": True, "autoMemoryEnabled": False}
    team = json.loads((tmp_path / "team.json").read_text(encoding="utf-8"))
    assert team["alzz_26"] == {"name": "Alisha", "folder": "Alisha", "doppel": "doppel.alisha"}


def test_other_providers_need_only_agents_md(tmp_path, monkeypatch):
    use_temp_root(tmp_path, monkeypatch)
    setup_doppel.setup_doppel("sam_1", "Sam", "codex", "doppel.sam", "Sam")
    names = sorted(p.name for p in (tmp_path / "doppels" / "Sam").iterdir())
    assert names == ["AGENTS.md", "status.md"]


def test_running_again_keeps_a_persona_and_status(tmp_path, monkeypatch):
    use_temp_root(tmp_path, monkeypatch)
    setup_doppel.setup_doppel("alzz_26", "Alisha", "claude", "doppel.alisha", "Alisha")
    folder = tmp_path / "doppels" / "Alisha"
    persona = "quiz persona\n\n## Scope\n- rules"
    (folder / "AGENTS.md").write_text(persona, encoding="utf-8")
    (folder / "status.md").write_text("busy", encoding="utf-8")
    setup_doppel.setup_doppel("alzz_26", "Alisha", "claude", "doppel.alisha", "Alisha")
    assert (folder / "AGENTS.md").read_text(encoding="utf-8") == persona
    assert (folder / "status.md").read_text(encoding="utf-8") == "busy"


def test_an_old_persona_gets_the_scope_rules(tmp_path, monkeypatch):
    use_temp_root(tmp_path, monkeypatch)
    folder = tmp_path / "doppels" / "Aliva"
    folder.mkdir(parents=True)
    (folder / "AGENTS.md").write_text("# Persona for Aliva's Doppel\n", encoding="utf-8")
    setup_doppel.setup_doppel("alzz_secondary", "Aliva", "claude", "doppel.aliva", "Aliva")
    persona = (folder / "AGENTS.md").read_text(encoding="utf-8")
    assert persona.startswith("# Persona for Aliva's Doppel") and "Never claim to be Aliva" in persona


def test_files_use_unix_line_endings(tmp_path, monkeypatch):
    use_temp_root(tmp_path, monkeypatch)
    setup_doppel.setup_doppel("alzz_26", "Alisha", "claude", "doppel.alisha", "Alisha")
    for path in (tmp_path / "doppels" / "Alisha").rglob("*"):
        if path.is_file():
            assert b"\r\n" not in path.read_bytes(), path


def test_unknown_provider_is_refused():
    with pytest.raises(ValueError):
        doppel_files.provider_files("notepad", "doppel.x")


def test_setup_reads_a_local_console_server(tmp_path):
    import setup

    (tmp_path / "switch-core.env").write_text(
        "SERVER_HOST=127.0.0.1\nSERVER_PORT=51972\nAGENT_REGISTRATION_TOKEN=abc123\n", encoding="utf-8"
    )
    assert setup.local_console_settings(tmp_path) == {
        "SWITCH_URL": "http://127.0.0.1:51972",
        "SWITCH_REGISTRATION_KEY": "abc123",
    }
    assert setup.local_console_settings(tmp_path / "missing") == {}
