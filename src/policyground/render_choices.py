"""Recorded, per-entity render choices (D38), shared by every tenant's renderer."""

from __future__ import annotations

import random


class Chooser:
    """Every random render choice goes through here, keyed by (entity, name) (D38).

    record: draws from the shared RNG in exactly the legacy order (so a fresh corpus is
            byte-identical to before) and remembers each choice.
    replay: reuses the remembered choice, so an entity whose facts didn't change renders
            identically in every later snapshot. A choice never made before (e.g. a new
            rate plan) is drawn from a per-entity RNG and remembered.
    """

    def __init__(self, rng: random.Random | None = None, saved: dict | None = None, seed: int = 42):
        self.rng, self.saved, self.seed = rng, saved if saved is not None else {}, seed
        self.entity = ""

    def for_entity(self, entity_id: str) -> "Chooser":
        self.entity = entity_id
        self.saved.setdefault(entity_id, {})
        return self

    def _source(self) -> random.Random:
        return self.rng or random.Random(f"{self.seed}-render-{self.entity}")

    def _get(self, name: str, draw):
        mine = self.saved[self.entity]
        if self.rng is None and name in mine:
            return mine[name]
        mine[name] = draw(self._source())
        return mine[name]

    def choice(self, name: str, seq: list):
        # r.choice (not randrange) so record mode consumes the RNG exactly as before.
        return seq[self._get(name, lambda r: seq.index(r.choice(seq)))]

    def sample(self, name: str, seq: list, k: int) -> list:
        return [seq[i] for i in self._get(name, lambda r: [seq.index(x) for x in r.sample(seq, k)])]

    def random(self, name: str) -> float:
        return self._get(name, lambda r: r.random())
