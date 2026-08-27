---
name: conclusion-message-refiner
description: >-
  Identifies check conclusions in text that are non-actionable or don't provide a short problem description.
  Use for check validation and to improve the quality of check conclusions.
metadata:
  author: marcin.wilk@canonical.com
  version: "1.0"
---

## Goal
The goal of this skill is to identify check conclusions that are non-actionable or don't provide a short problem description, and then improve them.

A good conclusion message must satisfy both criteria:
1. It has a short problem description (what is wrong, where relevant, in one or two sentences).
2. It is actionable (clear next step such as upgrade, verify config, fix service state, investigate a known bug/CVE, or collect specific evidence).

## Scope
Evaluate each YAML file (`.yaml` and `.yml`) in `../../../hotsos/defs/scenarios/` and all subdirectories.

For each file, inspect each `message` field under:
- `conclusions/<name>/raises/message`

There may be multiple conclusions per file.

## Supported Issue Types
Use the issue type names defined in `hotsos/core/issues/issue_types.py`.

### Bug/CVE types with online resources
If the raised type is one of the bug/CVE types below, use the ID fields to build the resource URL and use it to improve the message:

- `LaunchpadBug` + `bug-id` -> `https://bugs.launchpad.net/bugs/<bug-id>`
- `Bugzilla` + `bug-id` -> `https://bugzilla.redhat.com/show_bug.cgi?id=<bug-id>`
- `StoryBoardBug` + `bug-id` -> `https://storyboard.openstack.org/#!/story/<bug-id>`
- `CephTrackerBug` + `bug-id` -> `https://tracker.ceph.com/issues/<bug-id>`
- `UbuntuCVE` + `cve-id` -> `https://ubuntu.com/security/<cve-id>`
- `MitreCVE` + `cve-id` -> `https://www.cve.org/CVERecord?id=<cve-id>`

When a URL is available, use it to better understand the bug/CVE impact and preferred remediation language. Keep the final message concise and avoid copying long tracker text.

### Non-bug issue types
Also support operational warning/error types from the same file (examples):
- `SystemWarning`, `KernelError`, `KernelWarning`, `MemoryWarning`
- `OpenStackError`, `OpenstackWarning`, `OpenstackError`
- `OVNError`, `OVNWarning`, `OpenvSwitchWarning`
- `CephWarning`, `CephError`, `CephMonWarning`, `CephOSDError`, `CephOSDWarning`, `CephCrushWarning`, `CephCrushError`, `CephMapsWarning`, `CephRGWWarning`, `CephMgrError`, `CephDaemonWarning`, `CephDaemonVersionsError`, `CephHealthWarning`
- `JujuWarning`, `RabbitMQWarning`, `KubernetesWarning`, `KubernetesError`, `PacemakerWarning`, `MySQLWarning`, `LXDWarning`, `MAASWarning`, `MicroCloudWarning`, `VaultWarning`, `SSSDWarning`, `SOSReportWarning`, `SysCtlWarning`, `NFSNameResolutionError`, `BcacheWarning`, `SmartCtlWarning`, `NetworkWarning`

For these types, produce actionable text from scenario context and message variables (for example package/version placeholders, services, thresholds, host roles).

## Decision Rules
Classify each message:

1. Actionable + short problem description -> keep unchanged unless clarity can be improved materially.
2. Actionable but not short -> rewrite to be concise.
3. Short but not actionable -> rewrite to add clear next steps.
4. Neither short nor actionable -> rewrite fully.

## Strictness Policy
Use a strict, high-confidence policy and prefer false negatives over false positives.

Only modify a message when there is strong evidence it fails criteria. If evidence is weak or ambiguous, keep the original message unchanged.

### Strong Evidence Criteria
Treat evidence as strong when one or more of these are true:

1. The message is generic and non-descriptive (for example: "known bug identified").
2. The message is bug/CVE related and lacks an explicit, inline actionable next step (for example an upgrade, verification, config fix, or "see the bug for the workaround"). Naming a specific problem is NOT sufficient on its own: the attached resource URL is a reference, not a substitute for telling the reader what to do. A bug/CVE message that describes the problem but ends without an action verb directed at the reader is strong evidence and must be rewritten to add the missing next step, while preserving the existing problem detail. Only keep such a message unchanged when it already contains a clear reader-directed action (for example "Please upgrade ...", "See the bug for the workaround").
3. The message is composed mostly of placeholders and does not itself communicate problem + action.
4. The message is clearly missing either:
  - a short problem statement, or
  - an actionable next step.

Do not modify a message only because style can be improved. In strict mode, style-only rewrites are out of scope.

## Rewrite Rules
When rewriting `raises/message`:

1. Keep all variable placeholders exactly as-is (e.g. `{version}`, `{package}`, `{bad_meta_osds}`).
2. Preserve factual scope from scenario logic; do not invent conditions not present in checks/decision.
3. Keep message length typically to 1-3 sentences.
4. Include:
   - Problem statement first.
   - Why it matters (impact/risk) second, if needed.
   - Recommended action third (upgrade, validate config, restart/fix service, follow linked bug/CVE guidance, etc.).
5. For bug/CVE types, include explicit action such as upgrading or following tracker security guidance.
6. When the recommended action is a package/charm/service upgrade, phrase it as upgrading "to the latest version". Do not tell the reader to upgrade "to a fixed version" or "to a version that includes the fix": the exact fixed version is environment-specific and the reader cannot look it up from the message, whereas "the latest version" is always unambiguous and actionable, and the linked bug/CVE resource already documents the specific fix.
7. Do not remove critical identifiers such as bug IDs/CVE IDs.

## Context Preservation Rules
Before rewriting any message, build a context bundle from three sources and use all of them:

1. Original `raises/message` text.
2. Placeholder semantics from `raises/format-dict` and referenced `vars`.
3. External bug/CVE resource derived from issue type + ID.

Extract and preserve key context from the original message, such as:

1. Affected component/service (for example `neutron l3-agent`).
2. Affected behavior/feature (for example `dvr floating ips`).
3. Impact qualifier (for example `critically impacts`, `breaks`, `fails`).

Rewrites that drop key context are not allowed.

### Anti-Generic Rewrite Rule
Do not replace a specific message with a generic sentence that only says the bug/CVE exists.

For bug/CVE rewrites, the new message must contain:

1. Bug/CVE identifier context.
2. At least one specific problem detail from the original message (or equivalent detail confirmed by the external resource).
3. A clear remediation action.

If item (2) cannot be preserved with high confidence, keep the original and report as skipped.

### Message Composition Quality
The rewritten message must read as clean, natural prose, not as an original sentence with a boilerplate tail stapled on. Awkward output is a strong signal the rewrite logic is wrong.

1. Do not produce doubled punctuation (for example `ips.. This is`). If the preserved fragment already ends with `.`, `!`, or `?`, do not add another terminator before continuing.
2. Integrate the remediation action into the sentence flow rather than appending a fixed generic phrase to every message. Vary phrasing so it fits the specific problem.
3. Do not repeat the same clause twice (for example listing the affected feature in both a lead-in and a trailing phrase).
4. If the original already ends with a clear action (for example "Please upgrade...", "See the bug for the workaround"), keep that action and avoid adding a second, redundant one.
5. Prefer referring to the issue by its human identifier (for example `LP1883089`, `CVE-2024-3250`) inline, and rely on the emitted `resource` URL for the link rather than pasting long tracker text.
6. When recommending an upgrade, say "upgrade ... to the latest version" rather than "to a fixed version" or "to a version that includes the fix". The reader cannot derive the specific fixed version from the message, so those phrasings are not actionable; "the latest version" is, and the linked resource supplies the fix detail.
7. Always place the word "Please" (or "please") immediately before the verb that instructs the reader's next action. This applies to every actionable recommendation in the message — upgrades, verifications, investigations, restarts, checks, etc. The reader should see a polite directive, not a bare imperative. For example write "Please upgrade ..." instead of "Upgrade ...", and "Please check ..." instead of "Check ...".

## Variable Integrity Checks
For every message, parse referenced placeholders of the form `{name}` from `raises/message`.

When placeholders exist:

1. Locate their context in the same conclusion, especially `raises/format-dict`.
2. Preserve every referenced placeholder in the refined message.
3. Do not drop, rename, or introduce conflicting placeholders.
4. Keep placeholders semantically aligned with their original meaning from `format-dict` and surrounding conclusion context.

When no placeholders exist:

1. Do not add new placeholders unless they already exist in the same conclusion context and are required for correctness.

Validation rule before finalizing a rewrite:

1. `set(placeholders_in_new_message)` must include all placeholders found in the original message.
2. If the check fails, reject the rewrite and keep the original message.

### Placeholder-Only Message Handling
Some messages are intentionally composed from placeholders (for example `{version} {msg_common}`) where meaning is provided by `format-dict` or `vars`.

For these messages:

1. Expand context from `conclusions/<name>/raises/format-dict` and referenced `vars` before deciding whether the message is actionable.
2. If a rewrite is needed, preserve all original placeholders in the rewritten message.
3. Do not replace placeholder-based content with fully literal text that drops placeholders.
4. If preserving placeholders would make the rewrite incorrect or unclear, keep the original message and report it as a skipped modification with reason.

For placeholder-only bug/CVE messages, prefer augmenting the existing placeholder structure (while preserving placeholders) over replacing it with a fully literal sentence.

## File Update Behavior
If asked to apply changes, update only `raises/message` fields that fail the criteria.

Do not change:
- `type`
- `bug-id` or `cve-id`
- `format-dict`
- decision/check logic

In strict mode, if uncertain, do not change.

## Keeping Unit Test Fixtures In Sync
Each scenario has matching test fixtures under `../../../hotsos/defs/tests/scenarios/` that assert the exact message a conclusion raises. If you change a scenario `message` but not its fixtures, the unit tests fail. Whenever you actually apply a message change, update the fixtures in the same pass.

How fixtures reference messages:

1. A fixture usually lives at the same relative path as the scenario (for example scenario `openstack/neutron/bugs/lp1883089.yaml` maps to fixture `tests/scenarios/openstack/neutron/bugs/lp1883089.yaml`).
2. One scenario can have several fixtures (pass/fail/variant files in the same directory, sometimes with suffixes like `_fail`, `_pass`, `_2`). Check every fixture in that directory, not just the identically named one.
3. Bug/CVE conclusions assert under `raised-bugs:`, keyed by the resource URL (the same URL you emit in `resource`).
4. Non-bug conclusions assert under `raised-issues:`, keyed by the issue type name (for example `MemoryWarning`).

Critical detail — fixtures store the RENDERED message:

1. Placeholders are already substituted with the mock values defined in that fixture (for example `{version}` appears as `3.4.1`, not as `{version}`).
2. So you cannot copy your new scenario message verbatim. Render it: read the fixture's `mock`/`data-root` values and the scenario `format-dict` to compute what each placeholder resolves to, then write the substituted text.
3. If a placeholder resolves from `vars` (a static string), substitute that static value.
4. Preserve the fixture's YAML style (for example `>-` folded blocks) so only the message text changes.

Update procedure when applying a change:

1. Locate every fixture that contains the OLD rendered message for the affected conclusion (search by the resource URL for bugs, or by issue type + old text for issues).
2. Replace only the message value with the rendered version of the new message, keeping the URL/issue-type key unchanged.
3. Leave fixtures with `# none expected` untouched — they assert that nothing is raised.
4. Report each fixture you changed alongside the scenario change, so the mapping is auditable.

Add a `## Updated Test Fixtures` Markdown section to the output when fixtures are changed:

```markdown
## Updated Test Fixtures
- scenario: <relative scenario yaml path>
  conclusion: <conclusion key>
  fixture: <relative fixture path under hotsos/defs/tests/scenarios/>
  key: <resource URL or issue type used as the fixture key>
  old_rendered_message: <previous rendered message>
  new_rendered_message: <updated rendered message with placeholders substituted>
```

In dry-run mode, still list the fixtures you WOULD update in this section so the reviewer can see the full blast radius without any files being modified.

## Required Output
The skill must output a list of modified conclusions/checks and the reason for each change.

Output must be Markdown only. Do not output JSON, YAML, CSV, HTML, or mixed formats.

Use this format:

```markdown
## Modified Conclusions
- file: <relative yaml path>
  conclusion: <conclusion key>
  issue_type: <raises.type>
  evidence: <strong evidence used to justify modification>
  preserved_context: <key context retained from old message and/or resource>
  reason: <why previous message was non-actionable and/or lacked short problem description>
  old_message: <previous message>
  new_message: <updated message>
  placeholders_old: <list of placeholders in old message>
  placeholders_new: <list of placeholders in new message>
  placeholder_check: <"pass" if all old placeholders are present in new message; otherwise "fail" and keep original>
  resource: <bug/CVE URL if applicable, otherwise "n/a">
```

If any potential rewrite is rejected by strictness or placeholder validation, include this Markdown section:

```markdown
## Skipped Conclusions
- file: <relative yaml path>
  conclusion: <conclusion key>
  issue_type: <raises.type>
  reason: <why this was skipped>
  missing_context: <key context that could not be preserved confidently>
  old_message: <previous message>
  placeholders_old: <list of placeholders in old message>
  candidate_new_message: <proposed rewrite that was rejected>
  placeholders_candidate_new: <list of placeholders in candidate rewrite>
  placeholder_check: fail
```

If no changes are needed, output:

```markdown
## Modified Conclusions
No conclusions required updates.
```

## Examples of Non-Actionable Conclusions

### Example 1

```
message: >-
  The following certificates will expire in less than {apache2-certificates-days-to-expire} days:
  {apache2-certificates-path}
```

### Example 2

```
message: >-
  This node is running OpenStack nova-compute and Masakari but
  pacemaker-remote is not currently installed and is a
  requirement for Masakari to function correctly.
```

## Examples of Actionable Conclusions

### Example 1

```
message: >-
  The version of OpenStack Cinder ({version}) running on this host is
  impacted by regression LP2085851. There is a fix available in the Ubuntu
  archives and upgrading is recommended. Please check the bug description
  for more information.
```

## Examples of Conclusions without Short Problem Descriptions

### Example 1

```
message: known nova bug identified
```

## Examples of Conclusions with Short Problem Descriptions

### Example 1

```
message: >-
  OpenStack Nova has vGPUs enabled and the installed version ({version})
  has a known bug that can critically impact the nova-compute service.
  Please upgrade to resolve this issue.
```

## Example Rewrite

Before:

```yaml
raises:
  type: MitreCVE
  cve-id: CVE-2024-12084
  message: "known vulnerability detected"
```

After:

```yaml
raises:
  type: MitreCVE
  cve-id: CVE-2024-12084
  message: >-
    Installed package '{package}' version {version} is affected by
    CVE-2024-12084. Please upgrade '{package}' to the latest version and
    verify the fix from the CVE advisory.
```



