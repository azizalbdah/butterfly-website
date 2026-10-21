#!/usr/bin/env python3
"""Check an isolated baseline website rollback preserves current backend records."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('backup_tools', ROOT / 'scripts/local-backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
spec = importlib.util.spec_from_file_location('export_baseline', ROOT / 'scripts/export-baseline.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def main():
    before = backup.table_fingerprints()
    objects = backup.storage_inventory()
    if not all(before.get('public.'+name, {}).get('rows', 0) for name in ('enquiries','customers','quotations','bookings','enquiry_activities')):
        raise ValueError('Real current CRM fixture records are required.')
    opener = build_opener(ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix='butterfly-rollback-') as workdir:
        target = Path(workdir) / 'website'
        exported = baseline.export_baseline(ROOT, target)
        process = subprocess.Popen(['python3', str(ROOT / 'scripts/serve-public.py'), '--root', str(target), '--port', '8004'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(30):
                try:
                    with opener.open('http://127.0.0.1:8004/',timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise ValueError('Isolated baseline server did not become ready.')
            result = subprocess.run(['python3',str(ROOT / 'tests/browser_smoke.py'),'--port','8004'],capture_output=True)
            if result.returncode:
                raise ValueError('Isolated baseline browser acceptance failed.')
        finally:
            process.terminate()
            process.wait(timeout=10)
        if before != backup.table_fingerprints() or objects != backup.storage_inventory():
            raise ValueError('Backend data changed during website rollback rehearsal.')
        return {'status':'passed-local-website-only-rollback','baseline':exported['commit'],
                'baseline_files_verified':exported['verified_files'],'public_browser_groups':13,
                'all_backend_table_digests_preserved':True,'tables_verified':len(before),
                'storage_inventory_preserved':True,'production_redeployed':False,
                'database_restored':False}


if __name__ == '__main__':
    try:
        print(json.dumps(main(), indent=2))
    except Exception as error:
        raise SystemExit('FAIL isolated website rollback ('+type(error).__name__+').')
