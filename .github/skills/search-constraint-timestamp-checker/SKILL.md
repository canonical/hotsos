---
name: search-constraint-timestamp-checker
description: >-
  Review all hotsos scenarios, identifying checks that use search constraints and ensure that the search expression starts with a regex pattern to match the year, month, day parts of the timestamp. If the regular expression does not contain this, add it to the expression. Also add a matching "_old_logs" negative test for each so we have coverage that the constraint filters old log lines out.
metadata:
  author: edward.hope-morley@canonical.com
  version: "1.1"
---

## Goal
Review all hotsos scenarios, identifying checks that use search constraints and ensure that the search expression starts with a regex pattern to match the year, month, day parts of a log line timestamp. If the regular expression does not contain this, add it to the expression. Also ensure each such scenario has a corresponding negative test proving the constraint filters old/out-of-window log lines out.

## Scope
Check all files under hotsos/defs/scenarios. Tests live under hotsos/defs/tests/scenarios.

## Instructions
1. Identify all scenarios that search input and apply "constraints:".
2. If the input is from "command: journalctl" then check the search expression used in these scenarios and ensure that they start with a regex pattern to match the year, month, day parts of an ISO 8601 formatted timestamp.
3. If the input is from file then check that the search expression matches a timestamp at the start of each line.
4. For each scenario covered above, ensure a negative test exists that proves the constraint filters out non-qualifying log lines. Do NOT add these extra "filtered" log lines to the existing (positive) test. Instead:
   - Keep the existing positive test unchanged: its logs are within the constraint and it still raises the expected bug/issue.
   - Create a new test file alongside it named "<test-name>_old_logs.yaml" that mirrors the positive test but makes exactly two changes: (a) change the log timestamps so they fall outside the constraint, and (b) expect no bug/issue to be raised (leave the "raised-issues:" / "raised-bugs:" key present but empty).
   - The new file must set "target-name: <scenario>.yaml" so it runs against the same scenario.
   - Choose out-of-window timestamps according to the constraint type:
     * age-based (search-result-age-hours): shift every matching log line to a date older than the age window relative to the test's reference date (the mocked/copied `sos_commands/date/date`, defaulting to the fake data root date).
     * period-only (search-period-hours + min-results, no age): spread the matching log lines far enough apart in time that no single period window reaches min-results.
   - If an equivalent negative already exists (e.g. an existing "_old_logs" or "_outside_time" test, or a scenario whose only constraint is "min-results: 1" which cannot be filtered by time), no new file is needed.
5. Run the affected plugin tests to confirm positive tests still raise and the new "_old_logs" tests do not (e.g. `tox -epy3 -- tests.unit.<plugin>`).

## Output
All scenarios covered by the above use search expressions which, when matched, produce results whose first result group is the date of the log line, and each has a positive test plus a negative "_old_logs" test that verifies the timestamp constraint is applied.
