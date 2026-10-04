import pytest

from app.db.connection import get_db_connection
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.adapters import MockJobSourceAdapter


def test_mock_adapter_not_allowed_in_production_scan():
    conn = get_db_connection()
    with pytest.raises(ValueError) as excinfo:
        FreshJobScanner(conn=conn, adapters=[MockJobSourceAdapter()], allow_mock=False)
    assert "MockJobSourceAdapter cannot be used in production scans" in str(excinfo.value)

def test_mock_adapter_allowed_when_flag_set():
    conn = get_db_connection()
    scanner = FreshJobScanner(conn=conn, adapters=[MockJobSourceAdapter()], allow_mock=True)
    assert isinstance(scanner, FreshJobScanner)
