# Plan NNN: <title>, brief

Role: `<seat>`. Task file: `cowork/<yyyymmdd>/<task>.md`.

## Goal

State the question this answers or the deliverable it produces, and why it matters for the plan, in one or two sentences.

## Inputs

List exact paths, existing entry points, commits, and budgets; leave nothing the agent has to search for.

## Steps

1. **<location and path>** <action with the exact command>. Done when <observable condition has been used or verified>.
2. **<location and path>** <next action with the exact command>. Done when <observable condition has been used or verified>.

Write one action per step; name phase transitions and reports. Avoid "if needed", "as appropriate", and "consider"; decide every choice or give a default. Each gate states what it rules out and what happens on failure; calibrate stop thresholds against a control in the same setting.

## Stop and report if

List conditions whose outcome changes a conclusion or what runs next. At a stop, write `BLOCKED: <reason>` in the task's State and run `cowork/cw report "<conclusion>; <evidence path>"`.

## Outputs

List exact paths of all files this task writes, including records and durable evidence under `output/<yyyymmdd>/<task>/`.

## Completion summary

Fill `## Wrap-up` in the task record, whose path never moves, then run `cowork/cw report "<conclusion>; <evidence path>"`:

- Result: what was carried out and verified.
- Where: output paths, evidence, and commits.
- lesson: <one to three lesson lines>.
- Proposed next: the next action for the coordinator to review.
- User decision: pending until the user decides.
