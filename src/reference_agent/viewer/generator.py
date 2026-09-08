# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from reference_agent.bundle.document import (
    OKFDocument,
    OKFDocumentError,
    is_stale,
    normalize_verified,
    trust_tier,
)

_INDEX_NAME = "index.md"
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
_TYPE_PALETTE = {
    "BigQuery Dataset": "#8b5cf6",
    "BigQuery Table": "#3b82f6",
    "Reference": "#10b981",
}
_DEFAULT_NODE_COLOR = "#94a3b8"


@dataclass
class Concept:
    id: str
    type: str
    title: str
    description: str
    resource: str
    tags: list[str]
    body: str
    status: str = "stable"
    generated: dict[str, Any] = field(default_factory=dict)
    verified: list[dict[str, Any]] = field(default_factory=list)
    stale_after: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    trust_tier: str = "unverified"
    stale: bool = False
    link_targets: dict[str, str] = field(default_factory=dict)

    def to_node(self) -> dict[str, Any]:
        color = _TYPE_PALETTE.get(self.type, _DEFAULT_NODE_COLOR)
        return {
            "data": {
                "id": self.id,
                "label": self.title or self.id,
                "type": self.type,
                "description": self.description,
                "resource": self.resource,
                "tags": self.tags,
                "status": self.status,
                "generated": self.generated,
                "verified": self.verified,
                "stale_after": self.stale_after,
                "sources": self.sources,
                "trust_tier": self.trust_tier,
                "stale": self.stale,
                "color": color,
                "size": 30 + min(60, len(self.body) // 200),
            }
        }


def _resolve_concept_link(href: str, doc_dir: Path, bundle_root: Path) -> str | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or not parsed.path.endswith(".md"):
        return None

    bundle_root_resolved = bundle_root.resolve()
    target_path = parsed.path
    base = bundle_root_resolved if target_path.startswith("/") else doc_dir
    if target_path.startswith("/"):
        target_path = target_path.lstrip("/")

    try:
        resolved = (base / target_path).resolve().relative_to(bundle_root_resolved)
    except ValueError:
        return None

    return resolved.with_suffix("").as_posix()


def _extract_link_targets(body: str, doc_dir: Path, bundle_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _LINK_RE.finditer(body):
        href = m.group(1)
        target = _resolve_concept_link(href, doc_dir, bundle_root)
        if target:
            out[href] = target
    return out


def _walk_concepts(bundle_root: Path) -> list[Concept]:
    concepts: list[Concept] = []
    for md_path in sorted(bundle_root.rglob("*.md")):
        if md_path.name == _INDEX_NAME:
            continue
        rel = md_path.relative_to(bundle_root).with_suffix("")
        concept_id = "/".join(rel.parts)
        try:
            doc = OKFDocument.parse(md_path.read_text(encoding="utf-8"))
        except OKFDocumentError:
            continue
        fm = doc.frontmatter or {}
        tags = fm.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        generated = fm.get("generated") if isinstance(fm.get("generated"), dict) else {}
        sources = fm.get("sources")
        if isinstance(sources, dict):
            sources = [sources]
        elif not isinstance(sources, list):
            sources = []
        concept = Concept(
            id=concept_id,
            type=str(fm.get("type") or "Unknown"),
            title=str(fm.get("title") or concept_id),
            description=str(fm.get("description") or ""),
            resource=str(fm.get("resource") or ""),
            tags=[str(t) for t in tags],
            body=doc.body or "",
            status=str(fm.get("status") or "stable"),
            generated=generated or {},
            verified=normalize_verified(fm),
            stale_after=str(fm.get("stale_after") or ""),
            sources=[s for s in sources if isinstance(s, dict)],
            trust_tier=trust_tier(fm),
            stale=is_stale(fm),
            link_targets=_extract_link_targets(doc.body or "", md_path.parent, bundle_root),
        )
        concepts.append(concept)
    return concepts


def _build_graph(concepts: list[Concept]) -> dict[str, Any]:
    ids = {c.id for c in concepts}
    nodes = [c.to_node() for c in concepts]
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()
    link_targets: dict[str, dict[str, str]] = {}
    for c in concepts:
        link_targets[c.id] = {
            href: target
            for href, target in c.link_targets.items()
            if target in ids
        }
        for target in link_targets[c.id].values():
            if target == c.id or target not in ids:
                continue
            key = (c.id, target)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({
                "data": {
                    "id": f"{c.id}__{target}",
                    "source": c.id,
                    "target": target,
                }
            })
    bodies = {c.id: c.body for c in concepts}
    types = sorted({c.type for c in concepts})
    return {
        "nodes": nodes,
        "edges": edges,
        "bodies": bodies,
        "linkTargets": link_targets,
        "types": types,
        "palette": _TYPE_PALETTE,
    }


def _load_template() -> str:
    template_path = Path(__file__).parent / "templates" / "viz.html"
    return template_path.read_text(encoding="utf-8")


def _load_asset(name: str) -> str:
    asset_path = Path(__file__).parent / "static" / name
    return asset_path.read_text(encoding="utf-8")


def generate_visualization(
    bundle_root: Path,
    out_path: Path,
    *,
    bundle_name: str | None = None,
) -> dict[str, int]:
    """Walk a bundle and write a single self-contained HTML visualization.

    Returns counts: {'concepts': N, 'edges': M, 'bytes': K}.
    """
    bundle_root = Path(bundle_root)
    out_path = Path(out_path)
    if not bundle_root.is_dir():
        raise FileNotFoundError(f"Bundle directory not found: {bundle_root}")

    concepts = _walk_concepts(bundle_root)
    graph = _build_graph(concepts)
    template = _load_template()
    css = _load_asset("viz.css")
    js = _load_asset("viz.js")
    name = bundle_name or bundle_root.resolve().name

    html = (
        template
        .replace("/*__VIZ_CSS__*/", css)
        .replace("/*__VIZ_JS__*/", js)
        .replace("__BUNDLE_NAME__", json.dumps(name))
        .replace("__BUNDLE_DATA__", json.dumps(graph, default=str))
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    return {
        "concepts": len(concepts),
        "edges": len(graph["edges"]),
        "bytes": len(html.encode("utf-8")),
    }
