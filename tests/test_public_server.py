import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('public_server', Path(__file__).resolve().parents[1] / 'scripts/serve-public.py')
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class PublicPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'site'
        self.root.mkdir()
        for path in ('index.html', 'assets/calculator.js', 'fonts/logo.otf',
                     'supabase/.temp/start-secrets/env/docker.env', 'staff/.env.local', '.git/config'):
            file = self.root / path
            file.parent.mkdir(exist_ok=True, parents=True)
            file.write_text('fixture')

    def test_public_root_and_assets_resolve(self):
        self.assertEqual(server.resolve_public_path('/', self.root), self.root / 'index.html')
        self.assertEqual(server.resolve_public_path('/assets/calculator.js?v=4', self.root), self.root / 'assets/calculator.js')
        self.assertEqual(server.resolve_public_path('/fonts/logo.otf', self.root), self.root / 'fonts/logo.otf')

    def test_private_paths_traversal_and_listing_are_denied(self):
        for path in ('/.git/config', '/staff/.env.local', '/supabase/.temp/start-secrets/env/docker.env',
                     '/assets/../supabase/.temp/start-secrets/env/docker.env', '/assets/%2e%2e/supabase/config.toml',
                     '/assets/%2Ehidden', '/assets/', '/fonts/', '/%00', '/assets\\..\\supabase/config.toml'):
            with self.subTest(path=path):
                self.assertIsNone(server.resolve_public_path(path, self.root))

    def test_public_symlink_cannot_escape_or_serve_backend_data(self):
        outside = self.root.parent / 'private.env'
        outside.write_text('private fixture')
        (self.root / 'assets/outside.js').symlink_to(outside)
        (self.root / 'assets/backend.js').symlink_to(self.root / 'supabase/.temp/start-secrets/env/docker.env')
        self.assertIsNone(server.resolve_public_path('/assets/outside.js', self.root))
        self.assertIsNone(server.resolve_public_path('/assets/backend.js', self.root))


if __name__ == '__main__':
    unittest.main()
