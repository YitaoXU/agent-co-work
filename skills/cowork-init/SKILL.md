---
name: cowork-init
description: Install or upgrade agent-co-work in a project and confirm the initial seat table with the user.
---

# Initialize a project

Read [cowork](../cowork/SKILL.md) for the collaboration rules.

1. From the target project, run `python3 <kit-repo>/bin/cw init` and show its seat table and file plan to the user.
2. Ask the user to confirm the table or supply seat changes. For a change, rerun the plan with `--seat seat=agent:model:effort:life` for each override.
3. Once the table is confirmed, run that same command with `--apply`.
4. Inspect the resulting `cowork/seats.tsv`, pointers, and initial coordinator record. Run `cowork/cw lint`.
5. To update an existing installation, inspect `python3 <kit-repo>/bin/cw init --upgrade`, then apply that plan with `--apply`.
6. For a long effort, create `cowork/cw project new <name>` and prepare Direction and Plan through the core task loop. Create its first task with `cowork/cw new <task> --seat <seat> --kind task --project <name> --line main` and help fill its Goal and Brief.
