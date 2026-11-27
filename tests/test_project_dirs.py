"""Project directory defaults, legacy layouts and portable launch prompts."""
import shlex
import shutil
import unittest
from unittest import mock
import test_cw


class ProjectDirectoryTests(unittest.TestCase):
    for name in ('setUp', 'cw', 'configure', 'calls', 'clear_calls', 'install', 'new', 'snapshot', 'module'):
        locals()[name] = getattr(test_cw.CWTests, name)

    def prompt(self, task, **kwargs):
        lines = self.cw('start', task, '--print', **kwargs).stdout.splitlines()
        # Prompts contain newlines inside shell quotes; parse the complete output.
        words = shlex.split('\n'.join(lines))
        return next(word for word in words if word.startswith('You are seat '))

    def assert_output(self, task, relative, **kwargs):
        self.assertIn("Default outputs (the Brief and the project's AGENTS.md layout take precedence): "
                      + str(self.root / relative) + '/', self.prompt(task, **kwargs))

    def test_project_parent_and_misc_launch_defaults(self):
        self.install()
        self.cw('project', 'new', 'campaign')
        parent = self.new('parent')
        self.cw('set', parent, 'project=campaign')
        child = self.new('child', size='small')
        self.cw('set', child, 'parent=parent')
        standalone = self.new('standalone', size='small')
        for task, project in ((parent, 'campaign'), (child, 'campaign'), (standalone, '_misc')):
            with self.subTest(task=task.stem):
                self.assert_output(task, f'output/{project}/{test_cw.DAY}/{task.stem}')
        self.cw('project', 'new', 'second')
        self.cw('set', child, 'project=second')
        self.assert_output(child, f'output/second/{test_cw.DAY}/child')
        self.assertFalse((self.root / 'output').exists())
        self.assertEqual(self.calls(), [])

    def test_declared_layout_and_discussion_prompt(self):
        self.install()
        agents = self.root / 'AGENTS.md'
        agents.write_text(agents.read_text() + '\ncowork-outputs: output/{yyyymmdd}/{task}/\n')
        task = self.new('discussion', seat='discussion', size='small')
        self.assert_output(task, f'output/{test_cw.DAY}/discussion')
        agents.write_text(agents.read_text().replace('output/{yyyymmdd}/{task}/', 'results/{project}/{task}/{yyyymmdd}/'))
        self.assert_output(task, f'results/_misc/discussion/{test_cw.DAY}')
        self.assertFalse((self.root / 'results').exists())

    def test_layout_ignores_marked_block_and_rejects_invalid_templates(self):
        self.install()
        task = self.new('layout', size='small')
        agents = self.root / 'AGENTS.md'
        original = agents.read_text()
        agents.write_text(original.replace('<!-- agent-co-work:end -->',
                                          'cowork-outputs: ignored/{task}/\n<!-- agent-co-work:end -->'))
        self.assert_output(task, f'output/_misc/{test_cw.DAY}/layout')
        for template in ('../outside/{task}/', 'output/{unknown}/', ''):
            with self.subTest(template=template):
                agents.write_text(original + '\ncowork-outputs: ' + template + '\n')
                self.cw('start', task, '--print', code=1)
        self.assertEqual(self.calls(), [])

    def test_worktree_prompt_uses_main_checkout_and_layout(self):
        self.install()
        task = self.new('isolated', size='small')
        worktree = self.root / '.worktrees/isolated'
        worktree.mkdir(parents=True)
        self.cw('set', task, 'worktree=.worktrees/isolated')
        (self.root / 'AGENTS.md').write_text('cowork-outputs: evidence/{yyyymmdd}/{task}/\n')
        (worktree / 'AGENTS.md').write_text('cowork-outputs: wrong/{task}/\n')
        env = {'COWORK_ROOT': str(self.root)}
        self.assert_output(task, f'evidence/{test_cw.DAY}/isolated', cwd=worktree, env=env)
        self.assertIn(f'Working directory: {worktree}.', self.prompt(task, cwd=worktree, env=env))

    def test_project_new_creates_only_project_index_from_bundle(self):
        self.install()
        root_index = self.root / 'docs/plans/README.md'
        before = root_index.read_bytes()
        self.cw('project', 'new', 'campaign', script=self.root / 'cowork/cw')
        folder = self.root / 'docs/plans/campaign'
        self.assertEqual([p.name for p in folder.iterdir()], ['README.md'])
        self.assertEqual((folder / 'README.md').read_bytes(),
                         (test_cw.REPO / 'templates/plans-readme.md').read_bytes())
        self.assertEqual(root_index.read_bytes(), before)
        self.assertIn('[../brief-template.md](../brief-template.md)', (folder / 'README.md').read_text())

    def test_project_new_preserves_existing_folder_bytes(self):
        self.install()
        for name, populated in (('empty', False), ('retained', True)):
            folder = self.root / 'docs/plans' / name
            folder.mkdir()
            if populated:
                (folder / 'README.md').write_bytes(b'Retained\r\n\xff\n')
                (folder / 'old-plan.md').write_bytes(b'Old path remains valid\r\n')
            before = self.snapshot()
            output = self.cw('project', 'new', name).stdout
            self.assertEqual(sum(line.startswith('Note:') for line in output.splitlines()), 1)
            after = self.snapshot()
            self.assertEqual(before, {p: v for p, v in after.items() if p in before})
            self.assertEqual(set(after) - set(before), {f'cowork/projects/{name}.md'})

    def test_project_new_missing_case_variant_or_declared_layout_is_noop(self):
        for number, case in enumerate(('missing', 'Docs/plans', 'docs/Plans', 'declared')):
            with self.subTest(case=case), mock.patch.object(self, 'root', self.work / f'layout-{number}'):
                self.root.mkdir()
                self.install()
                shutil.rmtree(self.root / 'docs')
                if case not in ('missing', 'declared'):
                    (self.root / case).mkdir(parents=True)
                if case == 'declared':
                    (self.root / 'docs/plans').mkdir(parents=True)
                    agents = self.root / 'AGENTS.md'
                    agents.write_text(agents.read_text() + '\ncowork-outputs: output/{yyyymmdd}/{task}/\n')
                before = self.snapshot()
                output = self.cw('project', 'new', 'campaign').stdout
                after = self.snapshot()
                self.assertEqual(sum(line.startswith('Note:') for line in output.splitlines()), 1)
                self.assertEqual(before, {p: v for p, v in after.items() if p in before})
                self.assertEqual(set(after) - set(before), {'cowork/projects/campaign.md'})
                self.assertFalse((self.root / 'docs/plans/campaign').exists())
