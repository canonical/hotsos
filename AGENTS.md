# Hotsos — Agent Context

## Project Overview

**Hotsos** is a software analysis toolkit developed by Canonical. It performs repeatable, automated analysis of common cloud applications and subsystems (e.g., OpenStack, Kubernetes, Juju, Ceph, OVS/OVN, kernel). Analysis can run against a **live host** or a **sosreport**.

Output is a structured summary (YAML, JSON, Markdown, or HTML) containing key information per plugin, detected issues, known bugs, and suggested actions.

Entry point: `hotsos` CLI (`hotsos/cli.py`), backed by `HotSOSClient` in `hotsos/client.py`.

---

## Repository Layout

```
hotsos/                  # Main Python package
  cli.py                 # CLI entry point (click-based)
  client.py              # HotSOSClient — orchestrates plugin runs and output
  core/                  # Shared library code
    config.py            # HotSOSConfig global configuration
    plugintools.py       # Plugin registry, PluginPartBase, run ordering
    root_manager.py      # DataRootManager — abstracts host vs sosreport
    search.py            # Search helpers
    ycheck/              # YAML-defined check engine
      engine/            # Core engine: properties, handlers
      scenarios.py       # Scenario checker
      events.py          # Event checker
      common.py          # GlobalSearcher, shared utilities
    host_helpers/        # Helpers to query host state
      cli/               # CLI command catalog and execution
      network.py, packaging.py, systemd.py, sysctl.py, ...
    plugins/             # Plugin-specific Python primitives (per app/subsystem)
      openstack/, kernel/, juju/, storage/, openvswitch/, ...
    issues/              # IssuesManager — raise and collect detected issues/bugs
    formatters/          # Output formatters (yaml, json, markdown, html)
  defs/                  # YAML-defined analysis (checks, events, scenarios)
    scenarios/           # One subdirectory per plugin
    events/              # One subdirectory per plugin
    tests/               # YAML test fixtures
  plugin_extensions/     # Plugin output implementations (per app/subsystem)
    openstack/, kernel/, juju/, storage/, openvswitch/, ...
tests/
  unit/                  # Unit tests (stestr/unittest)
tools/                   # Validation and dashboard preview utilities
deb/                     # Debian packaging
snap/                    # Snap packaging
doc/                     # Documentation (Sphinx / ReadTheDocs)
```

---

## Key Concepts

### Plugins
Each supported application/subsystem is a **plugin** (e.g., `openstack`, `kernel`, `juju`, `storage`, `openvswitch`). Plugins register themselves via `PluginRegistryMeta` in `plugintools.py` and are imported in `hotsos/plugin_extensions/__init__.py`.

A plugin consists of:
- **`hotsos/defs/<scenarios|events>/<plugin>/`** — YAML-defined checks
- **`hotsos/core/plugins/<plugin>/`** — Python primitives/helpers for the plugin
- **`hotsos/plugin_extensions/<plugin>/`** — Output-producing classes (subclasses of `PluginPartBase`)

### PluginPartBase
Plugin output classes subclass `PluginPartBase`. They either:
- Implement a `summary` property — places data at `<plugin>` root in the summary.
- Implement `__summary_<key>` properties — places data at `<plugin>.<key>`.

Use `core.issues.IssuesManager` to raise issues rather than printing directly. **Never print to stdout.**

### YAML Checks (defs)
Checks are defined in YAML under `hotsos/defs/` using a high-level DSL evaluated by the `ycheck` engine. Two types:
- **Scenarios** (`defs/scenarios/`) — logical checks with conclusions and raised issues.
- **Events** (`defs/events/`) — log/file pattern searches.

### Writing Scenario Checks (practical tips)
- Mirror an existing scenario in the same plugin dir before writing a new one; conventions (naming, `vars:`, message style) vary little across the tree.
- `vars:` entries are resolved as **whole-value** substitution only (`expr: $my_var`). You cannot embed `$var` inside a larger literal string to interpolate a fragment — define the entire value (e.g. the whole regex) as one var instead. Also avoid YAML folded scalars (`>-`) for multi-line regexes: folding inserts a literal space at each line break and will silently corrupt the pattern. Keep regexes as a single-line quoted string.
- When a check uses `constraints:` (e.g. `search-result-age-hours`), the search `expr` must **start** with a capture of the log line's date (and ideally time as group 2) — see `hotsos/core/search.py::CommonTimestampMatcher.patterns` for the exact formats and `tools/validation/hotyvalidate.py::LEADING_TIMESTAMP_RE` for what's accepted (matched from the very start of the expr string, no leading `.*`).
- `format-dict` renderer `:unique_comma_join` is deterministic — it does `', '.join(sorted(set(value)))` — so expected test messages can be computed exactly (alphabetical, deduped).
- Validate new/changed scenarios with `tox -e yamllint` and `tox -e hotyvalidate` (the latter enforces the timestamp-capture rule above) in addition to `tox -e py3`.
- Scenario tests are YAML fixtures under `hotsos/defs/tests/scenarios/<plugin>/...` and are auto-discovered: each `tests/unit/<plugin>/test_scenarios.py` uses `@utils.load_templated_tests('scenarios/<plugin>')`, generating test methods named `test_yscenario_<relative_path_with_underscores>`. No Python test code is needed for a new scenario — just add the fixture file (use `target-name:` when the fixture filename differs from the scenario filename).
- Each plugin's fake data root has a fixed "current time" at `tests/unit/fake_data_root/<plugin>/sos_commands/date/date` (e.g. openstack = `Thu Feb 10 16:19:17 UTC 2022`). Positive fixtures should copy it via `copy-from-original: [sos_commands/date/date]` and place log timestamps relative to it; `_old_logs` negative fixtures reuse the same date file but push log timestamps outside the constraint window.

### Data Root
`DataRootManager` (via `HotSOSConfig`) abstracts whether hotsos is running against a live host or an unpacked sosreport directory. All file reads and command executions go through this abstraction.

### Output Formats
Supported: `yaml` (default), `json`, `markdown`, `html`. Controlled via `--format` CLI flag.

The html output format uses the [Canonical Vanilla Framework](https://github.com/canonical/vanilla-framework) to provide a dashboard view Hotsos' output. Key information is shown towards the top of the page and more detail is available as you scroll down.

---

## Development Workflow

### Running Tests

**Always use `tox` to run tests and linters in this project — never invoke `stestr`, `pytest`, `python -m unittest`, `flake8`, or `pylint` directly.** The `tox` environments provide the correct virtualenv, dependencies, and configuration; running the underlying tools directly will give unreliable or incorrect results. Use these canonical commands:

- Run unit tests: `tox -e py3`
- Run everything (all linters + unit tests): `tox`

When asked to "run the tests" (or similar), default to `tox -e py3` without waiting for further instruction.

```bash
# All linting and unit tests
tox

# Unit tests only
tox -e py3

# With coverage
tox -e py3-coverage,coveragereport

# Specific linters
tox -e pep8
tox -e pylint
tox -e yamllint

# Validate scenario search-expression timestamp constraints
tox -e hotyvalidate
```

Coverage must stay above **84%**.

### Key Dependencies
- `propertree` — YAML property tree evaluation
- `searchkit` — log/file search engine
- `click` — CLI framework
- `pyyaml`, `simplejson` — serialization
- `jinja2` — templating (markdown/html output)
- `cryptography`, `python-dateutil`, `pytz` — utility libraries

### Adding a New Plugin
1. Add Python primitives under `hotsos/core/plugins/<plugin>/`.
2. Add YAML defs under `hotsos/defs/scenarios/<plugin>/` and/or `hotsos/defs/events/<plugin>/`.
3. Add output class(es) under `hotsos/plugin_extensions/<plugin>/`.
4. Register the plugin import in `hotsos/plugin_extensions/__init__.py`.
5. Add unit tests under `tests/unit/`.

---

## Coding Conventions
- Python 3.8+
- PEP 8 style (flake8 enforced)
- Pylint enforced (see `pylintrc`)
- YAML files linted with `yamllint` (see `yamllintrc`)
- Shell scripts linted with `bashate`
- Do **not** print to stdout; use `log` (`hotsos/core/log.py`) for logging and `IssuesManager` for issues.
- Tests use `stestr` (unittest-compatible) under the hood, but always run them via `tox` (e.g. `tox -e py3`), never by calling `stestr` directly; fake data roots live in `tests/unit/fake_data_root/`.

---

## Useful Links
- Docs: https://hotsos.readthedocs.io/en/latest/
- Contributing guide: https://hotsos.readthedocs.io/en/latest/how-to/write-checks.html
- Install guide: https://hotsos.readthedocs.io/en/latest/how-to/install.html
