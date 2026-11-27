---
name: cowork-away
description: Prepare and run a user-approved task queue while the user is away, then report results, decisions, current work, and pending tasks on return.
---

# Work while the user is away

Use when the user says they will be away. Read [cowork](../cowork/SKILL.md) for records, approval commands, audits, scheduled checks, and handover; the coordinator owns this procedure.

1. **Window first.** Ask roughly how long the user will be away, their expected return, and what ends the window. Estimate each task's duration, reserve about 20% buffer, and order the queue to leave the most finished work. Include optional extra tasks for an early finish. At the expected return time, finish the current step, start nothing new, and keep checks running.
2. **Before.** Ask all questions now. Create `cowork/<date>/away.md` (`kind: task`, `seat: coordinator`, project as fits); its Brief is the away plan, with these sections:

```markdown
Window: <rough duration; expected return; what ends the window>
Queue with Briefs: <ordered tasks and optional extras; each duration and complete numbered Brief>
Pre-answers: <likely decisions per task, each with the user's answer or a rule>
Authorized actions: <actions pre-authorized by name, e.g. a named release push or server publish>
Limits: <tokens, GPU, time, cost>
```

3. **Approve once.** Show the formatted task list and full plan. The user's single "go" approves the plan and every listed Brief, including optional extras; use `cw set` to record `approved: user, <date> (away plan)` and `status: approved` on the away record and queued tasks. Begin only after that approval; start nothing outside the approved queue.
4. **During.** Ask no questions and request no approvals from the user. Apply a pre-answer and log `decided`. An unforeseen hard question (science, scope, budget, risk, a failed gate), or any deletion, data move, destructive Git, push, or external write not pre-authorized by name, parks the affected task: use `cw set` for `status: blocked`, write `BLOCKED:` in its State, and log `parked`. Continue independent queued tasks. For other unforeseen questions, take the reversible conservative choice and log `decided`.
   Keep State current. Scheduled checks and audit tiers apply unchanged; the coordinator accepts steps and drafts Wrap-ups. Tasks stop at `wrap-up`, never `closed`; Takeaways wait for the user.
   Append every decision, parked task, issue, completion, and check to `output/<date>/away/log.md`, one event per line:

```text
- <time> [decided|parked|issue|done|check] <task>: <what>; <evidence>
```

5. **Return.** On the user's next message, first send this summary in the user's language (per AGENTS.md), then continue. Translate the template headings for that response. Fill the away record's Wrap-up and set its status to `wrap-up` until the user answers; never infer their decisions.

```markdown
Window: <start to return>; Queue progress: <n/m completed>
1. Done
   <each task: result; evidence path>
2. Needs your decision
   1. <question; context; options; recommendation>
3. Decided for you
   <each pre-answer or default applied, for review>
4. Current phase
   <each running task: phase; next step; ETA>
5. Still pending
   <unstarted tasks; parked tasks with reasons>
```

6. **Handover continuity.** The away record is recovery context: preserve its approved plan, queue progress, pre-answers, named authorizations, limits, log path, and active checks in State/Handover. A successor reads that record and log and continues the same window and queue under [cowork's handover rules](../cowork/SKILL.md#size-limits-consolidation-and-handover).
