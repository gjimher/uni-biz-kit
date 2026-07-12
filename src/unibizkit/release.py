"""Small, dependency-free helpers for generated production release scripts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}"


def tag_prefix(app_id: str) -> str:
    return f"prod-{app_id}-v"


def parse_tag(app_id: str, tag: str) -> Version | None:
    match = re.fullmatch(re.escape(tag_prefix(app_id)) + r"(\d+)\.(\d+)", tag)
    if not match:
        return None
    return Version(int(match.group(1)), int(match.group(2)))


def version_tag(app_id: str, version: Version) -> str:
    return f"{tag_prefix(app_id)}{version.major}.{version.minor}"


def tagged_versions(app_id: str, tags: Iterable[str]) -> list[tuple[Version, str]]:
    found = [(version, tag) for tag in tags if (version := parse_tag(app_id, tag))]
    return sorted(found)


def next_version(app_id: str, tags: Iterable[str], *, major: bool = False) -> Version:
    versions = tagged_versions(app_id, tags)
    if not versions:
        return Version(1, 0)
    current = versions[-1][0]
    return Version(current.major + 1, 0) if major else Version(current.major, current.minor + 1)


def normalize_migration(sql: str) -> str:
    """Normalize only non-semantic formatting emitted around a SQL diff."""
    sql = sql.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in sql.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + ("\n" if lines else "")


def migration_hash(sql: str) -> str:
    return hashlib.sha256(normalize_migration(sql).encode()).hexdigest()


_INCOMPATIBLE_PATTERNS = (
    (r"\bdrop\s+table\b", "drops a table"),
    (r"\bdrop\s+column\b", "drops a column"),
    (r"\bdrop\s+(?:function|procedure)\b", "removes a function or procedure"),
    (r"\brename\s+(?:table|column|constraint|to)\b", "renames a database object"),
    (r"\balter\s+column\b[\s\S]{0,300}\btype\b", "changes a column type"),
    (r"\balter\s+column\b[\s\S]{0,300}\bset\s+not\s+null\b", "makes a column mandatory"),
    (r"\balter\s+column\b[\s\S]{0,300}\bdrop\s+default\b", "removes a column default"),
    (r"\badd\s+(?:constraint\s+\S+\s+)?(?:check|unique|foreign\s+key)\b", "adds a write-restricting constraint"),
    (r"\bcreate\s+unique\s+index\b", "adds a write-restricting unique index"),
)


def incompatible_migration_changes(sql: str) -> list[str]:
    """Return conservative reasons why an old application may stop writing."""
    normalized = normalize_migration(sql).lower()
    reasons = {
        reason
        for pattern, reason in _INCOMPATIBLE_PATTERNS
        if re.search(pattern, normalized, flags=re.IGNORECASE)
    }
    # Old clients cannot populate a newly required column unless the DB supplies it.
    for statement in re.split(r";\s*(?:\n|$)", normalized):
        if re.search(r"\badd\s+(?:column\s+)?[^;]+\bnot\s+null\b", statement):
            if not re.search(r"\bdefault\b", statement):
                reasons.add("adds a mandatory column without a default")
    return sorted(reasons)
