#!/usr/bin/env python3
"""Serve public website files only; never expose backend or local setup files."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = {
    'index.html', 'business.html', 'catering.html', 'links.html', 'favicon.ico',
    'CNAME', 'test', 'robots.txt', 'sitemap.xml', 'site.webmanifest',
}
PUBLIC_DIRECTORIES = {'assets', 'fonts', 'images'}


def allowed(relative):
    return ((len(relative.parts) == 1 and relative.name in PUBLIC_FILES)
            or (len(relative.parts) > 1 and relative.parts[0] in PUBLIC_DIRECTORIES))


def resolve_public_path(request_path, root=ROOT):
    root = Path(root).resolve()
    try:
        decoded = unquote(urlsplit(request_path).path, errors='strict')
        if not decoded.startswith('/') or '\x00' in decoded or '\\' in decoded:
            return None
        parts = [part for part in decoded.split('/') if part]
        if any(part.startswith('.') for part in parts):
            return None
        relative = Path(*parts) if parts else Path('index.html')
        if not allowed(relative):
            return None
        candidate = (root / relative).resolve()
        # Check the resolved target too: a public symlink may not expose a
        # backend file or a private artifact outside the document root.
        if not candidate.is_relative_to(root) or not allowed(candidate.relative_to(root)):
            return None
        return candidate if candidate.is_file() else None
    except (ValueError, OSError, UnicodeError):
        return None


class PublicHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        return str(resolve_public_path(path, self.directory) or Path(self.directory) / '.not-public')

    def send_head(self):
        if resolve_public_path(self.path, self.directory) is None:
            self.send_error(404, 'Not found.')
            return None
        return super().send_head()

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, format, *args):
        # URL query strings can contain sensitive input. Log only outcome,
        # never complete request paths or headers.
        if len(args) >= 2 and str(args[1]).isdigit():
            print('Public preview HTTP ' + str(args[1]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Choose a valid local port.')
    handler = partial(PublicHandler, directory=str(ROOT))
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Public-only preview listening on loopback port {args.port}.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
