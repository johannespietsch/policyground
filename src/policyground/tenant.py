"""Tenant spec + adapter loading (D44). A tenant lives in src/policyground/tenants/<name>/:

  spec.yaml   levels, subject, variant, doc naming, facts (type/unit/meaning), deadlines,
              chunking, prompt wording. Read by the core; no code.
  adapter.py  generate(seed, snapshot_date) -> kg dict; render(data, chooser) ->
              ({doc_id: markdown}, manifest); golden(data, manifest, seed) -> questions.
              Everything that needs code.
See .claude/skills/onboard-tenant/SKILL.md for how to add one.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

TENANTS_DIR = Path(__file__).parent / "tenants"
FACT_TYPES = {"int", "float", "time", "bool", "enum", "str"}
UNITS = {None, "hours", "days", "EUR"}


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class Spec:
    tenant: str
    levels: tuple[str, ...]
    subject: str
    variant: str | None
    doc_ids: dict
    facts: dict
    deadlines: tuple[dict, ...]
    keep_together: tuple[str, ...]
    prompt: dict

    def doc_id(self, entity: dict) -> str:
        pattern = self.doc_ids["subject"] if entity["type"] == self.subject else self.doc_ids["other"]
        return pattern.format(id=entity["id"], level=entity["type"])

    def parent_level(self, level: str) -> str | None:
        i = self.levels.index(level)
        return self.levels[i - 1] if i else None

    def facts_with_unit(self, unit: str) -> list[str]:
        return [k for k, f in self.facts.items() if f.get("unit") == unit]

    def facts_of_type(self, t: str) -> list[str]:
        return [k for k, f in self.facts.items() if f["type"] == t]


def _validate(raw: dict, name: str) -> Spec:
    def need(cond, msg):
        if not cond:
            raise SpecError(f"tenants/{name}/spec.yaml: {msg}")

    for key in ("tenant", "levels", "subject", "doc_ids", "facts"):
        need(key in raw, f"missing required key '{key}'")
    need(raw["tenant"] == name, f"tenant must be '{name}' (the directory name)")
    levels = tuple(raw["levels"])
    need(len(levels) >= 2 and len(set(levels)) == len(levels), "levels: at least 2, unique")
    need(raw["subject"] in levels, "subject must be one of levels")
    variant = raw.get("variant")
    need(variant is None or (variant in levels and levels.index(variant) == levels.index(raw["subject"]) + 1),
         "variant must be the level directly below subject")
    need({"subject", "other"} <= set(raw["doc_ids"]), "doc_ids needs 'subject' and 'other' patterns")
    for k, f in raw["facts"].items():
        need(f.get("type") in FACT_TYPES, f"fact {k}: type must be one of {sorted(FACT_TYPES)}")
        need(f.get("unit") in UNITS, f"fact {k}: unit must be one of {sorted(u for u in UNITS if u)} or absent")
        need(f["type"] != "enum" or f.get("values"), f"fact {k}: enum needs values")
        need(f.get("level") in (None, "variant"), f"fact {k}: level may only be 'variant'")
    for d in raw.get("deadlines", []):
        for key in ("name", "offset", "direction"):
            need(key in d, f"deadline {d}: missing '{key}'")
        need(d["offset"] in raw["facts"], f"deadline {d['name']}: offset fact '{d['offset']}' not in facts")
        need(raw["facts"][d["offset"]].get("unit") in ("hours", "days"),
             f"deadline {d['name']}: offset fact needs unit hours or days")
        need(d["direction"] in ("before", "after"), f"deadline {d['name']}: direction before|after")
        need(d.get("anchor_time") in (None, *[k for k, f in raw["facts"].items() if f["type"] == "time"]),
             f"deadline {d['name']}: anchor_time must be a time fact")
        need(isinstance(d.get("anchor_date_hints", []), list),
             f"deadline {d['name']}: anchor_date_hints must be a list of words")
    return Spec(tenant=name, levels=levels, subject=raw["subject"], variant=variant, doc_ids=raw["doc_ids"],
                facts=raw["facts"], deadlines=tuple(raw.get("deadlines", [])),
                keep_together=tuple(raw.get("chunking", {}).get("keep_together", [])),
                prompt=raw.get("prompt", {}))


@cache
def spec(name: str) -> Spec:
    path = TENANTS_DIR / name / "spec.yaml"
    if not path.exists():
        raise SpecError(f"no tenant '{name}': {path} missing (known: {known()})")
    return _validate(yaml.safe_load(path.read_text()), name)


def adapter(name: str):
    return importlib.import_module(f"policyground.tenants.{name}.adapter")


def known() -> list[str]:
    return sorted(p.name for p in TENANTS_DIR.iterdir() if (p / "spec.yaml").exists())
