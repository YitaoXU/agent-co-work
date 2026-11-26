---
name: cowork
description: Coordinate or perform a task in a project using agent-co-work seats, task records, and Herdr terminals.
---

# Collaboration rules

Read the project's AGENTS.md and follow its language conventions; agy also loads AGENTS.md (verified by `agy -p` in the dry-run).
Read `hc --skill` and `herdr-app --skill` before using Herdr; use command help to verify flags.
Use `hc` for agent lifecycle and messages; use `herdr-app` only for what the user sees.
The project's executable is `cowork/cw`; invoke it from the project or use `--root`.

## Seats

`cowork/seats.tsv` selects the agent, model, effort, and lifetime for each seat.
- `coordinator`: Claude Code; discuss, approve scope with the user, coordinate, and give final acceptance.
- `coordinator-alt`: agy; substitute when Claude's tokens run low.
- `advisor`: agy; discussion, plans, writing, and negotiation with the coordinator.
- `coder-heavy`: Codex gpt-6-astra high; cross-module or unclear work, and training, sampling, or scoring paths.
- `coder-light`: Codex gpt-6.1-sol max; specified single-module or mechanical work, tests, and batch runs.
- `auditor`: Codex; independent audits that run code. Claude gives final acceptance only.
There is no dispatch seat. Choose the Codex tier by the work above, not merely its size.
The user may name the agent for a task; it overrides the seat line and the tier rules.
Short seats explicitly use `--parent <caller t-id>`; long seats use `--no-parent`. Both retain the caller's `herdr.space` label.
Parentless seats send no hc blocked/exit notes to the coordinator; run `cw status` whenever a report arrives and at each scheduled check.
Without the caller's space label, seats launch hidden with a warning.

## Task loop

A project is a long effort, recorded in `cowork/projects/<name>.md`, owned by the coordinator: `status: active|closed`, Direction, Plan, Resources, Decisions. Standalone tasks may omit a project.
A task is a unit ending in a user decision: one feature, run, or analysis question with its synthesis; it may have one step or many and run on the main or side line.
A step is work inside a task: a review, implementation, audit, fix or check; record it in the task's State or a separate step file for another seat.
Use `kind: task|step|seat`, `project: <name>|-`, `line: main|side|-` and `draft -> approved -> running -> blocked (when needed) -> wrap-up -> closed`. Legacy `size: large|small|seat` and `debrief` / `## Debrief` remain readable.

1. Direction: the user and coordinator agree the project's Direction.
2. Plan: coordinator and advisor negotiate the numbered tasks, then discuss with the user; record user approval as a dated Decisions line.
3. Before every task: coordinator and advisor draft its Brief, then the user approves it (`approved: user, yyyy-mm-dd`, `status: approved`). No unapproved automatic continuation.
4. Run: coordinator dispatches steps and settles step-level questions. Hard questions (science, scope, budget, risk, a failed gate) go to the user before the affected work continues. Follow the review and acceptance rules below.
5. Wrap-up: coordinator and advisor negotiate result, lessons and next work, discuss with the user, then adjust Direction and Plan and record the user's decision.
6. Repeat from step 3 until the user closes the project; put durable conclusions in the project's own docs.

Multiple approved tasks may run in parallel, on either line; one task's Wrap-up does not block another approved task.
`cw start` requires a task's user approval and status approved/running/blocked; running or blocked tasks may relaunch. A worker step with a parent needs that parent to be an approved task with one of those statuses; advisor steps may run before approval to prepare the Plan and Brief. Standalone steps and seats are not task-gated.
Write a Goal and a numbered Brief with an action and done-condition per step, named phase transitions, stop conditions, and outputs; a project plan link may supply these.
Carry out the Brief in order, keeping State current with one concise line per finished step.
Finish each task with a Wrap-up: result, where, 1–3 `- lesson:` lines, proposed next, user decision. Do not infer the user's decision; record it when received.

## Resources

List only exclusive resources in the project's Resources section, one `<name>: <description>` per line; names match task names. Keep resource needs and estimated durations in Plan prose, not task headers. `cw new` never edits the Plan.
Treat separate exclusive phases as separate resources, for example `training-code` for merge/publish and `gpu` for allocation. CPU preparation can run while a GPU lock is held; resource locks do not gate `cw start`.
The coordinator sets/clears one queue head with `cw lock next <resource> <task|->`. A worker runs its own fresh host/resource checks, then `cw lock take <resource>` immediately before an exclusive phase. Another holder or another queued task prevents taking the lock.
The holder may `cw lock expect <resource> <time>` to notify the successor and coordinator; this is advisory and never permits early launch.
The holder releases with `cw lock release <resource> [--evidence <path>] [--note <text>]`; evidence defaults to its task record, and note records any demonstrated blocking dependency. Only a coordinator seat may recover a stale lock using `--force`.
Locks live in `cowork/locks/<resource>` across worktrees through `COWORK_ROOT`; the CLI serializes changes. Release frees the lock before notifications, preserves the queue head, and writes one State line to the caller with delivery outcomes. `cw status` flags closed/exited holders; it never frees them automatically.
Only the lock gates the successor's exclusive phase; record resource release, data return and task closure separately in State, each with time and an evidence path. Archiving remains a separate State entry.

## Records and messages

Keep coordination records committed under `cowork/`; durable conclusions belong in the project's own docs.
Daily task records live at `cowork/yyyymmdd/task.md` and are never moved.
Executed outputs, logs and receipts are never rewritten, renamed or deleted; append `CORRECTION <date>: <what>; <evidence>; supersedes <line>` to a wrong record, and redo a wrong output as a newly named run, recording which run supersedes which.
Keep documents people normally read in the project's docs; put drafts, reviews, findings, logs and superseded versions in one archive folder (default `docs/archive/`).
Write new logs, traces and findings directly to that folder; never rename executed artifacts later.
At Wrap-up the coordinator moves or merges superseded prose drafts there (never task records) and notes the change in the Wrap-up or project Decisions.
Edit conclusions and docs directly, noting the change in a dated Wrap-up or project Decisions line; never rerun passed acceptance, and correct a wrong acceptance with an appended line. Monitoring metrics used for training or selection are never independent acceptance.
An agent writes only its own task record; implementation outputs follow its assigned Brief.
Change task header fields only through `cw set`.
Generate `cowork/README.md` with `cw index` and daily lessons' From tasks with `cw lessons`.
At each task Wrap-up the coordinator runs `cw lessons` and proposes the day's Takeaways for the user to confirm.
When `lessons/README.md` passes its cap, or in the first session of a week, the coordinator proposes `cowork-consolidate`.
Change `cowork/coordinator.addr` only through `cw`.
Use `yyyymmdd-<task>` for terminal and session names; task names match `[a-z0-9-]{1,20}`.
`cw start` adds collision suffixes `-2` through `-9`, then errors; never truncate names.
Claude names its session at launch; Codex and agy launch without a task, then wait, rename with `hc keys` (one key per character, `space`, then `enter`), wait, and receive the task. Only agy first gets a one-word turn; Codex has no opening turn and uses `--no-daemon`.
After a startup `unavailable` / "still starting" send error, read the screen before retrying with backoff for at most 60 seconds; read and stop on ambiguous delivery failures.
If an agent exits while its task is known to be undelivered, `cw start` removes its terminal record and relaunches once with the same name; a second early exit stops with the screen tail, and delivered or ambiguous tasks are never relaunched.
Report with `cowork/cw report "<conclusion>; <path>"`; keep supporting evidence in files.
Use `cw report --to <task> "<conclusion>; <path>"` for direct task reports copied to the coordinator; resolve the sender's day first, else the newest matching record, log both delivery results in the sender's State, and report only to the coordinator if the target has no live terminal.
A seat reports only at a stop condition, a phase transition named in its Brief, and completion; every other step goes only into its State.
Messages carry the task prefix; the coordinator reads the evidence before presenting conclusions.
Wait for the report message, not the agy status: its `done` can precede the end of generation.
Without `HC_TERMINAL_ID`, `cw start` prints commands without launching or changing records.
An undelivered report is appended to State and printed for the user to relay; do not claim delivery.

## Escalation and review

At a stop condition, write `BLOCKED: <reason>` in State and report to the coordinator.
The coordinator resolves step questions and takes hard questions to the user as specified in the task loop.
The coordinator uses `cw approve <t>` for a seat's folder-trust prompt for the exact project root or a permission prompt for a command starting with `cowork/cw` (user, 2026-11-25). Match the displayed option text; agy command permission uses "always allow in this conversation". Other or unrecognized prompts go to the user without pressing keys.
On an unexpected failure, state-changing work (launches, shared environments, deleting or moving data) stops and reports; re-runnable work (tests, analysis, scratch outputs) fixes its own code and continues, stopping only at a decision gate, a frozen value, a shared dependency or a budget limit.
Check each detached long job using a monitoring schedule owned by its task (e.g. launchd or cron); these are the scheduled checks above, by default every 2 h and every 10 min near its end (user, 2026-11-26).
On seat replacement or handover, re-point the schedule to the current seat; at task close, cancel it and verify removal.
Never conclude that hardware or a service is missing from an error inside a sandbox; recheck in the intended execution context and record where the probe ran.
Every factual advisor statement cites a file path or command output.
An auditor checks the advisor's facts before a user decision.
Advisor and coordinator negotiate for at most two rounds; remaining disagreements go to the user.
The auditor uses a fresh session, is never the author, runs code, and writes findings to a file.
The coordinator accepts from those findings without rerunning the audit.
Coders and auditors never stage or commit; the coordinator commits after acceptance (user, 2026-11-25).
Workers never run destructive Git commands: `git reset --hard`, `git checkout -- .`, `git restore .`, `git clean`, or `git push --force`.
Worktrees are required when two or more coders edit the same repository at once; a single coder works where its Brief says (default: main checkout). The coordinator creates required worktrees with `cw new <task> --seat <seat> --kind task|step --worktree`; those coders edit implementation files only in their assigned worktree and keep their task record in the main checkout. The coordinator commits and merges accepted worktrees.

## Size limits and handover

Run `cowork/cw lint`: Goal <=3 lines, State <=10, Handover <=20, lessons/README.md <=40, cowork/README.md <=60.
Keep this skill <=150 lines. Review exact duplicate lines longer than 40 characters reported by lint; frontmatter and literal template lines are excluded.
Initiate coordinator handover around 60 percent context use, after a Wrap-up, or at end of day.
Use `cw handover context` for a fresh Claude coordinator; tokens low uses `cw handover tokens` to coordinator-alt, and the same process hands back.
The outgoing coordinator records context in its own Handover section; successors use their own seat files.
A successor launches without a parent, accepts with `cw handover --accept`, and becomes the report address only then.
`cw handover --accept` sends acceptance to the previous coordinator and records delivery in the caller's State.
Confirm the address changed before considering the handover complete.
