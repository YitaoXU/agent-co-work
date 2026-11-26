---
name: cowork-init
description: Install or upgrade agent-co-work in a project and confirm the initial seat table with the user.
---

# Initialize a project

Read [cowork](../cowork/SKILL.md) for the collaboration rules.

Use one fixed clone of the GitHub release per machine, shared by all target projects. If absent, clone it with `git clone <repo-url> <kit-clone>`; `<kit-clone>` may be `$HOME/.agent-co-work`. Private repositories need SSH access. The development checkout is not for deployment.

1. From the target project, run `git -C <kit-clone> pull --ff-only`, then `python3 <kit-clone>/bin/cw init` and show its seat table, printed kit version and file plan to the user. Check any warning about uncommitted kit changes or a development checkout before deploying.
2. Ask the user to confirm the table or supply seat changes. For a change, rerun the plan with `--seat seat=agent:model:effort:life` for each override.
3. Once the table is confirmed, run that same command with `--apply`.
4. Inspect the resulting `cowork/seats.tsv`, pointers, initial coordinator record and `cowork/kit-version`. The version file records the release clone's full HEAD and origin URL, with HTTPS credentials removed. Run `cowork/cw lint` and compare its installed version with the plan's `kit: to <sha>`.
5. To update an existing installation, run `git -C <kit-clone> pull --ff-only`, inspect `python3 <kit-clone>/bin/cw init --upgrade` including `kit: from <old|unknown> to <sha>`, then apply that plan with `--apply`. Recheck `cowork/kit-version` and `cowork/cw lint`; an unchanged version prints no version-change line. Plain init never stamps an older project missing that file; only fresh installs and `--upgrade` write it.
6. For a long effort, create `cowork/cw project new <name>` and prepare Direction and Plan through the core task loop. Create its first task with `cowork/cw new <task> --seat <seat> --kind task --project <name> --line main` and help fill its Goal and Brief.
