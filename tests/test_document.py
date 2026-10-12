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

from datetime import datetime, timezone

import pytest

from reference_agent.bundle.document import (
    OKFDocument,
    OKFDocumentError,
    is_stale,
    normalize_verified,
    trust_tier,
)


def test_roundtrip_preserves_frontmatter_and_body():
    src = (
        "---\n"
        "type: BigQuery Table\n"
        "title: Sample\n"
        "description: A sample table.\n"
        "tags: [a, b]\n"
        "timestamp: 2026-05-27T00:00:00+00:00\n"
        "---\n"
        "\n"
        "# Sample\n"
        "\n"
        "Body text.\n"
    )
    doc = OKFDocument.parse(src)
    assert doc.frontmatter["type"] == "BigQuery Table"
    assert doc.frontmatter["tags"] == ["a", "b"]
    assert doc.body.startswith("# Sample")

    serialized = doc.serialize()
    reparsed = OKFDocument.parse(serialized)
    assert reparsed.frontmatter == doc.frontmatter
    assert reparsed.body.strip() == doc.body.strip()


def test_parse_no_frontmatter_treats_all_as_body():
    src = "# Hello\n\nNo frontmatter here.\n"
    doc = OKFDocument.parse(src)
    assert doc.frontmatter == {}
    assert "Hello" in doc.body


def test_unterminated_frontmatter_raises():
    src = "---\ntype: X\nstill in frontmatter\n"
    with pytest.raises(OKFDocumentError):
        OKFDocument.parse(src)


@pytest.mark.parametrize("frontmatter", ["false", "0", "[]", "''", "true", "1", "[type]"])
def test_parse_rejects_non_mapping_frontmatter(frontmatter):
    with pytest.raises(OKFDocumentError, match="Frontmatter must be a YAML mapping"):
        OKFDocument.parse(f"---\n{frontmatter}\n---\n\nBody text.\n")


@pytest.mark.parametrize("frontmatter", ["", "# comment only", "null", "{}"])
def test_parse_accepts_empty_frontmatter(frontmatter):
    doc = OKFDocument.parse(f"---\n{frontmatter}\n---\n\nBody text.\n")
    assert doc.frontmatter == {}
    assert doc.body == "Body text."


def test_validate_rejects_missing_type():
    doc = OKFDocument(frontmatter={"title": "Y"})
    with pytest.raises(OKFDocumentError) as exc:
        doc.validate()
    assert "type" in str(exc.value)


def test_validate_accepts_type_only():
    # OKF v0.2 §11: `type` is the only always-required key.
    OKFDocument(frontmatter={"type": "X"}).validate()


def test_normalize_verified_treats_bare_mapping_as_list():
    fm = {"verified": {"by": "human:ahormati", "at": "2026-06-25T09:00:00Z"}}
    assert normalize_verified(fm) == [
        {"by": "human:ahormati", "at": "2026-06-25T09:00:00Z"}
    ]
    assert normalize_verified({}) == []


def test_trust_tier():
    assert trust_tier({}) == "unverified"
    assert trust_tier(
        {"verified": [{"by": "process:finance-nightly", "at": "x"}]}
    ) == "machine-confirmed"
    assert trust_tier(
        {"verified": [
            {"by": "process:finance-nightly", "at": "x"},
            {"by": "human:ahormati", "at": "y"},
        ]}
    ) == "human-reviewed"
    # A bare mapping is treated as a one-element list.
    assert trust_tier({"verified": {"by": "human:ahormati", "at": "z"}}) == "human-reviewed"


def test_is_stale():
    ref = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    assert is_stale({"stale_after": "2026-09-23T00:00:00Z"}, now=ref) is True
    assert is_stale({"stale_after": "2026-09-24T00:00:00Z"}, now=ref) is False
    assert is_stale({}, now=ref) is False
    assert is_stale({"stale_after": "not-a-date"}, now=ref) is False
    # A date-only value is ignored rather than read as midnight in whichever
    # zone the consumer happens to run in.
    assert is_stale({"stale_after": "2026-09-23"}, now=ref) is False
    assert is_stale({"stale_after": "2026-09-23T00:00:00"}, now=ref) is False
