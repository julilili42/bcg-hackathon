"""Use cases are configuration (ADR 0002). One YAML per domain in ``core/domains/``."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from reach.core.matching import normalize
from reach.core.schemas import DomainOut, Lang

DOMAINS_DIR = Path(__file__).resolve().parent / "domains"


class StatusSpec(BaseModel):
    good: list[str]
    bad: list[str]
    labels: dict[Lang, dict[str, str]]


class AlternativeSpec(BaseModel):
    radius_km: float = 15.0
    max_results: int = 3


class DomainConfig(BaseModel):
    id: str
    entity_type: str
    names: dict[Lang, str]
    statuses: StatusSpec
    status_keywords: dict[str, list[str]] = Field(default_factory=dict)
    attributes: dict[str, str] = Field(default_factory=dict)
    matching_hints: list[str] = Field(default_factory=list)
    alternative: AlternativeSpec = Field(default_factory=AlternativeSpec)
    templates: dict[Lang, dict[str, str]]

    @property
    def all_statuses(self) -> list[str]:
        return [*self.statuses.good, *self.statuses.bad]

    def is_good(self, status: str) -> bool:
        return status in self.statuses.good

    def label(self, lang: Lang, status: str) -> str:
        return self.statuses.labels.get(lang, {}).get(status, status)

    def t(self, lang: Lang, key: str, **kwargs: object) -> str:
        template = self.templates.get(lang, {}).get(key) or self.templates["en"].get(key) or ""
        return template.format(**kwargs)

    def to_out(self) -> DomainOut:
        return DomainOut(
            id=self.id,
            entity_type=self.entity_type,
            names={str(k): v for k, v in self.names.items()},
            good_statuses=list(self.statuses.good),
            bad_statuses=list(self.statuses.bad),
            status_labels={k: dict(v) for k, v in self.statuses.labels.items()},
        )


def load_domain_file(path: Path) -> DomainConfig:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return DomainConfig.model_validate(raw)


@lru_cache(maxsize=1)
def load_domains(directory: Path = DOMAINS_DIR) -> dict[str, DomainConfig]:
    configs = [load_domain_file(p) for p in sorted(directory.glob("*.yaml"))]
    return {c.id: c for c in configs}


def detect_domain(text: str, domains: Mapping[str, DomainConfig], default_id: str) -> DomainConfig:
    """Pick the domain whose hints appear most in the text; ties and no hits fall back to the default."""
    norm = f" {normalize(text)} "
    best: tuple[int, str] | None = None
    for cfg in domains.values():
        hits = sum(1 for hint in cfg.matching_hints if f" {normalize(hint)} " in norm)
        if hits and (best is None or hits > best[0]):
            best = (hits, cfg.id)
    chosen = best[1] if best else default_id
    return domains[chosen] if chosen in domains else next(iter(domains.values()))
