#!/usr/bin/env python3
"""Restore a local preview backup into a NEW disposable database; never production."""
from __future__ import annotations

import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import struct
import subprocess
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener

SPEC = importlib.util.spec_from_file_location('local_backup', Path(__file__).with_name('local-backup.py'))
backup_tools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_tools)


def restore_check(backup_set, key_file, destination, fixtures=None, runtime_api=False, cli=None):
    started = time.monotonic()
    os.umask(0o077)
    backup_set = backup_tools.safe_private_path(backup_set)
    key_file = backup_tools.safe_private_path(key_file)
    destination = backup_tools.safe_private_path(destination, must_not_exist=True)
    manifest = json.loads((backup_set / 'manifest.json').read_text())
    if manifest.get('format') != 'butterfly-local-aes256gcm-v1' or manifest.get('status') != 'completed' or manifest.get('local_preview_only') is not True:
        raise backup_tools.BackupError('Not a completed, supported local-preview backup.')
    if manifest.get('source_container') != backup_tools.CONTAINER or manifest.get('source_database') != 'postgres':
        raise backup_tools.BackupError('Unexpected source; only the isolated local preview is supported.')
    key = backup_tools.read_private(key_file)
    if len(key) != 32:
        raise backup_tools.BackupError('Encryption key has an invalid size.')

    def read(name):
        path = (backup_set / name).resolve()
        if not path.is_relative_to(backup_set) or not path.is_file():
            raise backup_tools.BackupError('Unsafe or missing backup artifact.')
        encrypted = path.read_bytes()
        info = manifest.get('artifacts', {}).get(name)
        if not info or backup_tools.digest(encrypted) != info.get('encrypted_sha256'):
            raise backup_tools.BackupError('Encrypted artifact checksum mismatch.')
        body = backup_tools.decrypt(key, name, encrypted)
        if backup_tools.digest(body) != info.get('plaintext_sha256') or len(body) != info.get('bytes'):
            raise backup_tools.BackupError('Recovered artifact checksum mismatch.')
        return body

    # Authenticate all inputs before creating any database target.
    artifacts = {name: read(name) for name in manifest['artifacts']}
    required = {'database.dump.aesgcm','roles.sql.aesgcm','source-inventory.json.aesgcm','supabase-config.toml.aesgcm'}
    if not required.issubset(artifacts):
        raise backup_tools.BackupError('The backup set is missing a required recovery artifact.')
    inventory = json.loads(artifacts['source-inventory.json.aesgcm'])
    required.update(item['artifact'] for item in inventory['objects'])
    if runtime_api:
        required.update(('runtime-bindings.json.aesgcm','storage-volume.tar.aesgcm'))
    if not required.issubset(artifacts):
        raise backup_tools.BackupError('The backup set is missing required object/runtime artifacts.')
    if backup_tools.role_fingerprint() != inventory['roles_sha256']:
        raise backup_tools.BackupError('The existing local cluster roles differ from this backup; isolated database rehearsal cannot recreate them safely.')
    target_db = 'butterfly_recovery_' + secrets.token_hex(8)
    if not target_db.startswith('butterfly_recovery_') or target_db == backup_tools.SOURCE_DB:
        raise backup_tools.BackupError('Unsafe restore target rejected.')
    before = backup_tools.table_fingerprints()
    destination.mkdir(parents=True, mode=0o700)
    if not fixtures and 'acceptance-fixtures.json.aesgcm' in artifacts:
        fixtures = destination / 'acceptance-fixtures.json'
        backup_tools.write_private(fixtures, artifacts['acceptance-fixtures.json.aesgcm'])
    # Target names are generated internally. There is no flag to restore over an existing DB.
    backup_tools.sql(f'CREATE DATABASE {backup_tools.identifier(target_db)} WITH TEMPLATE template0 OWNER postgres;')
    try:
        backup_tools.sql('DROP SCHEMA public;', target_db)
        backup_tools.command(['docker','exec','-i',backup_tools.CONTAINER,'pg_restore','--exit-on-error','-U',backup_tools.OPERATOR_ROLE,'-d',target_db],
                             data=artifacts['database.dump.aesgcm'])
        restored = backup_tools.table_fingerprints(target_db)
        if restored != inventory['tables']:
            raise backup_tools.BackupError('Recovered table contents/counts do not match the captured backup.')
        if backup_tools.policy_fingerprint(target_db) != inventory['policy_sha256']:
            raise backup_tools.BackupError('Recovered RLS/function definitions differ from the captured backup.')
        object_checks = 0
        for item in inventory['objects']:
            body = artifacts[item['artifact']]
            if len(body) != item['bytes'] or backup_tools.digest(body) != item['sha256']:
                raise backup_tools.BackupError('Recovered uploaded-file bytes do not match the inventory.')
            # Hashed local file names avoid exposing customer-supplied object names via the filesystem.
            output = destination / ('object-' + backup_tools.digest((item['bucket'] + '\0' + item['path']).encode()))
            backup_tools.write_private(output, body)
            if backup_tools.digest(output.read_bytes()) != item['sha256']:
                raise backup_tools.BackupError('Recovered uploaded-file write failed verification.')
            object_checks += 1
        restored_objects = backup_tools.storage_inventory(target_db)
        if restored_objects != [{k:v for k,v in item.items() if k in ('bucket','path','metadata')} for item in inventory['objects']]:
            raise backup_tools.BackupError('Restored Storage metadata differs from recovered object bytes.')
        role_checks = verify_restored_roles(target_db, fixtures) if fixtures else []
        runtime_report = (verify_runtime_api(artifacts, inventory, destination, fixtures, cli)
                          if runtime_api else None)
        if before != backup_tools.table_fingerprints() or backup_tools.role_fingerprint() != inventory['roles_sha256']:
            raise backup_tools.BackupError('Source data changed during rehearsal; investigate before claiming source preservation.')
        report = {
            'status': 'passed-local-isolated-restore', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'source_preserved': True, 'target_database': target_db,
            'tables_verified': len(restored), 'object_files_verified': object_checks,
            'policy_function_digest_verified': True, 'role_checks': role_checks,
            'existing_cluster_role_inventory_verified': True,
            'separate_supabase_runtime': runtime_report,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'limitations': ['Local isolated recovery only; no hosted-project recovery or production cutover',
                           'Encrypted global-role export is not replayed; recovery of custom roles into a differently configured cluster is untested',
                           'Hosted SMTP/DNS/account rebinding and external service recovery are untested',
                           'No production backup, cutover, off-site retention or production recovery is configured'],
        }
        if not runtime_api:
            report['limitations'].append('Second Auth/Storage HTTP runtime was not exercised')
        if not runtime_report or not runtime_report.get('edge_runtime_exercised'):
            report['limitations'].append('Edge runtimes were not exercised in this recovery clone')
        backup_tools.write_private(destination / 'restore-report.json', json.dumps(report, indent=2).encode())
        return report
    finally:
        # Only the internally generated, fresh rehearsal database may be removed.
        backup_tools.sql(f'DROP DATABASE {backup_tools.identifier(target_db)};')


def verify_runtime_api(artifacts, inventory, destination, fixtures, cli):
    """Rehearse real Auth/MFA and Storage in an independent disposable project."""
    if not fixtures:
        raise backup_tools.BackupError('Runtime recovery requires the private acceptance fixture.')
    cli = Path(cli or '/workspace/.butterfly-tools/supabase').resolve()
    if backup_tools.command([str(cli), '--version']).decode().strip() != '2.121.0':
        raise backup_tools.BackupError('Runtime rehearsal requires the documented official CLI version 2.121.0.')
    bindings = json.loads(artifacts['runtime-bindings.json.aesgcm'])
    workdir = destination / 'runtime-project'
    config_dir = workdir / 'supabase'
    config_dir.mkdir(parents=True, mode=0o700)
    project = 'butterfly-staff-recovery-' + secrets.token_hex(5)
    config = artifacts['supabase-config.toml.aesgcm'].decode()
    config = re.sub(r'(?m)^project_id\s*=.*$', 'project_id = ' + json.dumps(project), config)
    for old, new in ((54321,55321),(54322,55322),(54320,55320),(54324,55324)):
        config = config.replace(str(old), str(new))
    config = config.replace('[auth]\n', '[auth]\njwt_secret = "env(BUTTERFLY_RECOVERY_JWT_SECRET)"\nsigning_keys_path = "./signing_keys.json"\njwt_issuer = '
                            + json.dumps(bindings['jwt_issuer']) + '\n', 1)
    edge_enabled = all(name in artifacts for name in ('edge-bindings.env.aesgcm','edge-bundles.json.aesgcm'))
    if edge_enabled:
        bundles = json.loads(artifacts['edge-bundles.json.aesgcm'])
        if set(bundles) != {'invite-staff','publish-site','site-media','submit-enquiry'}:
            raise backup_tools.BackupError('Unexpected captured Edge handler set.')
        for name, source in bundles.items():
            folder = config_dir / 'functions' / name
            folder.mkdir(parents=True, mode=0o700)
            backup_tools.write_private(folder / 'index.js', source.encode())
            backup_tools.write_private(folder / 'import_map.json', b'{"imports":{}}')
            pattern = r'(?m)^import_map\s*=\s*"./functions/' + re.escape(name) + r'/production-import-map.json"$'
            replacement = ('import_map = "./functions/' + name + '/import_map.json"\n'
                           'entrypoint = "./functions/' + name + '/index.js"')
            config, count = re.subn(pattern, replacement, config)
            if count != 1:
                raise backup_tools.BackupError('Captured Edge configuration cannot be rebound safely.')
    else:
        config = re.sub(r'(\[edge_runtime\]\s*\n)enabled\s*=\s*true', r'\1enabled = false', config)
    backup_tools.write_private(config_dir / 'config.toml', config.encode())
    backup_tools.write_private(config_dir / 'signing_keys.json', json.dumps(bindings['signing_keys']).encode())
    migration_sources = json.loads(artifacts.get('migration-sources.json.aesgcm',b'{}'))
    if migration_sources:
        (config_dir/'migrations').mkdir(mode=0o700)
        for name,source in migration_sources.items():
            if not re.fullmatch(r'[0-9]{14}_[a-z0-9_]+\.sql',name) or not isinstance(source,str):
                raise backup_tools.BackupError('Invalid captured migration source.')
            backup_tools.write_private(config_dir/'migrations'/name,source.encode())
    log = destination / 'runtime-start.log'
    env = dict(os.environ, SUPABASE_USE_SLIM_IMAGES='true', BUTTERFLY_RECOVERY_JWT_SECRET=bindings['legacy_jwt_secret'])
    original_container = backup_tools.CONTAINER
    clone_db = 'supabase_db_' + project
    recovery_db = 'butterfly_recovery_' + secrets.token_hex(8)
    checks = []
    try:
        # All generated output is private: CLI output can contain server keys.
        with open(log, 'xb') as stream:
            os.chmod(log, 0o600)
            result = subprocess.run([str(cli), 'start', '--workdir', str(workdir), '--exclude',
                                     'studio,vector,realtime,imgproxy,logflare,supavisor,postgres-meta,edge-runtime',
                                     '--ignore-health-check'], env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise backup_tools.BackupError('Disposable Supabase runtime startup failed; inspect its private log.')
        status = json.loads(backup_tools.command([str(cli), 'status', '--workdir', str(workdir), '-o', 'json'], env=env))
        if status.get('API_URL') != 'http://127.0.0.1:55321' or status.get('JWT_SECRET') != bindings['legacy_jwt_secret']:
            raise backup_tools.BackupError('Disposable API endpoint or legacy signing binding differs from the backup.')
        backup_tools.CONTAINER = clone_db
        if migration_sources:
            versions=json.loads(backup_tools.sql("select coalesce(jsonb_agg(version order by version),'[]'::jsonb)::text from supabase_migrations.schema_migrations;"))
            if versions!=sorted(name.split('_')[0] for name in migration_sources):
                raise backup_tools.BackupError('Captured migrations did not apply to the fresh Supabase project.')
            checks.append('clean-versioned-migrations-applied')
        if backup_tools.role_fingerprint() != inventory['roles_sha256']:
            raise backup_tools.BackupError('Fresh CLI cluster roles differ from captured role inventory.')
        backup_tools.sql(f'CREATE DATABASE {backup_tools.identifier(recovery_db)} WITH TEMPLATE template0 OWNER postgres;')
        backup_tools.sql('DROP SCHEMA public;', recovery_db)
        backup_tools.command(['docker','exec','-i',clone_db,'pg_restore','--exit-on-error','-U',backup_tools.OPERATOR_ROLE,'-d',recovery_db],
                             data=artifacts['database.dump.aesgcm'])
        if backup_tools.table_fingerprints(recovery_db) != inventory['tables']:
            raise backup_tools.BackupError('Independent runtime database differs from the backup.')
        if backup_tools.policy_fingerprint(recovery_db) != inventory['policy_sha256']:
            raise backup_tools.BackupError('Independent runtime policies differ from the backup.')
        checks.append('independent-cluster-database-and-policy-digests')
        # Recreate only newly generated services, keeping CLI image/probes/volumes.
        local_start_spec = importlib.util.spec_from_file_location('local_start', Path(__file__).with_name('local-start.py'))
        local_start = importlib.util.module_from_spec(local_start_spec)
        local_start_spec.loader.exec_module(local_start)
        for service, binding in (('auth','GOTRUE_DB_DATABASE_URL'),('rest','PGRST_DB_URI'),('storage','DATABASE_URL')):
            name = 'supabase_' + service + '_' + project
            metadata = json.loads(backup_tools.command(['docker','inspect',name]))[0]
            if metadata['Config'].get('Labels', {}).get('com.supabase.cli.project') != project:
                raise backup_tools.BackupError('Disposable service ownership check failed.')
            settings = copy.deepcopy(metadata['Config'])
            values = dict(value.split('=',1) for value in settings['Env'] if '=' in value)
            parsed = urlsplit(values[binding])
            if parsed.path != '/postgres':
                raise backup_tools.BackupError('Unexpected disposable database connection binding.')
            values[binding] = urlunsplit(parsed._replace(path='/' + recovery_db))
            values.update(bindings['service_signing_bindings'][service])
            values['HTTP_PROXY'] = values['http_proxy'] = ''
            settings['Env'] = [key + '=' + value for key,value in values.items()]
            settings['HostConfig'] = copy.deepcopy(metadata['HostConfig'])
            endpoints = {}
            for network, endpoint in metadata['NetworkSettings']['Networks'].items():
                if network != 'supabase_network_' + project:
                    raise backup_tools.BackupError('Unexpected disposable service network.')
                endpoints[network] = {key: copy.deepcopy(endpoint[key]) for key in ('IPAMConfig','Links','Aliases','DriverOpts')
                                      if endpoint.get(key) is not None}
            settings['NetworkingConfig'] = {'EndpointsConfig': endpoints}
            backup_tools.command(['docker','rm','--force',name])
            local_start.create_container(name, settings)
            backup_tools.command(['docker','start',name])
        storage = 'supabase_storage_' + project
        backup_tools.command(['docker','cp','-a','-',storage + ':/mnt'],
                             data=artifacts['storage-volume.tar.aesgcm'])
        backup_tools.CONTAINER = original_container
        opener = build_opener(ProxyHandler({}), backup_tools.NoRedirect())
        api = status['API_URL']

        def request(method, path, *, token=None, data=None, raw=None, headers=None):
            request_headers = {'apikey': status['ANON_KEY'], 'Authorization': 'Bearer ' + (token or status['ANON_KEY'])}
            request_headers.update(headers or {})
            body = raw
            if data is not None:
                body = json.dumps(data).encode()
                request_headers['Content-Type'] = 'application/json'
            try:
                with opener.open(Request(api + path, data=body, headers=request_headers, method=method), timeout=20) as response:
                    return response.status, response.read()
            except HTTPError as response:
                return response.code, response.read()

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if all(request('GET', path)[0] == 200 for path in ('/auth/v1/health','/storage/v1/status','/rest/v1/')):
                    break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise backup_tools.BackupError('Restored Auth/Storage/Data API readiness failed.')
        accounts = json.loads(backup_tools.read_private(fixtures))['accounts']
        code, body = request('POST','/auth/v1/signup',data={'email':'recovery-probe@butterfly.test','password':'Disabled9!RecoveryProbe'})
        error = json.loads(body)
        if code not in (400,403,422) or (error.get('error_code') or error.get('code')) != 'signup_disabled':
            raise backup_tools.BackupError('Restored Auth configuration allows public signup.')
        checks.append('restored-auth-public-signup-disabled')
        code, body = request('POST','/auth/v1/token?grant_type=refresh_token',
                             data={'refresh_token':accounts['admin']['refresh_token']})
        if code != 200:
            raise backup_tools.BackupError('A recovered existing administrator session cannot refresh.')
        code, body = request('GET','/rest/v1/staff_members?select=user_id',token=json.loads(body)['access_token'])
        if code != 200 or len(json.loads(body)) != inventory['tables']['public.staff_members']['rows']:
            raise backup_tools.BackupError('Recovered administrator session lost its MFA permissions.')
        checks.append('restored-existing-session-refresh-and-aal2-access')
        sessions = {}
        for role, name in (('admin','admin'),('sales','sales'),('marketing','marketing'),('inactive','disabled'),('outsider','outsider')):
            account = accounts[name]
            code, body = request('POST','/auth/v1/token?grant_type=password', data={'email':account['email'],'password':account['password']})
            if code != 200:
                raise backup_tools.BackupError('Restored Auth password login failed for ' + role)
            session = json.loads(body)
            sessions[role] = session['access_token']
            code, body = request('GET','/rest/v1/staff_members?select=user_id',token=sessions[role])
            expected = 0 if role in ('inactive','outsider') else 1
            if code != 200 or len(json.loads(body)) != expected:
                raise backup_tools.BackupError('Restored API role boundary failed for ' + role)
            checks.append('auth-login-and-api-role:' + role)
        admin = accounts['admin']
        code, body = request('GET','/auth/v1/user',token=sessions['admin'])
        if code != 200 or not any(factor.get('id') == admin['totp_factor_id'] and factor.get('status') == 'verified'
                                  for factor in json.loads(body).get('factors', [])):
            raise backup_tools.BackupError('The restored verified MFA factor is missing.')
        code, body = request('POST','/auth/v1/factors/' + admin['totp_factor_id'] + '/challenge',token=sessions['admin'],data={})
        if code != 200:
            raise backup_tools.BackupError('Restored MFA challenge failed.')
        challenge = json.loads(body)['id']
        # Avoid replaying the same TOTP time step used by source acceptance.
        if int(time.time()) // 30 == int(admin.get('mfa_verified_at', 0)) // 30:
            time.sleep(31 - int(time.time()) % 30)
        raw_secret = base64.b32decode(admin['totp_secret'].upper() + '=' * (-len(admin['totp_secret']) % 8))
        value = hmac.new(raw_secret, struct.pack('>Q', int(time.time()) // 30), hashlib.sha1).digest()
        offset = value[-1] & 15
        otp = str((struct.unpack('>I', value[offset:offset+4])[0] & 0x7fffffff) % 1000000).zfill(6)
        code, body = request('POST','/auth/v1/factors/' + admin['totp_factor_id'] + '/verify',token=sessions['admin'],
                             data={'challenge_id':challenge,'code':otp})
        if code != 200:
            raise backup_tools.BackupError('Restored MFA verification failed.')
        admin_token = json.loads(body)['access_token']
        code, body = request('GET','/rest/v1/staff_members?select=user_id',token=admin_token)
        if code != 200 or len(json.loads(body)) != inventory['tables']['public.staff_members']['rows']:
            raise backup_tools.BackupError('Restored MFA administrator cannot read the expected staff list.')
        checks.append('restored-verified-totp-and-aal2-admin-api')
        if not inventory['objects']:
            raise backup_tools.BackupError('No uploaded-file fixture exists for real Storage recovery.')
        for item in inventory['objects']:
            path = quote(item['bucket'],safe='') + '/' + quote(item['path'],safe='/')
            for role, token in (('marketing',sessions['marketing']),('admin',admin_token)):
                code, body = request('GET','/storage/v1/object/authenticated/' + path,token=token)
                if code != 200 or backup_tools.digest(body) != item['sha256']:
                    raise backup_tools.BackupError('Restored private Storage bytes failed for ' + role)
            for role, token in (('sales',sessions['sales']),('inactive',sessions['inactive']),
                                ('outsider',sessions['outsider']),('admin-aal1',sessions['admin']),('anonymous',None)):
                if request('GET','/storage/v1/object/authenticated/' + path,token=token)[0] == 200:
                    raise backup_tools.BackupError('Restored private Storage boundary failed for ' + role)
            if request('GET','/storage/v1/object/public/' + path)[0] == 200:
                raise backup_tools.BackupError('Restored private Storage became public.')
        checks.append('restored-storage-api-bytes-and-role-boundaries')
        item = next((item for item in inventory['objects'] if item['bucket']=='staff-media'),None)
        if not item:
            raise backup_tools.BackupError('No mutable private staff-media fixture exists for upload recovery.')
        probe_path = '/storage/v1/object/' + quote(item['bucket'],safe='') + '/recovery-probe/' + secrets.token_hex(8) + '.png'
        code, _ = request('POST',probe_path,token=sessions['marketing'],raw=artifacts[item['artifact']],
                          headers={'Content-Type':item['metadata'].get('mimetype','image/png'),'x-upsert':'false'})
        if code not in (200,201):
            raise backup_tools.BackupError('Recovered Storage runtime cannot accept an authorized upload.')
        code, body = request('GET',probe_path.replace('/object/','/object/authenticated/',1),token=sessions['marketing'])
        if code != 200 or backup_tools.digest(body) != item['sha256']:
            raise backup_tools.BackupError('A new recovered-runtime upload could not be read back exactly.')
        checks.append('restored-storage-api-authorized-new-upload')
        if inventory.get('published_site'):
            code, body = request('POST','/rest/v1/rpc/get_published_site',data={})
            if code != 200 or json.loads(body) != inventory['published_site']:
                raise backup_tools.BackupError('Restored anonymous published content/catalogue differs from the backup.')
            for item in inventory['objects']:
                if item['bucket']=='site-media':
                    statement = "select coalesce(jsonb_agg(name),'[]'::jsonb)::text from public.site_published_media;"
                    expected = item['path'] in json.loads(backup_tools.command([
                        'docker','exec','-i',clone_db,'psql','-X','-At','-U',
                        backup_tools.OPERATOR_ROLE,'-d',recovery_db,'-c',statement]).decode())
                    code, body = request('POST','/rest/v1/rpc/is_site_media_published',data={'object_name':item['path']})
                    if code != 200 or json.loads(body) is not expected:
                        raise backup_tools.BackupError('Restored publication media visibility differs from its saved state.')
            checks.append('restored-published-content-catalogue-and-media-visibility')
        fixture = json.loads(backup_tools.read_private(fixtures))
        if fixture.get('crm'):
            crm = fixture['crm']
            code, body = request('GET','/rest/v1/bookings?id=eq.' + crm['booking_id'],token=admin_token)
            if code != 200 or len(json.loads(body)) != 1 or json.loads(body)[0]['amount_fils'] != crm['booking_amount_fils']:
                raise backup_tools.BackupError('Recovered booking lost its immutable accepted price.')
            for row_id, count in ((crm['assigned_enquiry'],1),(crm['other_enquiry'],0)):
                code, body = request('GET','/rest/v1/enquiries?id=eq.' + row_id,token=sessions['sales'])
                if code != 200 or len(json.loads(body)) != count:
                    raise backup_tools.BackupError('Recovered Sales assignment boundary failed.')
            checks.append('restored-crm-immutable-booking-price-and-assignment-boundaries')
        if edge_enabled:
            private_edge = destination / 'edge-runtime'
            private_edge.mkdir(mode=0o700)
            backup_tools.write_private(private_edge / 'edge.env', artifacts['edge-bindings.env.aesgcm'])
            local_start.PROJECT = project
            local_start.serve_functions(cli, workdir, workdir, private_edge, process_env=env)
            local_start.require_function(status)
            checks.append('restored-exact-captured-edge-handlers-and-private-bindings')
            for item in inventory['objects']:
                if item['bucket'] != 'site-media':
                    continue
                code, body = request('POST','/rest/v1/rpc/is_site_media_published',data={'object_name':item['path']})
                published = code == 200 and json.loads(body) is True
                code, body = request('GET','/functions/v1/site-media?name=' + quote(item['path'],safe=''))
                if (published and (code != 200 or backup_tools.digest(body) != item['sha256'])) or (not published and code != 404):
                    raise backup_tools.BackupError('Recovered Edge media serving lost its publication boundary.')
            checks.append('restored-public-photo-edge-bytes-and-private-staging-denial')
            catalogue = inventory['published_site']['catalogue_revision']
            request_key = str(uuid.uuid4())
            payload = {'action':'submit','request_key':request_key,'kind':'catering','service':'coffee',
                       'catalogue_revision':catalogue,'customer':{'name':'Isolated recovery probe','phone':'+9659' + str(secrets.randbelow(10**7)).zfill(7),'email':'','company':''},
                       'event_date':'','event_time':'','venue':'Isolated recovery only','notes':'','website':'',
                       'selection':{'guests':30,'hours':4,'package_id':None,'extras':{},'team_select':True}}
            origins = dict(line.split('=',1) for line in artifacts['edge-bindings.env.aesgcm'].decode().splitlines() if '=' in line)
            origin = origins['BUTTERFLY_PUBLIC_ORIGINS'].split(',')[0].strip()
            code, body = request('POST','/functions/v1/submit-enquiry',data=payload,headers={'Origin':origin})
            if code != 201 or not json.loads(body).get('receipt'):
                raise backup_tools.BackupError('Recovered enquiry Edge handler cannot save a new anonymous request.')
            receipt = json.loads(body)['receipt']
            code, body = request('GET','/rest/v1/enquiries?receipt=eq.' + quote(receipt,safe=''),token=admin_token)
            rows = json.loads(body)
            expected_price = round(inventory['published_site']['catalogue']['coffeePackages'][0]['price']*1000)
            if code != 200 or len(rows) != 1 or rows[0]['status'] != 'new' or rows[0]['assigned_to'] is not None or rows[0]['price_snapshot']['total_fils'] != expected_price:
                raise backup_tools.BackupError('Recovered enquiry lost its server price or initial assignment state.')
            row_id = rows[0]['id']
            code, body = request('POST','/functions/v1/submit-enquiry',data=payload,headers={'Origin':origin})
            if code != 200 or json.loads(body).get('receipt') != receipt:
                raise backup_tools.BackupError('Recovered enquiry retry created another record.')
            code, _ = request('POST','/functions/v1/submit-enquiry',data={'action':'whatsapp_open_requested','request_key':request_key},headers={'Origin':origin})
            if code != 202:
                raise backup_tools.BackupError('Recovered WhatsApp activity endpoint failed.')
            for table in ('quotations','bookings'):
                code, body = request('GET','/rest/v1/' + table + '?enquiry_id=eq.' + row_id,token=admin_token)
                if code != 200 or json.loads(body):
                    raise backup_tools.BackupError('Recovered WhatsApp activity fabricated a quotation or booking.')
            checks.append('restored-anonymous-capture-server-pricing-idempotency-and-whatsapp-separation')
        code, _ = request('POST','/auth/v1/recover?redirect_to=' + quote('http://127.0.0.1:5173/staff/',safe=''),
                           data={'email':accounts['recovery']['email']})
        if code != 200:
            raise backup_tools.BackupError('Restored Auth cannot request local password recovery.')
        mail_url = 'http://127.0.0.1:55324/api/v1/search?' + urlencode({'query':'to:' + accounts['recovery']['email']})
        for _ in range(15):
            with opener.open(mail_url,timeout=10) as response:
                if json.load(response).get('messages'):
                    break
            time.sleep(1)
        else:
            raise backup_tools.BackupError('Recovered Auth did not deliver password recovery to isolated local Mailpit.')
        checks.append('restored-auth-local-password-recovery-mail')
        return {'status':'passed-independent-local-api-restore', 'project':project,
                'checks':checks, 'independent_database_and_storage_volumes':True,
                'fresh_cli_cluster_role_inventory_verified':True,
                'auth_signing_keys_restored':True, 'source_users_logged_out':False,
                'edge_runtime_exercised':edge_enabled,
                'cleanup':'Disposable project and its volumes removed after rehearsal'}
    finally:
        backup_tools.CONTAINER = original_container
        # Explicit generated project only: never --all or the preview project.
        result = subprocess.run([str(cli),'stop','--project-id',project,'--no-backup','--workdir',str(workdir)],
                                capture_output=True, env=env)
        if result.returncode:
            raise backup_tools.BackupError('Disposable runtime cleanup failed; source was not targeted.')


def verify_restored_roles(database, fixtures):
    state = json.loads(backup_tools.read_private(fixtures))
    # The acceptance fixture may use either accounts or users as its top-level mapping.
    accounts = state.get('accounts') or state.get('users')
    if not isinstance(accounts, dict):
        raise backup_tools.BackupError('Acceptance fixture has no account mapping for restored permission checks.')
    checks = []
    for role in ('admin','sales','marketing','inactive','outsider'):
        account = accounts.get(role) or accounts.get({'inactive':'disabled','outsider':'uninvited'}.get(role,''))
        if not account:
            raise backup_tools.BackupError('Required restored-role fixture is absent: ' + role)
        user_id = account.get('user_id') or account.get('id')
        if not isinstance(user_id, str) or not __import__('re').fullmatch(r'[0-9a-fA-F-]{36}', user_id):
            raise backup_tools.BackupError('Acceptance fixture user identifier is invalid.')
        session_id = account.get('session_id')
        if not session_id:
            token = account.get('access_token') or (account.get('session') or {}).get('access_token')
            try:
                encoded = token.split('.')[1]
                session_id = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))['session_id']
            except (AttributeError, IndexError, ValueError, KeyError):
                raise backup_tools.BackupError('Restored-role fixture lacks a session identifier.') from None
        for aal in (('aal1','aal2') if role == 'admin' else ('aal1',)):
            claims = json.dumps({'sub':user_id,'role':'authenticated','aal':aal,'session_id':session_id}).replace("'", "''")
            statement = f"SET ROLE authenticated; SET request.jwt.claims = '{claims}'; SELECT count(*) FROM public.staff_members;"
            # psql prints SET command tags before the final row.
            count = int(backup_tools.sql(statement, database).splitlines()[-1])
            expected = 0 if role in ('inactive','outsider') else 1
            if role == 'admin' and aal == 'aal2':
                expected = int(backup_tools.sql('SELECT count(*) FROM public.staff_members;', database))
            if count != expected:
                raise backup_tools.BackupError('A restored staff role boundary failed.')
            is_admin = backup_tools.sql(f"SET ROLE authenticated; SET request.jwt.claims = '{claims}'; SELECT public.app_is_admin();", database).splitlines()[-1]
            if is_admin != ('t' if role == 'admin' and aal == 'aal2' else 'f'):
                raise backup_tools.BackupError('A restored administrator MFA boundary failed.')
            checks.append(role + ':' + aal)
    if not checks:
        raise backup_tools.BackupError('No restored role checks executed.')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-set', required=True)
    parser.add_argument('--key-file', required=True)
    parser.add_argument('--destination', required=True, help='Fresh private recovery evidence directory.')
    parser.add_argument('--fixtures', help='Private acceptance fixture for restored direct SQL/RLS role checks.')
    parser.add_argument('--runtime-api', action='store_true', help='Also start and destroy an independent local Supabase Auth/Storage recovery project.')
    parser.add_argument('--cli', default='/workspace/.butterfly-tools/supabase')
    args = parser.parse_args()
    try:
        result = restore_check(args.backup_set, args.key_file, args.destination, args.fixtures, args.runtime_api, args.cli)
    except (backup_tools.BackupError, OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
