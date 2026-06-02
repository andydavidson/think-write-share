import os
import sys

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear per-session rate-limiter state between tests."""
    import app as app_module
    app_module._rl_sessions.clear()
    yield
    app_module._rl_sessions.clear()


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture()
def client(db_path, monkeypatch):
    import db as db_module
    # Patch DB_PATH before the TestClient lifespan starts so init_db() uses
    # the temp file.
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    from app import app as fastapi_app
    with TestClient(fastapi_app) as c:
        yield c
