"""Offline integration tests: python3 -m unittest discover -s tests -v."""
import pathlib
import base64
import json
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/publish_pages.sh'


def run(*args, cwd=ROOT, ok=True):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if ok and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result


class PublishPagesTest(unittest.TestCase):
    def test_offline_tree_check_and_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            tree = base / 'tree'
            before = run('git', 'rev-parse', 'HEAD', 'origin/gh-pages').stdout
            run(str(SCRIPT), '--dry-run', str(tree))
            self.assertEqual({p.name for p in tree.iterdir()},
                             {'.nojekyll', 'index.html', 'report'})
            expected = set(run('git', 'ls-tree', '-r', '--name-only',
                               'HEAD', 'report').stdout.splitlines())
            actual = {str(p.relative_to(tree)) for p in
                      (tree / 'report').rglob('*') if p.is_file()}
            self.assertEqual(actual, expected)
            self.assertEqual((tree / 'index.html').read_bytes(),
                             (ROOT / 'scripts/pages-index.html').read_bytes())
            self.assertIn('report/demo.html', (tree / 'index.html').read_text())
            for name in ('index.html', 'glc.html', 'demo.html'):
                self.assertTrue((tree / 'report' / name).stat().st_size)
            figures = json.loads((ROOT / 'measure/out/glc_demo.json').read_text())
            self.assertEqual([d['grid'] for d in figures], [0, 2, 4, 8, 16, 32])
            glc = (tree / 'report/glc.html').read_text()
            for figure in figures:
                png = (tree / 'report/assets' / figure['file']).read_bytes()
                self.assertEqual(len(png), figure['bytes'])
                self.assertIn('data:image/png;base64,' +
                              base64.b64encode(png).decode(), glc)
            for font in (ROOT / 'report/assets').glob('*.woff2'):
                self.assertEqual(font.read_bytes(),
                                 (tree / 'report/assets' / font.name).read_bytes())
            run('git', 'init', '-q', '-b', 'gh-pages', str(tree))
            run('git', 'add', '.', cwd=tree)
            run('git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                'commit', '-qm', 'Expected generated site', cwd=tree)
            clone = base / 'pages'
            run('git', 'clone', '-q', '--branch', 'gh-pages', str(tree), str(clone))
            args = (str(SCRIPT), '--check', '--pages-repo', str(clone),
                    '--pages-ref', 'HEAD')
            original = run('git', 'rev-parse', 'HEAD', cwd=clone).stdout
            self.assertIn('Pages match', run(*args).stdout)
            (clone / 'unexpected.txt').write_text('stale asset')
            run('git', 'add', '.', cwd=clone)
            run('git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                'commit', '-qm', 'Drift', cwd=clone)
            drift = run('git', 'rev-parse', 'HEAD', cwd=clone).stdout
            result = run(*args, ok=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn('unexpected.txt', result.stdout)
            self.assertEqual(run('git', 'rev-parse', 'HEAD', cwd=clone).stdout, drift)
            self.assertNotEqual(original, drift)
            self.assertEqual(run('git', 'rev-parse', 'HEAD', 'origin/gh-pages').stdout,
                             before)
            self.assertFalse(run('git', 'status', '--porcelain', cwd=clone).stdout)
