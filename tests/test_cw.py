"""CLI integration tests; every subprocess uses a recorded, isolated fake hc."""
import datetime as dt
import hashlib
import json
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
CW = REPO / 'bin/cw'
SCRATCH = REPO / '.tmp'
SCREENS = REPO / 'tests/fixtures/screens'
DAY = dt.date.today().strftime('%Y%m%d')
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
log = pathlib.Path(os.environ['FAKE_LOG'])
with log.open('a') as f:
    f.write(json.dumps(args) + '\n')
config = json.loads(pathlib.Path(os.environ['FAKE_CONFIG']).read_text())
def accept_handover():
    if config.get('accept'):
        root = pathlib.Path(os.environ['FAKE_PROJECT'])
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        launch = [call for call in calls if call[0] == 'run'][-1]
        name = launch[launch.index('--name') + 1]
        (root / 'cowork/coordinator.addr').write_text('t42 ' + name + '\n')
# hc 0.1.22 Terminal/RunResult and WaitResult from `hc schema`, plus the
# compact ls shape observed with `hc ls --json`. Configs override these defaults.
def record(address, **changes):
    result = {'address': address, 'labels': {}, 'argv': ['codex'],
              'cwd': os.environ['FAKE_PROJECT'], 'state': 'live', 'created_ms': 0,
              'screen': 'exact', 'cols': 200, 'rows': 120,
              'status': {'app': 'codex', 'state': 'idle'}, 'first_message': None}
    result.update(changes)
    return result
cmd = args[0]
if cmd == config.get('sleep_command'):
    time.sleep(30)
if cmd in config.get('fail', []):
    print('fake failure', file=sys.stderr)
    sys.exit(9)
errors = config.get('errors', {}).get(cmd, [])
n = sum(json.loads(line)[0] == cmd for line in log.read_text().splitlines()) - 1
if n < len(errors) and errors[n]:
    print(json.dumps({'error': errors[n]}), file=sys.stderr)
    sys.exit(1)
if cmd == 'ls':
    result = {'hidden_finished': 0, 'terminals': [
        {'address': 't' + str(n + 2), 'agent': 'codex',
         'cwd': os.environ['FAKE_PROJECT'], 'state': 'live', 'status': 'idle',
         'turn': 1, **item} for n, item in enumerate(config.get('live', []))]}
elif cmd == 'get':
    result = record(args[1], name='caller', labels={'herdr.space': 'space-a'})
    result.update(config.get('get', {}).get(args[1], {}))
    if args[1] == 't42' and (result.get('status') or {}).get('state') != 'blocked':
        accept_handover()
elif cmd == 'run':
    result = record('t42', name=args[args.index('--name') + 1],
                    argv=args[args.index('--') + 1:], status=None)
    result.update(config.get('run', {}))
    sequence = config.get('runs', [{}])
    result.update(sequence[min(n, len(sequence) - 1)])
    if config.get('edit_on_run'):
        p = pathlib.Path(config['edit_on_run'])
        p.write_text(p.read_text().replace('## State\n', '## State\n- agent wrote progress\n'))
elif cmd == 'wait':
    if '--timeout' not in args or not 0 < int(args[args.index('--timeout') + 1]) <= 20:
        print('startup wait needs an explicit timeout of at most 20 seconds', file=sys.stderr)
        sys.exit(99)
    wait_file = log.with_suffix('.wait')
    n = int(wait_file.read_text()) if wait_file.exists() else 0
    wait_file.write_text(str(n + 1))
    sequence = config.get('waits', [{}])
    result = {'terminal': args[1], 'ended': True, 'reason': 'status', 'turn': n + 1,
              'children': [], 'status': 'idle'}
    result.update(sequence[min(n, len(sequence) - 1)])
    if result['reason'] in ('timeout', 'message'):
        result['ended'] = False
    accept_handover()
elif cmd == 'send':
    send_file = log.with_suffix('.send')
    n = int(send_file.read_text()) if send_file.exists() else 0
    send_file.write_text(str(n + 1))
    sequence = config.get('send_errors', [])
    if n < len(sequence) and sequence[n]:
        print(json.dumps({'error': sequence[n]}), file=sys.stderr)
        sys.exit(1)
    result = {'turn': 1, 'started': True, 'status': 'working'}
    result.update(config.get('send', {}))
elif cmd == 'read':
    # Use the recorded calls so clear_calls also resets a screen sequence
    # between table-driven approval cases.
    sequence = config.get('screens', [config.get('screen', 'Trust this folder?\nWaiting for permission.')])
    sys.stdout.write(sequence[min(n, len(sequence) - 1)])
    sys.exit(0)
elif cmd == 'keys':
    result = {'turn': 1, 'status': 'idle'}
    accept_handover()
elif cmd == 'rm':
    result = {'removed': args[1]}
else:
    print('Unexpected fake hc command: ' + cmd, file=sys.stderr)
    sys.exit(99)
print(json.dumps(result))
'''


class CWTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='cw-test-', dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.root = self.work / 'project with spaces'
        self.root.mkdir()
        fake_dir = self.work / 'fake-bin'
        fake_dir.mkdir()
        fake = fake_dir / 'hc'
        fake.write_text(FAKE)
        fake.chmod(0o755)
        self.log = self.work / 'calls.jsonl'
        self.config = self.work / 'config.json'
        self.config.write_text('{}')
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('HC_', 'COWORK_'))}
        self.env.update(PATH=str(fake_dir) + os.pathsep + os.environ.get('PATH', ''),
                        FAKE_LOG=str(self.log), FAKE_CONFIG=str(self.config), FAKE_PROJECT=str(self.root),
                        TMPDIR=str(SCRATCH), PYTHONDONTWRITEBYTECODE='1')

    def cw(self, *args, code=0, live=False, env=None, script=CW, cwd=None):
        environ = dict(self.env)
        if live:
            environ['HC_TERMINAL_ID'] = 't1'
        if env:
            environ.update(env)
        result = subprocess.run([sys.executable, str(script), *map(str, args)], cwd=cwd or self.root,
                                env=environ, text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def configure(self, **values):
        self.config.write_text(json.dumps(values))

    def claude_screens(self, screen):
        selected = screen.replace('❯ No, exit', '  No, exit').replace('❯ 1. No, exit', '  1. No, exit')
        selected = selected.replace('  Yes, I trust this folder', '❯ Yes, I trust this folder').replace(
            '  2. Yes, I trust this folder', '❯ 2. Yes, I trust this folder')
        return [screen, screen, screen, selected]

    def run_recheck_trust(self, accepted_on=1, redraw=False, deadline=120):
        module = self.module()
        before = (SCREENS / 'claude-trust-recheck2.txt').read_text()
        folder = next(line.strip() for line in before.splitlines() if line.strip().startswith('/'))
        before = before.replace(folder, str(self.root))
        selected = self.claude_screens(before)[-1]
        elapsed, calls, navigation, moved = [0], [], [0], [False]
        def fake_hc(*args, **kwargs):
            calls.append((elapsed[0], args))
            if args[0] == 'read':
                return selected if moved[0] else before + ('\n' if redraw and elapsed[0] >= 1 else '')
            if args[0] == 'keys':
                keys = args[2:-1]
                if keys == ('down',):
                    navigation[0] += 1
                    moved[0] = accepted_on is not None and navigation[0] >= accepted_on and elapsed[0] >= 2
                if 'enter' in keys:
                    self.assertTrue(moved[0], 'Enter requires a freshly validated Yes selection')
            return {'state': 'live', 'status': {'state': 'blocked'}, 'foreground': {'cwd': str(self.root)}}
        def sleep(seconds):
            elapsed[0] += seconds
        result, error = None, None
        with mock.patch.object(module, 'hc', side_effect=fake_hc), \
                mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), \
                mock.patch.object(module.time, 'sleep', side_effect=sleep), mock.patch.object(module.sys, 'stderr'):
            try:
                result = module.approve(self.root, 't45', 'claude', set(), screen=before, deadline=deadline)
            except module.CWError as exc:
                error = exc
        return result, error, elapsed[0], calls

    def run_audit_trust(self, initial=None, after=None, cwd_after=None, seen=None, name='t45'):
        before = (SCREENS / 'claude-trust-run2-before.txt').read_text()
        folder = next(line.strip() for line in before.splitlines() if line.strip().startswith('/'))
        before = before.replace(folder, str(self.root))
        initial = before if initial is None else initial
        after = self.claude_screens(before)[-1] if after is None else after
        module, elapsed, navigation, calls = self.module(), [0], [False], []
        def fake_hc(*args, **kwargs):
            calls.append(args)
            if args[0] == 'read':
                return after if navigation[0] else initial
            if args[0] == 'keys':
                navigation[0] = navigation[0] or any(key in ('up', 'down') for key in args[2:-1])
            cwd = cwd_after if navigation[0] and cwd_after is not None else str(self.root)
            return {'state': 'live', 'status': {'state': 'blocked'}, 'foreground': {'cwd': cwd}}
        def sleep(seconds):
            elapsed[0] += seconds
        result, error = None, None
        with mock.patch.object(module, 'hc', side_effect=fake_hc), \
                mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), \
                mock.patch.object(module.time, 'sleep', side_effect=sleep), mock.patch.object(module.sys, 'stderr'):
            try:
                result = module.approve(self.root, name, 'claude', seen if seen is not None else set(),
                                        screen=initial, deadline=120)
            except module.CWError as exc:
                error = exc
        return result, error, [list(args[2:-1]) for args in calls if args[0] == 'keys']

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def clear_calls(self):
        self.log.write_text('')

    def install(self, live=False):
        self.cw('init', '--apply', live=live)
        self.clear_calls()

    def new(self, task='work', seat='coder-heavy', size='large', approve=True):
        self.cw('new', task, '--seat', seat, '--size', size)
        p = self.root / f'cowork/{DAY}/{task}.md'
        if approve and size == 'large':
            self.cw('set', p, 'status=approved', f'approved=user, {dt.date.today()}')
        return p

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
                for p in self.root.rglob('*') if p.is_file()}

    def module(self):
        loader = importlib.machinery.SourceFileLoader('cw_test', str(CW))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def test_help_lists_commands(self):
        output = self.cw('--help').stdout
        for command in ('init', 'seats', 'seat', 'new', 'set', 'start', 'approve', 'check', 'status', 'report', 'handover', 'index', 'lessons', 'lint'):
            self.assertIn(command, output)

    def test_readme_links_to_core_task_loop_rules(self):
        readme = (REPO / 'README.md').read_text()
        core = (REPO / 'skills/cowork/SKILL.md').read_text()
        self.assertIn('(skills/cowork/SKILL.md#task-loop)', readme)
        self.assertIn('## Task loop\n', core)
        self.assertNotIn('Discuss the Debrief with the user before the next large task.', readme)

    def test_init_plan_apply_noop_and_existing_text(self):
        (self.root / 'AGENTS.md').write_text('Existing project rules without newline')
        (self.root / 'CLAUDE.md').write_text('Existing Claude rules\n')
        before = self.snapshot()
        plan = self.cw('init', '--seat', 'advisor=claude:test:high:short').stdout
        self.assertIn('AGENTS.md: append', plan)
        self.assertEqual(before, self.snapshot())
        self.cw('init', '--seat', 'advisor=claude:test:high:short', '--apply')
        self.assertTrue((self.root / 'AGENTS.md').read_text().startswith('Existing project rules without newline\n'))
        self.assertTrue((self.root / 'CLAUDE.md').read_text().startswith('Existing Claude rules\n'))
        self.assertIn('advisor\tclaude\ttest\thigh\tshort', self.cw('seats').stdout)
        self.assertEqual((self.root / 'cowork/coordinator.addr').read_text(), '- -\n')
        self.assertEqual(len(list((self.root / '.agents/skills').glob('*/SKILL.md'))), 4)
        before = self.snapshot()
        self.assertIn('nothing to do', self.cw('init', '--apply').stdout)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_init_rerun_on_later_day_creates_no_seat(self):
        self.install()
        p = self.root / f'cowork/{DAY}'
        p.rename(p.with_name('20000101'))
        before = self.snapshot()
        self.assertIn('nothing to do', self.cw('init', '--apply').stdout)
        self.assertEqual(before, self.snapshot())

    def test_existing_instruction_line_endings_are_preserved(self):
        agents = self.root / 'AGENTS.md'
        claude = self.root / 'CLAUDE.md'
        agents.write_bytes(b'Project rules\r\nSecond line\r\n')
        claude.write_bytes(b'Claude rules\r\n@AGENTS.md\r\n')
        self.install()
        self.assertTrue(agents.read_bytes().startswith(b'Project rules\r\nSecond line\r\n'))
        self.assertEqual(claude.read_bytes(), b'Claude rules\r\n@AGENTS.md\r\n')
        before = self.snapshot()
        self.cw('init', '--upgrade', '--apply')
        self.assertEqual(before, self.snapshot())

    def test_init_rejects_instruction_aliases_before_any_writes(self):
        for real_name, link_name in (('AGENTS.md', 'CLAUDE.md'), ('CLAUDE.md', 'AGENTS.md')):
            with self.subTest(real=real_name):
                project = self.root / real_name.lower()
                project.mkdir()
                real = project / real_name
                link = project / link_name
                real.write_bytes(b'Existing shared instructions\r\n')
                real.chmod(0o640)
                link.symlink_to(real_name)
                before = self.snapshot()
                for flags in ((), ('--apply',)):
                    result = self.cw('init', *flags, cwd=project, code=1)
                    self.assertIn('AGENTS.md and CLAUDE.md alias the same file', result.stderr)
                    self.assertEqual(before, self.snapshot())
                    self.assertTrue(link.is_symlink())
                    self.assertFalse((project / 'cowork').exists())

    def test_init_preserves_outside_instruction_hard_link_and_mode(self):
        agents = self.root / 'AGENTS.md'
        agents.write_text('Existing project rules\n')
        agents.chmod(0o640)
        outside = self.work / 'outside-instructions.md'
        os.link(agents, outside)
        before = outside.read_bytes()
        self.install()
        self.assertEqual(outside.read_bytes(), before)
        self.assertTrue(agents.read_bytes().startswith(before))
        self.assertIn('<!-- agent-co-work:begin', agents.read_text())
        self.assertEqual(agents.stat().st_mode & 0o777, 0o640)
        self.assertEqual(outside.stat().st_mode & 0o777, 0o640)

    def test_upgrade_only_owned_content_and_existing_pointer(self):
        (self.root / 'CLAUDE.md').write_text('Keep this\n@AGENTS.md\nAnd this\n')
        self.install()
        agents = self.root / 'AGENTS.md'
        original = agents.read_text()
        agents.write_text('before\n' + original.replace('Coordination files are in', 'Custom block content:') + 'after\n')
        seats = self.root / 'cowork/seats.tsv'
        seats.write_text(seats.read_text() + '# keep seat comment\n')
        (self.root / '.agents/skills/cowork/SKILL.md').write_text('old skill\n')
        (self.root / 'cowork/cw').write_text('old script\n')
        (self.root / 'cowork/kit-version').write_text('old-kit -\n')
        before = self.snapshot()
        self.cw('init', '--upgrade')
        self.assertEqual(before, self.snapshot())
        self.cw('init', '--upgrade', '--apply')
        self.assertEqual(agents.read_text(), 'before\n' + original + 'after\n')
        allowed = {'AGENTS.md', 'cowork/cw', 'cowork/kit-version'} | {f'{base}/{s}/SKILL.md' for base in ('.agents/skills', '.claude/skills') for s in ('cowork', 'cowork-init', 'cowork-seat', 'cowork-consolidate')}
        after = self.snapshot()
        for path in before.keys() - allowed:
            self.assertEqual(before[path], after[path], path)
        self.assertTrue(os.access(self.root / 'cowork/cw', os.X_OK))

    def test_vendored_script_is_standalone(self):
        self.install()
        isolated = self.work / 'isolated'
        isolated.mkdir()
        script = isolated / 'cw'
        shutil.copyfile(self.root / 'cowork/cw', script)
        fresh = self.work / 'fresh'
        fresh.mkdir()
        self.cw('init', '--apply', script=script, cwd=fresh)
        self.cw('new', 'portable', '--seat', 'advisor', '--size', 'small', script=fresh / 'cowork/cw', cwd=fresh)
        self.cw('start', f'cowork/{DAY}/portable.md', script=fresh / 'cowork/cw', cwd=fresh)
        self.assertEqual(self.calls(), [])

    def test_init_herdr_address(self):
        self.install(live=True)
        self.assertEqual((self.root / 'cowork/coordinator.addr').read_text(), 't1 caller\n')
        before = self.snapshot()
        self.cw('init', '--apply', live=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_unnamed_caller_uses_title_for_init_and_accept(self):
        self.configure(get={'t1': {'name': None, 'title': 'User opened terminal'}})
        self.install(live=True)
        address = self.root / 'cowork/coordinator.addr'
        self.assertEqual(address.read_text(), 't1 User opened terminal\n')
        record = self.root / f'cowork/{DAY}/coordinator.md'
        self.assertIn('terminal: User opened terminal (t1)', record.read_text())
        for title in ('Another title', None):
            self.configure(get={'t2': {'name': None, 'title': title}})
            self.cw('handover', '--accept', live=True, env={'HC_TERMINAL_ID': 't2', 'COWORK_TASK': str(record)})
            self.assertEqual(address.read_text(), f't2 {title or "-"}\n')

    def test_seat_changes_only_one_line_and_own_state(self):
        self.install()
        task = self.new()
        p = self.root / 'cowork/seats.tsv'
        p.write_text(p.read_text().replace('coder-light\tcodex\tgpt-6.1-sol\tmax\tlong', 'coder-light codex gpt-6.1-sol max long # personal comment'))
        old = p.read_text().splitlines()
        self.cw('seat', 'set', 'coder-light', 'claude', 'other-model', 'high', env={'COWORK_TASK': str(task)})
        new = p.read_text().splitlines()
        self.assertEqual(sum(a != b for a, b in zip(old, new)), 1)
        self.assertIn('# personal comment', p.read_text())
        self.assertIn('seat coder-light: claude other-model high long', task.read_text())
        before = self.snapshot()
        result = self.cw('seat', 'set', 'coder-light', 'unknown', 'x', 'y', code=1)
        self.assertIn('known adapters: claude, agy, codex', result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_seat_args_set_preserve_and_clear_keep_comments_and_own_state(self):
        self.install()
        task = self.new()
        table = self.root / 'cowork/seats.tsv'
        original = table.read_text()
        table.write_text(original.replace('coder-light\tcodex\tgpt-6.1-sol\tmax\tlong',
                                           'coder-light codex gpt-6.1-sol max long "--tag #literal" # personal comment'))
        before = table.read_text().splitlines()
        coordinator = self.root / f'cowork/{DAY}/coordinator.md'
        coordinator_before = coordinator.read_bytes()
        extra = '--sandbox workspace-write --tag "#updated" --config "label=two words"'
        own = {'COWORK_TASK': str(task)}
        self.cw('seat', 'set', 'coder-light', 'codex', 'custom', 'high', f'--args={extra}',
                env=own, script=self.root / 'cowork/cw')
        self.assertEqual(sum(a != b for a, b in zip(before, table.read_text().splitlines())), 1)
        self.assertIn('# personal comment', table.read_text())
        self.assertEqual(self.module().get_seat(self.root, 'coder-light')['args'], extra)
        self.cw('seat', 'set', 'coder-light', 'agy', 'other', 'xhigh', env=own)
        self.assertEqual(self.module().get_seat(self.root, 'coder-light')['args'], extra)
        self.assertIn('args=', task.read_text())
        self.cw('seat', 'set', 'coder-light', 'agy', 'other', 'xhigh', '--args=-', env=own)
        self.assertEqual(self.module().get_seat(self.root, 'coder-light')['args'], '-')
        self.assertIn('# personal comment', table.read_text())
        self.assertEqual(coordinator.read_bytes(), coordinator_before)
        self.assertEqual(self.calls(), [])

    def test_seat_args_append_to_all_adapters_and_preview_is_read_only(self):
        self.install()
        extra = '--config "label=two words" --tag "#literal" --literal "{name}" --note "$(touch never)"'
        expected = ['--config', 'label=two words', '--tag', '#literal', '--literal', '{name}', '--note', '$(touch never)']
        for agent in ('codex', 'agy', 'claude'):
            with self.subTest(agent=agent):
                self.cw('seat', 'set', 'coder-light', agent, 'model', 'high', f'--args={extra}')
                p = self.new(agent, seat='coder-light', size='small')
                before = self.snapshot()
                preview = self.cw('start', p, '--print').stdout
                self.assertEqual(shlex.split(preview.splitlines()[0])[-len(expected):], expected)
                self.assertEqual(before, self.snapshot())
                self.clear_calls()
                self.cw('start', p, live=True)
                launch = next(c for c in self.calls() if c[0] == 'run')
                self.assertEqual(launch[-len(expected):], expected)
                self.assertFalse((self.root / 'never').exists())

    def test_task_agent_override_retains_seat_args(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'codex', 'model', 'max', '--args=--tag "two words"')
        table = (self.root / 'cowork/seats.tsv').read_bytes()
        p = self.new(seat='coder-light', size='small')
        self.cw('set', p, 'agent=agy:override:xhigh:short')
        self.cw('start', p, live=True)
        launch = next(c for c in self.calls() if c[0] == 'run')
        self.assertEqual(launch[-7:], ['agy', '--model', 'override', '--effort', 'xhigh', '--tag', 'two words'])
        self.assertNotIn('--outlive-parent', launch)
        self.assertIn('COWORK_SEAT=coder-light', launch)
        self.cw('set', p, 'agent=-')
        self.assertEqual(shlex.split(self.cw('start', p, '--print').stdout.splitlines()[0])[-2:], ['--tag', 'two words'])
        self.assertEqual(table, (self.root / 'cowork/seats.tsv').read_bytes())

    def test_invalid_seat_args_are_rejected_before_writes(self):
        self.install()
        for extra in ('--config "unterminated', '--sandbox\nworkspace-write', '--sandbox\rworkspace-write'):
            with self.subTest(extra=extra):
                before = self.snapshot()
                self.cw('seat', 'set', 'coder-light', 'codex', 'model', 'max', f'--args={extra}', code=1)
                self.assertEqual(before, self.snapshot())
                self.assertEqual(self.calls(), [])

    def test_invalid_seat_column_quoting_stops_before_launch(self):
        self.install()
        p = self.new()
        table = self.root / 'cowork/seats.tsv'
        original = table.read_text()
        base = 'coder-light\tcodex\tgpt-6.1-sol\tmax\tlong'
        for suffix in (' --sandbox workspace-write', ' "unterminated',
                       ' ' + shlex.quote('--config "unterminated'), ' "one" "two"'):
            with self.subTest(suffix=suffix):
                table.write_text(original.replace(base, base + suffix))
                before = self.snapshot()
                result = self.cw('start', p, live=True, code=1)
                self.assertIn('Invalid seat', result.stderr)
                self.assertEqual(before, self.snapshot())
                self.assertEqual(self.calls(), [])

    def test_legacy_and_dash_seat_args_mean_no_extra_arguments(self):
        module = self.module()
        for suffix in ('', ' -', ' ""'):
            with self.subTest(suffix=suffix):
                row = module.seat_rows('coder-light codex model high long' + suffix)['coder-light']
                self.assertEqual(module.extra_argv(row['args']), [])

    def test_new_and_set_preserve_body_and_validate_names(self):
        self.install()
        p = self.new(approve=False)
        p.write_text(p.read_text() + 'User text: leave unchanged\n')
        before = p.read_text().split('## Goal', 1)[1]
        self.cw('set', p, 'status=approved', f'approved=user, {dt.date.today()}')
        self.assertEqual(before, p.read_text().split('## Goal', 1)[1])
        self.cw('new', 'work', '--seat', 'advisor', '--size', 'small', code=1)
        for name in ('../bad', 'x' * 21, 'Uppercase', ''):
            self.cw('new', name, '--seat', 'advisor', '--size', 'small', code=1)
        self.cw('set', p, 'unknown=value', code=1)

    def test_task_agent_override_preserves_seat_and_can_be_reset(self):
        self.install()
        table = (self.root / 'cowork/seats.tsv').read_bytes()
        self.cw('new', 'custom', '--seat', 'coder-heavy', '--size', 'small',
                '--agent', 'agy:user-model:xhigh:short')
        p = self.root / f'cowork/{DAY}/custom.md'
        self.assertIn('agent: agy:user-model:xhigh:short', p.read_text())
        self.cw('start', p, live=True)
        launch = next(c for c in self.calls() if c[0] == 'run')
        self.assertEqual(launch[-5:], ['agy', '--model', 'user-model', '--effort', 'xhigh'])
        self.assertNotIn('--outlive-parent', launch)
        self.assertIn('COWORK_SEAT=coder-heavy', launch)
        self.assertIn(f'{DAY}-custom', launch)
        self.assertIn('You are seat coder-heavy on task custom', self.calls()[-1][2])
        body = p.read_text().split('## Goal', 1)[1]
        self.cw('set', p, 'agent=claude:another-model:high')
        self.assertEqual(body, p.read_text().split('## Goal', 1)[1])
        self.clear_calls()
        self.cw('start', p, live=True)
        launch = next(c for c in self.calls() if c[0] == 'run')
        self.assertIn('--no-parent', launch)
        self.assertEqual(launch[-8:-1], ['claude', '-n', f'{DAY}-custom', '--model', 'another-model', '--effort', 'high'])
        self.cw('set', p, 'agent=-')
        self.assertIn('codex --no-daemon -m gpt-6-astra -c model_reasoning_effort=high',
                      self.cw('start', p, '--print').stdout)
        self.assertEqual(table, (self.root / 'cowork/seats.tsv').read_bytes())

    def test_task_agent_override_inherits_short_life_and_supports_old_records(self):
        self.install()
        p = self.new(seat='advisor', size='small')
        self.assertIn('agent: -', p.read_text())
        p.write_text(p.read_text().replace('agent: -\n', ''))
        self.assertIn('agy --model', self.cw('start', p, '--print').stdout)
        self.cw('set', p, 'agent=codex:chosen-model:max')
        output = self.cw('start', p, '--print').stdout
        self.assertIn('codex --no-daemon -m chosen-model -c model_reasoning_effort=max', output)
        self.assertNotIn('--outlive-parent', output)
        self.cw('set', p, 'agent=codex:chosen-model:max:long')
        self.assertIn('--no-parent', self.cw('start', p, '--print').stdout)

    def test_task_agent_override_rejects_bad_values_before_changes_or_launches(self):
        self.install()
        p = self.new(size='small')
        original = p.read_text()
        for value in ('', 'codex', 'codex:model', 'codex::high', 'codex:model:',
                      'codex:model:high:', 'codex:model:high:forever', 'codex:model:high:long:extra',
                      'unknown:model:high', 'codex:bad model:high', 'codex:model:high#bad',
                      'codex:model:high\nstatus: closed'):
            with self.subTest(value=value):
                before = self.snapshot()
                self.cw('new', 'invalid', '--seat', 'advisor', '--size', 'small', '--agent', value, code=1)
                self.cw('set', p, 'agent=' + value, code=1)
                self.assertEqual(before, self.snapshot())
                self.assertEqual(self.calls(), [])
        p.write_text(original.replace('agent: -', 'agent: unknown:model:high'))
        for flags in ((), ('--print',)):
            self.cw('start', p, *flags, live=True, code=1)
        self.assertEqual(self.calls(), [])

    def test_large_approval_gate(self):
        self.install()
        p = self.new(approve=False)
        self.cw('start', p, live=True, code=1)
        self.cw('set', p, 'status=approved')
        self.cw('start', p, live=True, code=1)
        self.assertEqual(self.calls(), [])
        self.cw('set', p, 'status=blocked', f'approved=user, {dt.date.today()}')
        self.cw('start', p, live=True)
        self.assertIn('status: running', p.read_text())

    def test_task_header_enums_reject_invalid_edits_without_writes(self):
        self.install()
        p = self.new(approve=False)
        before = self.snapshot()
        for key, invalid in (('size', ('Large', 'urgent', '')), ('status', ('Approved', 'unknown', ''))):
            for value in invalid:
                with self.subTest(key=key, value=value):
                    result = self.cw('set', p, f'{key}={value}', code=1)
                    self.assertIn(f'Invalid task {key}', result.stderr)
                    self.assertIn(str(p), result.stderr)
                    self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_malformed_task_header_cannot_preview_or_launch(self):
        self.install()
        p = self.new(approve=False)
        original = p.read_text()
        for key, invalid in (('kind', ('Large', 'urgent', '', None)),
                             ('status', ('Approved', 'unknown', '', None))):
            for value in invalid:
                with self.subTest(key=key, value=value):
                    replacement = '' if value is None else f'{key}: {value}\n'
                    p.write_text(''.join(replacement if line.startswith(key + ':') else line
                                         for line in original.splitlines(keepends=True)))
                    before = self.snapshot()
                    for flags in (('--print',), ()):
                        result = self.cw('start', p, *flags, live=True, code=1)
                        self.assertIn(f'Invalid task {key}', result.stderr)
                        self.assertIn(str(p), result.stderr)
                        self.assertNotIn('hc run', result.stdout)
                        self.assertEqual(before, self.snapshot())
                    self.assertEqual(self.calls(), [])

    def test_header_syntax_and_agent_errors_include_task_path(self):
        self.install()
        p = self.new()
        original = p.read_text()
        for invalid in ('No frontmatter\n', '---\nsize: small\n', original.replace('agent: -', 'agent: unknown:model:high')):
            with self.subTest(invalid=invalid):
                p.write_text(invalid)
                before = self.snapshot()
                for command in (('start', p), ('index',), ('status',)):
                    result = self.cw(*command, live=True, code=1)
                    self.assertIn(str(p), result.stderr)
                    self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.calls(), [])

    def test_seat_text_adds_agent_field_to_legacy_template(self):
        module = self.module()
        legacy = (REPO / 'templates/task.md').read_text().replace('agent: -\n', '')
        legacy = legacy.replace('kind: {kind}', 'size: {size}').format(task='successor', size='seat', project='-', line='-', parent='coordinator', seat='coordinator')
        with mock.patch.object(module, 'render', return_value=legacy):
            text = module.new_text('successor', 'seat', 'coordinator', 'coordinator')
        self.assertEqual(module.header(text)[0]['agent'], '-')
        self.assertIn('## Handover\n', text)

    def test_coordinator_identity_refuses_before_side_effects(self):
        self.install(live=True)
        p = self.new()
        commands = [
            ('start', p), ('start', p, '--print'),
            ('lock', 'next', 'gpu', '-'), ('lock', 'take', 'gpu'),
            ('lock', 'release', 'gpu', '--force'),
            ('handover', 'context'), ('handover', 'tokens'),
            ('seat', 'set', 'advisor', 'codex', 'model', 'high'),
        ]
        before = self.snapshot()
        for command in commands:
            with self.subTest(command=command):
                result = self.cw(*command, env={'HC_TERMINAL_ID': 't99'}, code=1)
                self.assertIn('HC_TERMINAL_ID=t99 but cowork/coordinator.addr is t1; '
                              'if you are t1, rerun with HC_TERMINAL_ID=t1', result.stderr)
                self.assertEqual(before, self.snapshot())
                self.assertEqual(self.calls(), [])
        self.cw('start', p, '--print', env={'HC_TERMINAL_ID': 't1'})
        self.cw('lock', 'next', 'gpu', '-', live=True)
        self.cw('lock', 'take', 'gpu', live=True)
        self.cw('lock', 'release', 'gpu', '--force', live=True)
        self.cw('seat', 'set', 'advisor', 'codex', 'model', 'high', live=True)

    def test_identity_guard_exempts_seats_offline_accept_and_report(self):
        self.install(live=True)
        p = self.new()
        seat = {'HC_TERMINAL_ID': 't99', 'COWORK_TASK': str(p)}
        self.cw('start', p, '--print', env=seat)
        self.cw('lock', 'take', 'gpu', env=seat)
        self.cw('lock', 'release', 'gpu', env=seat)
        coordinator = self.root / f'cowork/{DAY}/coordinator.md'
        coord_env = {'HC_TERMINAL_ID': 't99', 'COWORK_TASK': str(coordinator)}
        self.cw('lock', 'next', 'gpu', '-', env=coord_env)
        self.cw('lock', 'take', 'gpu', env=coord_env)
        self.cw('lock', 'release', 'gpu', '--force', env=coord_env)
        self.cw('seat', 'set', 'advisor', 'codex', 'model', 'high', env=coord_env)
        self.cw('start', p, '--print')
        self.cw('seat', 'set', 'advisor', 'codex', 'model', 'high')
        self.cw('lock', 'next', 'gpu', '-')
        self.cw('lock', 'take', 'gpu')
        self.cw('lock', 'release', 'gpu', '--force', code=1)  # release succeeds; report is offline
        self.cw('report', 'identity exemption; result.md', env={'HC_TERMINAL_ID': 't99'})
        self.assertTrue(any(c[:2] == ['send', 't1'] for c in self.calls()))
        self.cw('handover', '--accept', env={'HC_TERMINAL_ID': 't99'})
        self.assertTrue((self.root / 'cowork/coordinator.addr').read_text().startswith('t99 '))

    def test_all_adapters_short_and_long(self):
        self.install()
        for agent in ('claude', 'agy', 'codex'):
            for life in ('short', 'long'):
                with self.subTest(agent=agent, life=life):
                    self.cw('seat', 'set', 'coder-light', agent, 'test-model', 'high', life)
                    task = agent + '-' + life
                    p = self.new(task, seat='coder-light')
                    self.clear_calls()
                    self.cw('start', p, live=True)
                    calls = self.calls()
                    launch = next(c for c in calls if c[0] == 'run')
                    name = f'{DAY}-{task}'
                    self.assertEqual(launch[launch.index('--name') + 1], name)
                    self.assertEqual(launch[launch.index('--cwd') + 1], str(self.root))
                    self.assertNotIn('--outlive-parent', launch)
                    self.assertEqual('--no-parent' in launch, life == 'long')
                    self.assertEqual('--parent' in launch, life == 'short')
                    if life == 'short':
                        self.assertEqual(launch[launch.index('--parent') + 1], 't1')
                    self.assertIn('herdr.space=space-a', launch)
                    payload = launch[launch.index('--') + 1:]
                    self.assertEqual(payload[:4], ['env', f'COWORK_ROOT={self.root}', f'COWORK_TASK={p}', 'COWORK_SEAT=coder-light'])
                    if agent in ('codex', 'agy'):
                        expected = (['codex', '--no-daemon', '-m', 'test-model', '-c', 'model_reasoning_effort=high']
                                    if agent == 'codex' else ['agy', '--model', 'test-model', '--effort', 'high'])
                        self.assertEqual(payload[4:], expected)
                        self.assertEqual([c[0] for c in calls], ['ls', 'get', 'run', 'wait', 'send', 'wait', 'keys', 'wait', 'send'] if agent == 'agy' else ['ls', 'get', 'run', 'wait', 'keys', 'wait', 'send'])
                        self.assertEqual(calls[-3], ['keys', 't42', *list('/rename'), 'space', *list(name), 'enter', '--json'])
                        preview = self.cw('start', p, '--print').stdout
                        self.assertIn('hc keys ' + name + ' / r e n a m e space ', preview)
                        self.assertNotIn('hc send ' + name + " '/rename", preview)
                        self.assertIn('Read skill cowork', calls[-1][2])
                    elif agent == 'claude':
                        self.assertEqual(payload[4:11], ['claude', '-n', name, '--model', 'test-model', '--effort', 'high'])
                    self.assertIn(f'terminal: {name} (t42)', p.read_text())

    def test_print_and_no_herdr_are_read_only(self):
        self.install()
        p = self.new()
        before = self.snapshot()
        output = self.cw('start', p).stdout
        self.assertIn('codex --no-daemon', output)
        self.assertIn('/ r e n a m e space', output)
        self.assertEqual(self.calls(), [])
        self.cw('start', p, '--print', live=True)
        self.assertEqual([c[0] for c in self.calls()], ['ls', 'get'])
        self.assertEqual(before, self.snapshot())

    def test_name_collisions_and_exhaustion(self):
        self.install()
        p = self.new('x' * 20)
        name = f'{DAY}-' + 'x' * 20
        self.configure(live=[{'name': name, 'state': 'live'}, {'name': name + '-2', 'state': 'finished'}])
        self.cw('start', p, live=True)
        launch = next(c for c in self.calls() if c[0] == 'run')
        self.assertIn(name + '-2', launch)
        self.assertLessEqual(len(name + '-9'), 32)
        self.clear_calls()
        self.configure(live=[{'name': name + suffix, 'state': 'live'} for suffix in ('', *('-' + str(n) for n in range(2, 10)))])
        self.cw('start', p, live=True, code=1)
        self.assertNotIn('run', [c[0] for c in self.calls()])

    def test_blocked_wait_stops_before_keys_or_task(self):
        self.install()
        p = self.new()
        self.configure(waits=[{'status': 'blocked', 'reason': 'status'}])
        result = self.cw('start', p, live=True, code=2)
        self.assertIn('Trust this folder?', result.stderr)
        self.assertIn('hc keys t42', result.stderr)
        self.assertEqual([c[0] for c in self.calls()], ['ls', 'get', 'run', *['wait', 'read'] * 3])
        self.assertNotIn('status: running', p.read_text())

    def test_second_wait_blocked_and_timeout_retry(self):
        self.install()
        p = self.new()
        self.configure(waits=[{'status': 'working', 'reason': 'timeout'}, {'status': 'idle'}, {'status': 'blocked'}])
        self.cw('start', p, live=True, code=2)
        self.assertEqual(len([c for c in self.calls() if c[0] == 'send']), 0)
        self.assertEqual(len([c for c in self.calls() if c[0] == 'keys']), 1)
        self.assertEqual(len([c for c in self.calls() if c[0] == 'wait']), 5)

    def test_codex_rename_key_failure_does_not_send_task_or_retry(self):
        self.install()
        p = self.new()
        self.configure(fail=['keys'])
        self.cw('start', p, live=True, code=1)
        self.assertEqual([c[0] for c in self.calls()], ['ls', 'get', 'run', 'wait', 'keys'])
        self.assertNotIn('status: running', p.read_text())

    def test_approve_matches_agent_option_text(self):
        self.install()
        cases = [
            ('codex', f'Do you trust the contents of this directory?\n{self.root}\n❯ 1. Trust and continue\n  2. Quit', ['enter']),
            ('claude', f'Do you trust this folder?\n{self.root}\n❯ 1. No, exit\n  2. Yes, I trust this folder', ['down', 'enter']),
            ('agy', f'Do you trust the files in this folder?\n{self.root}\n❯ 1. Do not trust\n  2. Trust parent folder\n  3. Trust folder', ['down', 'down', 'enter']),
            ('codex', f'Do you trust this directory?\nDirectory: {self.root}\n  1. Quit\n  2. Trust and continue\n❯ 3. Cancel', ['up', 'enter']),
            ('agy', 'Requesting permission for:\n  cowork/cw report "done; docs/result.md"\nRun this command?\n❯ 1. Allow once\n  2. No\n  3. Always allow in this conversation', ['down', 'down', 'enter']),
        ]
        for agent, screen, keys in cases:
            with self.subTest(agent=agent, screen=screen):
                self.configure(screens=self.claude_screens(screen) if agent == 'claude' else [screen],
                               get={'t42': {'status': {'app': agent, 'state': 'blocked'}}})
                self.clear_calls()
                self.cw('approve', 't42', live=True)
                expected = [['read', 't42', '--lines', '0'], ['get', 't42', '--json']]
                if agent == 'claude':
                    expected += [['read', 't42', '--lines', '0'], ['get', 't42', '--json']] * 2
                    expected += [['keys', 't42', 'down', '--json'], ['read', 't42', '--lines', '0'],
                                 ['get', 't42', '--json'], ['keys', 't42', 'enter', '--json']]
                else:
                    expected += [['keys', 't42', *keys, '--json']]
                self.assertEqual(self.calls(), expected)

    def test_approve_sanitized_captured_screens(self):
        self.install()
        codex = (SCREENS / 'codex-trust.txt').read_text()
        folder = Path(next(line.strip() for line in codex.splitlines() if line.strip().startswith('/')))
        agy = (SCREENS / 'agy-trust.txt').read_text()
        agy_folder = Path(next(line.strip() for line in agy.splitlines() if line.strip().startswith('/')))
        claude = (SCREENS / 'claude-trust-live.txt').read_text()
        claude_folder = Path(next(line.strip() for line in claude.splitlines() if line.strip().startswith('/')))
        cases = [
            ('codex-trust.txt', folder, {'status': None, 'foreground': {'argv': ['/bin/codex']}}, ['enter']),
            ('codex-trust.txt', folder, {'status': {'app': 'codex', 'state': 'blocked'}}, ['enter']),
            ('codex-trust.txt', folder, {'status': None, 'argv': ['env', 'COWORK_SEAT=coder-light', '/bin/codex']}, ['enter']),
            ('claude-trust.txt', self.root, {'status': {'app': 'claude', 'state': 'blocked'},
                                          'foreground': {'argv': ['node'], 'cwd': str(self.root)}}, ['down', 'enter']),
            ('claude-trust-live.txt', claude_folder,
             {'status': {'app': 'claude', 'state': 'blocked'},
              'foreground': {'argv': ['node'], 'cwd': str(claude_folder)}}, ['down', 'enter']),
            ('agy-trust.txt', agy_folder, {'status': {'app': 'antigravity', 'state': 'blocked'},
                                        'foreground': {'argv': ['/bin/agy']}}, ['enter']),
            ('agy-cw-permission.txt', self.root, {'status': {'app': 'codex', 'state': 'blocked'},
                                               'foreground': {'argv': ['/bin/agy']}}, ['down', 'enter']),
        ]
        for fixture, root, info, keys in cases:
            with self.subTest(fixture=fixture, info=info):
                capture = (SCREENS / fixture).read_text()
                self.configure(screens=self.claude_screens(capture) if fixture.startswith('claude-') else [capture],
                               get={'t42': {'argv': ['env', 'COWORK_TASK=codex', 'sh'], 'cwd': str(root), **info}})
                self.clear_calls()
                self.cw('--root', root, 'approve', 't42', live=True)
                if fixture.startswith('claude-'):
                    self.assertEqual([call for call in self.calls() if call[0] == 'keys'],
                                     [['keys', 't42', 'down', '--json'], ['keys', 't42', 'enter', '--json']])
                else:
                    self.assertEqual(self.calls()[-1], ['keys', 't42', *keys, '--json'])

    def test_pathless_claude_trust_requires_matching_foreground_cwd(self):
        self.install()
        for foreground in ({'cwd': str(self.work)}, {'cwd': None}, {'cwd': ''}, {'cwd': '.'}, {}, None):
            with self.subTest(foreground=foreground):
                self.configure(screen=(SCREENS / 'claude-trust.txt').read_text(),
                               get={'t42': {'status': {'app': 'claude', 'state': 'blocked'},
                                            'cwd': str(self.root), 'foreground': foreground}})
                self.clear_calls()
                self.cw('approve', 't42', live=True, code=2)
                self.assertNotIn('keys', [c[0] for c in self.calls()])

    def test_permission_requires_complete_current_command_region(self):
        self.install()
        fixture = (SCREENS / 'agy-cw-permission.txt').read_text()
        before, rest = fixture.split('Requesting permission for:\n')
        _, after = rest.split('\nRun this command?')
        requests = [
            'cowork/cw seats\ntouch x', 'touch x', 'cowork/cw seats; touch x',
            'cowork/cw seats && touch x', 'cowork/cw seats || touch x',
            'cowork/cw seats | touch x', 'cowork/cw report "$(touch x)"',
            'cowork/cw report "`touch x`"', 'cowork/cw seats > x',
            'cowork/cw seats\n', 'cowork/cw seats\nRequesting permission for:\ntouch x',
        ]
        for request in requests:
            with self.subTest(request=request):
                screen = before + 'Previous command:\ncowork/cw seats\nRequesting permission for:\n' + request + '\nRun this command?' + after
                self.configure(screen=screen, get={'t42': {'status': {'app': 'agy', 'state': 'blocked'}}})
                self.clear_calls()
                self.cw('approve', 't42', live=True, code=2)
                self.assertNotIn('keys', [c[0] for c in self.calls()])

        for screen in (fixture.replace('Run this command?', 'Run it?'),
                       fixture.replace('Requesting permission for:', 'Command:'),
                       fixture + '\nRun this command?'):
            with self.subTest(screen=screen):
                self.configure(screen=screen, get={'t42': {'status': {'app': 'agy', 'state': 'blocked'}}})
                self.clear_calls()
                self.cw('approve', 't42', live=True, code=2)
                self.assertNotIn('keys', [c[0] for c in self.calls()])

    def test_agy_hc_send_permission_capture_is_never_approved(self):
        self.install()
        self.configure(screen=(SCREENS / 'agy-hc-send-permission.txt').read_text(),
                       get={'t42': {'status': {'app': 'agy', 'state': 'blocked'}}})
        self.cw('approve', 't42', live=True, code=2)
        self.assertEqual(self.calls(), [['read', 't42', '--lines', '0'], ['get', 't42', '--json']])

    def test_pathless_claude_trust_uses_current_folder_after_directory_change(self):
        self.install()
        self.configure(screens=self.claude_screens((SCREENS / 'claude-trust.txt').read_text()),
                       get={'t42': {'status': {'app': 'claude', 'state': 'blocked'},
                                    'cwd': str(self.work), 'foreground': {'cwd': str(self.root)}}})
        self.cw('approve', 't42', live=True)
        self.assertEqual([call for call in self.calls() if call[0] == 'keys'],
                         [['keys', 't42', 'down', '--json'], ['keys', 't42', 'enter', '--json']])

    def test_approve_refuses_unrecognized_or_out_of_scope_prompts(self):
        self.install()
        screens = [
            f'Do you trust this folder?\n{self.root}/other\n❯ 1. Trust and continue\n  2. Quit',
            f'Do you trust this folder?\n{self.root}\n{self.work}\n❯ 1. Trust and continue\n  2. Quit',
            'Allow execution?\nCommand: rm -rf output\n❯ 1. Yes, proceed\n  2. No',
            'Allow execution?\nCommand: echo cowork/cw\n❯ 1. Yes, proceed\n  2. No',
            'Allow execution?\nCommand: cowork/cw report x; rm -rf output\n❯ 1. Yes, proceed\n  2. No',
            'Allow execution?\nCommand: cowork/cw report "$(touch bad)"\n❯ 1. Yes, proceed\n  2. No',
            f'Do you trust this folder?\n{self.root}\nNo option list',
        ]
        for screen in screens:
            with self.subTest(screen=screen):
                self.configure(screen=screen)
                self.clear_calls()
                result = self.cw('approve', 't42', live=True, code=2)
                self.assertIn(screen.splitlines()[-1], result.stderr)
                self.assertNotIn('keys', [c[0] for c in self.calls()])

    def test_start_approves_recognized_blocked_wait(self):
        self.install()
        p = self.new()
        self.configure(waits=[{'status': 'blocked'}, {'status': 'idle'}],
                       screen=f'Do you trust this folder?\n{self.root}\n❯ 1. Trust and continue\n  2. Quit')
        self.cw('start', p, live=True)
        self.assertEqual([c[0] for c in self.calls()], ['ls', 'get', 'run', 'wait', 'read', 'keys', 'wait', 'keys', 'wait', 'send'])
        self.assertIn('status: running', p.read_text())

    def test_start_timeout_inspects_and_approves_null_status(self):
        self.install()
        p = self.new()
        self.configure(waits=[{'reason': 'timeout', 'status': None}, {'status': 'idle'}],
                       screen=f'Folder access\n{self.root}\nTrust this folder?\n› 1. Trust and continue\n  2. Back to Agent Command Center')
        self.cw('start', p, live=True)
        self.assertEqual([c[0] for c in self.calls()], ['ls', 'get', 'run', 'wait', 'read', 'keys', 'wait', 'keys', 'wait', 'send'])
        self.assertIn('status: running', p.read_text())

    def test_agy_transient_blocked_startup_and_permission(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'agy', 'model', 'high')
        p = self.new(seat='coder-light')
        self.configure(waits=[{'status': 'blocked'}, {'status': 'blocked'}, {'status': 'idle'}],
                       screens=['Signing in...', (SCREENS / 'agy-cw-permission.txt').read_text()])
        self.cw('start', p, live=True)
        calls = self.calls()
        self.assertEqual([c[0] for c in calls], ['ls', 'get', 'run', 'wait', 'read', 'wait', 'read', 'keys', 'wait', 'send', 'wait', 'keys', 'wait', 'send'])
        keys = [c for c in calls if c[0] == 'keys']
        self.assertEqual(keys[0], ['keys', 't42', 'down', 'enter', '--json'])
        self.assertEqual(keys[1], ['keys', 't42', *list('/rename'), 'space', *list(f'{DAY}-work'), 'enter', '--json'])
        self.assertNotIn('/rename', calls[-1][2])
        self.assertIn('status: running', p.read_text())

    def test_handover_approves_recognized_blocked_wait(self):
        self.install(live=True)
        self.configure(accept=True, get={'t42': {'status': {'app': 'claude', 'state': 'blocked'}}},
                       screens=self.claude_screens(f'Do you trust this folder?\n{self.root}\n❯ 1. No, exit\n  2. Yes, I trust this folder'))
        self.cw('handover', 'context', live=True)
        self.assertEqual([call for call in self.calls() if call[0] == 'keys'],
                         [['keys', 't42', 'down', '--json'], ['keys', 't42', 'enter', '--json']])

    def test_claude_handover_waits_for_complete_live_trust_screen(self):
        self.install(live=True)
        capture = (SCREENS / 'claude-trust-live.txt').read_text()
        folder = next(line.strip() for line in capture.splitlines() if line.strip().startswith('/'))
        complete = capture.replace(folder, str(self.root))
        partial = complete.split(' ❯ No, exit')[0]
        self.configure(accept=True, screens=[partial, *self.claude_screens(complete)],
                       get={'t42': {'foreground': {'cwd': str(self.root)}, 'status': {'app': 'claude', 'state': 'blocked'}}})
        self.cw('handover', 'context', live=True)
        calls = self.calls()
        self.assertEqual([c for c in calls if c[0] == 'keys'],
                         [['keys', 't42', 'down', '--json'], ['keys', 't42', 'enter', '--json']])
        self.assertEqual(len([c for c in calls if c[0] == 'read']), 5)

    def test_unmatched_blocked_screen_stops_after_three_identical_reads(self):
        module = self.module()
        for screens in (['Signing in...'] * 3,
                        ['Trust this folder? A', 'Trust this folder? A', 'Trust this folder? B'] + ['Trust this folder? B'] * 2):
            with self.subTest(screens=screens):
                unread = iter(screens)
                def fake_hc(*args, **kwargs):
                    return next(unread) if args[0] == 'read' else {'status': 'blocked'}
                with mock.patch.object(module, 'hc', side_effect=fake_hc) as calls, mock.patch.object(module.time, 'sleep'), mock.patch.object(module.sys, 'stderr'):
                    with self.assertRaises(module.Blocked):
                        module.wait_ready('t42', self.root, 'codex')
                self.assertEqual(sum(call.args[0] == 'read' for call in calls.call_args_list), len(screens))
                self.assertFalse(any(call.args[0] == 'keys' for call in calls.call_args_list))

    def test_claude_start_waits_and_approves_root_trust(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high')
        p = self.new(seat='coder-light')
        self.configure(waits=[{'status': 'blocked'}, {'status': 'idle'}],
                       get={'t42': {'status': {'state': 'blocked'}}},
                       screens=self.claude_screens(f'Do you trust this folder?\n{self.root}\n❯ 1. No, exit\n  2. Yes, I trust this folder'))
        self.cw('start', p, live=True)
        self.assertEqual([call for call in self.calls() if call[0] == 'keys'],
                         [['keys', 't42', 'down', '--json'], ['keys', 't42', 'enter', '--json']])
        self.assertIn('status: running', p.read_text())

    def test_claude_known_undelivered_task_recovers_after_read(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high')
        p = self.new(seat='coder-light')
        self.configure(run={'first_message': {'sent': False, 'reason': 'blocked'}},
                       waits=[{'status': 'blocked'}, {'status': 'idle'}],
                       get={'t42': {'status': {'state': 'blocked'}}},
                       screens=[f'Do you trust this folder?\n{self.root}\n❯ 1. No, exit\n  2. Yes, I trust this folder',
                                *self.claude_screens(f'Do you trust this folder?\n{self.root}\n❯ 1. No, exit\n  2. Yes, I trust this folder')])
        self.cw('start', p, live=True)
        calls = self.calls()
        self.assertEqual([c[0] for c in calls], ['ls', 'get', 'run', 'read', 'wait', 'read', 'get',
                                               'read', 'get', 'read', 'get', 'keys',
                                               'read', 'get', 'keys', 'wait', 'send', 'wait'])
        self.assertEqual(calls[2][-1], next(call[2] for call in calls if call[0] == 'send'))

    def test_approve_never_types_into_nonblocked_terminal(self):
        self.install()
        self.configure(screen=f'Do you trust this folder?\n{self.root}\n❯ 1. Trust and continue\n  2. Quit')
        self.cw('approve', 't42', live=True, code=2)
        self.assertNotIn('keys', [c[0] for c in self.calls()])

    def test_repeated_blocked_prompt_is_not_approved_twice(self):
        self.install()
        p = self.new()
        self.configure(waits=[{'status': 'blocked'}], screen=f'Do you trust this folder?\n{self.root}\n❯ 1. Trust and continue\n  2. Quit')
        self.cw('start', p, live=True, code=2)
        self.assertEqual(len([c for c in self.calls() if c[0] == 'keys']), 1)

    def test_claude_traced_trust_separates_navigation_and_confirmation(self):
        module = self.module()
        before = (SCREENS / 'claude-trust-run2-before.txt').read_text()
        selected = (SCREENS / 'claude-trust-run2-selected.txt').read_text()
        root = Path(next(line.strip() for line in before.splitlines() if line.strip().startswith('/')))
        for screen, expected_keys in ((before, [('down',), ('enter',)]), (selected, [('enter',)])):
            with self.subTest(initial=screen):
                elapsed, calls, navigated = [0], [], [False]
                def fake_hc(*args, **kwargs):
                    calls.append((elapsed[0], args))
                    if args[0] == 'read':
                        return selected if navigated[0] or screen == selected else before
                    if args[0] == 'keys' and 'down' in args:
                        navigated[0] = True
                    return {'state': 'live', 'status': {'state': 'blocked'},
                            'foreground': {'cwd': str(root)}}
                def sleep(seconds):
                    elapsed[0] += seconds
                with mock.patch.object(module, 'hc', side_effect=fake_hc), \
                        mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), \
                        mock.patch.object(module.time, 'sleep', side_effect=sleep):
                    self.assertTrue(module.approve(root, 't42', 'claude', set(), screen=screen))
                keys = [(when, args[2:-1]) for when, args in calls if args[0] == 'keys']
                self.assertEqual([args for _, args in keys], expected_keys)
                self.assertGreaterEqual(keys[0][0], 2)
                if len(keys) > 1:
                    self.assertGreaterEqual(keys[-1][0] - keys[0][0], 1)
                self.assertEqual([args[0] for _, args in calls][-3:], ['read', 'get', 'keys'])

    def test_claude_traced_trust_revalidates_before_enter(self):
        module = self.module()
        before = (SCREENS / 'claude-trust-run2-before.txt').read_text()
        selected = (SCREENS / 'claude-trust-run2-selected.txt').read_text()
        root = Path(next(line.strip() for line in before.splitlines() if line.strip().startswith('/')))
        for after in (before, selected.replace(str(root), str(self.root)), 'New permission request'):
            with self.subTest(after=after):
                elapsed, navigated = [0], [False]
                def fake_hc(*args, **kwargs):
                    if args[0] == 'read':
                        return after if navigated[0] else before
                    if args[0] == 'keys':
                        navigated[0] = True
                    return {
                        'state': 'live', 'status': {'state': 'blocked'}, 'foreground': {'cwd': str(root)}}
                def sleep(seconds):
                    elapsed[0] += seconds
                with mock.patch.object(module, 'hc', side_effect=fake_hc) as calls, \
                        mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), \
                        mock.patch.object(module.time, 'sleep', side_effect=sleep), mock.patch.object(module.sys, 'stderr'):
                    with self.assertRaisesRegex(module.Blocked, 'approval keys were already pressed'):
                        module.approve(root, 't42', 'claude', set(), screen=before)
                self.assertEqual([call.args[2:-1] for call in calls.call_args_list if call.args[0] == 'keys'],
                                 [('down',)] * (3 if after == before else 1))

    def test_claude_traced_trust_pathless_confirmation_rechecks_foreground(self):
        module = self.module()
        screen = (SCREENS / 'claude-trust.txt').read_text().replace('❯ No, exit', '  No, exit').replace(
            '  Yes, I trust this folder', '❯ Yes, I trust this folder')
        contexts = iter([str(self.root), str(self.work)])
        def fake_hc(*args, **kwargs):
            return screen if args[0] == 'read' else {
                'state': 'live', 'status': {'state': 'blocked'}, 'foreground': {'cwd': next(contexts)}}
        with mock.patch.object(module, 'hc', side_effect=fake_hc) as calls, \
                mock.patch.object(module.time, 'sleep'), mock.patch.object(module.sys, 'stderr'):
            with self.assertRaisesRegex(module.Blocked, 'no keys were pressed'):
                module.approve(self.root, 't42', 'claude', set(), screen=screen)
        self.assertFalse(any(call.args[0] == 'keys' for call in calls.call_args_list))

    def test_claude_traced_trust_never_navigates_after_prompt_finishes(self):
        module = self.module()
        screen = (SCREENS / 'claude-trust.txt').read_text()
        for status in ('working', 'idle', 'done'):
            with self.subTest(status=status), \
                    mock.patch.object(module, 'hc', return_value={'state': 'live',
                                      'foreground': {'cwd': str(self.root)}, 'status': {'state': status}}) as calls, \
                    mock.patch.object(module.sys, 'stderr'):
                with self.assertRaisesRegex(module.Blocked, 'no keys were pressed'):
                    module.approve(self.root, 't42', 'claude', screen=screen)
                self.assertEqual([call.args[0] for call in calls.call_args_list], ['get'])

    def test_claude_traced_trust_skips_enter_when_prompt_finishes_during_pause(self):
        module = self.module()
        screens = self.claude_screens((SCREENS / 'claude-trust.txt').read_text())
        before, selected = screens[0], screens[-1]
        for status in ('working', 'idle', 'done'):
            with self.subTest(status=status):
                contexts = iter(['blocked', status])
                def fake_hc(*args, **kwargs):
                    if args[0] == 'read':
                        return selected
                    return {'state': 'live', 'foreground': {'cwd': str(self.root)},
                            'status': {'state': next(contexts)}} if args[0] == 'get' else {}
                with mock.patch.object(module, 'hc', side_effect=fake_hc) as calls, \
                        mock.patch.object(module.time, 'sleep'):
                    self.assertTrue(module.approve(self.root, 't42', 'claude', set(), screen=before))
                self.assertFalse(any(call.args[0] == 'keys' for call in calls.call_args_list))

    def test_traced_trust_blocked_messages_distinguish_prior_keys(self):
        module = self.module()
        screen = f'Trust this folder?\n{self.root}\n> 1. Trust and continue\n  2. Quit'
        seen = set()
        with mock.patch.object(module, 'hc') as calls, mock.patch.object(module.sys, 'stderr'):
            with self.assertRaisesRegex(module.Blocked, 'no keys were pressed'):
                module.approve(self.root, 't42', 'codex', seen, screen='Unknown prompt')
            calls.assert_not_called()
            self.assertTrue(module.approve(self.root, 't42', 'codex', seen, screen=screen))
            with self.assertRaisesRegex(module.Blocked, 'approval keys were already pressed'):
                module.approve(self.root, 't42', 'codex', seen, screen=screen)
            calls.assert_called_once_with('keys', 't42', 'enter', '--json', deadline=mock.ANY)

    def test_claude_recheck_trust_waits_before_any_key(self):
        result, error, _, calls = self.run_recheck_trust()
        self.assertIsNone(error)
        self.assertTrue(result)
        keys = [(when, args[2:-1]) for when, args in calls if args[0] == 'keys']
        self.assertEqual([args for _, args in keys], [('down',), ('enter',)])
        self.assertGreaterEqual(keys[0][0], 2)
        self.assertGreaterEqual(sum(args[0] == 'read' and when <= keys[0][0] for when, args in calls), 2)
        self.assertGreaterEqual(keys[1][0] - keys[0][0], 1)

    def test_claude_recheck_trust_retries_dropped_navigation(self):
        for accepted_on in (2, 3):
            with self.subTest(accepted_on=accepted_on):
                result, error, _, calls = self.run_recheck_trust(accepted_on=accepted_on)
                self.assertIsNone(error)
                self.assertTrue(result)
                keys = [(when, args[2:-1]) for when, args in calls if args[0] == 'keys']
                self.assertEqual([args for _, args in keys], [('down',)] * accepted_on + [('enter',)])
                self.assertTrue(all(later[0] - earlier[0] >= 1 for earlier, later in zip(keys, keys[1:])))

    def test_claude_recheck_trust_navigation_retries_are_bounded(self):
        result, error, elapsed, calls = self.run_recheck_trust(accepted_on=None)
        self.assertIsNone(result)
        self.assertEqual(type(error).__name__, 'Blocked')
        self.assertIn('approval keys were already pressed', str(error))
        self.assertEqual([args[2:-1] for _, args in calls if args[0] == 'keys'], [('down',)] * 3)
        self.assertLessEqual(elapsed, 5)

    def test_claude_recheck_trust_redraw_restarts_stability_check(self):
        result, error, _, calls = self.run_recheck_trust(redraw=True)
        self.assertIsNone(error)
        self.assertTrue(result)
        self.assertGreaterEqual(next(when for when, args in calls if args[0] == 'keys'), 3)

    def test_claude_recheck_trust_stays_inside_startup_deadline(self):
        result, error, elapsed, calls = self.run_recheck_trust(deadline=1.5)
        self.assertIsNone(result)
        self.assertIn('startup timed out', str(error))
        self.assertEqual(elapsed, 1.5)
        self.assertFalse(any(args[0] == 'keys' for _, args in calls))

    def test_claude_audit_trust_confirmation_requires_explicit_unique_marker(self):
        partial = f'Trust this folder?\n{self.root}\n  Yes, I trust this folder\n'
        selected = self.claude_screens((SCREENS / 'claude-trust.txt').read_text())[-1]
        for after in (partial, selected.replace('❯', ' '), selected.replace('  No, exit', '❯ No, exit')):
            with self.subTest(after=after):
                result, error, keys = self.run_audit_trust(after=after)
                self.assertIsNone(result)
                self.assertEqual(type(error).__name__, 'Blocked')
                self.assertEqual(keys, [['down']])

    def test_claude_audit_trust_conflicting_foreground_blocks_path_bearing_screen(self):
        result, error, keys = self.run_audit_trust(cwd_after=str(self.work))
        self.assertIsNone(result)
        self.assertEqual(type(error).__name__, 'Blocked')
        self.assertEqual(keys, [['down']])

    def test_claude_audit_trust_cosmetic_redraw_never_confirms_twice(self):
        before = (SCREENS / 'claude-trust-run2-before.txt').read_text()
        folder = next(line.strip() for line in before.splitlines() if line.strip().startswith('/'))
        selected = self.claude_screens(before.replace(folder, str(self.root)))[-1]
        for redrawn in (selected + '\n', '\x1b[32m' + selected + '\x1b[0m',
                        selected.replace('No, exit', 'NO, EXIT').replace('Yes, I trust', 'YES, I TRUST'),
                        selected.replace(str(self.root), str(self.root) + '/.'),
                        selected.replace('  No, exit', '  1. No, exit').replace('❯ Yes, I trust', '❯ 2. Yes, I trust')):
            with self.subTest(redrawn=redrawn):
                seen = set()
                result, error, keys = self.run_audit_trust(seen=seen)
                self.assertTrue(result)
                self.assertIsNone(error)
                self.assertEqual(keys, [['down'], ['enter']])
                result, error, keys = self.run_audit_trust(initial=redrawn, after=redrawn, seen=seen)
                self.assertIsNone(result)
                self.assertIn('already pressed', str(error))
                self.assertEqual(keys, [])

    def test_claude_audit_trust_confirmation_history_is_per_terminal(self):
        seen = set()
        for name in ('t45', 't46'):
            with self.subTest(name=name):
                result, error, keys = self.run_audit_trust(seen=seen, name=name)
                self.assertTrue(result)
                self.assertIsNone(error)
                self.assertEqual(keys, [['down'], ['enter']])

    def test_startup_send_reads_before_retry(self):
        self.install()
        p = self.new()
        self.configure(send_errors=[{'kind': 'unavailable', 'message': 'still starting: output has not settled', 'hint': 'read first'}])
        self.cw('start', p, live=True)
        calls = self.calls()
        self.assertEqual([c[0] for c in calls], ['ls', 'get', 'run', 'wait', 'keys', 'wait', 'send', 'read', 'send'])
        self.assertEqual(calls[6], calls[8])

    def test_ambiguous_send_reads_and_stops_without_retry(self):
        self.install()
        p = self.new()
        self.configure(send_errors=[{'kind': 'unavailable', 'message': 'connection lost', 'hint': 'inspect'}])
        self.cw('start', p, live=True, code=1)
        self.assertEqual([c[0] for c in self.calls()], ['ls', 'get', 'run', 'wait', 'keys', 'wait', 'send', 'read'])
        self.assertNotIn('status: running', p.read_text())

    def test_startup_retry_has_sixty_second_deadline(self):
        module = self.module()
        elapsed = [0]
        calls = []
        def fake_hc(*args, **kwargs):
            calls.append(args[0])
            if args[0] == 'send':
                raise module.HCError('startup', {'kind': 'unavailable', 'message': 'still starting'})
            return 'screen'
        def sleep(seconds):
            elapsed[0] += seconds
        with mock.patch.object(module, 'hc', side_effect=fake_hc), mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), mock.patch.object(module.time, 'sleep', side_effect=sleep):
            with self.assertRaises(module.HCError):
                module.send_ready('t42', 'task')
        self.assertEqual(elapsed[0], 60)
        self.assertEqual(calls, ['send', 'read'] * (len(calls) // 2))

    def test_hc_timeout_uses_remaining_budget_or_fixed_default(self):
        module = self.module()
        result = subprocess.CompletedProcess(['hc'], 0, '{}', '')
        with mock.patch.object(module.time, 'monotonic', return_value=100), mock.patch.object(module.subprocess, 'run', return_value=result) as run:
            module.hc('get', 't42', '--json')
            self.assertEqual(run.call_args.kwargs['timeout'], 60)
            module.hc('get', 't42', '--json', deadline=100.25)
            self.assertEqual(run.call_args.kwargs['timeout'], .25)
            with self.assertRaisesRegex(module.HCTimeout, 'deadline expired.*inspection required'):
                module.hc('send', 't42', 'task', deadline=100)
            self.assertEqual(run.call_count, 2)

    def test_opt_in_trace_records_launch_and_approval_outside_project(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high')
        p = self.new(seat='coder-light')
        screen = (SCREENS / 'claude-trust.txt').read_text()
        receipt = {'sent': True, 'via': 'argv'}
        self.configure(run={'first_message': receipt},
                       waits=[{'status': 'blocked'}, {'status': 'idle'}], screens=self.claude_screens(screen),
                       get={'t42': {'foreground': {'cwd': str(self.root)},
                                    'status': {'app': 'claude', 'state': 'blocked'}}})
        # The repro root can be a scratch project while its trace lives in
        # the main checkout. Trace writes must append without inside(root).
        trace_path = self.work / 'launch trace.jsonl'
        trace_path.write_text('{"event":"previous-run"}\n')
        self.cw('start', p, live=True, env={'COWORK_TRACE': str(trace_path)})
        entries = [json.loads(line) for line in trace_path.read_text().splitlines()]
        self.assertEqual(entries.pop(0), {'event': 'previous-run'})
        calls = [entry for entry in entries if entry['event'] == 'hc.call']
        self.assertEqual([entry['args'] for entry in calls], self.calls())
        results = [entry for entry in entries if entry['event'] == 'hc.result']
        self.assertEqual([entry['args'] for entry in results], self.calls())
        run = next(entry for entry in results if entry['args'][0] == 'run')
        self.assertEqual(run['result']['first_message'], receipt)
        self.assertEqual(run['result']['state'], 'live')
        waits = [entry['result'] for entry in results if entry['args'][0] == 'wait']
        self.assertEqual([(entry['status'], entry['reason']) for entry in waits],
                         [('blocked', 'status'), ('idle', 'status')])
        get = next(entry for entry in results if entry['args'][:2] == ['get', 't42'])
        self.assertEqual(get['result']['foreground']['cwd'], str(self.root))
        screen_read = next(entry for entry in results if entry['args'][0] == 'read')
        self.assertEqual(screen_read['screen'], screen)
        self.assertEqual(screen_read['screen_sha1'], hashlib.sha1(screen.encode('utf-8')).hexdigest())
        keys = [entry['keys'] for entry in calls if entry['args'][0] == 'keys']
        self.assertEqual(keys, [['down'], ['enter']])
        decision = next(entry for entry in entries if entry['event'] == 'approve.decision')
        self.assertEqual({key: decision[key] for key in
                          ('decision', 'keys_none', 'screen_seen', 'repeats', 'required', 'cwd')},
                         {'decision': 'keys', 'keys_none': False, 'screen_seen': False,
                          'repeats': 1, 'required': False, 'cwd': str(self.root)})
        for entry in entries:
            self.assertIsNotNone(dt.datetime.fromisoformat(entry['time']).tzinfo)
            self.assertIsInstance(entry['pid'], int)

    def test_trace_distinguishes_unmatched_and_repeated_approval_decisions(self):
        module = self.module()
        trace_path = self.work / 'decisions.jsonl'
        screen = f'Trust this folder?\n{self.root}\n> 1. Trust and continue\n  2. Quit'
        with mock.patch.dict(os.environ, COWORK_TRACE=str(trace_path)), \
                mock.patch.object(module.subprocess, 'run',
                                  return_value=subprocess.CompletedProcess(['hc'], 0, '{}', '')) as run, \
                mock.patch.object(module.sys, 'stderr'):
            self.assertFalse(module.approve(self.root, 't42', 'codex', screen='Drawing...',
                                            required=False, repeats=2))
            with self.assertRaises(module.Blocked):
                module.approve(self.root, 't42', 'codex', screen='Drawing...', repeats=3)
            seen = set()
            self.assertTrue(module.approve(self.root, 't42', 'codex', seen, screen=screen,
                                           required=False, repeats=1))
            with self.assertRaises(module.Blocked):
                module.approve(self.root, 't42', 'codex', seen, screen=screen,
                               required=False, repeats=1)
        self.assertEqual(run.call_count, 1)
        entries = [json.loads(line) for line in trace_path.read_text().splitlines()]
        decisions = [entry for entry in entries if entry['event'] == 'approve.decision']
        self.assertEqual([(entry['decision'], entry['keys_none'], entry['screen_seen'],
                           entry['repeats'], entry['required']) for entry in decisions],
                         [('defer', True, False, 2, False), ('blocked', True, False, 3, True),
                          ('keys', False, False, 1, False), ('blocked', False, True, 1, False)])

    def test_trace_records_hc_errors_and_timeouts_without_retry(self):
        module = self.module()
        trace_path = self.work / 'errors.jsonl'
        error = {'kind': 'unavailable', 'message': 'still starting'}
        with mock.patch.dict(os.environ, COWORK_TRACE=str(trace_path)), \
                mock.patch.object(module.time, 'monotonic', return_value=100), \
                mock.patch.object(module.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess(['hc'], 1, '', json.dumps({'error': error}))
            with self.assertRaises(module.HCError):
                module.hc('get', 't42', '--json')
            run.return_value = subprocess.CompletedProcess(['hc'], 0, json.dumps({'error': error}), '')
            with self.assertRaises(module.HCError):
                module.hc('wait', 't42', '--json')
            run.side_effect = subprocess.TimeoutExpired(['hc', 'keys'], 1)
            with self.assertRaises(module.HCTimeout):
                module.hc('keys', 't42', 'down', 'enter', '--json', deadline=101)
            with self.assertRaisesRegex(module.HCTimeout, 'deadline expired'):
                module.hc('send', 't42', 'task', '--json', deadline=100)
            self.assertEqual(run.call_count, 3)
        entries = [json.loads(line) for line in trace_path.read_text().splitlines()]
        self.assertEqual([entry['event'] for entry in entries], ['hc.call', 'hc.error'] * 4)
        errors = [entry for entry in entries if entry['event'] == 'hc.error']
        self.assertEqual([entry['error_type'] for entry in errors],
                         ['HCError', 'HCError', 'HCTimeout', 'HCTimeout'])
        self.assertEqual([entry['error'] for entry in errors[:2]], [error, error])
        self.assertIn('delivery may have occurred', errors[2]['message'])
        self.assertIn('deadline expired', errors[3]['message'])

    def test_trace_disabled_leaves_hc_io_unchanged(self):
        module = self.module()
        with mock.patch.dict(os.environ, COWORK_TRACE=''), \
                mock.patch.object(module.Path, 'open') as opened, \
                mock.patch.object(module.subprocess, 'run',
                                  return_value=subprocess.CompletedProcess(['hc'], 0, '{}', '')) as run:
            self.assertEqual(module.hc('get', 't42', '--json'), {})
        opened.assert_not_called()
        run.assert_called_once()

    def test_trace_rejects_relative_path_before_hc_call(self):
        module = self.module()
        with mock.patch.dict(os.environ, COWORK_TRACE='relative.jsonl'), \
                mock.patch.object(module.subprocess, 'run') as run:
            with self.assertRaisesRegex(module.CWError, 'COWORK_TRACE must be an absolute file path'):
                module.hc('run', '--bg', '--json')
        run.assert_not_called()

    def test_sleeping_hc_is_bounded_throughout_start_handover_and_approve(self):
        self.install(live=True)
        p = self.new()
        runner = '''import pathlib, sys
namespace = {'__name__': 'cw_timeout_test', '__file__': sys.argv.pop(1)}
exec(compile(pathlib.Path(namespace['__file__']).read_text(), namespace['__file__'], 'exec'), namespace)
namespace['STARTUP_TIMEOUT'] = 2.6
sys.exit(namespace['main']())
'''
        cases = [(('start', str(p)), command) for command in ('ls', 'get', 'run', 'wait', 'read', 'keys', 'send')]
        cases += [(('handover', 'context'), command) for command in ('get', 'ls', 'run', 'wait')]
        cases += [(('approve', 't42'), command) for command in ('read', 'get', 'keys')]
        for args, command in cases:
            with self.subTest(args=args, command=command):
                self.clear_calls()
                self.configure(sleep_command=command,
                               waits=[{'status': 'blocked'}] if command in ('read', 'keys') else [{'status': 'idle'}],
                               screen=(SCREENS / 'claude-trust.txt').read_text(),
                               get={'t42': {'status': {'app': 'claude', 'state': 'blocked'},
                                            'foreground': {'cwd': str(self.root)}}})
                # Start uses Codex, whose captured trust screen has a path.
                if args[0] == 'start':
                    config = json.loads(self.config.read_text())
                    config['screen'] = f'Trust this folder?\n{self.root}\n> 1. Trust and continue\n  2. Quit'
                    self.configure(**config)
                elif args == ('handover', 'context') and command == 'wait':
                    config = json.loads(self.config.read_text())
                    config['run'] = {'first_message': {'sent': False, 'reason': 'blocked'}}
                    self.configure(**config)
                env = dict(self.env, HC_TERMINAL_ID='t1')
                proc = subprocess.Popen([sys.executable, '-c', runner, str(CW), *args],
                                        cwd=self.root, env=env, text=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, start_new_session=True)
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    self.fail(f'watchdog expired for {args} at hc {command}')
                finally:
                    # Also reap a sleeping fake hc if the regression removes
                    # the production timeout and the watchdog has to intervene.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.communicate()
                self.assertEqual(proc.returncode, 1, stdout + stderr)
                self.assertIn(f'hc {command} timed out; inspection required', stderr)
                calls = self.calls()
                self.assertEqual(calls[-1][0], command)
                self.assertEqual(sum(call[0] == command for call in calls), 1)
                self.assertLessEqual(sum(call[0] == 'run' for call in calls), 1)
                self.assertLessEqual(sum(call[0] == 'send' for call in calls), 1)

    def test_wait_retries_stop_at_total_deadline(self):
        module = self.module()
        for status, reason in ((None, 'timeout'), ('blocked', 'status'), ('working', 'timeout')):
            with self.subTest(status=status):
                elapsed, calls = [0], []
                def fake_hc(*args, **kwargs):
                    calls.append(args)
                    if args[0] == 'wait':
                        elapsed[0] += int(args[args.index('--timeout') + 1])
                        return {'status': status, 'reason': reason}
                    return f'Signing in... {elapsed[0]}'
                def sleep(seconds):
                    elapsed[0] += seconds
                with mock.patch.object(module, 'hc', side_effect=fake_hc), mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), mock.patch.object(module.time, 'sleep', side_effect=sleep):
                    with self.assertRaisesRegex(module.CWError, 't42 startup timed out after 120 seconds.*hc read t42'):
                        module.wait_ready('t42', self.root, 'agy')
                self.assertEqual(elapsed[0], 120)
                self.assertEqual(len([c for c in calls if c[0] == 'read']), len([c for c in calls if c[0] == 'wait']))

    def test_launch_waits_share_one_deadline(self):
        self.install()
        p = self.new()
        module = self.module()
        values = module.header(p.read_text())[0]
        commands = module.launch_plan(self.root, p, values, module.get_seat(self.root, values['seat']), 'name', 'task', {'labels': {'herdr.space': 'test'}})
        elapsed, calls, waits = [0], [], [0]
        def fake_hc(*args, **kwargs):
            calls.append(args)
            if args[0] == 'run':
                return {'address': 't42'}
            if args[0] == 'wait':
                waits[0] += 1
                elapsed[0] += int(args[args.index('--timeout') + 1])
                return {'status': 'idle' if waits[0] == 4 else None,
                        'reason': 'status' if waits[0] == 4 else 'timeout'}
            return 'Starting...' if args[0] == 'read' else {}
        def sleep(seconds):
            elapsed[0] += seconds
        with mock.patch.object(module, 'hc', side_effect=fake_hc), \
                mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), \
                mock.patch.object(module.time, 'sleep', side_effect=sleep):
            with self.assertRaisesRegex(module.CWError, 'timed out after 120 seconds'):
                module.execute_launch(commands, self.root, 'codex')
        self.assertEqual(elapsed[0], 120)
        self.assertEqual([c for c in calls if c[0] == 'send'], [])
        self.assertEqual([list(c) for c in calls if c[0] == 'keys'],
                         [['keys', 't42', *list('/rename'), 'space', *list('name'), 'enter', '--json']])

    def test_handover_final_wait_shares_launch_deadline(self):
        self.install(live=True)
        p = self.root / f'cowork/{DAY}/coordinator.md'
        module = self.module()
        elapsed, calls = [0], []
        def fake_hc(*args, **kwargs):
            calls.append(args)
            if args[0] == 'get':
                if args[1] == 't42':
                    successor = self.root / f'cowork/{DAY}/coordinator-2.md'
                    values = module.header(successor.read_text())[0]
                    self.assertEqual(values['terminal'], f'{DAY}-coordinator-2 (t42)')
                    self.assertEqual(values['status'], 'running')
                return {'name': 'caller', 'cwd': str(self.root), 'labels': {'herdr.space': 'test'},
                        'status': {'state': 'working'}}
            if args[0] == 'ls':
                return []
            if args[0] == 'run':
                elapsed[0] += 20
                return {'address': 't42', 'state': 'live'}
            return 'Starting...' if args[0] == 'read' else {}
        def sleep(seconds):
            elapsed[0] += seconds
        args = type('Args', (), {'accept': False, 'reason': 'context'})()
        with mock.patch.dict(os.environ, HC_TERMINAL_ID='t1', COWORK_TASK=str(p)), mock.patch.object(module, 'hc', side_effect=fake_hc), mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), mock.patch.object(module.time, 'sleep', side_effect=sleep):
            with self.assertRaisesRegex(module.CWError, 'has not accepted'):
                module.handover(self.root, args)
        self.assertEqual(elapsed[0], 120)
        self.assertEqual([c for c in calls if c[0] == 'wait'], [])
        self.assertEqual((self.root / 'cowork/coordinator.addr').read_text(), 't1 caller\n')

    def test_send_retry_respects_remaining_launch_deadline(self):
        module = self.module()
        elapsed = [110]
        def fake_hc(*args, **kwargs):
            if args[0] == 'send':
                raise module.HCError('startup', {'kind': 'unavailable', 'message': 'still starting'})
            return 'Starting...'
        def sleep(seconds):
            elapsed[0] += seconds
        with mock.patch.object(module, 'hc', side_effect=fake_hc), mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), mock.patch.object(module.time, 'sleep', side_effect=sleep):
            with self.assertRaisesRegex(module.CWError, 'timed out after 120 seconds'):
                module.send_ready('t42', 'task', deadline=120)
        self.assertEqual(elapsed[0], 120)

    def test_wait_message_and_timeout_keep_waiting(self):
        self.install()
        p = self.new()
        self.configure(waits=[{'reason': 'message', 'status': 'idle'},
                              {'reason': 'timeout', 'status': 'idle'},
                              {'reason': 'status', 'status': 'idle'}])
        self.cw('start', p, live=True)
        self.assertEqual(len([c for c in self.calls() if c[0] == 'wait']), 4)

    def test_fast_claude_delivered_launch_returns_on_live_ready_status(self):
        module = self.module()
        commands = [['hc', 'run', '--json'], ['hc', 'wait', 'name', '--timeout', '20', '--json']]
        # Run 1 returned a live terminal with no first_message receipt, then
        # working/message. A delivered Claude task already runs from argv.
        for receipt in (None, {'sent': True}):
            for status, reason in (('working', 'message'), ('working', 'timeout'),
                                   ('idle', 'timeout'), ('idle', 'status'), ('done', 'status')):
                with self.subTest(receipt=receipt, status=status, reason=reason):
                    responses = iter([{'address': 't41', 'state': 'live', 'first_message': receipt},
                                      {'status': status, 'reason': reason}])
                    with mock.patch.object(module, 'hc', side_effect=lambda *args, **kwargs: next(responses)) as calls:
                        self.assertEqual(module.execute_launch(commands, self.root, 'claude'), 't41')
                    self.assertEqual([call.args[0] for call in calls.call_args_list], ['run', 'wait'])

    def test_fast_claude_start_records_delivery_before_wait_and_preserves_progress(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high')
        p = self.new(seat='coder-light')
        module = self.module()
        def fake_hc(*args, **kwargs):
            if args[0] == 'ls':
                return []
            if args[0] == 'get':
                return {'labels': {'herdr.space': 'test'}}
            if args[0] == 'run':
                self.assertNotIn('status: running', p.read_text())
                return {'address': 't41', 'state': 'live'}
            self.assertEqual(args[0], 'wait')
            values = module.header(p.read_text())[0]
            self.assertEqual(values['terminal'], f'{DAY}-work (t41)')
            self.assertEqual(values['status'], 'running')
            p.write_text(module.edit_header(p.read_text(), {'status': 'wrap-up'}, p))
            return {'status': 'done', 'reason': 'status'}
        with mock.patch.dict(os.environ, HC_TERMINAL_ID='t1'), \
                mock.patch.object(module, 'hc', side_effect=fake_hc), mock.patch.object(module.sys, 'stdout'):
            module.start(self.root, type('Args', (), {'taskfile': str(p), 'print': False})())
        self.assertEqual(module.header(p.read_text())[0]['status'], 'wrap-up')

    def test_fast_claude_blocked_start_keeps_terminal_and_marks_blocked(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high')
        p = self.new(seat='coder-light')
        self.configure(waits=[{'status': 'blocked'}], screen='Unknown permission request',
                       get={'t42': {'status': {'state': 'blocked'}}})
        result = self.cw('start', p, live=True, code=2)
        values = self.module().header(p.read_text())[0]
        self.assertEqual(values['terminal'], f'{DAY}-work (t42)')
        self.assertEqual(values['status'], 'blocked')
        self.assertIn('no keys were pressed', result.stderr)
        self.assertFalse(any(call[0] == 'keys' for call in self.calls()))

    def test_fast_claude_finished_run_is_never_marked_running(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high')
        p = self.new(seat='coder-light')
        for receipt in (None, {'sent': True}):
            with self.subTest(receipt=receipt):
                self.clear_calls()
                before = p.read_bytes()
                self.configure(run={'state': 'finished', 'first_message': receipt})
                self.cw('start', p, live=True, code=1)
                self.assertEqual(p.read_bytes(), before)
                self.assertEqual(sum(call[0] == 'run' for call in self.calls()), 1)

    def test_fast_claude_handover_blocked_keeps_successor_terminal(self):
        self.install(live=True)
        self.configure(screen='Unknown permission request',
                       get={'t42': {'status': {'state': 'blocked'}}})
        self.cw('handover', 'context', live=True, code=2)
        successor = self.root / f'cowork/{DAY}/coordinator-2.md'
        values = self.module().header(successor.read_text())[0]
        self.assertEqual(values['terminal'], f'{DAY}-coordinator-2 (t42)')
        self.assertEqual(values['status'], 'blocked')
        self.assertEqual((self.root / 'cowork/coordinator.addr').read_text(), 't1 caller\n')

    def test_fast_claude_undelivered_task_waits_before_recovery_send(self):
        module = self.module()
        commands = [['hc', 'run', '--json', 'task'], ['hc', 'wait', 'name', '--timeout', '20', '--json']]
        waits = iter([{'status': 'working', 'reason': 'message'}, {'status': 'idle', 'reason': 'status'},
                      {'status': 'working', 'reason': 'message'}])
        def fake_hc(*args, **kwargs):
            if args[0] == 'run':
                return {'address': 't41', 'state': 'live', 'first_message': {'sent': False}}
            if args[0] == 'wait':
                return next(waits)
            return 'Starting...' if args[0] == 'read' else {'status': 'working'}
        with mock.patch.object(module, 'hc', side_effect=fake_hc) as calls:
            self.assertEqual(module.execute_launch(commands, self.root, 'claude', prompt='task'), 't41')
        self.assertEqual([call.args[0] for call in calls.call_args_list],
                         ['run', 'read', 'wait', 'wait', 'send', 'wait'])

    def test_hc_wait_transport_grace_stays_inside_launch_deadline(self):
        module = self.module()
        result = subprocess.CompletedProcess(['hc'], 0, '{"status":"idle","reason":"status"}', '')
        for remaining in (120, 20, 2):
            with self.subTest(remaining=remaining), \
                    mock.patch.object(module.time, 'monotonic', return_value=100), \
                    mock.patch.object(module.subprocess, 'run', return_value=result) as run:
                module.wait_ready('t42', self.root, 'codex', deadline=100 + remaining)
                args = run.call_args.args[0]
                wait_seconds = int(args[args.index('--timeout') + 1])
                budget = run.call_args.kwargs['timeout']
                self.assertGreaterEqual(budget - wait_seconds, 1)
                self.assertLessEqual(budget, remaining)

    def test_launch_uses_address_and_accepts_null_first_message(self):
        self.install()
        p = self.new()
        self.configure(run={'address': 't43', 'first_message': None})
        self.cw('start', p, live=True, script=self.root / 'cowork/cw')
        calls = self.calls()
        self.assertEqual([c[0] for c in calls], ['ls', 'get', 'run', 'wait', 'keys', 'wait', 'send'])
        self.assertTrue(all(c[1] == 't43' for c in calls if c[0] in ('wait', 'keys', 'send')))
        self.assertIn(f'terminal: {DAY}-work (t43)', p.read_text())
        self.assertIn('status: running', p.read_text())

    def test_launch_preserves_progress_written_during_startup(self):
        self.install()
        p = self.new()
        self.configure(edit_on_run=str(p))
        self.cw('start', p, live=True)
        self.assertIn('- agent wrote progress', p.read_text())
        self.assertIn('status: running', p.read_text())

    def test_launch_failure_never_retries_or_marks_running(self):
        self.install()
        p = self.new()
        for config in ({'fail': ['run']},
                       {'run': {'address': 't42', 'first_message': {'sent': False}}},
                       {'fail': ['send']},
                       {'waits': [{'status': 'error'}]}):
            with self.subTest(config=config):
                self.configure(**config)
                self.clear_calls()
                self.cw('start', p, live=True, code=1)
                self.assertEqual(len([c for c in self.calls() if c[0] == 'run']), 1)
                self.assertNotIn('status: running', p.read_text())

    def test_early_exit_relaunches_once_with_same_name_and_new_address(self):
        self.install()
        p = self.new()
        self.configure(runs=[{}, {'address': 't43'}],
                       waits=[{'reason': 'exit', 'exit_code': 1, 'status': None}, {'status': 'idle'}],
                       screen='account/read failed: workspace routing discovery timed out')
        result = self.cw('start', p, live=True, script=self.root / 'cowork/cw')
        calls = self.calls()
        self.assertEqual([c[0] for c in calls],
                         ['ls', 'get', 'run', 'wait', 'read', 'rm', 'run', 'wait', 'keys', 'wait', 'send'])
        self.assertEqual(calls[2], calls[6])
        self.assertEqual(calls[5], ['rm', 't42', '--json'])
        self.assertTrue(all(c[1] == 't43' for c in calls[7:]))
        self.assertIn('relaunching once', result.stderr)
        self.assertIn(f'terminal: {DAY}-work (t43)', p.read_text())
        self.assertIn('status: running', p.read_text())

    def test_exit_after_rename_still_relaunches_before_task_delivery(self):
        self.install()
        p = self.new()
        self.configure(waits=[{'status': 'idle'}, {'reason': 'exited', 'status': None}, {'status': 'idle'}])
        self.cw('start', p, live=True)
        calls = self.calls()
        self.assertEqual(sum(c[0] == 'run' for c in calls), 2)
        self.assertEqual(sum(c[0] == 'keys' for c in calls), 2)
        self.assertEqual(sum(c[0] == 'send' for c in calls), 1)

    def test_second_early_exit_stops_with_screen_tail_without_marking_running(self):
        self.install()
        p = self.new()
        before = p.read_bytes()
        self.configure(waits=[{'reason': 'exit', 'exit_code': 1, 'status': None}],
                       screens=['first failed', '\n'.join(f'failure line {i}' for i in range(20))])
        result = self.cw('start', p, live=True, code=1)
        calls = self.calls()
        self.assertEqual(sum(c[0] == 'run' for c in calls), 2)
        self.assertEqual(sum(c[0] == 'rm' for c in calls), 1)
        self.assertEqual([c for c in calls if c[0] in ('keys', 'send')], [])
        self.assertIn('failure line 8\n', result.stderr)
        self.assertIn('failure line 19\n', result.stderr)
        self.assertNotIn('failure line 7\n', result.stderr)
        self.assertEqual(before, p.read_bytes())

    def test_finished_run_result_is_retried_before_waiting(self):
        self.install()
        p = self.new()
        self.configure(runs=[{'state': 'finished'}, {'address': 't43'}])
        self.cw('start', p, live=True)
        self.assertEqual([c[0] for c in self.calls()],
                         ['ls', 'get', 'run', 'read', 'rm', 'run', 'wait', 'keys', 'wait', 'send'])

    def test_agy_opening_turn_does_not_count_as_task_delivery(self):
        self.install()
        p = self.new(seat='advisor', size='small')
        self.configure(waits=[{'status': 'idle'}, {'reason': 'exit', 'status': None}, {'status': 'idle'}])
        self.cw('start', p, live=True)
        sends = [c[2] for c in self.calls() if c[0] == 'send']
        self.assertEqual(sends[:2], ['Reply with the single word: ready.'] * 2)
        self.assertEqual(len(sends), 3)
        self.assertIn('You are seat advisor', sends[-1])

    def test_finished_rejection_before_task_send_can_relaunch(self):
        self.install()
        p = self.new()
        self.configure(errors={'keys': [{'kind': 'finished', 'message': 'terminal exited'}]})
        self.cw('start', p, live=True)
        calls = self.calls()
        self.assertEqual(sum(c[0] == 'run' for c in calls), 2)
        self.assertEqual(sum(c[0] == 'send' for c in calls), 1)

    def test_finished_task_send_rejection_stops_without_relaunch(self):
        self.install()
        p = self.new()
        self.configure(send_errors=[{'kind': 'finished', 'message': 'terminal exited'}])
        self.cw('start', p, live=True, code=1)
        calls = self.calls()
        self.assertEqual(sum(c[0] == 'run' for c in calls), 1)
        self.assertEqual(sum(c[0] == 'send' for c in calls), 1)
        self.assertEqual(calls[-1][0], 'read')
        self.assertNotIn('rm', [c[0] for c in calls])

    def test_claude_exit_never_relaunches_delivered_or_unknown_task(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high')
        p = self.new(seat='coder-light')
        for receipt in (None, {'sent': True}):
            with self.subTest(receipt=receipt):
                self.clear_calls()
                self.configure(run={'first_message': receipt}, waits=[{'reason': 'exit', 'status': None}])
                self.cw('start', p, live=True, code=1)
                self.assertEqual(sum(c[0] == 'run' for c in self.calls()), 1)
                self.assertEqual(self.calls()[-1][0], 'read')
                self.assertNotIn('rm', [c[0] for c in self.calls()])

    def test_claude_exit_after_recovery_delivery_never_relaunches(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high')
        p = self.new(seat='coder-light')
        self.configure(run={'first_message': {'sent': False}},
                       waits=[{'status': 'idle'}, {'reason': 'exit', 'status': None}])
        self.cw('start', p, live=True, code=1)
        self.assertEqual([c[0] for c in self.calls()], ['ls', 'get', 'run', 'read', 'wait', 'send', 'wait', 'read'])

    def test_claude_known_undelivered_exit_retries_with_correct_prompt_and_args(self):
        self.install()
        self.cw('seat', 'set', 'coder-light', 'claude', 'model', 'high', '--args=--tag "two words"')
        p = self.new(seat='coder-light')
        self.configure(run={'first_message': {'sent': False}}, runs=[{}, {'address': 't43'}],
                       waits=[{'reason': 'exit', 'status': None}, {'status': 'idle'}])
        self.cw('start', p, live=True)
        calls = self.calls()
        launches = [c for c in calls if c[0] == 'run']
        sends = [c for c in calls if c[0] == 'send']
        self.assertEqual(len(launches), 2)
        self.assertEqual(launches[0], launches[1])
        self.assertEqual(launches[1][-2:], ['--tag', 'two words'])
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0][1:3], ['t43', launches[1][-3]])
        self.assertIn('You are seat coder-light on task work', sends[0][2])

    def test_failed_early_exit_cleanup_stops_before_second_launch(self):
        self.install()
        p = self.new()
        self.configure(fail=['rm'], waits=[{'reason': 'exit', 'status': None}])
        self.cw('start', p, live=True, code=1)
        self.assertEqual([c[0] for c in self.calls()], ['ls', 'get', 'run', 'wait', 'read', 'rm'])
        self.assertNotIn('status: running', p.read_text())

    def test_early_exit_retry_keeps_original_launch_deadline(self):
        self.install()
        p = self.new()
        module = self.module()
        values = module.header(p.read_text())[0]
        commands = module.launch_plan(self.root, p, values, module.get_seat(self.root, values['seat']),
                                      'name', 'task', {'labels': {'herdr.space': 'test'}})
        elapsed, calls = [0], []
        def fake_hc(*args, **kwargs):
            calls.append((args, kwargs['deadline']))
            if args[0] == 'run':
                return {'address': 't42'}
            if args[0] == 'wait':
                elapsed[0] += 115 if elapsed[0] == 0 else int(args[args.index('--timeout') + 1])
                return {'reason': 'exit' if elapsed[0] == 115 else 'timeout', 'status': None}
            return 'startup failed' if args[0] == 'read' else {}
        def sleep(seconds):
            elapsed[0] += seconds
        with mock.patch.object(module, 'hc', side_effect=fake_hc), \
                mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), \
                mock.patch.object(module.time, 'sleep', side_effect=sleep), \
                mock.patch.object(module.sys, 'stderr'):
            with self.assertRaisesRegex(module.CWError, 'startup timed out after 120 seconds'):
                module.execute_launch(commands, self.root, 'codex', retry_early_exit=True)
        self.assertEqual(elapsed[0], 120)
        self.assertEqual({deadline for _, deadline in calls}, {120})
        self.assertEqual(sum(args[0] == 'run' for args, _ in calls), 2)
        self.assertEqual(sum(args[0] == 'rm' for args, _ in calls), 1)
        self.assertFalse(any(args[0] == 'send' for args, _ in calls))

    def test_missing_space_warns_and_launches_hidden(self):
        self.install()
        p = self.new()
        self.configure(get={'t1': {'address': 't1', 'name': 'caller', 'labels': {}}})
        self.assertIn('hidden', self.cw('start', p, live=True).stderr)
        launch = next(c for c in self.calls() if c[0] == 'run')
        self.assertNotIn('--label', launch)
        self.assertIn('--no-parent', launch)

    def test_report_delivery_and_all_fallbacks(self):
        self.install(live=True)
        p = self.new()
        environ = {'COWORK_TASK': str(p)}
        self.cw('report', 'done; docs/result.md', live=True, env=environ)
        self.assertIn(['send', 't1', '[work] done; docs/result.md', '--json'], self.calls())
        self.assertNotIn('undelivered', p.read_text())
        self.configure(fail=['send'])
        result = self.cw('report', 'send failed; docs/result.md', live=True, env=environ, code=1)
        self.assertIn('Relay to coordinator:', result.stdout)
        self.cw('report', 'offline; docs/result.md', env=environ, code=1)
        (self.root / 'cowork/coordinator.addr').write_text('- -\n')
        self.clear_calls()
        self.cw('report', 'no address; docs/result.md', live=True, env=environ, code=1)
        self.assertEqual(self.calls(), [])
        self.assertEqual(p.read_text().count('REPORT (undelivered):'), 3)

    def test_report_to_prefers_sender_day_then_newest_record(self):
        self.install(live=True)
        sender = self.new()
        peer = self.new('peer', size='small')
        self.cw('set', peer, 'terminal=peer (t7)')
        for day, tid in (('20000101', 't8'), ('29990101', 't9')):
            older = self.root / f'cowork/{day}/peer.md'
            older.parent.mkdir()
            older.write_text(peer.read_text().replace('(t7)', f'({tid})'))
        before = {p: p.read_bytes() for p in self.root.glob('cowork/*/peer.md')}
        env = {'COWORK_TASK': str(sender)}
        self.cw('report', '--to', 'peer', 'ready; result.md', live=True, env=env)
        self.assertEqual(self.calls(), [['get', 't7', '--json'],
                                       ['send', 't7', '[work] ready; result.md', '--json'],
                                       ['send', 't1', '[work] ready; result.md', '--json']])
        self.assertIn('REPORT to peer (t7) (delivered)', sender.read_text())
        self.assertIn('REPORT to coordinator (t1) (delivered)', sender.read_text())
        self.assertTrue(all(p.read_bytes() == text for p, text in before.items()))
        peer.unlink()
        self.clear_calls()
        self.cw('report', '--to', 'peer', 'ready; result.md', live=True, env=env)
        self.assertEqual([c[1] for c in self.calls()], ['t9', 't9', 't1'])

    def test_report_to_unavailable_target_only_sends_coordinator(self):
        self.install(live=True)
        sender = self.new()
        peer = self.new('peer', size='small')
        for target, terminal, config, expected in (
                ('missing', '-', {}, 'task record not found'),
                ('peer', '-', {}, 'no terminal assigned'),
                ('peer', '', {}, 'no terminal assigned'),
                ('peer', 'peer (t7)', {'get': {'t7': {'state': 'finished'}}}, 'not live'),
                ('peer', 'peer (t7)', {'fail': ['get']}, 'unavailable')):
            with self.subTest(expected=expected):
                self.cw('set', peer, 'terminal=' + terminal)
                self.configure(**config)
                self.clear_calls()
                result = self.cw('report', '--to', target, 'ready; result.md', live=True,
                                 env={'COWORK_TASK': str(sender)})
                sends = [c for c in self.calls() if c[0] == 'send']
                self.assertEqual(len(sends), 1)
                self.assertEqual(sends[0][1], 't1')
                self.assertIn(expected, sends[0][2])
                self.assertIn('coordinator only', result.stdout)
                self.assertIn(f'REPORT to {target} (skipped)', sender.read_text())

    def test_report_to_records_partial_failures_and_offline(self):
        self.install(live=True)
        sender = self.new()
        peer = self.new('peer', size='small')
        self.cw('set', peer, 'terminal=peer (t7)')
        error = {'kind': 'unavailable', 'message': 'transport failed'}
        for errors, target_result, coordinator_result in (([error, None], 'undelivered', 'delivered'),
                                                        ([None, error], 'delivered', 'undelivered')):
            with self.subTest(errors=errors):
                self.configure(send_errors=errors)
                self.log.with_suffix('.send').unlink(missing_ok=True)
                self.clear_calls()
                result = self.cw('report', '--to', 'peer', 'ready; result.md', live=True,
                                 env={'COWORK_TASK': str(sender)}, code=1)
                self.assertEqual([c[1] for c in self.calls() if c[0] == 'send'], ['t7', 't1'])
                self.assertIn(f'REPORT to peer (t7) ({target_result})', result.stdout)
                self.assertIn(f'REPORT to coordinator (t1) ({coordinator_result})', result.stdout)
                self.assertEqual('Relay to coordinator:' in result.stdout, coordinator_result == 'undelivered')
        self.clear_calls()
        result = self.cw('report', '--to', 'peer', 'offline; result.md',
                         env={'COWORK_TASK': str(sender)}, code=1)
        self.assertEqual(self.calls(), [])
        self.assertIn('REPORT to peer (skipped)', result.stdout)
        self.assertIn('REPORT to coordinator (t1) (undelivered)', result.stdout)
        self.configure()
        (self.root / 'cowork/coordinator.addr').write_text('- -\n')
        result = self.cw('report', '--to', 'peer', 'no address; result.md', live=True,
                         env={'COWORK_TASK': str(sender)}, code=1)
        self.assertEqual([c[1] for c in self.calls() if c[0] == 'send'], ['t7'])
        self.assertIn('REPORT to peer (t7) (delivered)', result.stdout)
        self.assertIn('REPORT to coordinator (-) (undelivered)', result.stdout)

    def test_report_to_coordinator_terminal_sends_once_and_validates_target(self):
        self.install(live=True)
        sender = self.new()
        env = {'COWORK_TASK': str(sender)}
        self.cw('report', '--to', 'coordinator', 'ready; result.md', live=True, env=env)
        self.assertEqual(len([c for c in self.calls() if c[0] == 'send']), 1)
        self.assertEqual(sender.read_text().count('(delivered)'), 2)
        self.clear_calls()
        before = self.snapshot()
        self.cw('report', '--to', '../escape', 'ready; result.md', live=True, env=env, code=1)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_handover_context_tokens_and_return(self):
        self.install(live=True)
        for reason, seat, agent in (('context', 'coordinator', 'claude'), ('tokens', 'coordinator', 'agy'), ('tokens', 'coordinator-alt', 'claude')):
            with self.subTest(reason=reason, seat=seat):
                p = self.root / f'cowork/{DAY}/coordinator.md'
                self.cw('set', p, 'seat=' + seat)
                (self.root / 'cowork/coordinator.addr').write_text('t1 caller\n')
                self.configure(accept=True)
                self.clear_calls()
                self.cw('handover', reason, live=True, env={'COWORK_TASK': str(p)})
                launch = next(c for c in self.calls() if c[0] == 'run')
                self.assertIn('--no-parent', launch)
                self.assertIn('herdr.space=space-a', launch)
                self.assertIn(agent, launch)
                prompt = launch[-1] if agent == 'claude' else [c[2] for c in self.calls() if c[0] == 'send'][-1]
                self.assertIn('handover --accept', prompt)
                self.assertNotIn('hc send', prompt)
                self.assertNotIn('cw report', prompt)
                if agent == 'claude':
                    self.assertFalse(any(c[0] == 'wait' for c in self.calls()))
                else:
                    self.assertIn(['wait', 't42', '--timeout', '20', '--json'], self.calls())
                self.assertTrue((self.root / 'cowork/coordinator.addr').read_text().startswith('t42 ' + DAY + '-coordinator-'))
                successor = self.root / f'cowork/{DAY}/{launch[launch.index("--name") + 1][9:]}.md'
                self.assertIn('(t42)', successor.read_text())
                self.assertIn('agent: -\n', successor.read_text())
                self.assertIn('status: running', successor.read_text())
                self.assertEqual(p.read_text().count('## Handover'), 1)

    def test_handover_accept_and_authority(self):
        self.install(live=True)
        p = self.root / f'cowork/{DAY}/coordinator.md'
        self.cw('handover', '--accept', live=True, env={'HC_TERMINAL_ID': 't2', 'COWORK_TASK': str(p)})
        self.assertEqual((self.root / 'cowork/coordinator.addr').read_text(), 't2 caller\n')
        self.assertIn(['send', 't1', f'[coordinator] Coordinator handover accepted; {p}', '--json'], self.calls())
        self.assertIn('HANDOVER acceptance to t1 (delivered)', p.read_text())
        self.cw('handover', 'context', live=True, env={'COWORK_TASK': str(p)}, code=1)
        worker = self.new()
        self.cw('handover', '--accept', live=True, env={'COWORK_TASK': str(worker)}, code=1)
        self.cw('handover', '--accept', env={'COWORK_TASK': str(p)}, code=1)

    def test_handover_accept_records_delivery_in_own_state_only(self):
        self.install(live=True)
        outgoing = self.root / f'cowork/{DAY}/coordinator.md'
        previous = outgoing.read_bytes()
        successor = self.new('successor', seat='coordinator-alt', size='small')
        self.cw('set', successor, 'size=seat')
        env = {'HC_TERMINAL_ID': 't2', 'COWORK_TASK': str(successor)}
        self.cw('handover', '--accept', live=True, env=env)
        self.assertEqual(self.calls(), [['get', 't2', '--json'],
                                       ['send', 't1', f'[successor] Coordinator handover accepted; {successor}', '--json']])
        self.assertIn('HANDOVER acceptance to t1 (delivered)', successor.read_text())
        self.assertEqual(outgoing.read_bytes(), previous)
        state = successor.read_bytes()
        self.clear_calls()
        self.cw('handover', '--accept', live=True, env=env)
        self.assertEqual(self.calls(), [['get', 't2', '--json']])
        self.assertEqual(successor.read_bytes(), state)

    def test_handover_accept_failed_notification_is_recorded_without_resend(self):
        self.install(live=True)
        successor = self.new('successor', seat='coordinator', size='small')
        self.cw('set', successor, 'size=seat')
        self.configure(fail=['send'])
        result = self.cw('handover', '--accept', live=True,
                         env={'HC_TERMINAL_ID': 't2', 'COWORK_TASK': str(successor)}, code=1)
        self.assertEqual((self.root / 'cowork/coordinator.addr').read_text(), 't2 caller\n')
        self.assertIn('HANDOVER acceptance to t1 (undelivered)', successor.read_text())
        self.assertIn('Relay to previous coordinator: [successor]', result.stdout)
        self.assertEqual(len([c for c in self.calls() if c[0] == 'send']), 1)

    def test_handover_must_confirm_address_change(self):
        self.install(live=True)
        module = self.module()
        elapsed = [0]
        address = self.root / 'cowork/coordinator.addr'
        def fake_hc(*args, **kwargs):
            if args[0] == 'run':
                address.write_text('t99 wrong successor\n')
                return {'address': 't42'}
            if args[0] == 'ls':
                return []
            return {'status': {'state': 'idle'}, 'labels': {'herdr.space': 'test'}}
        def sleep(seconds):
            elapsed[0] += seconds
        args = type('Args', (), {'accept': False, 'reason': 'context'})()
        with mock.patch.dict(os.environ, HC_TERMINAL_ID='t1', COWORK_TASK=f'cowork/{DAY}/coordinator.md'), mock.patch.object(module, 'hc', side_effect=fake_hc), mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), mock.patch.object(module.time, 'sleep', side_effect=sleep):
            with self.assertRaisesRegex(module.CWError, "has not accepted; coordinator.addr is still 't99 wrong successor'"):
                module.handover(self.root, args)
        self.assertEqual(elapsed[0], 120)

    def test_handover_accepts_address_while_successor_stays_working(self):
        self.install(live=True)
        module = self.module()
        p = self.root / f'cowork/{DAY}/coordinator.md'
        address = self.root / 'cowork/coordinator.addr'
        for reason in ('context', 'tokens'):
            with self.subTest(reason=reason):
                address.write_text('t1 caller\n')
                elapsed, calls = [0], []
                def fake_hc(*args, **kwargs):
                    calls.append(args)
                    if args[0] == 'run':
                        return {'address': 't42'}
                    if args[0] == 'ls':
                        return []
                    if args[0] == 'wait':
                        return {'status': 'idle'}
                    return {'status': {'state': 'working'}, 'labels': {'herdr.space': 'test'}}
                def sleep(seconds):
                    elapsed[0] += seconds
                    address.write_text('t42 successor\n' if elapsed[0] >= 2 else 't99 wrong successor\n')
                args = type('Args', (), {'accept': False, 'reason': reason})()
                with mock.patch.dict(os.environ, HC_TERMINAL_ID='t1', COWORK_TASK=str(p)), mock.patch.object(module, 'hc', side_effect=fake_hc), mock.patch.object(module.time, 'monotonic', side_effect=lambda: elapsed[0]), mock.patch.object(module.time, 'sleep', side_effect=sleep), mock.patch.object(module.sys, 'stdout'):
                    module.handover(self.root, args)
                self.assertEqual(elapsed[0], 2)
                self.assertEqual(sum(c[0] == 'wait' for c in calls), 0 if reason == 'context' else 3)

    def test_index_lessons_and_takeaways(self):
        self.install()
        p = self.new()
        p.write_text(p.read_text().replace('## Wrap-up\n', '## Wrap-up\nresult: passed\n- lesson: Keep evidence in files.\n- lesson: Verify CLI flags.\n'))
        self.cw('lessons', DAY)
        lesson = self.root / f'cowork/lessons/{DAY}.md'
        lesson.write_text(lesson.read_text().replace('## Takeaways\n', '## Takeaways\n\nUser takeaway, kept byte for byte.\n'))
        takeaway = lesson.read_text().split('## Takeaways', 1)[1]
        p.write_text(p.read_text().replace('Verify CLI flags.', 'Inspect installed CLI help.'))
        self.cw('lessons', DAY)
        self.assertEqual(takeaway, lesson.read_text().split('## Takeaways', 1)[1])
        self.assertIn('Inspect installed CLI help.', lesson.read_text())
        self.assertNotIn('Verify CLI flags.', lesson.read_text())
        self.cw('index')
        index = (self.root / 'cowork/README.md').read_text()
        self.assertIn(f'[{p.stem}]({DAY}/work.md)', index)
        self.assertEqual(index.count(f'{DAY}/work.md'), 1)
        self.assertIn('Coordinator: - -', index)
        self.assertIn('lessons/README.md', index)
        self.assertLessEqual(len(index.splitlines()), 60)
        self.cw('lint')

    def test_index_active_then_other_recent_tasks_once_each(self):
        self.install()
        active = self.new('active')
        closed = self.new('closed')
        self.cw('set', closed, 'status=closed')
        self.cw('index')
        text = (self.root / 'cowork/README.md').read_text()
        first, second = text.split('## Other tasks of the last 7 days')
        self.assertIn(f'{DAY}/{active.name}', first)
        self.assertNotIn(f'{DAY}/{active.name}', second)
        self.assertNotIn(f'{DAY}/{closed.name}', first)
        self.assertIn(f'{DAY}/{closed.name}', second)
        self.assertEqual(text.count(f'{DAY}/{closed.name}'), 1)

    def test_lint_excludes_frontmatter_and_literal_template_lines(self):
        self.install()
        p = self.new('first')
        q = self.new('second')
        template = 'Debrief contains result, where, 1–3 `- lesson:` lines, proposed next, and user decision.'
        # The generated task status line and literal marked-block instruction
        # are longer than forty characters; only actual repeated prose counts.
        literal = next(line for line in (REPO / 'templates/agents-block.md').read_text().splitlines() if len(line) > 40)
        for task in (p, q):
            task.write_text(task.read_text() + literal + '\n' + template + '\n')
        output = self.cw('lint').stdout
        self.assertNotIn('Duplicate: status:', output)
        self.assertNotIn('Duplicate: ' + literal, output)
        self.assertIn('Duplicate: ' + template, output)

    def fake_git(self, *, repository=True, fail_add=False):
        script = Path(self.env['PATH'].split(os.pathsep)[0]) / 'git'
        script.write_text(f'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['FAKE_LOG'], 'a') as f:
    f.write(json.dumps(['git', *args]) + '\\n')
if args == ['rev-parse', '--is-inside-work-tree']:
    print({'true' if repository else 'false'!r})
    sys.exit({0 if repository else 1})
if args[:2] == ['worktree', 'add']:
    if {fail_add!r}:
        print('branch already exists', file=sys.stderr)
        sys.exit(1)
    pathlib.Path(args[2]).mkdir(parents=True)
    sys.exit(0)
sys.exit(99)
''')
        script.chmod(0o755)

    def test_new_worktree_records_branch_and_launch_directory(self):
        self.install()
        self.fake_git()
        self.cw('new', 'isolated', '--seat', 'coder-heavy', '--size', 'small', '--worktree')
        p = self.root / f'cowork/{DAY}/isolated.md'
        worktree = self.root / '.worktrees/isolated'
        self.assertIn('worktree: .worktrees/isolated', p.read_text())
        self.assertEqual(self.calls(), [['git', 'rev-parse', '--is-inside-work-tree'], ['git', 'worktree', 'add', '.worktrees/isolated', '-b', 'isolated']])
        self.clear_calls()
        self.cw('start', p, live=True)
        launch = next(c for c in self.calls() if c[0] == 'run')
        self.assertEqual(launch[launch.index('--cwd') + 1], str(worktree))
        self.assertIn(f'COWORK_ROOT={self.root}', launch)
        self.assertIn(f'Working directory: {worktree}.', self.calls()[-1][2])
        # COWORK_ROOT directs records back to the coordinator's checkout even
        # when a tracked cowork directory also exists in the coder's worktree.
        (worktree / 'cowork').mkdir()
        (worktree / 'cowork/seats.tsv').write_text('invalid table')
        self.assertIn('coder-heavy', self.cw('seats', cwd=worktree, env={'COWORK_ROOT': str(self.root)}).stdout)

    def test_new_worktree_refuses_non_repo_or_git_failure_without_record(self):
        self.install()
        for repository, fail_add in ((False, False), (True, True)):
            self.fake_git(repository=repository, fail_add=fail_add)
            before = self.snapshot()
            self.cw('new', 'isolated', '--seat', 'coder-heavy', '--size', 'small', '--worktree', code=1)
            self.assertEqual(before, self.snapshot())

    def test_init_appends_worktree_ignore_without_rewriting_existing_bytes(self):
        ignore = self.root / '.gitignore'
        ignore.write_bytes(b'local-files\r\ncache')
        self.install()
        self.assertEqual(ignore.read_bytes(), b'local-files\r\ncache\n.worktrees/\n')
        before = self.snapshot()
        self.cw('init', '--apply')
        self.assertEqual(before, self.snapshot())

    def test_index_recent_window_and_overflow_preserve_existing_file(self):
        self.install()
        p = self.new()
        old_day = (dt.date.today() - dt.timedelta(days=7)).strftime('%Y%m%d')
        old_dir = self.root / 'cowork' / old_day
        old_dir.mkdir()
        old = old_dir / 'old.md'
        old.write_text(p.read_text().replace('task: work', 'task: old').replace('status: approved', 'status: closed'))
        self.cw('index')
        overview = self.root / 'cowork/README.md'
        self.assertNotIn('old.md', overview.read_text())
        for n in range(60):
            (p.parent / f'item-{n}.md').write_text(p.read_text().replace('task: work', f'task: item-{n}'))
        before = overview.read_bytes()
        self.cw('index', code=1)
        self.assertEqual(before, overview.read_bytes())

    def test_lint_caps_and_duplicate_diagnostics(self):
        self.install()
        p = self.new()
        text = p.read_text().replace('## Goal\n', '## Goal\n' + 'goal\n' * 4).replace('## State\n', '## State\n' + 'state\n' * 11)
        p.write_text(text + '\n## Handover\n' + 'handover\n' * 21)
        for file, n in (('cowork/README.md', 61), ('cowork/lessons/README.md', 41)):
            (self.root / file).write_text(('An exact duplicate line longer than forty characters.\n') * n)
        output = self.cw('lint', code=1).stdout
        for finding in ('Goal has 4', 'State has 11', 'Handover has 21', 'cap 60', 'cap 40', 'Duplicate:'):
            self.assertIn(finding, output)

    def test_check_status_and_closed_tasks(self):
        self.install(live=True)
        p = self.new()
        self.cw('set', p, f'terminal={DAY}-work (t42)', 'status=running')
        p.write_text(p.read_text().replace('## State\n', '## State\n- oldest\n- second\n- third\n- BLOCKED: input needed\n'))
        self.configure(get={'t42': {'address': 't42', 'state': 'finished', 'status': None}})
        output = self.cw('check', p, live=True).stdout
        self.assertNotIn('oldest', output)
        self.assertIn('second', output)
        output = self.cw('status', live=True).stdout
        for flag in ('finished/unknown', 'exited', 'BLOCKED: in State'):
            self.assertIn(flag, output)
        self.cw('set', p, 'status=closed')
        self.assertNotIn('work.md', self.cw('status', live=True).stdout)

    def test_status_flags_nested_blocked_and_error_states(self):
        self.install()
        p = self.new()
        self.cw('set', p, f'terminal={DAY}-work (t42)', 'status=running')
        for state in ('blocked', 'error', 'working'):
            with self.subTest(state=state):
                self.configure(get={'t42': {'status': {'app': 'codex', 'state': state}}})
                output = self.cw('status', live=True, script=self.root / 'cowork/cw').stdout
                self.assertIn(f't42 live/{state}', output)
                self.assertNotIn("{'app'", output)
                if state in ('blocked', 'error'):
                    self.assertIn(f' ! {state}', output)
                else:
                    self.assertNotIn(' ! ', output)

    def test_task_writes_preserve_outside_hard_link_and_mode(self):
        self.install()
        p = self.new()
        p.chmod(0o640)
        outside = self.work / 'outside-task.md'
        os.link(p, outside)
        before = outside.read_bytes()
        self.cw('set', p, 'status=closed', script=self.root / 'cowork/cw')
        self.assertIn('status: closed', p.read_text())
        self.assertEqual(outside.read_bytes(), before)
        self.assertEqual(p.stat().st_mode & 0o777, 0o640)
        self.assertEqual(outside.stat().st_mode & 0o777, 0o640)
        self.assertNotEqual(p.stat().st_ino, outside.stat().st_ino)

    def test_task_writes_preserve_in_root_symlink(self):
        self.install()
        p = self.new()
        p.chmod(0o640)
        alias = p.with_name('alias.md')
        alias.symlink_to(p.name)
        self.cw('set', alias, 'status=closed')
        self.assertTrue(alias.is_symlink())
        self.assertIn('status: closed', p.read_text())
        self.assertEqual(p.stat().st_mode & 0o777, 0o640)

    def test_root_discovery_and_escape_rejection(self):
        self.install()
        nested = self.root / 'nested/deep'
        nested.mkdir(parents=True)
        self.assertIn('coder-heavy', self.cw('seats', cwd=nested).stdout)
        self.assertIn('coder-heavy', self.cw('--root', self.root, 'seats', cwd=self.work).stdout)
        outside = self.work / 'outside.md'
        outside.write_text('untouched\n')
        self.cw('set', outside, 'status=closed', code=1)
        self.assertEqual(outside.read_text(), 'untouched\n')
        (self.root / 'cowork' / DAY / 'escape.md').symlink_to(outside)
        self.cw('set', f'cowork/{DAY}/escape.md', 'status=closed', code=1)

    def test_symlink_init_and_malformed_markers_do_not_mutate(self):
        outside = self.work / 'outside'
        outside.mkdir()
        (self.root / 'cowork').symlink_to(outside, target_is_directory=True)
        self.cw('init', '--apply', code=1)
        self.assertEqual(list(outside.iterdir()), [])
        (self.root / 'cowork').unlink()
        (self.root / 'AGENTS.md').write_text('<!-- agent-co-work:begin v1 -->\nBroken block\n')
        before = self.snapshot()
        self.cw('init', '--apply', code=1)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
