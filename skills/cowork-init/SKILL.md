---
name: cowork-init
description: Install or upgrade agent-co-work in a project and confirm the initial seat table with the user.
---

# Initialize a project

Read [cowork](../cowork/SKILL.md) for the collaboration rules.

Use the GitHub release `git@github.com:YitaoXU/agent-co-work.git` at `~/.agent-co-work`, one fixed clone per machine shared by all target projects. GitHub SSH access is required.

1. Work from the target project's root in the coordinator's own Herdr app tab, with `HC_TERMINAL_ID` and the tab's `herdr.space` label set. If `~/.agent-co-work` is missing, run `git clone git@github.com:YitaoXU/agent-co-work.git ~/.agent-co-work`; otherwise run `git -C ~/.agent-co-work pull --ff-only`. Use the environment's normal permissions for access to that clone and for `hc` during `--apply`.
2. For a fresh installation (no `cowork/cw`), run `python3 ~/.agent-co-work/bin/cw init`; for an existing installation, run `python3 ~/.agent-co-work/bin/cw init --upgrade`. Show the seat table, file plan and printed kit version (`kit: to <sha>` or `kit: from <old|unknown> to <sha>`) to the user. Check any warning about uncommitted kit changes or a development checkout before deploying.
3. Ask the user to confirm the table and plan or supply seat changes. For fresh-install changes, rerun the plan with `--seat seat=agent:model:effort:life` for each override; existing seats are preserved on upgrade (use `cowork-seat` for seat changes). Apply that exact init command with `--apply` only after the user's confirmation.
4. Inspect the resulting `cowork/seats.tsv`, pointers, initial coordinator record and `cowork/kit-version`. The version file records the release clone's full HEAD and origin URL, with HTTPS credentials removed. Run `cowork/cw lint` and compare its installed version with the plan.
5. An unchanged version prints no version-change line. Plain init never stamps an older project missing `cowork/kit-version`; only fresh installs and `--upgrade` write it. Always install or upgrade using `python3 ~/.agent-co-work/bin/cw` so the release clone supplies the skills and templates.
6. For a long effort, create `cowork/cw project new <name>` and prepare Direction and Plan through the core task loop. Create its first task with `cowork/cw new <task> --seat <seat> --kind task --project <name> --line main` and help fill its Goal and Brief.
