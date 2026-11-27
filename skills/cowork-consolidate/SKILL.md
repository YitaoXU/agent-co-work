---
name: cowork-consolidate
description: Consolidate accumulating agent-co-work records, decisions, lessons, archives, outputs, and agent memory at length guidelines, Wrap-ups, weekly reviews, or milestones.
---

# Consolidate records

Read [cowork](../cowork/SKILL.md) for ownership, immutable evidence, and soft length guidelines. The coordinator integrates shared records; workers roll up only their own State and assigned outputs.

1. At weekly consolidation, run `cw lint` and raise its Git advisories with the user. Inspect the requested scope at task Wrap-up when length guidelines approach or are exceeded, weekly, or at project milestones. Inventory the classes below, their current counts, active constraints, and cited evidence before editing.
2. Preserve history first, then summarize. Keep dates, provenance, active decisions, outstanding blockers, and links to the original evidence. Never infer a user decision or rewrite an executed receipt.

| Class | Trigger / guideline | Consolidation action |
|---|---|---|
| Task State | Near 10 nonempty lines | Append detailed history and verbatim LOCK/HANDOVER/REPORT receipts to `output/<project>/<yyyymmdd>/<task>/log.md`, then keep a rolling summary and that link in State. Retain unresolved report receipts in State until delivery resolves them so `cw status` still flags them; keep milestone timestamps/evidence paths. Daily task files never move. |
| Project Decisions / Plan | Near 20 nonempty Decisions lines; milestone | Append older decisions verbatim to `cowork/projects/archive/<name>-history.md`; link it from Decisions, retain current constraints, prune completed Plan rows, and promote durable rules to `docs/`. |
| Lessons | Daily at Wrap-up; weekly or near 40 README lines | Run `cw lessons [yyyymmdd]`, inspect task sources, and discuss Takeaways with the user. Distill equivalent lessons into `cowork/lessons/README.md` with source links and Last consolidation date; remove rules now in docs/skills, roll older batches (e.g. over 30 days) into `cowork/lessons/archive/yyyy-mm.md`, and preserve source task Wrap-ups. |
| Overview / Goal / Handover | Before index/handover; guidelines 60 / 3 / 20 | Coordinator closes accepted finished tasks, then runs `cw index`: tasks and seats only, with steps counted on each parent task line; closed entries fall out after 7 days. Condense Goal and recovery context without moving daily records. |
| Prose archives | Wrap-up/milestone; advisory 10 loose drafts | Merge related superseded prose verbatim into dated `docs/archive/` rollups and note the merge in Wrap-up or Decisions. Executed findings, logs, and receipts remain at their original paths. |
| Outputs / scratch | Wrap-up/milestone; project storage policy | Distill conclusions into `docs/`, keep a short README per task output folder, and export needed `.tmp/` evidence before disposal. Prune unreferenced intermediates only under project policy or a user-approved manifest; cited executed evidence and receipts are protected. |
| Agent memory | Wrap-up/milestone or duplication; advisory 80 lines | Promote durable conventions to `docs/` or `AGENTS.md`, remove stale task pointers, and retain a compact index of active, non-obvious pointers. Verify memory against project docs and records. |

3. Run `cw index`, `cw lessons` for relevant days, and `cw lint`; review duplicate diagnostics and resolve redundancy only within the authorized scope. Regenerating lessons preserves Takeaways; confirm changed Takeaways with the user.
4. Report the changed paths, preserved history locations, remaining over-guideline warnings, and any cleanup that still needs a project policy or user decision.

Length and duplicate warnings are advisory: keep records concise and consolidate when over; they do not block index, init or lint. Invalid project/header/seat schemas, names and paths remain hard failures.
