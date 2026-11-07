import os

import pytest

os.environ.setdefault("SWITCH_URL", "http://test")


@pytest.fixture(autouse=True)
def no_room_documents(monkeypatch):
    """Tests never reach a real Switch server to write ledger documents."""
    import listener

    async def skip():
        return None

    monkeypatch.setattr(listener, "sync_ledger_docs", skip)
