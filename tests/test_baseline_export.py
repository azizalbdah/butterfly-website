import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('baseline_export', Path(__file__).resolve().parents[1] / 'scripts/export-baseline.py')
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class BaselineExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'checkout'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'baseline-test@example.invalid')
        self.git('config', 'user.name', 'Baseline Test')
        (self.repo / 'index.html').write_text('<h1>Saved baseline</h1>')
        self.git('add', 'index.html')
        self.git('commit', '-qm', 'baseline')
        self.commit = self.git('rev-parse', 'HEAD').strip()
        self.git('tag', 'baseline-test')
        self.git('branch', 'backup-test')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL).decode()

    def export(self, dest):
        return exporter.export_baseline(self.repo, dest, self.commit, 'baseline-test', 'backup-test')

    def test_exports_saved_commit_even_when_working_copy_has_changed(self):
        (self.repo / 'index.html').write_text('uncommitted work')
        (self.repo / 'private.env').write_text('not part of Git')
        result = self.export(self.root / 'preview')
        self.assertEqual(result['verified_files'], 1)
        self.assertEqual((self.root / 'preview/index.html').read_text(), '<h1>Saved baseline</h1>')
        self.assertFalse((self.root / 'preview/private.env').exists())
        self.assertEqual((self.repo / 'index.html').read_text(), 'uncommitted work')
        self.assertFalse(result['production_deployment_verified'])

    def test_refuses_to_overwrite_or_export_inside_checkout(self):
        dest = self.root / 'preview'
        dest.mkdir()
        (dest / 'keep').write_text('user file')
        with self.assertRaises(ValueError):
            self.export(dest)
        self.assertEqual((dest / 'keep').read_text(), 'user file')
        with self.assertRaises(ValueError):
            self.export(self.repo / 'preview')

    def test_refuses_checkpoint_that_moved(self):
        (self.repo / 'index.html').write_text('later version')
        self.git('add', 'index.html')
        self.git('commit', '-qm', 'later change')
        self.git('branch', '-f', 'backup-test', 'HEAD')
        with self.assertRaises(ValueError):
            self.export(self.root / 'preview')
        self.assertFalse((self.root / 'preview').exists())


if __name__ == '__main__':
    unittest.main()
