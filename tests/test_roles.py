"""Trust boundaries (D15), checked against the running database. Skipped if it's down."""

import psycopg
import pytest

from policyground.db import connect

try:
    connect("api_ro").close()
except psycopg.OperationalError:
    pytest.skip("postgres not running (make up)", allow_module_level=True)


def test_api_ro_cannot_write():
    with connect("api_ro") as conn:
        conn.execute("SELECT count(*) FROM chunks")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM chunks")


def test_ingest_rw_cannot_change_schema():
    with connect("ingest_rw") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("CREATE TABLE nope (id int)")
