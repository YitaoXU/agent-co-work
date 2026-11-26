---
name: cowork-consolidate
description: Collect daily agent-co-work lessons and consolidate weekly takeaways from task Wrap-ups (including legacy Debriefs).
---

# Consolidate records

Read [cowork](../cowork/SKILL.md) for ownership, record locations, and length limits.

1. Run `cowork/cw lessons [yyyymmdd]` for the requested day and inspect the source task links.
2. Discuss useful conclusions with the user and capture them in that day's Takeaways section.
3. For weekly consolidation, read the week's lesson files and the current `cowork/lessons/README.md`.
4. Merge equivalent takeaways into concise entries in the distilled README, retaining source links and distinct lessons; update Last consolidation with the date.
5. Run `cowork/cw index` and `cowork/cw lint`; inspect duplicate reports and revise redundant prose within the requested consolidation scope.
6. Report the changed lesson paths and any remaining cap violations.
