from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FeaturedProject:
    name: str
    title: str | None = None
    summary: str | None = None
    proud_reason: str | None = None
    impact: str | None = None
    labels: list[str] = field(default_factory=list)


def load_featured_projects(path: str | None) -> dict[str, FeaturedProject]:
    if not path:
        return {}

    metadata_path = Path(path)
    if not metadata_path.exists() or not metadata_path.is_file():
        return {}

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Featured projects metadata must be a JSON array.")

    projects: dict[str, FeaturedProject] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        project = _parse_featured_project(item)
        if project:
            projects[_normalize_project_name(project.name)] = project
    return projects


def find_featured_project(name: str, projects: dict[str, FeaturedProject]) -> FeaturedProject | None:
    return projects.get(_normalize_project_name(name))


def _parse_featured_project(item: dict[str, Any]) -> FeaturedProject | None:
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    labels = item.get("labels", [])
    if not isinstance(labels, list):
        labels = []

    return FeaturedProject(
        name=name.strip(),
        title=_optional_str(item.get("title")),
        summary=_optional_str(item.get("summary")),
        proud_reason=_optional_str(item.get("proud_reason")),
        impact=_optional_str(item.get("impact")),
        labels=[label.strip() for label in labels if isinstance(label, str) and label.strip()],
    )


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _normalize_project_name(name: str) -> str:
    return name.lower().replace("_", "-")
