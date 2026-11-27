"""Read-only hygiene integration tests against disposable local Git repositories."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock, skipUnless

REPO = Path(__file__).resolve().parents[1]
CW = REPO / 'bin/cw'
loader = importlib.machinery.SourceFileLoader('cw_git_checks', str(CW))
spec = importlib.util.spec_from_loader(loader.name, loader)
cw_module = importlib.util.module_from_spec(spec)
loader.exec_module(cw_module)


@skipUnless(shutil.which('git'), 'Git fixtures require git')
class GitChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cw-git-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'project with spaces'
        self.root.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('HC_', 'COWORK_', 'GIT_'))}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='fixture@localhost',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='fixture@localhost',
                        PYTHONDONTWRITEBYTECODE='1')
        self.cw('init', '--apply')

    def cw(self, *args, env=None):
        result = subprocess.run([sys.executable, str(CW), '--root', str(self.root), *map(str, args)],
                                cwd=self.root, env=env or self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def git(self, *args, env=None, root=None):
        result = subprocess.run(['git', '-C', str(root or self.root), *map(str, args)],
                                env={**self.env, **(env or {})}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def repo(self):
        self.git('init', '--quiet', '-b', 'trunk')
        self.git('commit', '--quiet', '--allow-empty', '-m', 'Initial fixture')

    def record(self, name, status='running', worktree=None):
        self.cw('new', name, '--kind', 'step', '--seat', 'worker-heavy')
        path = self.root / 'cowork' / cw_module.today() / (name + '.md')
        self.cw('set', path, f'status={status}', f'worktree={worktree or ".worktrees/" + name}')
        return path

    def worktree(self, path, branch=None):
        self.git('worktree', 'add', '--quiet', *(['-b', branch] if branch else ['--detach']), path)
        return Path(path)

    def snapshot(self):
        # Git metadata and bytes must be unchanged by both inspection commands.
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in (self.root / '.git').rglob('*') if p.is_file()}

    def git_lines(self, output):
        return [line for line in output.splitlines() if 'git (trunk=' in line]

    def test_categories_grouping_dirty_counts_and_read_only(self):
        self.repo()
        outside = self.worktree(self.root.parent / 'outside "copy"', 'outside')
        inside = self.worktree(self.root / 'review copies' / 'inside', 'inside')
        orphan = self.worktree(self.root / '.worktrees/orphan', 'orphan')
        closed = self.worktree(self.root / '.worktrees/closed', 'closed')
        self.record('closed', 'closed')
        gone = self.worktree(self.root / '.worktrees/gone', 'gone')
        shutil.rmtree(gone)  # Only disposable fixtures, to create a prunable entry.
        gone.mkdir()  # A leftover directory is not a live checkout; don't inspect its parent repo.
        (outside / 'new file').write_text('changed')
        self.git('branch', 'merged-unused')
        before = self.snapshot()
        status = self.cw('status')
        self.assertEqual(len(self.git_lines(status)), 1)
        for label in ('1 prunable', '1 outside root', '1 outside .worktrees/',
                      '5 merged worktree', '2 missing task', '1 closed task',
                      '1 merged branch without worktree'):
            self.assertIn(label, status)
        lint = self.cw('lint')
        lines = self.git_lines(lint)
        self.assertEqual(len(lines), 6, lint)
        for path in (outside, inside, orphan, closed, gone):
            line = next(line for line in lines if repr(str(path)) in line)
            self.assertIn('merged worktree', line)
            if path != gone:
                self.assertIn('uncommitted=' + ('1' if path == outside else '0'), line)
            else:
                self.assertNotIn('uncommitted=', line)
        self.assertIn('Validation OK; 6 over guideline.', lint)
        self.assertNotIn('Caps OK.', lint)
        self.assertEqual(before, self.snapshot())

    def test_active_worktrees_and_reserved_branches_excluded(self):
        self.repo()
        for name in ('live', 'reserved'):
            self.record(name)
        self.worktree(self.root / '.worktrees/live', 'custom-live')
        self.git('branch', 'reserved')
        self.assertEqual(self.git_lines(self.cw('status')), [])
        self.assertIn('Caps OK.', self.cw('lint'))
        # A live task is still reported for a location-policy violation, without
        # the merged label; matching uses its explicit header, not its task name.
        path = self.root / 'other/checkout'
        self.record('explicit', worktree=str(path))
        self.worktree(path, 'explicit-branch')
        line, = self.git_lines(self.cw('lint'))
        self.assertIn('outside .worktrees/', line)
        self.assertNotIn('merged worktree', line)

    def test_detached_worktree_and_newest_named_task_record(self):
        self.repo()
        self.worktree(self.root / '.worktrees/reused')
        record = self.record('reused')
        older = self.root / 'cowork/20000101/reused.md'
        older.parent.mkdir()
        older.write_text(cw_module.edit_header(record.read_text(), {'status': 'closed'}, older))
        self.assertEqual(self.git_lines(self.cw('lint')), [])
        self.cw('set', record, 'status=closed')
        line, = self.git_lines(self.cw('lint'))
        self.assertIn('merged worktree, closed task', line)

    def test_unmerged_stale_threshold_and_current_root_branch(self):
        self.repo()
        base = self.git('rev-parse', 'HEAD')
        for name, age in (('stale', 8), ('recent', 6)):
            self.git('switch', '--quiet', '-c', name, base)
            stamp = str(int(time.time()) - age * 86400) + ' +0000'
            self.git('commit', '--quiet', '--allow-empty', '-m', name,
                     env={'GIT_AUTHOR_DATE': stamp, 'GIT_COMMITTER_DATE': stamp})
        self.git('switch', '--quiet', 'trunk')
        line, = self.git_lines(self.cw('lint'))
        self.assertIn("branch 'stale': stale unmerged branch (>7 days; not removable)", line)
        self.assertNotIn('merged branch without worktree', line)
        self.assertNotIn('recent', line)
        self.git('switch', '--quiet', 'stale')
        lines = self.git_lines(self.cw('lint'))
        self.assertTrue(all('trunk=stale' in line for line in lines))
        self.assertTrue(any("branch 'trunk': merged branch without worktree" in line for line in lines))
        self.assertFalse(any("branch 'stale':" in line for line in lines))

    def test_detached_root_skips_ancestry_but_retains_location_findings(self):
        self.repo()
        self.worktree(self.root / 'review')
        self.git('switch', '--quiet', '--detach')
        line, = self.git_lines(self.cw('lint'))
        self.assertIn('detached HEAD; ancestry skipped', line)
        self.assertIn('outside .worktrees/', line)
        self.assertNotIn('merged worktree', line)

    def test_non_git_missing_git_and_unborn_roots_are_quiet(self):
        self.assertEqual(self.git_lines(self.cw('status')), [])
        self.assertIn('Caps OK.', self.cw('lint'))
        self.git('init', '--quiet', '-b', 'trunk')
        self.assertEqual(self.git_lines(self.cw('status')), [])
        self.assertIn('Caps OK.', self.cw('lint'))
        env = {**self.env, 'PATH': str(self.root / 'no-binaries')}
        self.assertEqual(self.git_lines(self.cw('status', env=env)), [])
        self.assertIn('Caps OK.', self.cw('lint', env=env))

    def test_nested_project_does_not_report_main_checkout_outside_root(self):
        self.repo()
        self.root = self.root / 'nested project'
        self.root.mkdir()
        self.cw('init', '--apply')
        self.assertEqual(self.git_lines(self.cw('status')), [])
        self.assertIn('Caps OK.', self.cw('lint'))

    def test_status_never_queries_each_worktree_and_all_queries_read_only(self):
        self.repo()
        other = self.worktree(self.root / '.worktrees/missing')
        run = subprocess.run
        calls = []
        def observed(argv, **kwargs):
            calls.append(argv)
            return run(argv, **kwargs)
        with mock.patch.object(cw_module.subprocess, 'run', side_effect=observed):
            cw_module.git_hygiene(self.root)
        self.assertTrue(calls)
        for argv in calls:
            self.assertEqual(argv[:4], ['git', '--no-optional-locks', '-C', str(self.root)])
            self.assertIn(argv[4], ('rev-parse', 'worktree', 'symbolic-ref', 'for-each-ref', 'merge-base'))
            if argv[4] == 'worktree':
                self.assertEqual(argv[5:], ['list', '--porcelain', '-z'])
        calls.clear()
        with mock.patch.object(cw_module.subprocess, 'run', side_effect=observed):
            cw_module.git_hygiene(self.root, dirty=True)
        self.assertTrue(any(argv[3] == str(other) and argv[4] == 'status' for argv in calls))
        self.assertTrue(all(argv[1] == '--no-optional-locks' for argv in calls))

    def test_dirty_rename_counts_one_change(self):
        self.repo()
        path = self.worktree(self.root / '.worktrees/rename')
        (path / 'old').write_text('content')
        self.git('add', 'old', root=path)
        self.git('commit', '--quiet', '-m', 'File fixture', root=path)
        self.git('mv', 'old', 'new', root=path)
        line, = self.git_lines(self.cw('lint'))
        self.assertIn('uncommitted=1', line)
        self.assertNotIn('merged worktree', line)

    def test_close_warns_for_path_registration_or_branch_and_still_closes(self):
        self.repo()
        record = self.record('kept')
        path = self.worktree(self.root / '.worktrees/kept', 'custom-kept')
        output = self.cw('set', record, 'status=closed')
        self.assertIn('Warning: closing task with remaining worktree/branch', output)
        self.assertIn('custom-kept', output)
        self.assertEqual(cw_module.header(record.read_text())[0]['status'], 'closed')
        self.git('worktree', 'remove', path)
        # The standard branch name remains detectable without registration.
        self.git('branch', 'kept')
        self.assertIn('branches: kept', self.cw('set', record, 'status=closed'))
        self.git('branch', '-d', 'kept')
        self.assertNotIn('Warning:', self.cw('set', record, 'status=closed'))
        other = self.record('prunable')
        path = self.worktree(self.root / '.worktrees/prunable')
        shutil.rmtree(path)
        self.assertIn('Warning:', self.cw('set', other, 'status=closed'))


if __name__ == '__main__':
    unittest.main()
