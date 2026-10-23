"""`policy.changed` events (PLAN M4, D33/D34)."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

TOPIC = "policy.changed"
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:19092")


@dataclass
class PolicyChanged:
    tenant: str
    entity_type: str
    entity_id: str
    key: str
    value: object
    version: int        # per (entity, key), partner-assigned, increasing (D34)
    valid_from: str     # ISO date the change takes effect
    property_id: str    # the partition key (D33): all of a property's changes stay in order
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    produced_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self)).encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PolicyChanged":
        return cls(**json.loads(raw))
