---
name: cowork
description: Coordinate or perform a task in a project using agent-co-work seats, task records, and Herdr terminals.
---

# Collaboration rules

Read the project's AGENTS.md and follow its language conventions. Invoke the project CLI as `cowork/cw` (or with `--root`).
Read `hc --skill` and `herdr-app --skill` before using Herdr; use `hc` for agent lifecycle and messages, `herdr-app` only for what the user sees.

## Seats

`cowork/seats.tsv` assigns each seat's agent, model, effort, lifetime (`short`/`long`), and optional `args`; a task's `agent:` or `args:` overrides or extends it (use `-a never` only per task for unattended runs/tests, never seat-wide).
- `coordinator` (and `coordinator-alt` when tokens run low): discuss with the user, draft Direction/Plan/Briefs/Wrap-ups, coordinate, decide, and give final acceptance.
- `advisor`: review, propose alternatives, and cite evidence; never owns the plan.
- `coder-heavy` / `coder-light` / `auditor`: heavy handles cross-module, unclear, or critical-path work; light handles specified single-module, mechanical, or batch work; `auditor` runs fresh-session checks for high-risk changes.
Long seats launch parentless in the caller's `herdr.space` (sending no hc blocked/exit notes); run `cw status` on every report and scheduled check.

## Task loop

A project is a long effort, recorded in `cowork/projects/<name>.md`, owned by the coordinator: `status: active|closed`, Direction, Plan, Resources, Decisions. Standalone tasks may omit a project.
A task is a unit ending in a user decision: one feature, run, or analysis question with its synthesis; it may have one step or many and run on the main or side line.
A step is work inside a task: a review, implementation, audit, fix or check; record it in the task's State or a separate step file for another seat.
Use `kind: task|step|seat`, `project: <name>|-`, `line: main|side|-` and `draft -> approved -> running -> blocked (when needed) -> wrap-up -> closed`. Legacy `size: large|small|seat` and `debrief` / `## Debrief` remain readable.

1. Direction: the user and coordinator agree the project's Direction.
2. Plan: coordinator drafts the numbered tasks, consults the advisor as needed (recording adopted points and why), and discusses with the user; record user approval as a dated Decisions line.
3. Before every task: coordinator drafts its Brief (with advisor review as needed), then the user approves it (`approved: user, yyyy-mm-dd`, `status: approved`). No unapproved automatic continuation.
4. Run: coordinator dispatches steps and settles step-level questions. Hard questions (science, scope, budget, risk, a failed gate) go to the user before the affected work continues. Follow the review and acceptance rules below.
5. Wrap-up: coordinator drafts the Wrap-up (with advisor input as needed), sends the user a short conclusion-first summary (done, result, evidence path, next, decision needed), adjusts Direction/Plan after user decision, and records it.
6. Repeat from step 3 until the user closes the project; put durable conclusions in the project's own docs.

Multiple approved tasks may run in parallel, on either line; one task's Wrap-up does not block another approved task.
`cw start` requires a task's user approval and status approved/running/blocked; running or blocked tasks may relaunch. A worker step with a parent needs that parent to be an approved task with one of those statuses; advisor steps may run before approval to prepare the Plan and Brief. Standalone steps and seats are not task-gated.
Write a Goal and an unambiguous numbered Brief (action, done-condition meaning used/verified, defaults, named phase transitions, calibrated stop gates, outputs); cite project docs or plan links rather than restating them.
Carry out the Brief in order, settling routine step defaults and keeping State as a rolling summary (<=10 lines); before rolling up State, archive detailed history and CLI receipts verbatim to `output/<yyyymmdd>/<task>/log.md` and link it.
Finish each task with a Wrap-up (result, where, 1-3 `- lesson:` lines, proposed next, user decision); never infer the user's decision, and only the coordinator sets `status: wrap-up` or `closed` after acceptance.

## Resources

List only exclusive resources in the project's Resources section, one `<name>: <description>` per line; names match task names. Keep resource needs and estimated durations in Plan prose, not task headers. `cw new` never edits the Plan.
Treat separate exclusive phases as separate resources, for example `training-code` for merge/publish and `gpu` for allocation. CPU preparation can run while a GPU lock is held; resource locks do not gate `cw start`.
The coordinator sets one queue head with `cw lock next <resource> <task|->` (backlog in Plan; initial holder takes before queuing a successor). Workers check the host/resources before `take`; for phases needing another resource idle, reserve via `next`, acquire in fixed order, hold across failures, and advance `next` only after verification; locks never replace host guards.
The holder may `cw lock expect <resource> <time>` to notify the successor and coordinator; this is advisory and never permits early launch.
Release with `cw lock release <resource> [--evidence <path>] [--note <text>]`. Only a coordinator recovers a stale lock with `--force --holder <yyyymmdd/task>` (checked under lock); inspect `cw status` before any retry after exit `3` (mutated, delivery/receipt failed) or error.
Locks live in `cowork/locks/<resource>` across worktrees through `COWORK_ROOT`; the CLI serializes changes. Release frees the lock before notifications, preserves the queue head, and writes one State line to the caller with delivery outcomes. `cw status` flags closed/exited holders; it never frees them automatically.
Only the lock gates the successor's exclusive phase; record resource release, data return and task closure separately in State, each with time and an evidence path. Archiving remains a separate State entry.

## Records and messages

Project repos commit code, data, and living `docs/` by default; `cowork/`, `output/`, `.scratch/`, `.tmp/`, and `.worktrees/` are gitignored by fresh `cw init` (existing tracked repos keep their choice; projects may declare a "where things go" override in `AGENTS.md` without moving existing files merely to match defaults).
Daily records at `cowork/yyyymmdd/<task>.md` never move. Write structured task outputs, audit findings, and logs directly to `output/<yyyymmdd>/<task>/`; use `.scratch/` for host-local operational receipts, `.tmp/` for disposable scratch (never cite `.tmp/` as durable evidence; delete only after exporting needed evidence), and `docs/archive/` for merged superseded prose.
Executed outputs, logs, and receipts are never rewritten, renamed, or deleted; append `CORRECTION <date>: <what>; <evidence>; supersedes <line>` to a wrong record, and redo a wrong output as a newly named run stating what it supersedes.
Edit living conclusions and docs directly with a dated Wrap-up or Decisions note; never rerun passed acceptance (append corrections), never treat training/selection metrics as independent acceptance, and label untested layers explicitly.
An agent writes only its own task record and Brief-assigned outputs; shared living indexes default to coordinator integration from worker deltas unless a Brief names one writer.
Edit task headers only through `cw set`, and `cowork/coordinator.addr` only through `cw`.
At Wrap-up, the coordinator runs `cw index` and `cw lessons`, and confirms the day's Takeaways with the user.
Task and resource names match `[a-z0-9-]{1,20}`; terminal names are `yyyymmdd-<task>` (collision suffixes `-2`..`-9`, never truncated).
Use `cw start` to launch seats (handles adapter naming, startup retries, and one undelivered early-exit relaunch; never relaunches delivered or ambiguous starts; prints commands without `HC_TERMINAL_ID`).
Report with `cowork/cw report [--to <task>] "<conclusion>; <path>"` (evidence in files) only at stop conditions, named phase transitions, and completion; every other step goes only into `State`.
The coordinator reads the cited evidence before presenting conclusions and waits for `cw report`, not terminal `done` status (which can lag or fire early on `agy`).
An undelivered report appends `REPORT (undelivered):` to `State` and prints a relay line (never claim delivery); if blocked by a sandbox, retry outside the sandbox within normal permissions. A later matching delivery appends `REPORT (delivered):` without deleting the original failure receipt; `cw status` flags unresolved undelivered reports from State history.

## Code

- Keep code simple, general, and free of redundancy: extend the owning module, delete superseded code, keep compatibility code only for named retained artifacts, and keep case/run literals out of shared layers.
- Preserve compatibility of retained artifacts and comparability of evaluated runs: changes to core compute apply only to new runs, and runs record their code commit.
- Scale checks to the change; write necessary tests only (nontrivial pure logic, bug regressions, and preflight/end-to-end checks on critical paths rather than mocks alone; delete tests with superseded code; docs need link/lint checks, not code tests).
- Run jobs through shared project entry points with explicit stop/budget limits (no per-run wrapper scripts), activate the project environment in the same shell, and keep test/smoke outputs separated from real run outputs.

## Escalation and review

At a stop condition, write `BLOCKED: <reason>` in State and report to the coordinator.
The coordinator resolves step questions and takes hard questions to the user as specified in the task loop.
The coordinator may answer harmless in-project prompts for the user (project-root/assigned-worktree trust, reading files, running `cowork/cw`, running programs and tests inside the project); deletions, data moves, destructive Git, pushes, external writes, and any risky or unrecognized prompt go to the user without pressing keys.
Automation handles only verified deterministic dialogs (project-root trust, assigned-worktree trust during `cw start`, and plain `cowork/cw` commands); standalone `cw approve <t>` stays root-only; for other harmless prompts, read the full screen first (`hc read`) before answering.
On an unexpected failure, state-changing work (launches, shared environments, deleting or moving data) stops and reports; re-runnable work (tests, analysis, scratch outputs) fixes its own code and continues, stopping only at a decision gate, a frozen value, a shared dependency or a budget limit.
Check each detached long job using a monitoring schedule owned by its task (e.g. launchd or cron); these are the scheduled checks above, by default every 2 h and every 10 min near its end (user, 2026-11-26).
Record the schedule ID/path and target terminal in task outputs/State; re-point on seat replacement or handover, and cancel with verified removal at task close.
Never conclude that hardware or a service is missing from an error inside a sandbox; recheck in the intended execution context and record where the probe ran.
Every factual advisor statement cites a file path or command output; advisor reviews take at most two rounds, with unresolved hard disagreements going to the user.
Audit rigor matches change risk (coordinator gives final acceptance without rerunning passed audits):
- Records, docs, and routine plans: coordinator verifies links, facts, and citations directly (use a fresh auditor only for high-risk plans or claims).
- Ordinary code: worker runs relevant tests; coordinator reviews the diff and test output.
- Critical paths (training/sampling/scoring, releases, safety/approval/lock code): fresh-session `auditor` (never the author) runs code and writes findings to `output/<yyyymmdd>/<task>/`; coordinator accepts from those findings.
- Compute/GPU arms: pre-launch Brief/config review, worker early acceptance gate (e.g. first collection/checkpoint), no rerun of passed runs, and independent reading only for quantitative claims.
Coders and auditors never stage or commit; the coordinator commits after acceptance (user, 2026-11-25).
Workers never run destructive Git commands: `git reset --hard`, `git checkout -- .`, `git restore .`, `git clean`, or `git push --force`.
Prefer scope separation over worktrees: protect critical runtime scopes with a resource lock (one integrator at a time) and commit unlocked scopes with explicit paths (`git add <paths>`, never `git add -A`). Use `cw new --worktree` only when concurrent edits overlap files or need checkout isolation, and remove retired branches and worktrees promptly upon merge or task close.

## Size limits, consolidation, and handover

Run `cowork/cw lint`: caps are `Goal <=3`, `State <=10`, `Handover <=20`, project `Decisions <=20`, `lessons/README.md <=40`, `cowork/README.md <=60`, this skill `<=150`; review reported duplicates (>40 chars).
Summarize and archive every accumulating document promptly (never leave one to grow unbounded); run `cowork-consolidate` at task Wrap-up when caps near, weekly, or at project milestones:
- `State` -> roll up into `output/<yyyymmdd>/<task>/log.md` (verbatim CLI receipts first); project `Decisions` -> archive older lines to `cowork/projects/archive/<name>-history.md`; `lessons/README.md` -> distill weekly from daily `cowork/lessons/yyyymmdd.md` (roll older batches to `cowork/lessons/archive/yyyy-mm.md`).
- `docs/archive/` -> merge superseded prose drafts into dated rollups (never rewrite executed findings/receipts); `output/` -> distill conclusions into `docs/` and prune unreferenced intermediates only under project policy; agent memory -> promote durable rules to `docs/`/`AGENTS.md` and prune stale entries (`<=80` lines).
Initiate coordinator handover around 60% context use, after a Wrap-up, or at end of day: record recovery context in the outgoing `Handover` section and run `cw handover context` (same seat) or `cw handover tokens` (to/from `coordinator-alt`).
The successor uses its own seat file, reads the outgoing record, `cowork/README.md`, `cowork/projects/`, and active tasks, then runs `cw handover --accept` to take over `cowork/coordinator.addr` and notify the outgoing coordinator.
