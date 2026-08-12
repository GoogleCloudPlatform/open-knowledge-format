# Publishing an OKF bundle to Google Cloud Knowledge Catalog

How to push an OKF bundle into a [Google Cloud Knowledge Catalog][kc] EntryGroup
and pull it back as clean OKF, using **`kcmd`** — the Metadata-as-Code CLI in
[`toolbox/mdcode`][mdcode] of the `knowledge-catalog` repo.

Read [Known limitations](#known-limitations) before using this on a bundle you
care about. Some OKF frontmatter does not survive a round-trip today.

[kc]: https://docs.cloud.google.com/dataplex/docs/catalog-overview
[mdcode]: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/toolbox/mdcode

## How it works

`kcmd` syncs a local directory against the catalog: a `catalog.yaml` manifest
names a scope, `catalog/` holds the snapshot, and `kcmd pull` / `kcmd push`
move it. Its generic Documents Layout maps one markdown file to one entry, with
the body stored on the `dataplex-types.global.overview` aspect.

That layout carries only `title`, `description`, `tags`, and the body. OKF's
signal layer (`type`, `resource`, `generated`, `sources`, …) has no home in it,
so you declare a **custom `okf` aspect type** and move the signal there.

Because `kcmd` expects that signal in a `catalogEntry:` block rather than as
top-level OKF frontmatter, you translate each file into a "pushable" form in a
throwaway `.staging/` tree, push from there, and delete it. Your `catalog/`
directory stays clean OKF and remains readable by every other OKF tool.

```
catalog/            .staging/catalog/          Knowledge Catalog
clean OKF     ──►   pushable form       ──►    entries + aspects
  (git)             (throwaway)                (service)
              ◄──                       ◄──
```

## Prerequisites

- A GCP project with the BigQuery and Dataplex APIs enabled.
- `gcloud`, authenticated for application default credentials.
- [Bun](https://bun.sh). Required, not optional — `kcmd`'s build compiles the
  binary with `bun build --compile`, and the translation scripts are run with
  `bun`.

```bash
gcloud auth application-default login
gcloud config set project <your-project-id>
gcloud config set compute/region us-central1
```

**Set both, and set them with `gcloud config`.** `kcmd` reads its project and
location from `gcloud config get-value project` and `gcloud config get-value
compute/region` — there is no flag and no environment variable. If either is
unset, every command fails with `Unable to retrieve project, location, or
token. Ensure gcloud is configured.` The location also has to match the one you
create the aspect type in, because the aspect is keyed
`<project>.<location>.okf`.

Build the CLI (it is not yet published as a binary):

```bash
git clone https://github.com/GoogleCloudPlatform/knowledge-catalog
cd knowledge-catalog/toolbox/mdcode
npm install && npm run build      # produces dist/kcmd
```

## Run the demo first

`toolbox/mdcode/demo/okf` runs the whole of this document against a 14-file GA4
sample bundle. Run it there first — it proves your environment before you have
changed anything, so a later failure is about your bundle and not your setup.

```bash
cd demo/okf
bun setup.ts
bun push.ts
bun pull.ts
git diff --exit-code catalog/    # should be empty
bun cleanup.ts
```

The rest of this document is how to do the same thing with your own bundle.

## Step 1 — Copy the connector

Copy everything in [`demo/okf`][demo] except `catalog/` into a directory of your
own. The EntryGroup name is hardcoded as `okf_ga4` in `setup.ts` and
`cleanup.ts`; change it in both.

[demo]: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/toolbox/mdcode/demo/okf

Two more things to change if that directory is not two levels below
`toolbox/mdcode`:

- The scripts locate the binary as `path.resolve(root, '../../dist/kcmd')`.
- They `import * as kcmd from 'kcmd'`, purely to call
  `kcmd.gcp.ApiContext.default()` for the project and location that make up the
  aspect key. Either keep the module resolvable or read the two values from
  `gcloud config get-value` yourself.

Add `.staging/` and the generated `catalog.yaml` to `.gitignore`.

## Step 2 — Set up the catalog side

```bash
bun setup.ts
```

That creates the EntryGroup, creates the custom `okf` aspect type from
`okf-aspect.json`, and writes a `catalog.yaml` with your project and location
substituted in. Re-running it is safe — it ignores "already exists".

Do this rather than running the `gcloud` commands by hand. The aspect is keyed
`<project>.<location>.okf` and that key has to appear in the manifest verbatim,
which is the easiest thing in the whole setup to get wrong.

## Step 3 — Add your bundle

Copy the bundle so its root is `catalog/`:

```bash
cp -R /path/to/bundle/. catalog/
```

Entry names come from file paths: `references/metrics/purchasers.md` becomes
entry `references/metrics/purchasers`.

## Step 4 — Translate and push

```bash
bun push.ts
```

Nothing stops you from pointing `kcmd push` straight at a clean OKF bundle, and
it will appear to work — `title`, `description`, `tags`, and the body all map
natively. It silently drops `resource`, `type`, `generated`, and `sources`,
because the layout has no idea those keys are meaningful. The translation step
exists for exactly that reason.

Useful flags: `kcmd push --validate-only` checks without applying, and
`--force` overrides the "catalog changed underneath you" guard. Note that the
`toolbox/mdcode` README is stale here — it documents a `--dry-run` flag and a
`kcmd status` command, neither of which exists. The real command set is `init`,
`pull`, `push`, and `mcp`, and `pull` takes no flags at all.

The transformation, so you can reimplement it in another language. Clean OKF on
disk:

```yaml
---
type: Reference
resource: https://support.google.com/analytics/answer/9037342
title: Purchasers Audience Metric
description: Computes the count or list of users who have completed a purchase.
tags: [metric, ga4]
generated: { by: reference_agent/gemini-3.5-flash, at: 2026-07-10T21:16:12+00:00 }
sources:
  - id: sample_queries
    resource: https://support.google.com/analytics/answer/9037342
    title: Sample queries for audiences based on BigQuery data
---
```

The same file staged for `kcmd`:

```yaml
---
title: Purchasers Audience Metric
description: Computes the count or list of users who have completed a purchase.
tags: [metric, ga4]
catalogEntry:
  resource:
    name: https://support.google.com/analytics/answer/9037342
  aspects:
    <project>.<location>.okf:
      okf_type: Reference
      generated: { by: reference_agent/gemini-3.5-flash, at: 2026-07-10T21:16:12+00:00 }
      sources:
        - id: sample_queries
          resource: https://support.google.com/analytics/answer/9037342
          title: Sample queries for audiences based on BigQuery data
---
```

`title`, `description`, and `tags` stay top-level; `resource` moves to
`catalogEntry.resource.name`; `type` becomes `okf_type`; `generated` and
`sources` move onto the aspect. The body is untouched. Emit keys in a fixed
order so round-trips produce stable diffs.

`index.md` files carry no frontmatter (SPEC §8), so the translation passes them
through untouched in both directions. Going back, that has to be detected
rather than assumed: `kcmd` always writes frontmatter on pull, so the reverse
translation emits body only when the entry has no OKF signal at all — no
`okf_type`, no `generated`, no `sources`, no `resource.name`. Without that
check, every index file in your bundle would grow a frontmatter block on the
first pull.

The layout also derives hierarchy from your directory structure: each entry's
`resource.parent` is set to its directory's `index` entry, so the bundle tree
shows up as a real parent/child hierarchy in the catalog. To make that total,
`kcmd` **synthesizes an `index` entry for every directory that doesn't have
one** — see the round-trip note below, because those synthesized entries come
back as files.

## Step 5 — Verify the round-trip

```bash
bun pull.ts
git diff --exit-code catalog/
```

A pull immediately after a push leaves `catalog/` byte-identical only if every
directory in your bundle already has an `index.md` and every non-index document
has a `title`. The demo bundle satisfies both, which is why its round-trip is
clean; yours may not. Expect two specific diffs, both from `kcmd` rather than
from the translation:

- **New `index.md` files.** Directories without one get a synthesized `index`
  entry on push, which comes back as a file on pull — empty, if nothing gave it
  a body.
- **Added `title:` keys.** When a document has no `title`, `kcmd` falls back to
  the resource URI, so a document with `resource:` and no `title:` returns with
  `title:` set to that URI.

Any *other* diff means the translation is lossy for something in your bundle.
Check it against the limitations below before pushing anything further.

## Step 6 — Clean up

```bash
bun cleanup.ts
```

Deletes the EntryGroup, then the aspect type — in that order, because the
aspect type cannot be deleted while entries still reference it.

## The manifest

You do not need this to run the steps above; `setup.ts` writes the file. Read it
before you change the aspect list.

```yaml
scope: kb.<project>.<location>.<entryGroup>
snapshot:
  entries:
    - dataplex-types.global.generic
  aspects:
    - dataplex-types.global.generic
    - dataplex-types.global.overview
    - <project>.<location>.okf
publishing:
  entries:
    - dataplex-types.global.generic
  aspects:
    - dataplex-types.global.generic
    - dataplex-types.global.overview
    - <project>.<location>.okf
```

Four rules, each enforced by `kcmd`:

- The `kb.` prefix on `scope` selects the Knowledge Base source, which is what
  binds the EntryGroup to the Documents Layout.
- **Every entry type you push must be listed in `snapshot.entries`.** Types are
  resolved from that list alone; anything missing throws `Unknown entry type
  <type> in snapshot`. This is why `kcmd init --kb` is not enough on its own —
  it writes the `scope:` line and nothing else, and a manifest straight from
  `init` fails on push.
- **`publishing` must be a subset of `snapshot`.** Listing an aspect or entry
  type under `publishing` that is absent from `snapshot` is a load-time error
  (`Publishing aspect type '<x>' is not listed in snapshot aspects`).
- **Once `publishing` exists, any aspect not named in it is silently skipped on
  push.** This is the easy one to get wrong: omit
  `dataplex-types.global.overview` and every document body is dropped without
  an error. Omit your `okf` aspect and the whole signal layer goes with it.

`dataplex-types.global.generic` appears in both lists because it is the entry
type *and* because `kcmd` always attaches the entry's own type aspect (Dataplex
requires it on create) — so it has to be publishable too.

Entry type is always `dataplex-types.global.generic`. OKF `type` values are
freeform strings (SPEC §4.1), not Dataplex type references, so the real value
lives on the aspect instead. One sharp edge: `kcmd` treats a top-level `type:`
as a Dataplex entry type if and only if it has exactly three dot-separated
segments, so an OKF type like `foo.bar.baz` would be misread as one. Anything
else falls back to generic.

## Frontmatter mapping

| OKF | Knowledge Catalog |
|---|---|
| Bundle root | EntryGroup |
| File path | Entry name (`.md` stripped, so `tables/orders.md` → `tables/orders`) |
| Directory | Parent `index` entry, via `resource.parent` |
| Markdown body | `dataplex-types.global.overview` aspect, `contentType: MARKDOWN` |
| `title` | `resource.displayName` |
| `description` | `resource.description` |
| `tags` | `resource.labels`, each set to `"true"` |
| `resource` | `catalogEntry.resource.name` |
| `type` | `okf` aspect → `okf_type` |
| `generated` | `okf` aspect → `generated {by, at}` |
| `sources` | `okf` aspect → `sources[] {id, resource, title}` |
| everything else | **dropped** — see below |

## Known limitations

**Signal fields are dropped.** `okf-aspect.json` covers three of roughly ten OKF
signal fields. Lost on every round-trip: `verified` (§5.2) — so trust tiers
(§5.3) collapse and every concept reads as *unverified* in the catalog —
`status` (§5.4), `stale_after` (§5.5), the per-source credibility signals
`author` / `usage_count` / `last_modified` (§5.1), and the computation contract
fields (§10). Extend `okf-aspect.json` and the translation in `okf.ts` to cover
what your bundle actually uses, keeping the existing `index` values stable —
Dataplex keys record fields by index.

**Unknown keys are dropped.** The translation works from an allowlist, so
producer-defined keys do not survive, even though §4.1 asks consumers to
preserve them. Add a catch-all field to the aspect if you need them.

**Cross-links break.** OKF bodies link with bundle-relative or relative paths
(§6.1). Those strings are stored verbatim and resolve to nothing in the catalog
UI, so the bundle graph flattens into disconnected documents. Nothing rewrites
them. Do not "fix" this by rewriting links in your source bundle — the relative
form is what makes bundles render on GitHub.

**Tags are stored as labels, and the mapping is not faithful.** Each tag becomes
an entry label key with the value `"true"`, and only labels whose value is
exactly `"true"` are read back as tags. So a label set on the entry by anything
else never appears as a tag, and tag strings have to be valid Dataplex label
keys — a tag with uppercase characters or spaces will be rejected by the
service, even though OKF places no such restriction on tags.

**Renames destroy catalog-side state.** Entry identity is the file path, so
renaming a file deletes one entry and creates another, discarding anything the
catalog accumulated against the old one.

**Deletes leave orphans.** Removing a file does not remove its entry. Prune by
hand.

**There is no merge story.** `kcmd push` only pushes changes since the last pull
and refuses if the catalog moved underneath. With bundles in git you have two
writable copies and no way to reconcile them. Treat git as authoritative and the
catalog as a projection: push on merge to main, and do not pull into a tracked
bundle.

**Anyone with a basic role on the project can read the whole EntryGroup.**
Knowledge Catalog has no entry-level access control — policies attach to entry
groups and above, and everything you push inherits the entry group's access.
`roles/viewer` on the hosting project is a full catalog reader and a strict
superset of `roles/dataplex.catalogViewer`, additionally carrying
`entryGroups.export` (bulk metadata dump) and `entries.getData`. This is not
"public by default," but it does mean a bundle is readable and bulk-exportable
by every project viewer. Push into a project with no basic-role grants, grant
`roles/dataplex.catalogViewer` per entry group, and check what your concept
names, column names, and prose disclose before pushing.

**Scale is untested.** The demo is 14 files. Push is per-file with no batching,
and Dataplex enforces per-request and per-minute quotas. Test before running a
bundle of several hundred documents.
