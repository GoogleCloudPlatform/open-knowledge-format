# Publishing an OKF bundle to Google Cloud Knowledge Catalog

Push an OKF bundle into a [Knowledge Catalog][kc] EntryGroup and pull it back as
clean OKF, using **`kcmd`** from [`toolbox/mdcode`][mdcode].

Read [Limitations](#limitations) first.

[kc]: https://docs.cloud.google.com/dataplex/docs/catalog-overview
[mdcode]: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/toolbox/mdcode
[demo]: https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/toolbox/mdcode/demo/okf

## Prerequisites

A GCP project with the Dataplex API enabled, `gcloud`, and [Bun](https://bun.sh).

```bash
gcloud auth application-default login
gcloud config set project <your-project-id>
gcloud config set compute/region us-central1
```

Set both. `kcmd` reads project and location from `gcloud config`; there is no
flag and no environment variable.

Build the CLI:

```bash
git clone https://github.com/GoogleCloudPlatform/knowledge-catalog
cd knowledge-catalog/toolbox/mdcode
npm install && npm run build      # produces dist/kcmd
```

## 1. Run the demo

Confirms the environment before you change anything.

```bash
cd demo/okf
bun setup.ts && bun push.ts && bun pull.ts
git diff --exit-code catalog/     # should be empty
bun cleanup.ts
```

## 2. Copy the connector

Copy everything in [`demo/okf`][demo] except `catalog/` into your own directory,
then edit:

- `entryGroup` in `setup.ts` and `cleanup.ts` — hardcoded to `okf_ga4`.
- `path.resolve(root, '../../dist/kcmd')` in `push.ts` and `pull.ts`, if your
  directory is not two levels below `toolbox/mdcode`. Those two also
  `import * as kcmd from 'kcmd'`, so keep that module resolvable.

Add `.staging/` and `catalog.yaml` to `.gitignore`.

## 3. Set up the catalog side

Creates the EntryGroup, the custom `okf` aspect type, and `catalog.yaml`.
Re-running is safe.

```bash
bun setup.ts
```

## 4. Add your bundle

```bash
cp -R /path/to/bundle/. catalog/
```

## 5. Push

```bash
bun push.ts
```

## 6. Verify the round-trip

```bash
bun pull.ts
git diff catalog/                 # first pull: YAML normalization
git add catalog/ && bun pull.ts
git diff --exit-code catalog/     # now clean
```

The first pull rewrites every frontmatter block into `kcmd`'s YAML style —
sequences indented, timestamps unquoted, mapping keys reordered, lines
rewrapped at a different width. No values change. Commit that normalization
once and later pulls are byte-identical, which is what makes `--exit-code`
worth running. The demo skips this only because its `catalog/` was generated
by a pull already.

Two content diffs are also expected and are not translation loss:

- Directories without an `index.md` gain one — `kcmd` synthesizes an `index`
  entry for every directory.
- A document with `resource:` and no `title:` comes back with `title:` set to
  the resource URI.

Any other diff is a key the translation doesn't carry. See
[Limitations](#limitations).

## 7. Clean up

Deletes the EntryGroup. The `okf` aspect type is left in place — it is scoped
to the project, not to your EntryGroup, so every OKF bundle in the project
shares one. `cleanup.ts` prints the command to remove it once nothing else
needs it.

```bash
bun cleanup.ts
```

## Limitations

- **Seven frontmatter keys are carried**, plus the markdown body. `title`,
  `description` and `tags` become native entry fields, `resource` becomes
  `catalogEntry.resource.name`, and `type`, `generated` and `sources` go on the
  `okf` aspect. To carry more, add fields to `okf-aspect.json` and `okf.ts`,
  keeping existing `index` values stable.
- **Only `.md` files are carried.** Anything else in the bundle — images, HTML,
  CSV — is ignored in both directions: never pushed, and left alone on pull.
- **Cross-links resolve to nothing.** Relative paths (§6.1) are stored verbatim.
  Don't rewrite them in your source — the relative form is what renders on
  GitHub.
- **Tags become entry labels set to `"true"`**, and only labels with that exact
  value are read back as tags. Dataplex caps label keys at 128 characters.
- **Renames orphan catalog state, deletes leave entries behind**, and there is
  no merge story. Treat git as authoritative: push on merge, don't pull into a
  tracked bundle.
- **No entry-level access control.** Anyone with a basic role on the project can
  read and bulk-export the EntryGroup — `roles/viewer` is a strict superset of
  `roles/dataplex.catalogViewer` and adds `entryGroups.export`. Not public by
  default, but check what your bundle discloses before pushing.
- **Scale is untested** beyond the 14-file demo. Push is per-file, and Dataplex
  enforces quotas.
