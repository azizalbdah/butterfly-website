#!/usr/bin/env python3
"""Build a curated staff deployment root, including provider response-header rules."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build(destination):
    destination = Path(destination).expanduser().resolve()
    if destination == ROOT or destination.is_relative_to(ROOT) or destination.exists():
        raise ValueError('Choose a fresh release directory outside the checkout.')
    result = subprocess.run(['npm', 'run', 'build'], cwd=ROOT / 'staff', capture_output=True)
    if result.returncode:
        raise ValueError('Staff build failed; verify public build configuration and installed dependencies.')
    dist = ROOT / 'staff/dist'
    files = sorted(p for p in dist.rglob('*') if p.is_file())
    if any(p.is_symlink() or p.name.startswith('.') or p.suffix == '.map' for p in dist.rglob('*')):
        raise ValueError('Unexpected hidden file, symlink or source map in the release.')
    headers = (dist / '_headers').read_text()
    if not all(value in headers for value in ("frame-ancestors 'none'", 'X-Frame-Options: DENY', 'Referrer-Policy: no-referrer', 'X-Content-Type-Options: nosniff')):
        raise ValueError('Required staff response headers are missing.')
    destination.mkdir(parents=True)
    manifest = {}
    for source in files:
        relative = source.relative_to(dist)
        target = destination / ('_headers' if relative.as_posix() == '_headers' else 'staff/' + relative.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest[target.relative_to(destination).as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / '_redirects').write_text('/ /staff/ 302\n')
    (destination / 'release-manifest.json').write_text(json.dumps({'files_sha256':manifest,
        'scope':'Staff client only; no public site or server configuration',
        'headers':'Netlify/Cloudflare Pages _headers format; verify actual HTTPS response headers after hosting'}, indent=2)+'\n')
    return {'status':'built-staff-release','file_count':len(manifest),'destination':str(destination),'deployed':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.destination)))
    except (OSError, ValueError) as error:
        parser.exit(1, str(error)+'\n')
