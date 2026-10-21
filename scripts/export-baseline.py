#!/usr/bin/env python3
"""Export and verify the saved public website without modifying a checkout."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

BASELINE = 'ad8cda04dc84c70dbf3a4f1fbc12f711d4fd35bd'
TAG = 'baseline/butterfly-pre-staff-2026-10-20-ad8cda0'
BACKUP_BRANCH = 'backup/butterfly-pre-staff-2026-10-20-ad8cda0'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def export_baseline(repo, destination, commit=BASELINE, tag=TAG, backup_branch=BACKUP_BRANCH):
    repo = Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    destination = Path(destination).resolve()
    archive_path = Path(str(destination) + '.tar')
    if destination.is_relative_to(repo) or archive_path.is_relative_to(repo):
        raise ValueError('Use a new destination outside the checkout.')
    if destination.exists() or archive_path.exists():
        raise ValueError('Destination or archive already exists; nothing was overwritten.')
    for ref in ('refs/tags/' + tag, 'refs/heads/' + backup_branch):
        actual = git(repo, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
        if actual != commit:
            raise ValueError('Saved checkpoint does not match expected baseline: ' + ref)
    entries = {}
    for row in git(repo, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not row:
            continue
        metadata, name = row.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('Unsupported baseline object: ' + name.decode())
        entries[name.decode()] = oid

    archive = git(repo, 'archive', '--format=tar', commit)
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        files = {}
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError('Unsafe archive entry: ' + member.name)
            if member.isfile():
                data = bundle.extractfile(member).read()
                oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                if entries.get(member.name) != oid:
                    raise ValueError('Archive file differs from saved commit: ' + member.name)
                files[member.name] = hashlib.sha256(data).hexdigest()
        if set(files) != set(entries):
            raise ValueError('Archive does not contain exactly the saved baseline files.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive writes refuse collisions and preserve existing user files.
        with archive_path.open('xb') as output:
            output.write(archive)
        destination.mkdir()
        bundle.extractall(destination, filter='data')

    for name, digest in files.items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Restored file failed verification: ' + name)
    return {
        'status': 'verified-local-export', 'commit': commit, 'tag': tag,
        'backup_branch': backup_branch, 'archive': str(archive_path),
        'archive_sha256': hashlib.sha256(archive).hexdigest(),
        'destination': str(destination), 'verified_files': len(files),
        'file_sha256': files,
        'production_deployment_verified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, help='New directory outside the checkout.')
    args = parser.parse_args()
    try:
        result = export_baseline(Path(__file__).resolve().parents[1], args.destination)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
