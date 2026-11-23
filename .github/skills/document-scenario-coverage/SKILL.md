---
name: document-scenario-coverage
description: >-
  Generate a human-readable catalog documenting what every hotsos scenario check
  does, written into the Sphinx docs source under doc/source. Use when asked to
  "document scenario coverage", "generate the scenario catalog", "document what
  each scenario checks", "list all scenarios in the docs", or to refresh the
  scenario reference page after scenarios are added, changed or removed. Reads
  every YAML file under hotsos/defs/scenarios/ and produces an RST reference
  page grouped by plugin, wired into the reference toctree.
metadata:
  author: hotsos maintainers
  version: "1.0"
---

# Document Scenario Coverage

## Goal

Produce and maintain a human-readable catalog that documents every hotsos
scenario check, so readers can see at a glance what analysis each plugin ships.
The catalog is written into the Sphinx documentation source under
`doc/source/` as a reStructuredText reference page and wired into the reference
`toctree`.

## Scope

Read **every** scenario definition file (`.yaml` and `.yml`) under
`hotsos/defs/scenarios/` and all its subdirectories (including per-plugin
`bugs/` subdirectories). Do **not** read `hotsos/defs/events/`, and do **not**
read the YAML test fixtures under `hotsos/defs/tests/`.

Group the output by plugin. The plugin is the first path segment under
`hotsos/defs/scenarios/`, for example `juju`, `kernel`, `openstack`,
`storage`, `system`.

## What to Extract per Scenario

For each scenario file, extract just enough to describe *what it checks* in
plain language. A scenario file uses the `ycheck` DSL and typically contains:

- **`checks`** — one or more named checks. Each check uses one or more
  properties such as `search` (log/file regex with optional `constraints`),
  `binary` (installed binary version ranges), `config`, `property`,
  `requires`, `input`, or `vars`. Summarise what each check looks for
  (for example: "searches unit logs for leadership errors in the last 7 days",
  or "matches installed Juju binary versions affected by a CVE").
- **`conclusions`** — one or more named conclusions. Each has a `decision`
  (which checks must be true) and a `raises` block containing:
  - `type` — the issue type (see `hotsos/core/issues/issue_types.py`).
  - `message` — the conclusion text shown to the user.
  - Optional bug/CVE identifiers (`bug-id`, `cve-id`).
- **`vars`** — reusable values; resolve `{placeholders}` in messages where it
  makes the description clearer, but keep entries concise.

For each scenario, capture:

1. Plugin name.
2. Scenario file name (relative path under the plugin directory).
3. A one- or two-sentence plain-language summary of what it checks.
4. The issue type(s) it can raise.
5. Any bug/CVE reference, rendered as a link when an ID is present:
   - `LaunchpadBug` + `bug-id` -> `https://bugs.launchpad.net/bugs/<bug-id>`
   - `Bugzilla` + `bug-id` -> `https://bugzilla.redhat.com/show_bug.cgi?id=<bug-id>`
   - `StoryBoardBug` + `bug-id` -> `https://storyboard.openstack.org/#!/story/<bug-id>`
   - `CephTrackerBug` + `bug-id` -> `https://tracker.ceph.com/issues/<bug-id>`
   - `UbuntuCVE` + `cve-id` -> `https://ubuntu.com/security/<cve-id>`
   - `MitreCVE` + `cve-id` -> `https://www.cve.org/CVERecord?id=<cve-id>`

Do not invent behaviour. If a scenario is too complex to summarise confidently,
describe it at the level the YAML supports and keep it short rather than
guessing.

## Output

Write the catalog to `doc/source/reference/scenario-catalog.rst` (create it if
missing, overwrite its generated body if it exists).

Structure the page as reStructuredText consistent with the existing docs (see
`doc/source/reference/plugins.rst` for tone and table style):

- A top-level title `Scenario catalog` and a short intro paragraph explaining
  that the page lists the ready-made scenario checks hotsos ships, grouped by
  plugin, and that it is a reference companion to
  :doc:`../explanation/architecture` and `plugins`.
- One top-level section per plugin (alphabetical), titled `<Name> plugin` where
  the plugin name has its first character upper-cased (for example `juju` ->
  `Juju plugin`, `openstack` -> `Openstack plugin`), underlined with `-`.
- Within a plugin, group scenarios by their subfolders and give each subfolder
  its own subheading:
  - Scenarios that live directly in the plugin directory go in a `list-table`
    under a `Common` subheading (underlined with `~`) placed first, before any
    subfolder subheadings.
  - Each subdirectory becomes a subheading, nested to match the folder depth
    (use `~` underlines for the first subfolder level and `^` for the second,
    for example `storage` -> `Ceph` -> `Ceph MON`).
  - Treat a `bugs/` directory as part of its parent, **not** as its own
    subheading: list the bug scenarios in the parent folder's table (for
    example `openstack/neutron/bugs/lp1794991.yaml` appears under the `Neutron`
    subheading, and `juju/bugs/lp1812361.yaml` appears in the plugin's `Common`
    table because its parent is the plugin root).
  - Derive each subheading title from the subfolder name, capitalised into a
    readable form, using well-known acronyms in upper case where appropriate
    (for example `neutron` -> `Neutron`, `ceph-osd` -> `Ceph OSD`,
    `oslo_messaging` -> `Oslo messaging`, `nfs` -> `NFS`).
  - The `Common` title is intentionally repeated across plugins, so
    `sphinx.ext.autosectionlabel` duplicate-label warnings are silenced via
    `suppress_warnings = ["autosectionlabel.*"]` in `doc/source/conf.py`.
- Under each heading/subheading, a `list-table` with header row and columns:
  `Scenario` | `Checks for` | `Raises` | `Reference`.
  - `Scenario`: the scenario file path relative to the current heading's folder
    (so bug scenarios show as `bugs/<name>.yaml`).
  - `Checks for`: the plain-language summary.
  - `Raises`: the issue type(s).
  - `Reference`: bug/CVE link(s) built from the rules above, or an empty cell.

Then wire the page into the reference table of contents by adding
`scenario-catalog` to the `toctree` in `doc/source/reference/index.rst` (after
`plugins`). Do not duplicate the entry if it is already present.

## Procedure

1. List every plugin directory under `hotsos/defs/scenarios/`.
2. For each plugin, read all scenario YAML files (including `bugs/`).
3. Extract the fields described above for each scenario.
4. Render the RST page and write it to
   `doc/source/reference/scenario-catalog.rst`.
5. Add the `scenario-catalog` entry to the reference `toctree` if absent.
6. Verify the docs still build, or at minimum that the RST is well-formed
   (matching indentation, valid `list-table` rows, resolvable `:doc:` links).

## Conventions

- Keep every summary concise — one or two sentences, present tense.
- Preserve alphabetical ordering of plugins, of subfolder subheadings within a
  plugin, and of scenario files within each table for stable diffs.
- Do not modify scenario YAML, test fixtures, or any file outside
  `doc/source/`.
- Do not print the catalog to stdout as the deliverable; the deliverable is the
  RST file.
