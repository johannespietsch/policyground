"""Postgres connections, one per role (D15). Callers name the role they need."""

from __future__ import annotations

import os

import psycopg
from pgvector.psycopg import register_vector

ROLES = ("ingest_rw", "api_ro")


def connect(role: str) -> psycopg.Connection:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; app code never connects as the admin")
    conn = psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5433")),
        dbname="policyground",
        user=role,
        password=os.environ.get(f"{role.upper()}_PASSWORD", role),
    )
    register_vector(conn)
    return conn
