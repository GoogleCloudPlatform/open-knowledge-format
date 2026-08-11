# Connector: Google Cloud Knowledge Catalog (via `kcmd`)

**Status:** design note. Describes a working prototype and the gaps between it
and a connector we would be willing to call v1.

This document covers moving OKF bundles into and out of [Google Cloud Knowledge
Catalog][kc] (renamed from Dataplex Universal Catalog; IAM identifiers still use
the `dataplex.*` prefix) using **`kcmd`**, the Metadata-as-Code CLI and library
that lives in [`toolbox/mdcode`][mdcode] of the `knowledge-catalog` repo.

OKF is deliberately vendor-neutral (SPEC.md §1). Nothing here is normative for
the format — this is one connector among many possible ones, and the mapping
choices below are the connector's, not the spec's.

[kc]: https://docs.cloud.google.com/dataplex/docs/catalog-overview
[mdcode]: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/toolbox/mdcode

## Why the two models don't line up

| | OKF bundle | Knowledge Catalog |
|---|---|---|
| Unit | A `.md` file with YAML frontmatter | An **entry** in an **EntryGroup** |
| Structure | Directory hierarchy; graph via markdown links | Flat entries under a group; relationships are not first-class |
| Typing | `type:` is a freeform string, not centrally registered (§4.1) | Entry types are registered resources (`dataplex-types.global.generic`, …) |
| Extra fields | Any producer-defined key; consumers preserve unknown keys (§4.1, §11) | **Aspects** — typed records, schema declared up front |
| Source of truth | Git | The catalog service |

`kcmd` already bridges the filesystem-to-service half of this: a `catalog.yaml`
manifest names a scope, `catalog/` holds a snapshot, and `kcmd pull` / `kcmd
push` sync it. It ships a generic **Documents Layout** that maps a tree of
markdown files to entries.

The mismatch that drives this connector's whole design: the Documents Layout
carries only `title` / `description` / `tags` plus the body. **OKF's signal
layer — `type`, `resource`, `generated`, `verified`, `sources`, `status`,
`stale_after` — has no generic home in it.** That signal layer is the
interesting part of OKF; a connector that drops it is just a markdown uploader.

## How the prototype works

Prototype lives at [`toolbox/mdcode/demo/okf/`][demo] and round-trips a 14-file
GA4 bundle. The shape is worth keeping.

[demo]: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/toolbox/mdcode/demo/okf

**A custom `okf` aspect type carries the signal.** Rather than teaching `kcmd`
about OKF, the connector declares a Dataplex aspect type (`okf-aspect.json`)
and moves the signal fields into it, passed through the Documents Layout's
`catalogEntry:` block. `kcmd` stays generic; all OKF knowledge lives in the
connector. **This is the right split and should be preserved.**

**A throwaway staging tree keeps on-disk files clean.** `catalog/` is pure OKF.
`push.ts` translates each file into the "pushable" form under `.staging/`, runs
the real `kcmd push` there, and deletes it. `pull.ts` is the inverse. So the
git-tracked bundle never acquires catalog-shaped scaffolding, and the same
bundle stays consumable by every other OKF tool.

**The mapping today:**

| OKF | Knowledge Catalog |
|---|---|
| Bundle root | EntryGroup — scope `kb.<project>.<location>.<entryGroup>` |
| File path `references/metrics/purchasers.md` | Entry `references/metrics/purchasers` |
| Markdown body | `dataplex-types.global.overview` aspect content |
| `title`, `description`, `tags` | Documents Layout native fields |
| `resource` | `catalogEntry.resource.name` |
| `type` | `okf` aspect → `okf_type` |
| `generated` | `okf` aspect → `generated {by, at}` |
| `sources` | `okf` aspect → `sources[] {id, resource, title}` |
| `index.md` (no frontmatter, §8) | Body-only entry, no OKF signal |

Entry type is always `dataplex-types.global.generic`. This is correct and not a
shortcut: OKF `type` values are freeform strings like `BigQuery Table` or
`Attested Computation` (§4.1) and are not Dataplex type references, so the real
value has to live on the aspect regardless.

## What's missing

Everything below is a gap in the prototype, not in `kcmd`.

### 1. The aspect covers three signal fields out of roughly ten

`okf-aspect.json` models `okf_type`, `generated`, and `sources{id, resource,
title}`. Silently dropped on every round-trip:

- **`verified`** (§5.2) — a list of `{by, at}` events. This is the input to
  trust tiers (§5.3), so without it every concept in the catalog reads as
  *unverified* and the human-reviewed / machine-confirmed distinction is gone.
  The most damaging omission of the set.
- **`status`** (§5.4) — `draft` / `stable` / `deprecated`. A deprecated concept
  is indistinguishable from a current one in the catalog.
- **`stale_after`** (§5.5) — the staleness date.
- **Source credibility signals** (§5.1) — `author`, `usage_count`,
  `last_modified` on each entry, plus the `usage_window` sibling. The
  connector's `pick()` allowlist keeps only `id` / `resource` / `title`.
- **Computation contract fields** (§10) for Attested Computation concepts.

Extending `okf-aspect.json` to cover the full v0.2 signal layer is mechanical
and should happen before anyone relies on this. Note `verified` needs the
bare-mapping-means-one-element-list rule (§5.2, §11).

### 2. Unknown keys are dropped, which the spec says they shouldn't be

§4.1: *"Consumers SHOULD preserve unknown keys when round-tripping."* The
`pick()` allowlist means a producer-defined key survives `push` → `pull` only
if the connector was taught about it. A bundle that goes through the catalog
and back comes out lossy in a way a plain `git diff` will show.

Options, roughly in order of preference:

1. A catch-all `extra` field on the `okf` aspect holding serialized JSON of
   unrecognized frontmatter keys. Ugly, lossless, cheap.
2. Treat git as authoritative and never pull into a tracked bundle (see §5
   below), which makes the loss unobservable rather than fixed.
3. Accept the loss and document it. Only defensible if the catalog is a
   read-only projection.

### 3. Cross-links break in the catalog

OKF bodies link with bundle-relative (`/tables/events_.md`) or relative
(`../tables/events_.md`) paths (§6.1). Those strings are stored verbatim on the
overview aspect and resolve to nothing in the catalog UI — the bundle graph,
which is a good part of what makes OKF worth having, silently flattens into
disconnected documents. Nothing in `mdcode` rewrites links (confirmed by
grepping `src/`).

Since the file-path-to-entry-name mapping is deterministic, push could rewrite
each link to the target entry, and pull could invert it. The catch is that
inverting reliably means knowing which links the connector wrote, so this
probably wants a marker or a link table on the aspect. Worth designing rather
than bolting on.

Do **not** solve this by rewriting links in the source bundle — §6.1's relative
form is deliberate, and it is what makes bundles render correctly on GitHub
([`4c40ef1`][commit] in the source repo exists precisely for that).

[commit]: https://github.com/GoogleCloudPlatform/knowledge-catalog/commit/4c40ef1

### 4. Entry identity is the file path, so renames destroy catalog state

Entry name derives from file path. Rename `metrics/revenue.md` →
`metrics/revenue-ytd.md` and the connector deletes one entry and creates
another. Anything the catalog accumulated against the old entry — aspects
applied out-of-band, tags, references from other systems — is gone, and OKF has
no opinion about it because in a bundle a rename is just a rename.

If bundles are expected to churn, entries need a stable identifier that
survives a move. That likely means a connector-owned id minted on first push
and stored both on the aspect and in the file (which puts a catalog-specific
key into clean OKF — a real cost, worth weighing against the alternative).

Related and unresolved: **deleting a file does not delete its entry.** Orphans
accumulate. Push needs a reconciliation pass, ideally behind a flag, since
"delete everything not in my local tree" is a dangerous default.

### 5. Two writable sources of truth, no merge story

`kcmd push` only pushes changes since the last pull and refuses if the catalog
moved underneath. That is sound for a catalog-first workflow. But OKF bundles
live in git and are edited by agents and humans through pull requests, so we
have two writable copies and a conflict rule that can only say *stop*.

The cleanest answer, and the recommended default: **git is authoritative; the
catalog is a projection.** Push on merge to main, never pull into a tracked
bundle. Discoverability and search in the catalog, review and history in git —
each side does what it is good at.

Bidirectional editing should be an explicit opt-in mode, and it needs a real
design: which side wins per field, whether catalog edits open a pull request
instead of landing directly, and what happens when an agent regenerates a
document that a human edited in the catalog UI. Not something to leave implied.

### 6. Access control is a deployment decision, not a detail

Knowledge Catalog has **no entry-level access control**. Policies attach to
entry groups, entry types, aspect types, glossaries, and project/folder/org.
Anything pushed onto an entry inherits the entry group's access.

The consequence worth stating plainly to anyone adopting this: `roles/viewer`
on the hosting project is a full catalog reader, and it is a *superset* of
`roles/dataplex.catalogViewer` — it additionally carries `entryGroups.export`
(bulk metadata dump) and `entries.getData`. So a bundle pushed into a project
where basic roles are handed out is readable, and bulk-exportable, by everyone
holding one.

To be precise rather than alarmist: this is not "public by default." It is
"visible to anyone with a basic role on the project," which makes it a project
hygiene question. But basic-role grants are common enough that broad visibility
is the default outcome unless someone chose otherwise.

Practical guidance: push bundles into a project with no basic-role grants, grant
`roles/dataplex.catalogViewer` per entry group, and decide deliberately before
pushing a bundle whose concept names, column names, or prose you would not show
to every project viewer. Bundle *content* is the disclosure surface here — data
values are not involved.

### 7. Scale is untested

14 files. Real bundles run to hundreds, and `bundles/stackoverflow/` in this
repo is already 30+. Push is per-file with no batching or concurrency, and
Dataplex has per-request and per-minute quotas. Someone should run a
thousand-document bundle before this is load-bearing.

## Recommended shape for v1

1. Extend `okf-aspect.json` to the full v0.2 signal layer, plus a catch-all for
   unknown keys. Mechanical, unblocks everything else.
2. Ship **one-way, git-authoritative push** first. It sidesteps merge semantics
   and the unknown-key problem entirely, and covers the discoverability use
   case that motivates this connector.
3. Add orphan reconciliation behind an explicit flag.
4. Design link rewriting and stable entry identity properly, together — they
   interact.
5. Treat bidirectional sync as a separate project with its own design doc.

## Open questions

- Should one EntryGroup hold one bundle, or should several bundles share a group
  with a path prefix? The prototype assumes one-to-one; multi-tenancy is
  unexplored.
- Do OKF Attested Computations (§10) map onto anything native in the catalog, or
  do they stay opaque aspect payloads?
- Should `okf_version` (§12) from the bundle-root `index.md` be recorded on the
  EntryGroup so consumers can tell which spec revision produced the entries?
- Is `okf-aspect.json` per-project, or should there be one shared, published
  aspect type so bundles from different producers are queryable together?
