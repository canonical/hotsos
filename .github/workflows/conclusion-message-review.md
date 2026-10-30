---
description: Review new or changed hotsos scenario conclusion messages in a pull request.
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    paths:
      - "hotsos/defs/scenarios/**/*.yaml"
      - "hotsos/defs/scenarios/**/*.yml"
permissions:
  contents: read
  pull-requests: read
engine: copilot
checkout:
  fetch-depth: 0
  fetch: ["main"]
tools:
  github:
    toolsets: [pull_requests, repos]
  bash:
    - "git diff:*"
    - "git log:*"
    - "git show:*"
    - "git merge-base:*"
    - "git rev-parse:*"
    - "cat:*"
    - "grep:*"
safe-outputs:
  add-comment:
    max: 1
    hide-older-comments: true
timeout-minutes: 15
---

# Conclusion Message PR Review

Review the hotsos scenario conclusion (`raises/message`) values added or
modified in pull request #${{ github.event.pull_request.number }} of
${{ github.repository }}.

## Instructions

1. Read `.github/skills/conclusion-message-pr-reviewer/SKILL.md` and follow it
   exactly. It defines the scope (only messages added or modified in this PR),
   the quality criteria, the strictness policy and the required Markdown output.
2. Determine the change set with
   `git diff --name-only --diff-filter=AMR origin/main...HEAD -- 'hotsos/defs/scenarios/**/*.yaml' 'hotsos/defs/scenarios/**/*.yml'`
   and inspect the diff hunks of each changed file. Fall back to `main` if
   `origin/main` is not available.
3. This review is read-only. Do not edit any file and do not propose rewritten
   messages.
4. Post the review output produced by the skill as a single comment on the
   pull request using the `add_comment` safe output.
5. If the PR does not add or change any conclusion message, post the
   "No new or changed conclusion messages in this PR." output from the skill
   rather than calling `noop`.
