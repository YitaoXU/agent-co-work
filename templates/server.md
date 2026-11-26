# Server access, transfers and shared Git history

Fill every placeholder and confirm the rules with the user before use. Read this before server access, transfers, Git or hardware use; it applies to both checkouts alongside skill `cowork`.

## 1. Server and working model

- SSH target: `{host}`; server checkout: `{server_root}`; shared branch: `{branch}`.
- Start each assigned Brief locally. For authorized server work, connect outside the sandbox with `ssh {host}`, then `cd {server_root}`, read the server's `AGENTS.md`, and follow it for subsequent work.
- Write server-side project content, including logs, caches and temporary files, only inside the server checkout.

## 2. Transfers

- Exclude `{large_files}` unless the user explicitly requests a named file; never transfer or Git-publish `{local_only}` paths.
- For `rsync`, use a separate `--exclude` for each excluded pattern. Exclude `._*` and `.DS_Store` from all transfers and disable macOS metadata copying (for example, `COPYFILE_DISABLE=1`). Remove only confirmed disposable metadata.
- Never delete a copy merely because it was excluded from a transfer; keep unrelated files in place.

## 3. Authoritative side per path

- Code, configurations, tests, tools and docs (including `AGENTS.md`, `CLAUDE.md`, Briefs and prompts) are local-owned: edit and commit locally, then publish through Git. Never edit them in the server checkout; tracked server-produced records use section 4.
- `{server_paths}` are server-owned: never edit them locally; track only small authored files allowed by the project's ignores. Never copy raw datasets, checkpoints, environments or caches locally.
- Mirror permitted server results one way, server to local, with a default 20 MB per-file cap and no `--delete`; exclude weights, optimizer states, videos, archives and arrays. The local mirror is read-only.
- `{local_only}` paths stay local and are ignored by the project repository; keep any pre-existing server copies in place. Kit-ignored `cowork/` and `output/` also stay local by default unless the project declares an override.
- Only one editor of the runtime scope at a time, holding its resource lock; the lock does not replace host/job guards. The server checkout changes only between jobs (section 4).
- If an untracked path differs between checkouts, report the conflict and keep both copies. Mirror an authorized move or rename as the same operation on the other side.

## 4. Shared Git history

- Both checkouts share branch `{branch}`; the local remote `server` points to the server checkout.
- Before publishing locally: `git fetch server && git merge server/{branch}`, then `git push server {branch}:incoming`. Pushing never changes the server working tree.
- On the server, verify no project job is running in the intended context, then apply only the published commit with `git merge --ff-only <commit>`; never update the checkout during a job.
- If refusal is solely because the server branch advanced, fetch, merge and publish again, then retry the fast-forward once. Stop and report conflicts, changes to code paths outside your assigned changes, or a second refusal; never force it.
- Jobs run only from the server main checkout, never a copied codebase or a separate runtime checkout. Before launch, fast-forward as above if needed, refuse a dirty runtime scope, and record each attempt's commit in its run evidence.
- The coordinator commits tracked server-produced records using explicit `git add <paths>`; `git diff --cached --stat` must show only assigned paths before committing. Never `git add -A`. Merge these records locally with the fetch/merge command above; kit-ignored records stay local by default.
- Keep temporary review/test worktrees under ignored `.worktrees/`; never run jobs there, and remove them after merge or task close.
- Forbidden: `git clean`, `git reset --hard`, `git checkout -- .`, `git restore .`, `git stash`, force pushes (including `git push --force`) and history rewrites.

## 5. Hardware

- Expected hardware: `{hardware}`. Treat this user-supplied baseline as unverified until probed outside the sandbox; recheck the host and allocation before execution.
- Probe the host name, visible devices, allocation, interconnect and driver in the intended execution context (for GPUs, include `hostname`, `CUDA_VISIBLE_DEVICES` and `nvidia-smi`). Record each probe's context, including whether it ran inside or outside the sandbox.
- A sandbox failure is inconclusive about host hardware or service availability. Repeat outside the sandbox within scope and permissions; reuse approvals and never bypass access controls. If access is unavailable or denied, report what could not be verified and record the restriction.
- After host access is confirmed, verify the framework's device build, runtime version and a small device operation before claiming runtime readiness; driver compatibility does not establish the installed framework runtime.
- Use only the authorized allocation; device visibility does not authorize occupying all devices, shared hardware is not exclusive, and device memory is per device. Record driver/runtime versions and measured peak device memory and throughput in run evidence.
