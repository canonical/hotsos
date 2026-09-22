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

### Data Root
`DataRootManager` (via `HotSOSConfig`) abstracts whether hotsos is running against a live host or an unpacked sosreport directory. All file reads and command executions go through this abstraction.

### Output Formats
Supported: `yaml` (default), `json`, `markdown`, `html`. Controlled via `--format` CLI flag.

The html output format uses the [Canonical Vanilla Framework](https://github.com/canonical/vanilla-framework) to provide a dashboard view Hotsos' output. Key information is shown towards the top of the page and more detail is available as you scroll down.

---

## Development Workflow

### Running Tests
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
- Tests use `stestr` (unittest-compatible); fake data roots live in `tests/unit/fake_data_root/`.

---

## Useful Links
- Docs: https://hotsos.readthedocs.io/en/latest/
- Contributing guide: https://hotsos.readthedocs.io/en/latest/how-to/write-checks.html
- Install guide: https://hotsos.readthedocs.io/en/latest/how-to/install.html
