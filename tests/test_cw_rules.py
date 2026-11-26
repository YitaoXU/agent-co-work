"""Offline regressions for task arguments, receipt history and lock/trust safety."""
import contextlib
import io
import os
import shlex
import subprocess
import json
import unittest
from unittest import mock
import test_cw
import test_cw_v3


class RuleTests(unittest.TestCase):
    for name in ('setUp', 'cw', 'configure', 'calls', 'clear_calls', 'install', 'new', 'snapshot', 'module', 'claude_screens'):
        locals()[name] = getattr(test_cw.CWTests, name)
    for name in ('record', 'lock', 'identity', 'copy_to_day'):
        locals()[name] = getattr(test_cw_v3.V3Tests, name)

    def test_task_args_new_set_quotes_legacy_and_all_adapters(self):
        self.install()
        for agent in ('claude', 'codex', 'agy'):
            with self.subTest(agent=agent):
                self.cw('seat', 'set', 'worker-light', agent, 'model', 'high', '--args=--label seat')
                p = self.record(agent, 'step', 'worker-light', '--args=--label "task # value" -a never')
                run = shlex.split(self.cw('start', p, '--print').stdout.splitlines()[0])
                self.assertEqual(run[-6:], ['--label', 'seat', '--label', 'task # value', '-a', 'never'])
                p.write_text(p.read_text().replace(' -a never\n', ' -a never  # keep comment\n'))
                self.cw('set', p, 'args=--label "new # value"')
                self.assertIn('args: --label "new # value"  # keep comment', p.read_text())
                self.assertEqual(shlex.split(self.cw('start', p, '--print').stdout.splitlines()[0])[-4:],
                                 ['--label', 'seat', '--label', 'new # value'])
                before = p.read_bytes()
                self.cw('set', p, 'args="unterminated', code=1)
                self.assertEqual(p.read_bytes(), before)
                p.write_text('\n'.join(line for line in p.read_text().splitlines() if not line.startswith('args:')) + '\n')
                self.assertEqual(shlex.split(self.cw('start', p, '--print').stdout.splitlines()[0])[-2:], ['--label', 'seat'])
        self.cw('new', 'invalid', '--kind', 'step', '--seat', 'advisor', '--args="bad', code=1)
        self.assertFalse((self.root / f'cowork/{test_cw.DAY}/invalid.md').exists())
        module = self.module()
        text = module.new_text('quotes', 'step', None, 'advisor')
        text = text.replace('args: -', 'args: --label "# same" # same')
        self.assertEqual(module.header(text)[0]['args'], '--label "# same"')
        self.assertEqual(self.calls(), [])

    def test_fresh_ignore_plan_partial_crlf_and_idempotence(self):
        cases = ((b'# retained\r\noutput/\r\n.tmp/\r\ncustom', 'cowork/, .scratch/, .worktrees/',
                  b'\r\ncowork/\r\n.scratch/\r\n.worktrees/\r\n'),
                 (b'local-files\r\ncache', 'cowork/, output/, .scratch/, .tmp/, .worktrees/',
                  b'\r\ncowork/\r\noutput/\r\n.scratch/\r\n.tmp/\r\n.worktrees/\r\n'))
        for i, (original, additions, suffix) in enumerate(cases):
            with self.subTest(original=original), mock.patch.object(self, 'root', self.work / f'fresh-{i}'):
                self.root.mkdir()
                ignore = self.root / '.gitignore'
                ignore.write_bytes(original)
                plan = self.cw('init').stdout
                self.assertIn('.gitignore: add ' + additions, plan)
                self.assertEqual(ignore.read_bytes(), original)
                self.install()
                expected = original + suffix
                self.assertEqual(ignore.read_bytes(), expected)
                before = self.snapshot()
                self.cw('init', '--apply')
                self.assertEqual(ignore.read_bytes(), expected)
                self.assertEqual(before, self.snapshot())

    def test_existing_init_and_upgrade_preserve_missing_ignore_defaults(self):
        self.install()
        ignore = self.root / '.gitignore'
        for content in (b'output/\r\ncustom', None):
            if content is None:
                ignore.unlink()
            else:
                ignore.write_bytes(content)
            for flags in ((), ('--upgrade',)):
                result = self.cw('init', *flags, '--apply')
                self.assertIn('missing defaults: cowork/', result.stdout)
                self.assertEqual(ignore.read_bytes() if ignore.exists() else None, content)

    def test_report_retry_preserves_failure_matches_payload_and_reflags(self):
        self.install(live=True)
        p = self.record('sender')
        env = {'COWORK_TASK': str(p)}
        self.cw('report', 'first try; evidence', live=True, env=env)
        self.assertNotIn('REPORT', p.read_text())
        payload = 'retry [literal]; evidence [v1]'
        self.configure(fail=['send'])
        self.cw('report', payload, live=True, env=env, code=1)
        failure = next(l for l in p.read_text().splitlines() if 'REPORT' in l)
        self.assertIn('! undelivered report', self.cw('status').stdout)
        self.configure()
        self.cw('report', 'different; evidence', live=True, env=env)
        self.assertIn('! undelivered report', self.cw('status').stdout)
        self.cw('report', payload, live=True, env=env)
        self.assertIn(failure, p.read_text())
        self.assertIn('- REPORT (delivered): ' + payload, p.read_text())
        self.assertNotIn('undelivered report', self.cw('status').stdout)
        self.configure(fail=['send'])
        self.cw('report', payload, live=True, env=env, code=1)
        self.cw('set', p, 'status=closed')
        self.assertIn('! undelivered report', self.cw('status').stdout)

    def test_direct_report_destinations_and_details_are_isolated(self):
        self.install(live=True)
        sender, peer = self.record('sender'), self.record('peer')
        self.cw('set', peer, 'terminal=peer (t7)')
        payload = 'same; evidence [v1]'
        env = {'COWORK_TASK': str(sender)}
        self.configure(fail=['send'])
        self.cw('report', '--to', 'peer', payload, live=True, env=env, code=1)
        module = self.module()
        self.assertEqual(module.unresolved_reports(sender.read_text()), {('peer', payload), ('coordinator', payload)})
        self.configure()
        self.cw('report', payload, live=True, env=env)
        self.assertEqual(module.unresolved_reports(sender.read_text()), {('peer', payload)})
        self.cw('report', '--to', 'peer', 'other; evidence', live=True, env=env)
        self.assertEqual(module.unresolved_reports(sender.read_text()), {('peer', payload)})
        self.cw('report', '--to', 'peer', payload, live=True, env=env)
        self.assertEqual(module.unresolved_reports(sender.read_text()), set())
        self.cw('set', peer, 'terminal=peer (t1)')
        self.configure(fail=['send'])
        self.cw('report', '--to', 'peer', payload, live=True, env=env, code=1)
        self.configure()
        self.cw('report', '--to', 'peer', payload, live=True, env=env)
        self.assertEqual(module.unresolved_reports(sender.read_text()), set())
        self.assertEqual(sender.read_text().count('REPORT to peer (t7) (undelivered)'), 1)

    def test_report_detail_delimiters_preserve_arbitrary_payloads(self):
        self.install(live=True)
        sender, peer = self.record('sender'), self.record('peer')
        self.cw('set', peer, 'terminal=peer (t1)')
        module = self.module()
        payload = 'result [same terminal as target; sent once]; evidence [detail: "literal"]'
        args = module.parser().parse_args(['report', '--to', 'peer', payload])
        for delivered, detail in ((False, 'error [nested [details]] "quote" [unbalanced'), (True, '')):
            with mock.patch.dict(os.environ, {**self.env, 'COWORK_TASK': str(sender), 'HC_TERMINAL_ID': 't2'}, clear=True), \
                 mock.patch.object(module, 'send_report', return_value=(delivered, detail)), \
                 mock.patch.object(module, 'hc', side_effect=lambda *a, **kw: '' if a[0] == 'read' else {'state': 'live'}), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(module.report(self.root, args), 0 if delivered else 1)
            self.assertEqual(module.unresolved_reports(sender.read_text()), set() if delivered else {('peer', payload), ('coordinator', payload)})
        legacy = '## State\n- REPORT to peer (t7) (undelivered): done; file [v1] [error [nested]]\n'
        self.assertEqual(module.unresolved_reports(legacy), {('peer', 'done; file [v1]')})
        legacy += '- REPORT to peer (t8) (delivered): done; file [v1]\n'
        self.assertEqual(module.unresolved_reports(legacy), set())

    def test_force_holder_preconditions_preserve_lock_and_receipts(self):
        self.install(live=True)
        a = self.record('holder')
        self.lock('take', task=a)
        path = self.root / 'cowork/locks/gpu'
        before = path.read_bytes()
        for flags in (('--force',), ('--holder', ''), ('--force', '--holder', ''), ('--holder', self.identity(a)), ('--force', '--holder', '-'),
                      ('--force', '--holder', 'holder'), ('--force', '--holder', '20000101/other')):
            with self.subTest(flags=flags):
                self.lock('release', 'gpu', *flags, code=1)
                self.assertEqual(path.read_bytes(), before)
        self.lock('release', 'gpu', '--force', '--holder', self.identity(a), live=True)
        before = path.read_bytes()
        self.lock('release', 'gpu', '--force', '--holder', self.identity(a), code=1)
        self.assertEqual(path.read_bytes(), before)

    def test_holder_is_read_and_compared_under_guard(self):
        self.install()
        a, b = self.record('owner'), self.record('successor')
        self.lock('take', task=a)
        module = self.module()
        path = self.root / 'cowork/locks/gpu'
        args = module.parser().parse_args(['lock', 'release', 'gpu', '--force', '--holder', self.identity(a)])
        original_flock = module.fcntl.flock
        changed = f'{self.identity(b)}\tnew\t-\t-\n'
        def flock(fd, operation):
            original_flock(fd, operation)
            path.write_text(changed)
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(module.fcntl, 'flock', side_effect=flock):
            with self.assertRaisesRegex(module.CWError, 'actual holder'):
                module.resource_lock(self.root, args)
        self.assertEqual(path.read_text(), changed)

    def test_lock_post_mutation_failures_exit_three(self):
        self.install(live=True)
        a = self.record('holder')
        module = self.module()
        path = self.root / 'cowork/locks/gpu'
        for action, fault in (('expect', 'notice'), ('release', 'notice'), ('release', 'receipt'), ('take', 'stdout')):
            with self.subTest(action=action, fault=fault):
                self.lock('take', task=a)
                args = module.parser().parse_args(['lock', action, 'gpu'] + (['soon'] if action == 'expect' else []))
                write = module.write
                def failing_write(root, target, text, **kwargs):
                    if target == a:
                        raise OSError('receipt denied')
                    return write(root, target, text, **kwargs)
                with mock.patch.dict(os.environ, {**self.env, 'COWORK_TASK': str(a)}, clear=True), \
                     mock.patch.object(module, 'send_report', return_value=(fault != 'notice', 'notice failed')), \
                     mock.patch.object(module, 'write', side_effect=failing_write if fault == 'receipt' else write), \
                     contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    if fault == 'stdout':
                        with mock.patch('builtins.print', side_effect=[OSError('stdout denied'), None]):
                            self.assertEqual(module.resource_lock(self.root, args), 3)
                    else:
                        self.assertEqual(module.resource_lock(self.root, args), 3)
                fields = path.read_text().strip().split('\t')
                self.assertEqual(fields[0], '-' if action == 'release' else self.identity(a))
                if action == 'expect':
                    self.assertEqual(fields[2], 'soon')

    def test_decisions_cap_counts_nonempty_lines_excludes_archive(self):
        self.install()
        self.cw('project', 'new', 'plan')
        p = self.root / 'cowork/projects/plan.md'
        text = p.read_text()
        p.write_text(text + '\n'.join(f'- decision {n}\n' for n in range(20)))
        archive = p.parent / 'archive'
        archive.mkdir()
        (archive / 'plan-history.md').write_text('## Decisions\n' + 'old\n' * 30)
        self.cw('lint')
        p.write_text(p.read_text() + '- decision 21\n')
        self.assertIn('Decisions has 21 lines (guideline 20)', self.cw('lint').stdout)

    def test_index_folds_steps_and_resolves_same_day_parents(self):
        self.install()
        parent = self.record('parent', 'task')
        older = self.copy_to_day(parent, '20000101')
        self.record('standalone')
        module = self.module()
        for n in range(65):
            p = parent.parent / f'step-{n}.md'
            p.write_text(module.new_text(f'step-{n}', 'step', 'parent', 'worker-heavy'))
        old_step = older.parent / 'old-step.md'
        old_step.write_text(module.new_text('old-step', 'step', 'parent', 'advisor'))
        self.cw('index')
        text = (self.root / 'cowork/README.md').read_text()
        self.assertIn('65 steps', text)
        self.assertIn('1 step\n', text)
        self.assertIn('[coordinator]', text)
        self.assertNotIn('step-0.md', text)
        self.assertNotIn('standalone.md', text)
        self.assertLessEqual(len(text.splitlines()), 60)

    def test_start_trust_exact_assigned_worktree_all_adapters(self):
        self.install()
        folder = self.root / '.worktrees/assigned'
        folder.mkdir(parents=True)
        for agent in ('codex', 'agy', 'claude'):
            p = self.record(agent, 'step', 'worker-light', '--agent', f'{agent}:model:high')
            self.cw('set', p, 'worktree=.worktrees/assigned')
            for displayed, allowed in ((folder, True), (self.root, True),
                                       (self.root / '.worktrees/sibling', False), (folder / 'nested', False)):
                with self.subTest(agent=agent, displayed=displayed, allowed=allowed):
                    if agent == 'claude':
                        screen = f'Do you trust this folder?\n{displayed}\n❯ No, exit\n  Yes, I trust this folder'
                        screens = self.claude_screens(screen)
                    else:
                        screen = (test_cw.SCREENS / f'{agent}-trust.txt').read_text()
                        screen = screen.replace('/workspace/demo2' if agent == 'codex' else '/workspace/demo3', str(displayed))
                        screens = [screen]
                    self.configure(screens=screens, waits=[{'status': 'blocked'}, {'status': 'idle'}] if allowed else [{'status': 'blocked'}],
                                   get={'t42': {'argv': [agent], 'status': {'app': agent, 'state': 'blocked'}, 'foreground': {'cwd': str(displayed)}}})
                    self.clear_calls()
                    self.log.with_suffix('.wait').write_text('0')
                    self.cw('start', p, live=True, code=0 if allowed else 2)
                    keys = [call for call in self.calls() if call[0] == 'keys']
                    if allowed:
                        expected = [['keys', 't42', 'down', '--json'], ['keys', 't42', 'enter', '--json']] if agent == 'claude' else [['keys', 't42', 'enter', '--json']]
                        self.assertEqual(keys[:len(expected)], expected)
                    else:
                        self.assertEqual(keys, [])
                    if allowed:
                        self.clear_calls()
                        self.cw('approve', 't42', live=True, code=0 if displayed == self.root else 2)
                        if displayed == folder:
                            self.assertNotIn('keys', [c[0] for c in self.calls()])

    def test_claude_current_folder_cannot_drift_to_sibling(self):
        self.install()
        module = self.module()
        assigned = self.root / '.worktrees/assigned'
        assigned.mkdir(parents=True)
        screen = f'Do you trust this folder?\n{assigned}\n❯ Yes, I trust this folder\n  No, exit'
        def hc(*args, **kwargs):
            if args[0] == 'read':
                return screen
            return {'state': 'live', 'status': {'state': 'blocked'}, 'foreground': {'cwd': str(self.root / 'sibling')}}
        with mock.patch.object(module, 'hc', side_effect=hc) as call, mock.patch.object(module.time, 'sleep'), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(module.Blocked):
                module.approve(self.root, 't42', 'claude', screen=screen, allowed_folder=assigned)
        self.assertNotIn('keys', [c.args[0] for c in call.call_args_list])

    def test_upgrade_without_marker_preserves_existing_or_absent_ignore(self):
        for name, content in (('existing', b'custom\r\n'), ('absent', None)):
            with self.subTest(name=name):
                root = self.root / name
                root.mkdir()
                ignore = root / '.gitignore'
                if content is not None:
                    ignore.write_bytes(content)
                for flags in ((), ('--apply',)):
                    result = self.cw('--root', root, 'init', '--upgrade', *flags)
                    self.assertIn('.gitignore unchanged; missing defaults:', result.stdout)
                    self.assertEqual(ignore.read_bytes() if ignore.exists() else None, content)
                self.assertTrue((root / 'cowork/cw').is_file())

    def test_lock_commit_point_precedes_temporary_directory_cleanup(self):
        self.install()
        owner = self.record('holder')
        self.lock('take', task=owner)
        path = self.root / 'cowork/locks/gpu'
        module = self.module()
        original_exit = module.tempfile.TemporaryDirectory.__exit__
        def fail_after_cleanup(directory, *args):
            original_exit(directory, *args)
            raise OSError('cleanup failed after atomic replacement')
        argv = ['cw', '--root', str(self.root), 'lock', 'release', 'gpu']
        with mock.patch.dict(os.environ, {**self.env, 'COWORK_TASK': str(owner)}, clear=True), \
             mock.patch.object(module.sys, 'argv', argv), \
             mock.patch.object(module.tempfile.TemporaryDirectory, '__exit__', fail_after_cleanup), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(module.main(), 3)
        self.assertTrue(path.read_text().startswith('-\t'))
        self.assertIn('cleanup failed after atomic replacement', error.getvalue())

    def test_lock_pre_replacement_failure_is_still_one_and_unchanged(self):
        self.install()
        owner = self.record('holder')
        self.lock('take', task=owner)
        path = self.root / 'cowork/locks/gpu'
        before = path.read_bytes()
        module = self.module()
        argv = ['cw', '--root', str(self.root), 'lock', 'release', 'gpu']
        with mock.patch.dict(os.environ, {**self.env, 'COWORK_TASK': str(owner)}, clear=True), \
             mock.patch.object(module.sys, 'argv', argv), \
             mock.patch.object(module.Path, 'replace', side_effect=OSError('replacement denied')), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_lock_failed_stdout_and_stderr_preserve_exit_three(self):
        self.install()
        owner = self.record('holder')
        self.lock('take', task=owner)
        module = self.module()
        argv = ['cw', '--root', str(self.root), 'lock', 'release', 'gpu']
        with mock.patch.dict(os.environ, {**self.env, 'COWORK_TASK': str(owner)}, clear=True), \
             mock.patch.object(module.sys, 'argv', argv), \
             mock.patch('builtins.print', side_effect=OSError('output unavailable')) as printing:
            self.assertEqual(module.main(), 3)
        self.assertEqual(printing.call_count, 2)
        self.assertTrue((self.root / 'cowork/locks/gpu').read_text().startswith('-\t'))

    def test_report_retry_timeout_success_visible_and_three_failures(self):
        self.install(live=True)
        sender, peer = self.record('sender'), self.record('peer')
        self.cw('set', peer, 'terminal=peer (t7)')
        module = self.module()
        original = sender.read_text()
        payload = 'retry result; output/result.md'
        message = '[sender] ' + payload
        for direct in (False, True):
            for scenario in ('timeout-success', 'visible', 'three-failures'):
                with self.subTest(direct=direct, scenario=scenario):
                    # Start with an earlier failure to verify append-only resolution.
                    sender.write_text(module.state_append(original, 'REPORT (undelivered): ' + payload))
                    elapsed, calls, sends = [0.0], [], {}
                    def transport(argv, **kwargs):
                        action, destination = argv[1:3]
                        calls.append((action, destination, kwargs['timeout']))
                        if action == 'get':
                            return subprocess.CompletedProcess(argv, 0, json.dumps({'state': 'live'}), '')
                        if action == 'read':
                            screen = '\x1b[32m' + (payload if direct else message).replace('; ', ';\n') + '\x1b[0m' if scenario == 'visible' else 'unfinished draft'
                            return subprocess.CompletedProcess(argv, 0, screen, '')
                        self.assertEqual(action, 'send')
                        sends[destination] = sends.get(destination, 0) + 1
                        self.assertAlmostEqual(kwargs['timeout'], 180)
                        if scenario == 'three-failures':
                            return subprocess.CompletedProcess(argv, 1, '', 'transport failed')
                        if sends[destination] == 1:
                            elapsed[0] += kwargs['timeout']
                            raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
                        return subprocess.CompletedProcess(argv, 0, '{}', '')
                    args = module.parser().parse_args(['report', *(['--to', 'peer'] if direct else []), payload])
                    with mock.patch.dict(os.environ, {**self.env, 'HC_TERMINAL_ID': 't2', 'COWORK_TASK': str(sender)}, clear=True), \
                         mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), \
                         mock.patch.object(module.subprocess, 'run', side_effect=transport), \
                         contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as error:
                        self.assertEqual(module.report(self.root, args), 1 if scenario == 'three-failures' else 0)
                    destinations = ('t7', 't1') if direct else ('t1',)
                    attempts = {'timeout-success': 2, 'visible': 1, 'three-failures': 3}[scenario]
                    self.assertEqual(sends, {dest: attempts for dest in destinations})
                    for dest in destinations:
                        actions = [action for action, address, _ in calls if address == dest and action != 'get']
                        self.assertEqual(actions, {'timeout-success': ['send', 'read', 'send'],
                                                  'visible': ['send', 'read'],
                                                  'three-failures': ['send', 'read', 'send', 'read', 'send']}[scenario])
                    state = module.section(sender.read_text(), 'State')
                    self.assertIn('- REPORT (undelivered): ' + payload, state)
                    if scenario == 'three-failures':
                        # Prior receipt plus one final failure per destination.
                        self.assertEqual(state.count('(undelivered)'), 3 if direct else 2)
                        self.assertNotIn('(delivered)', state)
                        self.assertIn('attempt 3/3', error.getvalue())
                    else:
                        self.assertEqual(state.count('(undelivered)'), 1)
                        self.assertIn('(delivered)', state)
                        self.assertEqual(module.unresolved_reports(sender.read_text()), set())
                    self.assertIn('waiting for target (draft or busy), attempt 1/3', error.getvalue())

    def test_direct_report_shares_ten_minute_budget_across_destinations(self):
        self.install(live=True)
        sender, peer = self.record('sender'), self.record('peer')
        self.cw('set', peer, 'terminal=peer (t7)')
        module = self.module()
        elapsed, calls = [0.0], []
        def transport(argv, **kwargs):
            action, dest = argv[1:3]
            calls.append((action, dest, kwargs['timeout']))
            if action == 'get':
                return subprocess.CompletedProcess(argv, 0, json.dumps({'state': 'live'}), '')
            if action == 'read':
                return subprocess.CompletedProcess(argv, 0, 'unfinished draft', '')
            elapsed[0] += kwargs['timeout']
            raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
        args = module.parser().parse_args(['report', '--to', 'peer', 'bounded; result.md'])
        with mock.patch.dict(os.environ, {**self.env, 'HC_TERMINAL_ID': 't2', 'COWORK_TASK': str(sender)}, clear=True), \
             mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), \
             mock.patch.object(module.subprocess, 'run', side_effect=transport), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.report(self.root, args), 1)
        self.assertEqual(elapsed[0], 600)
        self.assertEqual([(dest, timeout) for action, dest, timeout in calls if action == 'send'],
                         [('t7', 180), ('t7', 180), ('t7', 180), ('t1', 60)])
        self.assertEqual(sender.read_text().count('(undelivered)'), 2)

    def test_non_report_notifications_keep_single_send(self):
        self.install()
        module = self.module()
        with mock.patch.dict(os.environ, {**self.env, 'HC_TERMINAL_ID': 't2'}, clear=True), \
             mock.patch.object(module, 'hc', side_effect=module.HCTimeout('timeout')) as hc:
            self.assertEqual(module.send_report('t1', 'lock notice')[0], False)
        self.assertEqual(hc.call_count, 1)
        self.assertEqual(hc.call_args.args[:2], ('send', 't1'))
