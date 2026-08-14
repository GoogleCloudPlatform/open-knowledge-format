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

from dataclasses import dataclass, field
from pathlib import Path

from reference_agent.sources.base import Source


@dataclass
class ToolContext:
    source: Source
    bundle_root: Path
    model: str = ""


@dataclass
class WebState:
    allowed_hosts: set[str]
    max_pages: int
    allowed_path_prefixes: tuple[str, ...] = ()
    denied_path_substrings: tuple[str, ...] = ()
    max_depth: int = 2
    visited: set[str] = field(default_factory=set)
    fetched_count: int = 0
    url_depth: dict[str, int] = field(default_factory=dict)


_ctx: ToolContext | None = None
_web: WebState | None = None


def set_context(source: Source, bundle_root: Path, model: str = "") -> None:
    global _ctx
    _ctx = ToolContext(source=source, bundle_root=Path(bundle_root), model=model)


def get_context() -> ToolContext:
    if _ctx is None:
        raise RuntimeError(
            "Tool context not set. Call set_context() before invoking the agent."
        )
    return _ctx


def set_web_state(
    allowed_hosts: set[str],
    max_pages: int,
    *,
    seeds: list[str] | None = None,
    allowed_path_prefixes: list[str] | None = None,
    denied_path_substrings: list[str] | None = None,
    max_depth: int = 2,
) -> None:
    global _web
    _web = WebState(
        allowed_hosts=set(allowed_hosts),
        max_pages=int(max_pages),
        allowed_path_prefixes=tuple(allowed_path_prefixes or ()),
        denied_path_substrings=tuple(denied_path_substrings or ()),
        max_depth=int(max_depth),
    )
    for seed in seeds or ():
        _web.url_depth[seed] = 0


def get_web_state() -> WebState:
    if _web is None:
        raise RuntimeError(
            "Web state not set. Call set_web_state() before invoking the web agent."
        )
    return _web


def clear_web_state() -> None:
    global _web
    _web = None


def is_web_pass() -> bool:
    """True while the runner is executing the web-ingestion pass."""
    return _web is not None
