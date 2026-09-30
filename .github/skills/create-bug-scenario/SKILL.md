---
name: create-bug-scenario
description: >-
  Create a new hotsos scenario that detects a specific known bug or CVE and
  raises the appropriate issue, together with matching positive and negative
  test fixtures. Use when asked to "add a scenario for LP#<id>", "detect bug
  <id>", "add a check for CVE-<id>", or otherwise turn a known bug/CVE and its
  log/config signature into a hotsos check.
metadata:
  author: edward.hope-morley@canonical.com
  version: "0.1"
---

## Goal
Create a new hotsos scenario under `hotsos/defs/scenarios/<plugin>/` that detects
a specific known bug or CVE from its signature (log pattern, package version,
config value, service state, etc.) and raises the correct bug/CVE issue with an
actionable message. Add matching test fixtures under
`hotsos/defs/tests/scenarios/<plugin>/` that prove the scenario raises when the
signature is present and does not raise when it is absent or already fixed.

## Inputs required
Before starting, gather (ask the user if not provided):
- The bug/CVE tracker and ID (e.g. Launchpad `1934937`, CVE `2024-1234`).
- The affected plugin (e.g. `openstack`, `kernel`, `storage`, `openvswitch`).
- The signature that indicates the bug is present:
  - a log line regex and the log file/command it appears in, and/or
  - a package version boundary that contains the fix, and/or
  - a config value / service state.
- The recommended remediation to put in the message (e.g. upgrade a package).

## Scope
- New scenario: `hotsos/defs/scenarios/<plugin>/[<subdir>/]<name>.yaml`.
- New tests: `hotsos/defs/tests/scenarios/<plugin>/[<subdir>/]<name>.yaml`
  (positive) and `<name>_not_has_fix.yaml` / `<name>_fixed.yaml` (negative).
- Naming convention: use `lp<id>.yaml` for Launchpad bugs, `cve-<id>.yaml` for
  CVEs, or a short descriptive name for generic warnings.

## Instructions
1. Identify the correct issue type from `hotsos/core/issues/issue_types.py`:
   - Launchpad bug -> `type: LaunchpadBug`, `bug-id: <id>`.
   - Bugzilla -> `type: Bugzilla`, `bug-id: <id>`.
   - StoryBoard -> `type: StoryBoardBug`, `bug-id: <id>`.
   - Ceph tracker -> `type: CephTrackerBug`, `bug-id: <id>`.
   - Ubuntu CVE -> `type: UbuntuCVE`, `cve-id: <id>`.
   - Mitre CVE -> `type: MitreCVE`, `cve-id: <id>`.
   - If it is not a tracked bug/CVE, use the relevant plugin warning/error type.
2. Look at a nearby existing scenario in the same plugin dir and mirror its
   structure and conventions before writing anything new.
3. Write the scenario YAML using the DSL:
   - `vars:` — factor out the search `expr` and any shared message fragments.
   - `checks:` — one named check per signal. Common patterns:
     - log search: `input: var/log/<app>/*.log` with `expr: $expr`.
     - journalctl: `input: {command: journalctl}` with `search: {expr: $expr}`.
     - fix installed: `apt: {<pkg>: [{min: <version-with-fix>}]}`.
   - If the signature can persist in long-lived logs (e.g. syslog) after the
     fix is installed, gate the conclusion on `not: has_fix` so already-patched
     hosts do not raise.
   - `conclusions:` — set `decision:` to the check(s), and `raises:` with the
     issue `type`, `bug-id`/`cve-id`, an actionable `message`, and a
     `format-dict:` mapping any `{fields}` used in the message.
   - Set a sensible integer `priority:` when multiple conclusions can apply.
4. Write the message to the project quality bar (see the
   `conclusion-message-refiner` skill): a short problem description plus a clear,
   polite, actionable next step (start the action with "Please"; recommend
   upgrading to "the latest version" rather than a specific "fixed version").
5. Add search timestamp handling per the `search-constraint-timestamp-checker`
   skill if the check uses `constraints:` — the search expression must start
   with a capture of the log line's date.
6. Add the positive test fixture `hotsos/defs/tests/scenarios/<plugin>/<name>.yaml`:
   - `data-root: files:` — provide log/config content that matches the signature.
   - `data-root: copy-from-original:` — copy `sos_commands/date/date` (and any
     package listing such as `sos_commands/dpkg/dpkg_-l`) as needed.
   - `raised-bugs:` (or `raised-issues:`) — map the tracker URL to the expected
     message text.
   - Add `target-name: <name>.yaml` only when the test filename differs from the
     scenario filename.
7. Add at least one negative test that shares `target-name: <name>.yaml` and
   proves the scenario does NOT raise when:
   - the fix is installed (package version at/above the fix boundary), or
   - the signature is absent.
   Leave `raised-bugs:` / `raised-issues:` present but empty.
8. Run the affected plugin tests and confirm both the positive and negative
   tests pass:
   ```bash
   tox -e py3 -- tests.unit.test_<plugin>
   ```
9. Lint the new YAML:
   ```bash
   tox -e yamllint
   ```

## Output
A new scenario under `hotsos/defs/scenarios/<plugin>/` that raises the correct
bug/CVE issue with an actionable message when the signature is present, plus a
positive test that verifies it raises and a negative test that verifies it does
not raise once fixed/absent. All affected plugin tests and yamllint pass.
