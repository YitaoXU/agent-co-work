These fixtures preserve prompt wording, option order and selection markers from live screens. Paths and account details are sanitized to neutral demo values; paired screens use the same non-symlinked path.

codex-trust.txt and agy-trust.txt: full `hc read --lines 0` captures (2026-11-25, Codex 0.172.0). claude-trust.txt and agy-cw-permission.txt: transcribed from live screens of the same day; the first line of claude-trust.txt is reconstructed, and the option lines are exact.
claude-trust-live.txt and agy-hc-send-permission.txt: full captures from live handover tests (2026-11-25).
claude-trust-run2-before.txt and claude-trust-run2-selected.txt: paired captures (2026-11-26). Navigation changed the selection but the immediate Enter calls did not confirm.
claude-trust-recheck2.txt: unchanged No-selected screen (2026-11-26). The first navigation call did not move the selection; both reads were identical.
