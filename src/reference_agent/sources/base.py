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

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConceptRef:
    id: tuple[str, ...]
    type: str
    resource: str | None = None
    hint: dict[str, Any] = field(default_factory=dict)

    @property
    def id_str(self) -> str:
        return "/".join(self.id)


class Source(ABC):
    name: str = ""

    @abstractmethod
    def list_concepts(self) -> list[ConceptRef]:
        ...

    @abstractmethod
    def read_concept(self, ref: ConceptRef) -> dict[str, Any]:
        ...

    def sample_rows(self, ref: ConceptRef, n: int = 5) -> list[dict[str, Any]] | None:
        return None

    def find(self, concept_id: tuple[str, ...]) -> ConceptRef | None:
        for ref in self.list_concepts():
            if ref.id == concept_id:
                return ref
        return None
