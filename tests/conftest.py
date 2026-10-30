import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def engine():
    from app.database import get_engine, ping
    ok, msg = ping()
    if not ok:
        pytest.skip(f"Database not reachable: {msg}")
    return get_engine()


def pytest_report_header(config):
    return f"DB_HOST={os.getenv('DB_HOST', 'localhost')}  LLM_PROVIDER={os.getenv('LLM_PROVIDER', '-')}"
