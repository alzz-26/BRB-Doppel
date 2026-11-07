import asyncio

import httpx

import room_docs

ITEMS = [
    {"id": 1, "name": "Alisha", "text": "landing page | 1 day", "room_id": "r1", "status": "rejected", "reason": "not my task"},
    {"id": 2, "name": "Aliva", "text": "landing page, 1 day", "room_id": "r1", "status": "pending", "reason": None},
    {"id": 3, "name": "Aliva", "text": "elsewhere", "room_id": "r2", "status": "approved", "reason": None},
]


def test_render_shows_only_this_room_newest_first():
    text = room_docs.render_ledger(ITEMS, "r1")
    rows = [line for line in text.splitlines() if line.startswith("| ") and line[2].isdigit()]
    assert rows == [
        "| 2 | Aliva | landing page, 1 day | Waiting |  |",
        "| 1 | Alisha | landing page / 1 day | Rejected | not my task |",
    ]
    assert "elsewhere" not in text
    assert "Nothing has been raised" in room_docs.render_ledger(ITEMS, "r9")


def test_sync_writes_each_room_and_remembers_the_document(tmp_path, monkeypatch):
    monkeypatch.setattr(room_docs, "DOCS_PATH", tmp_path / "docs.json")
    monkeypatch.setattr(room_docs, "load_ledger", lambda: ITEMS)
    calls = []

    async def fake_sync(room_id, doc_id, content):
        calls.append((room_id, doc_id))
        return f"doc-{room_id}"

    monkeypatch.setattr(room_docs, "sync_room", fake_sync)
    asyncio.run(room_docs.sync_ledger_docs())
    asyncio.run(room_docs.sync_ledger_docs())
    assert calls == [("r1", None), ("r2", None), ("r1", "doc-r1"), ("r2", "doc-r2")]


def test_a_failed_room_does_not_stop_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(room_docs, "DOCS_PATH", tmp_path / "docs.json")
    monkeypatch.setattr(room_docs, "load_ledger", lambda: ITEMS)

    async def flaky_sync(room_id, doc_id, content):
        if room_id == "r1":
            raise OSError("switch is down")
        return "doc-r2"

    monkeypatch.setattr(room_docs, "sync_room", flaky_sync)
    asyncio.run(room_docs.sync_ledger_docs())
    assert room_docs.load_doc_ids() == {"r2": "doc-r2"}


def test_a_deleted_document_is_created_again(monkeypatch):
    sent = []

    def fake_op(connection_id, name, body):
        sent.append(name)
        request = httpx.Request("POST", "http://test")
        if name == "update_room_document":
            return httpx.Response(404, request=request)
        return httpx.Response(200, json={"result": {"document_id": "new"}}, request=request)

    monkeypatch.setattr(room_docs, "call_op", fake_op)
    assert room_docs.write_doc("c1", "old", "text") == "new"
    assert sent == ["update_room_document", "create_room_document"]
