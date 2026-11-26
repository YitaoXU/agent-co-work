---
name: cowork-seat
description: Change an agent-co-work seat, start or inspect its tasks, or perform coordinator handover.
---

# Operate a seat

Read [cowork](../cowork/SKILL.md) for seat selection, launch, approval, and handover rules.

1. Run `cowork/cw seats` and select the requested seat.
2. To swap its agent, run `cowork/cw seat set <seat> <agent> <model> <effort> [short|long]`; inspect the updated row and the caller's State entry.
3. To launch a prepared task, inspect `cowork/cw start <taskfile> --print`, then run `cowork/cw start <taskfile>`.
4. Inspect progress with `cowork/cw check <taskfile>` or `cowork/cw status`.
   Use `cowork/cw approve <t>` to inspect a blocked prompt under cowork's approval rules.
5. For handover, prepare the outgoing record's Handover section and run `cowork/cw handover context` or `cowork/cw handover tokens` as appropriate under cowork.
6. In the successor session, read the outgoing record, `cowork/projects/`, and active tasks, run `cowork/cw handover --accept`, then inspect `cowork/coordinator.addr`.
