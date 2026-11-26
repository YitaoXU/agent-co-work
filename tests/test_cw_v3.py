"""V3 record compatibility, approval gates and process-safe resource locks."""
import datetime as dt
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import test_cw


class V3Tests(unittest.TestCase):
    # Reuse only the isolated CLI harness, not its test cases.
    for name in ('setUp', 'cw', 'configure', 'calls', 'clear_calls', 'install', 'new', 'snapshot', 'module'):
        locals()[name] = getattr(test_cw.CWTests, name)

    def record(self, name, kind='step', seat='coder-heavy', *extra):
        self.cw('new', name, '--kind', kind, '--seat', seat, *extra)
        return self.root / f'cowork/{test_cw.DAY}/{name}.md'

    def lock(self, action, resource='gpu', *args, task=None, **kwargs):
        return self.cw('lock', action, resource, *args,
                       env={'COWORK_TASK': str(task)} if task else None, **kwargs)

    def identity(self, task):
        return task.relative_to(self.root / 'cowork').with_suffix('').as_posix()

    def copy_to_day(self, task, day):
        copy = self.root / 'cowork' / day / task.name
        copy.parent.mkdir(exist_ok=True)
        copy.write_bytes(task.read_bytes())
        return copy

    def test_project_creation_validation_and_portable_bundle(self):
        self.install()
        self.cw('project', 'new', 'campaign', script=self.root / 'cowork/cw')
        p = self.root / 'cowork/projects/campaign.md'
        before = p.read_bytes()
        for title in ('Direction', 'Plan', 'Resources', 'Decisions'):
            self.assertIn('## ' + title, p.read_text())
        self.assertNotIn('## State', p.read_text())
        self.record('arm', 'task', 'coder-heavy', '--project', 'campaign', '--line', 'main')
        self.assertEqual(p.read_bytes(), before)
        self.cw('project', 'new', 'campaign', code=1)
        for name in ('../bad', 'x' * 21, 'UPPER'):
            self.cw('project', 'new', name, code=1)
        self.cw('new', 'missing', '--kind', 'task', '--seat', 'advisor', '--project', 'absent', code=1)
        self.assertFalse((self.root / f'cowork/{test_cw.DAY}/missing.md').exists())
        self.cw('lint')
        p.write_text(p.read_text().replace('status: active', 'status: invalid'))
        self.assertIn('Invalid project status', self.cw('lint', code=1).stdout)

    def test_legacy_headers_edits_and_lessons(self):
        self.install()
        p = self.record('old', 'task')
        text = p.read_text().replace('kind: task', 'size: large').replace('status: draft', 'status: debrief')
        text = '\n'.join(line for line in text.splitlines() if not line.startswith(('project:', 'line:', 'agent:'))) + '\n'
        text = text.replace('## Wrap-up', '## Debrief\n- lesson: Legacy lessons remain available.')
        p.write_text(text)
        values = self.module().header(text)[0]
        self.assertEqual((values['kind'], values['status'], values['project'], values['line']), ('task', 'wrap-up', '-', '-'))
        self.cw('index')
        self.cw('lessons', test_cw.DAY)
        self.assertIn('Legacy lessons remain available.', (self.root / f'cowork/lessons/{test_cw.DAY}.md').read_text())
        self.cw('set', p, 'kind=step', 'line=side', 'project=-', 'agent=-', 'status=debrief')
        self.assertNotIn('size:', p.read_text())
        self.assertIn('kind: step', p.read_text())
        self.assertIn('status: wrap-up', p.read_text())
        self.cw('set', p, 'size=large')
        self.assertIn('kind: task', p.read_text())
        for field in ('kind=invalid', 'line=other', 'project=absent', 'uses=gpu'):
            before = p.read_bytes()
            self.cw('set', p, field, code=1)
            self.assertEqual(p.read_bytes(), before)

    def test_gates_parent_resolution_and_advisor_exception(self):
        self.install()
        parent = self.record('parent', 'task')
        worker = self.record('worker', 'step', 'coder-light', '--parent', 'parent')
        advisor = self.record('advice', 'step', 'advisor', '--parent', 'parent')
        standalone = self.record('standalone')
        for p in (parent, worker):
            self.cw('start', p, '--print', code=1)
        for p in (advisor, standalone):
            self.cw('start', p, '--print')
        for status in ('approved', 'running', 'blocked'):
            self.cw('set', parent, f'status={status}', f'approved=user, {dt.date.today()}')
            for p in (parent, worker):
                self.cw('start', p, '--print')
        for status in ('draft', 'wrap-up', 'closed'):
            self.cw('set', parent, f'status={status}')
            self.cw('start', worker, '--print', code=1)
        older = self.root / 'cowork/20000101/parent.md'
        older.parent.mkdir()
        older.write_text(parent.read_text().replace('status: closed', 'status: approved'))
        self.cw('start', worker, '--print', code=1)  # same-day closed wins
        parent.unlink()
        self.cw('start', worker, '--print')
        self.cw('set', older, 'kind=step')
        self.cw('start', worker, '--print', code=1)
        self.cw('set', worker, 'parent=absent')
        self.cw('start', worker, '--print', code=1)
        self.assertEqual(self.calls(), [])

    def test_approval_dates_require_real_calendar_days(self):
        self.install()
        parent = self.record('parent', 'task')
        worker = self.record('worker', 'step', 'coder-light', '--parent', 'parent')
        original = parent.read_text()
        for date in ('2026-99-99', '2026-00-01', '2026-01-00', '2026-04-31',
                     '2025-02-29', '1900-02-29', '0000-01-01', '2026-2-28'):
            with self.subTest(date=date):
                self.cw('set', parent, 'status=approved', f'approved=user, {date}', code=1)
                self.assertEqual(parent.read_text(), original)
                parent.write_text(original.replace('status: draft', 'status: approved')
                                  .replace('approved: -', f'approved: user, {date}'))
                for task in (parent, worker):
                    self.cw('start', task, '--print', live=True, code=1)
                parent.write_text(original)
        for date in ('2000-02-29', '2024-02-29', '2026-02-28', '9999-12-31'):
            with self.subTest(date=date):
                self.cw('set', parent, 'status=approved', f'approved=user, {date}')
                for task in (parent, worker):
                    self.cw('start', task, '--print')
        self.assertEqual(self.calls(), [])

    def test_task_names_reserve_sentinel_and_require_alphanumeric_edges(self):
        self.install()
        module = self.module()
        valid = [self.record(name) for name in ('a', 'a0', 'a--0', 'x' * 20)]
        for name in ('-', '--', '-a', 'a-', '-worker', 'worker-'):
            with self.subTest(name=name):
                before = self.snapshot()
                self.cw('new', '--kind', 'step', '--seat', 'coder-light', '--', name, code=1)
                self.cw('set', valid[0], f'task={name}', code=1)
                self.assertEqual(self.snapshot(), before)
                legacy = valid[0].read_text().replace('task: a\n', f'task: {name}\n')
                with self.assertRaises(module.CWError):
                    module.header(legacy)
                valid[0].write_text(legacy)
                self.lock('take', task=valid[0], code=1)
                valid[0].write_bytes(before[valid[0].relative_to(self.root).as_posix()][0])
                self.assertFalse((self.root / 'cowork/locks/gpu').exists())
        self.lock('take', task=valid[0])
        holder = (self.root / 'cowork/locks/gpu').read_text().split('\t')[0]
        self.assertEqual(holder, self.identity(valid[0]))
        self.assertNotEqual(holder, '-')
        self.lock('take', task=valid[1], code=1)

    def test_lint_reports_invalid_names_in_legacy_headers_and_record_paths(self):
        self.install()
        source = self.record('valid')
        for name in ('-', '-worker', 'worker-'):
            legacy = source.with_name(name + '.md')
            legacy.write_text(source.read_text().replace('task: valid', 'task: ' + name))
            self.lock('take', task=legacy, code=1)
        bad_header = source.with_name('bad-header.md')
        bad_header.write_text(source.read_text().replace('task: valid', 'task: -'))
        bad_path = source.with_name('-path.md')
        bad_path.write_bytes(source.read_bytes())
        self.lock('take', task=bad_path, code=1)
        output = self.cw('lint', code=1).stdout
        for path in ('-.md', '-worker.md', 'worker-.md', 'bad-header.md', '-path.md'):
            self.assertIn(f'cowork/{test_cw.DAY}/{path}', output)
        self.assertIn('Task names must match', output)
        self.assertFalse((self.root / 'cowork/locks/gpu').exists())

    def test_index_project_line_grouping(self):
        self.install()
        self.cw('project', 'new', 'campaign')
        for name, line in (('arm', 'main'), ('cleanup', 'side')):
            self.record(name, 'task', 'coder-heavy', '--project', 'campaign', '--line', line)
        self.record('standalone', 'task')
        self.cw('index')
        text = (self.root / 'cowork/README.md').read_text()
        for line in ('main', 'side'):
            self.assertIn('### [campaign](projects/campaign.md) / ' + line, text)
        self.assertIn('### Standalone / -', text)
        for name in ('arm', 'cleanup', 'standalone'):
            self.assertEqual(text.count(f'{test_cw.DAY}/{name}.md'), 1)
        self.assertLessEqual(len(text.splitlines()), 60)
        prompt = (test_cw.REPO / 'templates/handover-prompt.txt').read_text()
        self.assertIn('cowork/projects/', prompt)

    def test_lock_queue_ownership_estimate_and_release(self):
        self.install(live=True)
        a, b = self.record('arm-a'), self.record('arm-b')
        self.cw('set', b, f'terminal={test_cw.DAY}-arm-b (t9)')
        self.lock('next', 'gpu', 'arm-b', task=a, code=1)
        self.lock('next', 'gpu', 'arm-b')
        self.lock('take', task=a, code=1)
        self.lock('take', task=b)
        lock = self.root / 'cowork/locks/gpu'
        self.assertEqual(lock.read_text().strip().split('\t')[::3], [self.identity(b), '-'])
        self.lock('take', task=a, code=1)
        self.lock('expect', 'gpu', 'tomorrow', task=a, code=1)
        before = b.read_bytes()
        self.lock('expect', 'gpu', 'tomorrow', task=b, live=True)
        self.assertEqual(b.read_bytes(), before)
        self.assertIn('estimate != release', [c for c in self.calls() if c[0] == 'send'][-1][2])
        held = lock.read_bytes()
        self.lock('take', task=b)
        self.assertEqual(lock.read_bytes(), held)
        self.lock('next', 'gpu', 'arm-a')
        self.lock('take', task=b, code=1)  # another queue head wins, even for holder
        self.lock('release', task=a, code=1)
        self.lock('release', task=b, live=True)
        self.assertEqual(lock.read_text().strip().split('\t')[::3], ['-', self.identity(a)])
        state = self.module().section(b.read_text(), 'State')
        self.assertEqual(len([line for line in state.splitlines() if line.strip()]), 1)
        self.lock('take', task=a)
        self.cw('lint')

    def test_same_name_daily_records_cannot_change_another_holders_lock(self):
        self.install()
        current = self.record('holder')
        older = self.copy_to_day(current, '20000101')
        self.lock('take', task=older)
        lock = self.root / 'cowork/locks/gpu'
        held = lock.read_bytes()
        for action, args in (('take', ()), ('expect', ('tomorrow',)), ('release', ())):
            self.lock(action, 'gpu', *args, task=current, code=1)
            self.assertEqual(lock.read_bytes(), held)
        self.lock('take', task=older)
        self.assertEqual(lock.read_bytes(), held)
        self.cw('set', older, 'status=closed')
        status = self.cw('status').stdout
        self.assertIn('holder=20000101/holder', status)
        self.assertIn('! stale holder', status)
        self.cw('set', older, 'status=running', 'terminal=old-holder (t8)')
        self.configure(get={'t8': {'state': 'finished'}})
        self.assertIn('! stale holder', self.cw('status', live=True).stdout)
        older.unlink()
        self.assertIn('! stale holder', self.cw('status').stdout)
        self.lock('take', task=current, code=1)

    def test_queue_resolves_names_once_and_accepts_dated_record_paths(self):
        self.install(live=True)
        owner = self.copy_to_day(self.record('owner'), '20000101')
        peer = self.record('peer')
        self.cw('set', peer, 'terminal=peer (t7)')
        older = self.copy_to_day(peer, '20000101')
        newest = self.copy_to_day(peer, '29990101')
        self.cw('set', older, 'terminal=older-peer (t8)')
        self.cw('set', newest, 'terminal=newest-peer (t9)')
        self.lock('take', task=owner)
        self.lock('next', 'gpu', 'peer')
        lock = self.root / 'cowork/locks/gpu'
        self.assertEqual(lock.read_text().strip().split('\t')[3], self.identity(peer))
        self.clear_calls()
        result = self.lock('expect', 'gpu', 'tomorrow', task=owner, live=True)
        self.assertEqual([c[1] for c in self.calls() if c[0] == 'send'], ['t7', 't1'])
        self.assertIn(f'{self.identity(peer)} (t7)', result.stdout)
        for call in self.calls():
            if call[0] == 'send':
                self.assertTrue(call[2].startswith('[20000101/owner] LOCK gpu'))
        for path in (self.identity(older), self.identity(older) + '.md',
                     older.relative_to(self.root), older):
            with self.subTest(path=path):
                self.lock('next', 'gpu', path)
                self.assertEqual(lock.read_text().strip().split('\t')[3], self.identity(older))
        self.lock('release', task=owner, live=True)
        self.lock('take', task=peer, code=1)
        self.lock('take', task=newest, code=1)
        self.lock('take', task=older)
        peer.unlink()
        self.lock('next', 'gpu', 'peer')
        self.assertEqual(lock.read_text().strip().split('\t')[3], self.identity(newest))
        self.assertIn('next=29990101/peer', self.cw('status').stdout)
        self.lock('next', 'gpu', '-')
        before = lock.read_bytes()
        for path in ('../escape', 'cowork/projects/peer.md', '20000101/-', '20000101/missing'):
            self.lock('next', 'gpu', path, code=1)
            self.assertEqual(lock.read_bytes(), before)

    def test_missing_queued_record_does_not_notify_a_same_name_record(self):
        self.install(live=True)
        owner, peer = self.record('owner'), self.record('peer')
        self.cw('set', peer, 'terminal=peer (t7)')
        older = self.copy_to_day(peer, '20000101')
        self.cw('set', older, 'terminal=older-peer (t8)')
        self.lock('take', task=owner)
        self.lock('next', 'gpu', self.identity(older))
        older.unlink()
        self.clear_calls()
        result = self.lock('release', task=owner, live=True)
        sends = [c for c in self.calls() if c[0] == 'send']
        self.assertEqual([c[1] for c in sends], ['t1'])
        self.assertIn('Target 20000101/peer skipped: task record not found', sends[0][2])
        self.assertIn('20000101/peer: skipped', result.stdout)
        self.lock('take', task=peer, code=1)

    def test_release_frees_before_send_and_records_one_line(self):
        self.install(live=True)
        a, b = self.record('a'), self.record('b')
        self.cw('set', b, f'terminal={test_cw.DAY}-b (t9)')
        self.lock('take', task=a)
        self.lock('next', 'gpu', 'b')
        module = self.module()
        args = module.parser().parse_args(['lock', 'release', 'gpu', '--note', 'Archive still pending'])
        snapshots = []
        def send(address, message, deadline=None):
            snapshots.append((address, (self.root / 'cowork/locks/gpu').read_text()))
            return False, 'simulated send failure'
        with mock.patch.dict(os.environ, {'COWORK_TASK': str(a), 'HC_TERMINAL_ID': 't2'}), \
             mock.patch.object(module, 'send_report', side_effect=send), \
             mock.patch.object(module, 'hc', return_value={'state': 'live'}):
            self.assertEqual(module.resource_lock(self.root, args), 3)
        self.assertEqual([address for address, _ in snapshots], ['t9', 't1'])
        self.assertTrue(all(text.startswith('-\t') for _, text in snapshots))
        state = module.section(a.read_text(), 'State')
        self.assertEqual(len([line for line in state.splitlines() if line.strip()]), 1)
        self.assertIn('Archive still pending', state)
        self.assertIn(f'cowork/{test_cw.DAY}/a.md', state)
        self.assertIn('undelivered', state)
        self.lock('take', task=b)

    def test_notifications_live_copy_and_same_terminal_deduplication(self):
        self.install(live=True)
        a, b = self.record('a'), self.record('b')
        self.cw('set', b, f'terminal={test_cw.DAY}-b (t9)')
        self.lock('next', 'gpu', 'b')
        self.assertIn('holder=-', self.cw('status').stdout)
        self.lock('next', 'gpu', '-')
        self.lock('take', task=a)
        self.lock('next', 'gpu', 'b')
        self.clear_calls()
        before = a.read_bytes()
        self.lock('expect', 'gpu', '18:00 UTC', task=a, live=True)
        self.assertEqual([c[1] for c in self.calls() if c[0] == 'send'], ['t9', 't1'])
        self.assertEqual(a.read_bytes(), before)
        self.cw('set', b, f'terminal={test_cw.DAY}-b (t1)')
        self.clear_calls()
        self.lock('release', task=a, live=True)
        self.assertEqual([c[1] for c in self.calls() if c[0] == 'send'], ['t1'])
        self.assertIn('same terminal as target', a.read_text())

    def test_stale_holder_force_release_and_offline_fallback(self):
        self.install()
        a = self.record('holder')
        self.lock('take', task=a)
        self.cw('set', a, 'status=closed')
        self.assertIn('! stale holder', self.cw('status').stdout)
        self.lock('release', 'gpu', '--force', '--holder', self.identity(a), task=a, code=1)
        self.lock('release', code=1)  # coordinator needs force
        result = self.lock('release', 'gpu', '--force', '--holder', self.identity(a), '--evidence', 'evidence.txt', code=3)
        self.assertIn('Relay to coordinator:', result.stdout)
        self.assertTrue((self.root / 'cowork/locks/gpu').read_text().startswith('-\t'))
        self.assertNotIn('lock gpu:', self.cw('status').stdout)
        self.cw('set', a, 'status=running', f'terminal={test_cw.DAY}-holder (t8)')
        self.lock('take', task=a)
        self.configure(get={'t8': {'state': 'finished'}})
        self.assertIn('! stale holder', self.cw('status', live=True).stdout)
        self.lock('next', 'gpu', '-')
        self.lock('next', 'gpu', 'missing', code=1)
        self.lock('take', '../escape', task=a, code=1)
        for value in ('', 'two\nlines', 'tab\tvalue'):
            self.lock('expect', 'gpu', value, task=a, code=1)

    def test_two_processes_cannot_both_acquire(self):
        self.install()
        a, b = self.record('racer-a'), self.record('racer-b')
        self.race_for_lock(a, b)

    def test_same_name_daily_tasks_cannot_both_acquire_in_two_processes(self):
        self.install()
        current = self.record('racer')
        older = self.copy_to_day(current, '20000101')
        self.race_for_lock(current, older)

    def race_for_lock(self, a, b):
        # Each child signals readiness then waits on stdin; both contend for the
        # actual flock/atomic-write path in separate interpreters.
        code = '''import runpy, sys
module = runpy.run_path(sys.argv[1], run_name='cw_race')
print('ready', flush=True)
sys.stdin.readline()
sys.argv = [sys.argv[1], 'lock', 'take', 'gpu']
sys.exit(module['main']())
'''
        processes = []
        for task in (a, b):
            env = {**self.env, 'COWORK_TASK': str(task), 'COWORK_ROOT': str(self.root)}
            processes.append(subprocess.Popen([sys.executable, '-c', code, str(test_cw.CW)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env, cwd=self.root))
        try:
            for process in processes:
                self.assertEqual(process.stdout.readline().strip(), 'ready')
            for process in processes:
                process.stdin.write('\n')
                process.stdin.flush()
            results = [process.communicate(timeout=10) for process in processes]
            self.assertEqual(sorted(process.returncode for process in processes), [0, 1], results)
            holder = (self.root / 'cowork/locks/gpu').read_text().split('\t')[0]
            winner = (a, b)[[process.returncode for process in processes].index(0)]
            self.assertEqual(holder, self.identity(winner))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()
