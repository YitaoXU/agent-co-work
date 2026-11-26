---
name: cowork-seat
description: Change an agent-co-work seat, start or inspect its tasks, or perform coordinator handover.
---

# Operate a seat

Read [cowork](../cowork/SKILL.md) for seat selection, launch, approval, and handover rules.

1. Run `cowork/cw seats` and select the requested seat. Missing template-default seats remain available through fallback; `cw seat set` can append such a seat to an older project's table.
2. Follow [cowork-init's seat questions](../cowork-init/SKILL.md#initialize-a-project): outside the sandbox probe `command -v claude codex agy`, discover models and model-dependent efforts, and propose only installed CLIs (including single-CLI presets). Show the table and ask keep defaults / adjust seats; for adjustments ask each seat's default / type your own `agent model effort [life]`, listing valid values. Claude uses its question tool (at most four questions per call); other coordinators ask in chat. Include discussion when relevant, warn about missing CLIs, and confirm the full resulting table. Do not offer `ultra`.
3. Run `cowork/cw seat set [--args='...'] <seat> <agent> <model> <effort> [short|long]`; inspect its row and the caller's State. Omitted args preserve existing options; clear incompatible args with `--args=-` or replace them when switching adapters. Never set `-a never` seat-wide.
4. To launch a prepared task, inspect `cowork/cw start <taskfile> --print`, then run `cowork/cw start <taskfile>`.
5. Inspect progress with `cowork/cw check <taskfile>` or `cowork/cw status`; use `cowork/cw approve <t>` to inspect a blocked prompt under cowork's approval rules.
6. For handover, prepare the outgoing record's Handover section and run `cowork/cw handover context` or `cowork/cw handover tokens` under cowork.
7. In the successor session, read the outgoing record, `cowork/projects/`, and active tasks, run `cowork/cw handover --accept`, then inspect `cowork/coordinator.addr`.
