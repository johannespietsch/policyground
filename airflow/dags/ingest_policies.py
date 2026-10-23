"""Nightly policy ingestion (PLAN M3, D28, D29).

    snapshot_ready (sensor) -> chunk -> embed -> upsert -> eval

One DAG run per snapshot day: the run's logical date ({{ ds }}) IS the snapshot
folder corpus/<tenant>/<ds>/. Each task shells out to the project's own venv via
`uv run`, so Airflow's dependencies never mix with the app's (D28). Tasks hand data
to each other through staging files, not XCom (D29).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, AsyncCallback, DeadlineAlert, DeadlineReference, Param, task

ROOT = os.environ.get("POLICYGROUND_ROOT", str(Path(__file__).resolve().parents[2]))
ARGS = "--tenant {{ params.tenant }} --date {{ ds }} --chunker {{ params.chunker }} --embedder {{ params.embedder }}"
RUN = f"cd {ROOT} && uv run python -m"

with DAG(
    dag_id="ingest_policies",
    schedule="@daily",
    start_date=datetime(2026, 10, 12),
    catchup=False,  # history is loaded with an explicit backfill, not on unpause
    max_active_runs=1,  # each run loads the embedding model; keep it to one at a time
    params={
        "tenant": Param("hotels", type="string"),
        # Mirrors policyground.config.PRODUCTION (D31). Duplicated on purpose: the DAG
        # runs in Airflow's venv and must not import the app package (D28).
        "chunker": Param("structural-v1", type="string"),
        "embedder": Param("e5-base-v2", type="string"),
        "fail_rate": Param(0.0, type="number", minimum=0, maximum=1,
                           description="Probability of a simulated 429 on each embed attempt"),
        "fail_first_tries": Param(0, type="integer", minimum=0,
                                  description="Embed attempts 1..n fail with a simulated 429"),
    },
    default_args={
        "retries": 4,
        "retry_delay": timedelta(seconds=15),
        "retry_exponential_backoff": True,   # 15s, 30s, 60s, 120s
        "max_retry_delay": timedelta(minutes=2),
    },
    # Replaces Airflow 2's sla= (removed in 3.0). Experimental in 3.3.2.
    deadline=DeadlineAlert(
        reference=DeadlineReference.DAGRUN_QUEUED_AT,
        interval=timedelta(minutes=int(os.environ.get("INGEST_DEADLINE_MINUTES", "4"))),
        callback=AsyncCallback("policyground_alerts.deadline_missed",
                               kwargs={"alert": "ingest_policies missed its deadline"}),
    ),
    tags=["policyground", "m3"],
) as dag:

    @task.sensor(poke_interval=20, timeout=timedelta(minutes=6), mode="reschedule", soft_fail=True)
    def snapshot_ready(tenant: str, ds: str) -> bool:
        """Wait for the day's snapshot folder. If it never appears, the run is
        skipped (soft_fail), not failed: a missing partner drop isn't a pipeline bug."""
        folder = Path(ROOT) / "corpus" / tenant / ds
        return folder.is_dir() and any(folder.glob("*.md"))

    chunk = BashOperator(task_id="chunk", bash_command=f"{RUN} policyground.ingest.steps chunk {ARGS}")
    embed = BashOperator(
        task_id="embed",
        bash_command=f"{RUN} policyground.ingest.steps embed {ARGS}",
        env={"FAIL_RATE": "{{ params.fail_rate }}",
             "FAIL_FIRST_TRIES": "{{ params.fail_first_tries }}",
             "TRY_NUMBER": "{{ ti.try_number }}"},
        append_env=True,  # keep PATH etc.; only add these
    )
    upsert = BashOperator(task_id="upsert", bash_command=f"{RUN} policyground.ingest.steps upsert {ARGS}")
    evaluate = BashOperator(
        task_id="eval",
        bash_command=(f"{RUN} policyground.eval.retrieval {ARGS} "
                      "--source airflow:{{ dag.dag_id }}:{{ run_id }}"),
    )

    snapshot_ready(tenant="{{ params.tenant }}", ds="{{ ds }}") >> chunk >> embed >> upsert >> evaluate
