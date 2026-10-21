#!/usr/bin/env python3
"""Encrypted backup of the isolated Butterfly local preview; never a hosted backup."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tomllib
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    raise SystemExit('The local recovery tools require the installed Python cryptography package; encryption was not bypassed.')

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'butterfly-staff-preview'
CONTAINER = 'supabase_db_' + PROJECT
STORAGE_CONTAINER = 'supabase_storage_' + PROJECT
SOURCE_DB = 'postgres'
OPERATOR_ROLE = 'supabase_admin'
SCHEMAS = ('public', 'auth', 'storage', 'supabase_migrations', 'extensions')
IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class BackupError(Exception):
    pass


def command(args, *, data=None, env=None):
    result = subprocess.run(args, input=data, capture_output=True, check=False, env=env)
    if result.returncode:
        # Do not echo database rows, token-bearing responses, or command stderr.
        raise BackupError(f'Local {Path(args[0]).name} operation failed (exit {result.returncode}).')
    return result.stdout


def sql(statement, database=SOURCE_DB):
    return command(['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-A', '-t', '-v',
                    'ON_ERROR_STOP=1', '-U', OPERATOR_ROLE, '-d', database], data=statement.encode()).decode().strip()


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise BackupError('Unsafe database identifier rejected.')
    return '"' + value + '"'


def safe_private_path(value, *, must_not_exist=False):
    path = Path(value).expanduser().resolve()
    if path == ROOT or path.is_relative_to(ROOT):
        raise BackupError('Private artifacts must stay outside the public checkout.')
    if must_not_exist and path.exists():
        raise BackupError('The requested artifact already exists; nothing was overwritten.')
    return path


def write_private(path, body):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(body)


def read_private(path):
    path = safe_private_path(path)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise BackupError('Credential/key file permissions must exclude group and other access.')
    return path.read_bytes()


def encrypt(key, name, body):
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, body, name.encode())


def decrypt(key, name, body):
    if len(body) < 28:
        raise BackupError('Encrypted artifact is truncated.')
    try:
        return AESGCM(key).decrypt(body[:12], body[12:], name.encode())
    except Exception:
        raise BackupError('Encrypted artifact failed authentication; restoration stopped.') from None


def digest(body):
    return hashlib.sha256(body).hexdigest()


def table_fingerprints(database=SOURCE_DB):
    rows = json.loads(sql("""
SELECT COALESCE(jsonb_agg(jsonb_build_array(n.nspname,c.relname) ORDER BY n.nspname,c.relname),'[]'::jsonb)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname IN ('public','auth','storage','supabase_migrations') AND c.relkind IN ('r','p');
""", database))
    result = {}
    for schema, table in rows:
        data = sql(f'SELECT COALESCE(jsonb_agg(rowdata ORDER BY rowdata::text),\'[]\'::jsonb)::text '
                   f'FROM (SELECT to_jsonb(t) rowdata FROM {identifier(schema)}.{identifier(table)} t) rows;', database).encode()
        result[schema + '.' + table] = {'rows': len(json.loads(data)), 'sha256': digest(data)}
    return result


def policy_fingerprint(database=SOURCE_DB):
    data = sql("""
SELECT jsonb_build_object(
 'policies',(SELECT COALESCE(jsonb_agg(to_jsonb(p) ORDER BY schemaname,tablename,policyname),'[]'::jsonb)
             FROM pg_policies p WHERE schemaname IN ('public','auth','storage')),
 'rls',(SELECT COALESCE(jsonb_agg(jsonb_build_array(n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity,
                               pg_get_userbyid(c.relowner),
                               (SELECT jsonb_agg(jsonb_build_array(a.grantor::regrole::text,a.grantee::regrole::text,
                                                                  a.privilege_type,a.is_grantable)
                                                 ORDER BY a.grantor,a.grantee,a.privilege_type,a.is_grantable)
                                FROM aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a))
                               ORDER BY n.nspname,c.relname),'[]'::jsonb)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname IN ('public','auth','storage') AND c.relkind IN ('r','p')),
 'functions',(SELECT COALESCE(jsonb_agg(jsonb_build_array(n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),
                             pg_get_functiondef(p.oid),pg_get_userbyid(p.proowner),
                             (SELECT jsonb_agg(jsonb_build_array(a.grantor::regrole::text,a.grantee::regrole::text,
                                                                a.privilege_type,a.is_grantable)
                                               ORDER BY a.grantor,a.grantee,a.privilege_type,a.is_grantable)
                              FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a))
                             ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)),'[]'::jsonb)
              FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname IN ('public','auth','storage') AND p.prokind='f'),
 'sequences',(SELECT COALESCE(jsonb_agg(jsonb_build_array(schemaname,sequencename,last_value)
                                      ORDER BY schemaname,sequencename),'[]'::jsonb)
              FROM pg_sequences WHERE schemaname IN ('public','auth','storage'))
)::text;
""", database).encode()
    return digest(data)


def storage_inventory(database=SOURCE_DB):
    return json.loads(sql("SELECT COALESCE(jsonb_agg(jsonb_build_object('bucket',bucket_id,'path',name,'metadata',metadata) "
                          "ORDER BY bucket_id,name),'[]'::jsonb) FROM storage.objects;", database))


def role_fingerprint():
    data = sql("""
SELECT jsonb_build_object(
 'roles',(SELECT jsonb_agg(jsonb_build_array(rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,
                                          rolcanlogin,rolreplication,rolbypassrls,rolvaliduntil)
                          ORDER BY rolname) FROM pg_roles),
 'memberships',(SELECT COALESCE(jsonb_agg(jsonb_build_array(pg_get_userbyid(roleid),pg_get_userbyid(member),
                                                         pg_get_userbyid(grantor),admin_option)
                                        ORDER BY roleid,member),'[]'::jsonb) FROM pg_auth_members)
)::text;
""").encode()
    return digest(data)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BackupError('Unexpected Storage redirect rejected before forwarding credentials.')


def credentials(path):
    state = json.loads(read_private(path))
    api = state.get('API_URL') or state.get('api_url')
    key = state.get('SERVICE_ROLE_KEY') or state.get('service_role_key')
    parsed = urlsplit(api or '')
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port != 54321 or parsed.path not in ('','/'):
        raise BackupError('This command accepts only the local preview API on 127.0.0.1:54321.')
    if not key:
        raise BackupError('Local preview server credential is unavailable.')
    return state, api.rstrip('/'), key


def runtime_bindings():
    """Capture required local signing material only inside the encrypted set."""
    inspected = json.loads(command(['docker', 'inspect', 'supabase_auth_' + PROJECT]))[0]
    env = dict(value.split('=', 1) for value in inspected['Config'].get('Env', []) if '=' in value)
    required = ('GOTRUE_JWT_KEYS', 'GOTRUE_JWT_SECRET', 'GOTRUE_JWT_ISSUER')
    if any(not env.get(name) for name in required):
        raise BackupError('Local Auth signing bindings are incomplete; recovery capture stopped.')
    keys = json.loads(env['GOTRUE_JWT_KEYS'])
    if not isinstance(keys, list) or not keys:
        raise BackupError('Unexpected local Auth signing-key format.')
    service_bindings = {}
    for service, names in (('rest', ('PGRST_JWT_SECRET',)),
                           ('storage', ('ANON_KEY','AUTH_JWT_SECRET','JWT_JWKS','SERVICE_KEY'))):
        metadata = json.loads(command(['docker','inspect','supabase_' + service + '_' + PROJECT]))[0]
        values = dict(value.split('=',1) for value in metadata['Config'].get('Env',[]) if '=' in value)
        service_bindings[service] = {name: values[name] for name in names if name in values}
    service_bindings['auth'] = {name: value for name,value in env.items() if name.startswith('GOTRUE_JWT_')}
    return {'signing_keys': keys, 'legacy_jwt_secret': env['GOTRUE_JWT_SECRET'],
            'jwt_issuer': env['GOTRUE_JWT_ISSUER'],
            'service_signing_bindings': service_bindings,
            'auth_environment': {name: value for name, value in env.items()
                                 if name.startswith('GOTRUE_') or name == 'API_EXTERNAL_URL'}}


def edge_artifacts(credential_file):
    """Capture verified self-contained handlers and their private server bindings."""
    folder = ROOT / 'supabase/functions/.env.local-preview'
    metadata = json.loads((folder / 'sdk-metadata.json').read_bytes())
    if metadata['lockfile_sha256'] != digest((ROOT / 'staff/package-lock.json').read_bytes()):
        raise BackupError('Edge bundles use a different dependency lockfile; rebuild before capture.')
    for name, expected in metadata['shared_sources_sha256'].items():
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT) or digest(source.read_bytes()) != expected:
            raise BackupError('Shared Edge source changed; rebuild before capture.')
    functions = {}
    for name in ('invite-staff', 'publish-site', 'site-media', 'submit-enquiry'):
        info = metadata['functions'][name]
        source = ROOT / 'supabase/functions' / name / 'index.ts'
        bundle = (folder / name / 'index.js').read_bytes()
        if digest(source.read_bytes()) != info['source_sha256'] or digest(bundle) != info['bundle_sha256']:
            raise BackupError('Edge handler source/artifact mismatch; rebuild before capture.')
        functions[name] = bundle.decode()
    bindings = read_private(Path(credential_file).resolve().parent / 'edge.env')
    return {'edge-bindings.env.aesgcm': bindings,
            'edge-bundles.json.aesgcm': json.dumps(functions).encode()}


def backup(destination, key_file, credential_file, fixture_file=None):
    destination = safe_private_path(destination, must_not_exist=True)
    key_file = safe_private_path(key_file, must_not_exist=True)
    if key_file == destination or key_file.is_relative_to(destination):
        raise BackupError('Keep the encryption key outside the backup set.')
    migration_sources = {p.name:p.read_text() for p in sorted((ROOT/'supabase/migrations').glob('*.sql'))}
    config_bytes = (ROOT / 'supabase/config.toml').read_bytes()
    config = tomllib.loads(config_bytes.decode())
    if config.get('project_id') != PROJECT:
        raise BackupError('Unexpected project; the local-only backup guard refused to proceed.')
    state, api, service_key = credentials(credential_file)
    captured_edge = edge_artifacts(credential_file)
    fixture_bytes = read_private(fixture_file) if fixture_file else None
    if fixture_bytes and json.loads(fixture_bytes).get('api_url') != api:
        raise BackupError('Acceptance fixture must belong to this exact local preview.')
    command(['docker', 'inspect', '--format', '{{.State.Running}}', CONTAINER])
    os.umask(0o077)
    destination.mkdir(parents=True, mode=0o700)
    key_file.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    key = AESGCM.generate_key(bit_length=256)
    write_private(key_file, key)
    before = table_fingerprints()
    policy_before = policy_fingerprint()
    roles_before = role_fingerprint()
    bindings_before = runtime_bindings()
    inventory = storage_inventory()
    args = ['docker', 'exec', CONTAINER, 'pg_dump', '-U', OPERATOR_ROLE, '-d', SOURCE_DB, '--format=custom']
    for schema in SCHEMAS:
        args.extend(['--schema', schema])
    database = command(args)
    artifacts = {}

    def save(name, body):
        encrypted = encrypt(key, name, body)
        output = destination / name
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_private(output, encrypted)
        artifacts[name] = {'plaintext_sha256': digest(body), 'encrypted_sha256': digest(encrypted), 'bytes': len(body)}

    if fixture_bytes:
        save('acceptance-fixtures.json.aesgcm', fixture_bytes)
    for name, body in captured_edge.items():
        save(name, body)
    save('database.dump.aesgcm', database)
    save('roles.sql.aesgcm', command(['docker','exec',CONTAINER,'pg_dumpall','-U',OPERATOR_ROLE,'--roles-only']))
    save('migration-sources.json.aesgcm', json.dumps(migration_sources).encode())
    save('runtime-bindings.json.aesgcm', json.dumps(bindings_before, sort_keys=True).encode())
    # Preserve Storage's versioned on-disk layout as well as independently
    # downloaded logical object bytes. This enables an actual API restore.
    save('storage-volume.tar.aesgcm', command(['docker', 'cp', STORAGE_CONTAINER + ':/mnt/.', '-']))
    opener = build_opener(NoRedirect())
    for item in inventory:
        key_path = quote(item['bucket'], safe='') + '/' + quote(item['path'], safe='/')
        request = Request(api + '/storage/v1/object/authenticated/' + key_path,
                          headers={'apikey': service_key, 'Authorization': 'Bearer ' + service_key})
        try:
            with opener.open(request, timeout=30) as response:
                body = response.read(10 * 1024 * 1024 + 1)
                if response.status != 200:
                    raise BackupError('A local Storage object could not be read.')
        except BackupError:
            raise
        except Exception:
            raise BackupError('Local Storage download failed; no credential values were logged.') from None
        if len(body) > 10 * 1024 * 1024:
            raise BackupError('Object exceeds the configured local preview limit.')
        item['sha256'] = digest(body)
        item['bytes'] = len(body)
        item['artifact'] = 'objects/' + digest((item['bucket'] + '\0' + item['path']).encode()) + '.aesgcm'
        save(item['artifact'], body)
    after = table_fingerprints()
    if (before != after or policy_before != policy_fingerprint() or roles_before != role_fingerprint()
            or bindings_before != runtime_bindings() or config_bytes != (ROOT / 'supabase/config.toml').read_bytes() or storage_inventory() != [
        {k:v for k,v in item.items() if k in ('bucket','path','metadata')} for item in inventory
    ]):
        raise BackupError('Source data changed during capture. The partial set is not a valid backup; retry after local writes stop.')
    if migration_sources != {p.name:p.read_text() for p in sorted((ROOT/'supabase/migrations').glob('*.sql'))}:
        raise BackupError('Migrations changed during capture; partial backup rejected.')
    if fixture_bytes and read_private(fixture_file) != fixture_bytes:
        raise BackupError('Acceptance fixtures changed during capture; partial backup rejected.')
    if captured_edge != edge_artifacts(credential_file):
        raise BackupError('Edge artifacts changed during capture; partial backup rejected.')
    published = (json.loads(sql('select public.get_published_site()::text;'))
                 if sql("select to_regprocedure('public.get_published_site()') is not null;") == 't' else None)
    save('source-inventory.json.aesgcm', json.dumps({'tables': before, 'objects': inventory, 'policy_sha256': policy_before,
                                                   'roles_sha256':roles_before,'published_site':published}, sort_keys=True).encode())
    save('supabase-config.toml.aesgcm', config_bytes)
    manifest = {
        'format': 'butterfly-local-aes256gcm-v1', 'status': 'completed', 'local_preview_only': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'project_id': PROJECT,
        'source_container': CONTAINER, 'source_database': SOURCE_DB,
        'database_version': sql('SHOW server_version;'),
        'application_commit': command(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip(),
        'application_working_tree_clean': not bool(command(['git','-C',str(ROOT),'status','--porcelain'])),
        'migrations': sorted(p.name for p in (ROOT / 'supabase/migrations').glob('*.sql')),
        'migration_sha256': {p.name:digest(p.read_bytes()) for p in sorted((ROOT / 'supabase/migrations').glob('*.sql'))},
        'credential_names_only': sorted(state), 'artifacts': artifacts,
        'table_count': len(before), 'object_count': len(inventory),
        'consistency': 'Local source table/policy/inventory digests unchanged across capture; local writes must remain stopped.',
        'limitations': ['Not a hosted-project backup', 'No production credentials, SMTP account, DNS or external service recovery',
                       'No scheduler, external retention or off-site key custody configured'],
    }
    write_private(destination / 'manifest.json', json.dumps(manifest, indent=2).encode())
    return {'status': 'completed-local-backup', 'manifest': str(destination / 'manifest.json'),
            'key_file': str(key_file), 'tables': len(before), 'objects': len(inventory)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, help='Fresh private directory outside the checkout.')
    parser.add_argument('--key-file', required=True, help='Fresh private key file outside the backup set and checkout.')
    parser.add_argument('--fixtures', help='Optional matching local test fixture, stored encrypted for repeatable recovery checks.')
    parser.add_argument('--credentials', default='/workspace/.butterfly-private/local-supabase.json')
    args = parser.parse_args()
    try:
        result = backup(args.destination, args.key_file, args.credentials, args.fixtures)
    except (BackupError, OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
