"""Install provenance from local release clones; no network or live Herdr."""
import os
import shutil
import subprocess
import unittest
from unittest import skipUnless
import test_cw


@skipUnless(shutil.which('git'), 'git is required for local clone fixtures')
class KitVersionTests(unittest.TestCase):
    for name in ('cw', 'snapshot', 'calls'):
        locals()[name] = getattr(test_cw.CWTests, name)

    def setUp(self):
        test_cw.CWTests.setUp(self)
        self.git_bin = shutil.which('git')
        self.env = {key: value for key, value in self.env.items() if not key.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME='Kit Test', GIT_COMMITTER_NAME='Kit Test',
                        GIT_AUTHOR_EMAIL='kit-test' + '@' + 'example.invalid',
                        GIT_COMMITTER_EMAIL='kit-test' + '@' + 'example.invalid',
                        GIT_TERMINAL_PROMPT='0')
        self.source = self.work / 'release-source'
        self.copy_assets(self.source)
        (self.source / 'tests').mkdir()
        (self.source / 'tests/fixture.txt').write_text('Release test fixture.\n')
        self.git('init', '--quiet', cwd=self.source)
        self.git('add', '.', cwd=self.source)
        self.git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Kit fixture', cwd=self.source)
        self.kit = self.work / 'kit clone'
        self.git('clone', '--quiet', '--no-hardlinks', str(self.source), str(self.kit), cwd=self.work)
        self.sha = self.git('rev-parse', 'HEAD')
        self.stamp = f'{self.sha} {self.source}\n'

    def copy_assets(self, destination):
        destination.mkdir()
        for name in ('bin', 'skills', 'templates'):
            shutil.copytree(test_cw.REPO / name, destination / name)
        for name in ('README.md', 'README.zh.md', '.gitignore'):
            shutil.copyfile(test_cw.REPO / name, destination / name)

    def git(self, *args, cwd=None):
        result = subprocess.run([self.git_bin, '-C', str(cwd or self.kit), *args],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def kit_cw(self, *args, **kwargs):
        return self.cw(*args, script=self.kit / 'bin/cw', **kwargs)

    def test_clone_install_plan_stamp_lint_and_idempotency(self):
        before = self.snapshot()
        plan = self.kit_cw('init')
        self.assertIn(f'kit: to {self.sha}\n', plan.stdout)
        self.assertIn('cowork/kit-version: create', plan.stdout)
        self.assertEqual(plan.stderr, '')
        self.assertEqual(before, self.snapshot())
        self.kit_cw('init', '--apply')
        self.assertEqual((self.root / 'cowork/kit-version').read_text(), self.stamp)
        lint = self.cw('lint', script=self.root / 'cowork/cw')
        self.assertIn('kit: ' + self.stamp, lint.stdout)
        self.assertIn('Caps OK.', lint.stdout)
        before = self.snapshot()
        for flags in ((), ('--upgrade',)):
            result = self.kit_cw('init', *flags, '--apply')
            self.assertIn('nothing to do', result.stdout)
            self.assertFalse(any(line.startswith('kit:') for line in result.stdout.splitlines()))
            self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_new_head_changes_version_only_on_upgrade(self):
        self.kit_cw('init', '--apply')
        self.git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '--allow-empty', '-m', 'Next release')
        next_sha = self.git('rev-parse', 'HEAD')
        before = self.snapshot()
        plain = self.kit_cw('init', '--apply')
        self.assertIn('nothing to do', plain.stdout)
        self.assertNotIn('kit:', plain.stdout)
        self.assertEqual(before, self.snapshot())
        plan = self.kit_cw('init', '--upgrade')
        self.assertIn(f'kit: from {self.sha} to {next_sha}\n', plan.stdout)
        self.assertIn('cowork/kit-version: replace', plan.stdout)
        self.assertEqual(before, self.snapshot())
        self.kit_cw('init', '--upgrade', '--apply')
        self.assertEqual((self.root / 'cowork/kit-version').read_text(), f'{next_sha} {self.source}\n')

    def test_fresh_install_replaces_an_orphan_version_stamp(self):
        (self.root / 'cowork').mkdir()
        version = self.root / 'cowork/kit-version'
        version.write_text('old-kit -\n')
        plan = self.kit_cw('init')
        self.assertIn(f'kit: to {self.sha}\n', plan.stdout)
        self.assertIn('cowork/kit-version: replace', plan.stdout)
        self.kit_cw('init', '--apply')
        self.assertEqual(version.read_text(), self.stamp)

    def test_older_project_is_not_stamped_by_plain_init(self):
        self.kit_cw('init', '--apply')
        version = self.root / 'cowork/kit-version'
        version.unlink()
        (self.root / 'cowork/cw').write_text('Old installed CLI.\n')
        (self.root / '.agents/skills/cowork/SKILL.md').write_text('Old installed skill.\n')
        before = self.snapshot()
        for flags in ((), ('--apply',)):
            plain = self.kit_cw('init', *flags)
            self.assertNotIn('kit:', plain.stdout)
            self.assertNotIn('cowork/kit-version:', plain.stdout)
            self.assertEqual(before, self.snapshot())
        plan = self.kit_cw('init', '--upgrade')
        self.assertIn(f'kit: from unknown to {self.sha}\n', plan.stdout)
        self.assertEqual(before, self.snapshot())
        self.kit_cw('init', '--upgrade', '--apply')
        self.assertEqual(version.read_text(), self.stamp)
        self.assertIn('Portable, standard-library-only', (self.root / 'cowork/cw').read_text())
        self.assertEqual((self.root / '.agents/skills/cowork/SKILL.md').read_bytes(),
                         (self.kit / 'skills/cowork/SKILL.md').read_bytes())

    def test_dirty_kit_paths_warn_without_changing_head_stamp(self):
        for name in ('README.md', 'README.zh.md', '.gitignore', 'bin/cw',
                     'skills/cowork-init/SKILL.md', 'templates/task.md', 'tests/fixture.txt'):
            with self.subTest(path=name):
                path = self.kit / name
                original = path.read_bytes()
                path.write_bytes(original + b'\n# Local edit.\n')
                try:
                    result = self.kit_cw('init')
                    self.assertIn('uncommitted changes in kit paths', result.stderr)
                    self.assertIn(f'kit: to {self.sha}\n', result.stdout)
                finally:
                    path.write_bytes(original)
        readme = self.kit / 'README.md'
        original = readme.read_bytes()
        readme.write_text('Staged kit change.\n')
        self.git('add', 'README.md')
        self.assertIn('uncommitted changes in kit paths', self.kit_cw('init').stderr)
        readme.write_bytes(original)
        self.git('add', 'README.md')
        (self.kit / 'tests/untracked.txt').write_text('Untracked kit change.\n')
        self.assertIn('uncommitted changes in kit paths', self.kit_cw('init').stderr)
        self.kit_cw('init', '--apply')
        self.assertEqual((self.root / 'cowork/kit-version').read_text(), self.stamp)

    def test_non_kit_edits_and_development_checkout_warnings(self):
        (self.kit / 'docs').mkdir()
        (self.kit / 'docs/note.md').write_text('A local development note.\n')
        self.assertEqual(self.kit_cw('init').stderr, '')
        (self.kit / 'cowork').mkdir()
        (self.kit / 'cowork/record.md').write_text('Local collaboration record.\n')
        warning = self.kit_cw('init').stderr
        self.assertIn('development checkout is not for deployment', warning)
        self.assertNotIn('uncommitted changes', warning)
        (self.kit / 'tools').mkdir()
        (self.kit / 'tools/publish-kit').write_text('Development-only tool.\n')
        (self.kit / 'cowork/record.md').unlink()
        (self.kit / 'cowork').rmdir()
        warning = self.kit_cw('init').stderr
        self.assertIn('development checkout is not for deployment', warning)
        self.assertNotIn('uncommitted changes', warning)

    def test_missing_origin_and_http_credentials(self):
        self.git('remote', 'remove', 'origin')
        self.kit_cw('init', '--apply')
        self.assertEqual((self.root / 'cowork/kit-version').read_text(), f'{self.sha} -\n')
        self.git('remote', 'add', 'origin', 'https://example.invalid/org/kit.git')
        for scheme in ('http', 'https'):
            with self.subTest(scheme=scheme):
                credential_url = scheme + '://user:secret' + '@' + 'example.invalid/org/kit.git'
                self.git('remote', 'set-url', 'origin', credential_url)
                result = self.kit_cw('init', '--upgrade', '--apply')
                version = (self.root / 'cowork/kit-version').read_text()
                self.assertEqual(version, f'{self.sha} {scheme}://example.invalid/org/kit.git\n')
                self.assertNotIn('secret', result.stdout + result.stderr + version)

    def test_vendored_script_does_not_borrow_target_repo_version(self):
        self.kit_cw('init', '--apply')
        self.git('init', '--quiet', cwd=self.root)
        (self.root / 'project.txt').write_text('Target project.\n')
        self.git('add', 'project.txt', cwd=self.root)
        self.git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Target fixture', cwd=self.root)
        nested = self.root / 'nested project'
        nested.mkdir()
        self.cw('init', '--apply', script=self.root / 'cowork/cw', cwd=nested)
        self.assertEqual((nested / 'cowork/kit-version').read_text(), 'unknown -\n')

    def test_non_git_copy_inside_another_repo_and_missing_git(self):
        enclosing = self.work / 'enclosing project'
        enclosing.mkdir()
        self.git('init', '--quiet', cwd=enclosing)
        loose = enclosing / 'loose kit'
        self.copy_assets(loose)
        self.cw('init', '--apply', script=loose / 'bin/cw')
        self.assertEqual((self.root / 'cowork/kit-version').read_text(), 'unknown -\n')
        no_git = self.work / 'no-git-bin'
        no_git.mkdir()
        fresh = self.work / 'no-git-project'
        fresh.mkdir()
        self.kit_cw('init', '--apply', cwd=fresh, env={'PATH': str(no_git)})
        self.assertEqual((fresh / 'cowork/kit-version').read_text(), 'unknown -\n')

    def test_lint_without_version_file_and_version_path_escape(self):
        self.kit_cw('init', '--apply')
        version = self.root / 'cowork/kit-version'
        version.unlink()
        self.assertIn('kit: unknown\n', self.cw('lint', script=self.root / 'cowork/cw').stdout)
        outside = self.work / 'outside-version'
        outside.write_text('Keep outside content.\n')
        version.symlink_to(outside)
        before = self.snapshot()
        for args in (('init', '--upgrade', '--apply'), ('lint',)):
            result = self.kit_cw(*args, code=1)
            self.assertIn('Path escapes project root', result.stderr)
            self.assertEqual(before, self.snapshot())
            self.assertEqual(outside.read_text(), 'Keep outside content.\n')

    def test_upgrade_vendored_plan_apply_uses_new_lint_and_preserves_records(self):
        self.kit_cw('init', '--apply')
        installed = self.root / 'cowork/cw'
        # Only the new lint knows this marker; exercising the installed subprocess
        # distinguishes it from an in-process call to the old implementation.
        source = self.source / 'bin/cw'
        source.write_text(source.read_text().replace("print('kit: ' +", "print('new lint'); print('kit: ' +"))
        self.git('add', 'bin/cw', cwd=self.source)
        self.git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'New lint', cwd=self.source)
        planned = self.git('rev-parse', 'HEAD', cwd=self.source)
        before = self.snapshot()
        plan = self.cw('upgrade', '--kit', self.kit, script=installed)
        self.assertIn('Upgrade kit: ' + planned, plan.stdout)
        self.assertIn('Confirm the upgrade plan', plan.stdout)
        self.assertNotIn('Confirm the seats,', plan.stdout)
        self.assertEqual(before, self.snapshot())
        # An upstream advance after review must not be pulled by --apply.
        self.git('-c', 'commit.gpgsign=false', 'commit', '--quiet', '--allow-empty', '-m', 'Later', cwd=self.source)
        applied = self.cw('upgrade', '--kit', self.kit, '--apply', script=installed)
        self.assertIn('new lint', applied.stdout)
        self.assertIn('kit: ' + planned, applied.stdout)
        self.assertEqual(planned, self.git('rev-parse', 'HEAD'))
        after = self.snapshot()
        for path in before.keys() - {'cowork/cw', 'cowork/kit-version'}:
            self.assertEqual(before[path], after[path], path)
        self.assertEqual(self.calls(), [])

    def test_upgrade_refuses_invalid_clones_before_pull_or_apply(self):
        self.kit_cw('init', '--apply')
        before = self.snapshot()
        invalid = self.work / 'invalid'
        self.copy_assets(invalid)
        nested = self.kit / 'nested'
        self.copy_assets(nested)
        for kit, expected in ((self.work / 'missing', 'existing release'),
                              (invalid, 'repository root'), (nested, 'repository root')):
            for flags in ((), ('--apply',)):
                result = self.cw('upgrade', '--kit', kit, *flags, code=1)
                self.assertIn(expected, result.stderr)
                self.assertEqual(before, self.snapshot())
        shutil.rmtree(nested)
        entry = self.kit / 'bin/cw'
        original = entry.read_bytes()
        entry.unlink()
        for flags in ((), ('--apply',)):
            self.assertIn('existing release', self.cw('upgrade', '--kit', self.kit, *flags, code=1).stderr)
        entry.write_bytes(original)
        entry.chmod(0o755)
        for name in ('cowork', 'tools/publish-kit'):
            path = self.kit / name
            path.mkdir(parents=True)
            for flags in ((), ('--apply',)):
                self.assertIn('development checkout', self.cw('upgrade', '--kit', self.kit, *flags, code=1).stderr)
            path.rmdir()
        # Dirty files outside KIT_PATHS must also refuse, before a failed pull.
        self.git('remote', 'remove', 'origin')
        for name in ('LICENSE', 'README.md'):
            path = self.kit / name
            original = path.read_bytes() if path.exists() else None
            path.write_text('Local changes.\n')
            for flags in ((), ('--apply',)):
                result = self.cw('upgrade', '--kit', self.kit, *flags, code=1)
                self.assertIn('clean release clone', result.stderr)
                self.assertEqual(before, self.snapshot())
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)
        result = self.cw('upgrade', '--kit', self.kit, code=1)
        self.assertIn('pull --ff-only failed', result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_upgrade_requires_both_install_files_and_skips_lint_after_init_failure(self):
        for flags in ((), ('--apply',)):
            result = self.cw('--root', self.root, 'upgrade', '--kit', self.kit, *flags, code=1)
            self.assertIn('existing install', result.stderr)
        self.kit_cw('init', '--apply')
        for name in ('cowork/cw', 'cowork/seats.tsv'):
            path = self.root / name
            original = path.read_bytes()
            path.unlink()
            for flags in ((), ('--apply',)):
                result = self.cw('--root', self.root, 'upgrade', '--kit', self.kit, *flags, code=1)
                self.assertIn('existing install', result.stderr)
            path.write_bytes(original)
        agents = self.root / 'AGENTS.md'
        agents.write_text('<!-- agent-co-work:begin v1 -->\nMalformed block\n')
        before = self.snapshot()
        result = self.cw('upgrade', '--kit', self.kit, '--apply', code=1)
        self.assertIn('Malformed', result.stderr)
        self.assertNotIn('Caps OK.', result.stdout)
        self.assertNotIn('Validation OK;', result.stdout)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
