"""Deadline Alert callback for the ingest DAG (D28).

AsyncCallbacks run in the Triggerer, so this must be a top-level async function in
an importable module (the plugins folder is on the Triggerer's path). It appends a
line to $AIRFLOW_HOME/deadline_alerts.log; a real deployment would page or post to
a channel here instead.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _get(obj, name):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


async def deadline_missed(**kwargs) -> None:
    context = kwargs.pop("context", None) or {}
    dag_run, deadline = _get(context, "dag_run"), _get(context, "deadline")
    record = {
        "fired_at": datetime.now(timezone.utc).isoformat(),
        "dag_id": _get(dag_run, "dag_id"),
        "run_id": _get(dag_run, "run_id"),
        "deadline_time": _get(deadline, "deadline_time"),
        **kwargs,
    }
    path = Path(os.environ.get("AIRFLOW_HOME", ".")) / "deadline_alerts.log"
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
