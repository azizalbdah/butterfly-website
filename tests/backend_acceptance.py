#!/usr/bin/env python3
"""Exercise genuine local Supabase Auth, RLS, private Storage and invitation APIs.

Requires the private CLI status JSON. Creates isolated local fixture accounts and
retains them for browser/recovery acceptance. Never prints credentials or tokens.
"""
import argparse
import base64
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import re
import secrets
import struct
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import uuid


class CheckFailed(Exception):
    pass


def check(condition, message):
    if not condition:
        raise CheckFailed(message)


def private_json(path, value):
    path = Path(path).resolve()
    checkout = Path(__file__).resolve().parents[1]
    check(not path.is_relative_to(checkout), 'Private fixture/report path must be outside the served checkout.')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    check(not (stat.S_IMODE(path.parent.stat().st_mode) & 0o077),
          'Choose an existing private 0700 directory for credential/report files.')
    temporary = path.with_suffix(path.suffix + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(value, output, indent=2)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def local_url(value):
    parsed = urlsplit(value)
    check(parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost'),
          'Acceptance can only create fixture data in a local Supabase instance.')
    check(not parsed.username and not parsed.password, 'Credentials must not be embedded in local URLs.')
    return value.rstrip('/')


def decode_json(body):
    try:
        return json.loads(body)
    except (ValueError, UnicodeError):
        return None


def totp(secret):
    raw = base64.b32decode(secret.upper() + '=' * (-len(secret) % 8))
    digest = hmac.new(raw, struct.pack('>Q', int(time.time()) // 30), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000).zfill(6)


def token_claims(token):
    encoded = token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Acceptance:
    def __init__(self, config, fixture_path):
        self.api = local_url(config['API_URL'])
        self.mail = local_url(config.get('INBUCKET_URL', 'http://127.0.0.1:54324'))
        self.anon = config.get('ANON_KEY') or config.get('PUBLISHABLE_KEY')
        self.service = config.get('SERVICE_ROLE_KEY') or config.get('SECRET_KEY')
        check(bool(self.anon and self.service), 'Private local config is missing API credential bindings.')
        self.jwt_secret = config.get('JWT_SECRET')
        self.run_id = uuid.uuid4().hex[:12]
        self.fixture_path = Path(fixture_path)
        self.fixture = {'run_id': self.run_id, 'api_url': self.api, 'accounts': {}, 'objects': []}
        self.passed = []

    def save(self):
        private_json(self.fixture_path, self.fixture)

    def passed_check(self, name):
        self.passed.append(name)
        print('PASS ' + name, flush=True)

    def request(self, method, path, *, token=None, admin=False, data=None, raw=None, headers=None):
        key = self.service if admin else self.anon
        request_headers = {'apikey': key, 'Authorization': 'Bearer ' + (token or key)}
        request_headers.update(headers or {})
        body = raw
        if data is not None:
            body = json.dumps(data).encode()
            request_headers['Content-Type'] = 'application/json'
        request = Request(self.api + path, data=body, method=method, headers=request_headers)
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read()
                return response.status, decode_json(body), body
        except HTTPError as response:
            body = response.read()
            return response.code, decode_json(body), body
        except (URLError, OSError):
            raise CheckFailed('Local API request failed; check stack readiness without exposing credentials.') from None

    def expect_request(self, method, path, *, statuses=(200,), label, **kwargs):
        status, data, body = self.request(method, path, **kwargs)
        check(status in statuses, label + f' (HTTP {status}; expected allowed outcome)')
        return data, body

    def create_user(self, name, role=None, active=True):
        email = f'acceptance.{self.run_id}.{name}@butterfly.test'
        password = 'Bf9!' + secrets.token_urlsafe(24)
        user, _ = self.expect_request('POST', '/auth/v1/admin/users', admin=True,
                                    data={'email': email, 'password': password, 'email_confirm': True},
                                    statuses=(200, 201), label='Create isolated local fixture account')
        user_id = user.get('id')
        check(isinstance(user_id, str), 'Fixture account creation returned no user identifier.')
        if role:
            self.expect_request('POST', '/rest/v1/staff_members', admin=True,
                                data={'user_id': user_id, 'display_name': 'Local acceptance ' + name,
                                      'role': role, 'active': active},
                                statuses=(201,), label='Trusted fixture membership creation')
        account = {'user_id': user_id, 'email': email, 'password': password, 'role': role, 'active': active}
        self.fixture['accounts'][name] = account
        self.save()
        return account

    def sign_in(self, account):
        session, _ = self.expect_request('POST', '/auth/v1/token?grant_type=password',
                                        data={'email': account['email'], 'password': account['password']},
                                        label='Real password sign-in')
        check(bool(session.get('access_token') and session.get('refresh_token')), 'Real sign-in returned no session.')
        account['access_token'] = session['access_token']
        account['refresh_token'] = session['refresh_token']
        claims = token_claims(session['access_token'])
        account['session_id'] = claims.get('session_id')
        account['session_aal'] = claims.get('aal')
        self.save()
        return session['access_token']

    def rows(self, path, token=None, admin=False):
        data, _ = self.expect_request('GET', '/rest/v1/' + path, token=token, admin=admin,
                                     label='Direct database read')
        check(isinstance(data, list), 'Database read returned an unexpected response type.')
        return data

    def enroll_admin(self, account):
        token = account['access_token']
        factor, _ = self.expect_request('POST', '/auth/v1/factors', token=token,
                                       data={'factor_type': 'totp', 'friendly_name': 'Butterfly acceptance'},
                                       label='Real TOTP enrollment')
        secret = factor.get('totp', {}).get('secret')
        factor_id = factor.get('id')
        check(bool(secret and factor_id), 'TOTP enrollment returned no usable factor.')
        challenge, _ = self.expect_request('POST', f'/auth/v1/factors/{factor_id}/challenge', token=token,
                                          data={}, label='Real MFA challenge')
        session, _ = self.expect_request('POST', f'/auth/v1/factors/{factor_id}/verify', token=token,
                                        data={'challenge_id': challenge.get('id'), 'code': totp(secret)},
                                        label='Real MFA verification')
        check(bool(session.get('access_token')), 'MFA verification returned no upgraded session.')
        account['aal1_access_token'] = token
        account['access_token'] = session['access_token']
        account['refresh_token'] = session['refresh_token']
        account['totp_secret'] = secret
        account['totp_factor_id'] = factor_id
        account['mfa_verified_at'] = time.time()
        claims = token_claims(session['access_token'])
        account['session_id'] = claims.get('session_id')
        account['session_aal'] = claims.get('aal')
        self.save()
        return account['access_token']

    def find_email_link(self, recipient, expected_type):
        """Read only locally generated Mailpit email; never contact a real mailbox."""
        for _ in range(12):
            try:
                with urlopen(self.mail + '/api/v1/search?' + urlencode({'query': 'to:' + recipient}), timeout=5) as response:
                    messages = json.load(response).get('messages', [])
                for message in messages:
                    with urlopen(self.mail + '/api/v1/message/' + quote(message['ID'], safe=''), timeout=5) as response:
                        full = json.load(response)
                    text = html.unescape((full.get('HTML') or '') + '\n' + (full.get('Text') or ''))
                    for candidate in re.findall(r'https?://[^\s<>"\']+', text):
                        parsed = urlsplit(candidate)
                        if parsed.hostname in ('127.0.0.1', 'localhost') and parsed.path == '/auth/v1/verify':
                            if parse_qs(parsed.query).get('type') == [expected_type]:
                                return candidate
            except (HTTPError, URLError, OSError, ValueError, KeyError):
                pass
            time.sleep(1)
        raise CheckFailed('Expected local invitation/recovery email was not delivered to Mailpit.')

    def verify_email_link(self, link):
        parsed = urlsplit(link)
        check(parsed.hostname in ('127.0.0.1', 'localhost') and parsed.path == '/auth/v1/verify',
              'Refusing to consume a nonlocal authentication link.')
        try:
            response = build_opener(NoRedirect()).open(link, timeout=10)
        except HTTPError as response:
            check(response.code in (302, 303), 'Authentication verification did not return a callback redirect.')
            location = response.headers.get('Location', '')
        else:
            with response:
                location = response.headers.get('Location', '')
        callback = urlsplit(location)
        check(callback.scheme == 'http' and callback.hostname == '127.0.0.1' and callback.port == 5173 and callback.path == '/staff/',
              'Authentication callback was not scoped to the local staff application.')
        fragment = parse_qs(callback.fragment)
        check('access_token' in fragment and 'error' not in fragment, 'Authentication callback did not establish a real session.')
        return fragment['access_token'][0]

    def run(self):
        self.save()
        status, signup_error, _ = self.request('POST', '/auth/v1/signup',
                                    data={'email': f'public.{self.run_id}@butterfly.test', 'password': 'Disabled9!' + secrets.token_urlsafe(20)})
        check(status in (400, 403, 422) and isinstance(signup_error, dict)
              and (signup_error.get('error_code') or signup_error.get('code')) == 'signup_disabled',
              'Public signup must be rejected specifically because signups are disabled.')
        self.passed_check('Public signup rejects uninvited users')

        accounts = {name: self.create_user(name, role, active) for name, role, active in (
            ('admin', 'admin', True), ('sales', 'sales', True), ('marketing', 'marketing', True),
            ('disabled', 'sales', False), ('outsider', None, True), ('recovery', 'sales', True),
            ('mfa_revocation', 'admin', True), ('ui_enroll', 'admin', True))}
        for account in accounts.values():
            self.sign_in(account)
        self.passed_check('Real local Auth password sessions established for all fixture identities')

        status, rows, _ = self.request('GET', '/rest/v1/staff_members?select=*')
        check(status in (401, 403) or (status == 200 and rows == []), 'Anonymous access exposed staff records.')
        for name in ('outsider', 'disabled'):
            rows = self.rows('staff_members?select=*', accounts[name]['access_token'])
            check(rows == [], 'Uninvited or inactive account exposed staff records.')
        self.passed_check('Anonymous, uninvited and inactive accounts cannot read staff records')

        for name in ('admin', 'sales', 'marketing'):
            rows = self.rows('staff_members?select=*', accounts[name]['access_token'])
            check(len(rows) == 1 and rows[0].get('user_id') == accounts[name]['user_id'],
                  'Pre-MFA or nonadmin access crossed membership boundaries.')
        self.passed_check('Own-profile discovery works while cross-member reads are denied at aal1')

        sales = accounts['sales']
        for name in ('sales', 'marketing', 'admin'):
            status, _, _ = self.request('PATCH', '/rest/v1/staff_members?user_id=eq.' + accounts[name]['user_id'],
                                       token=accounts[name]['access_token'], data={'role': 'admin'})
            check(status in (401, 403), 'Direct client role mutation was not denied.')
        self.expect_request('PUT', '/auth/v1/user', token=sales['access_token'],
                            data={'data': {'role': 'admin', 'active': True}}, label='Editable Auth metadata fixture change')
        self.sign_in(sales)
        actual_role, _ = self.expect_request('POST', '/rest/v1/rpc/app_staff_role', token=sales['access_token'], data={},
                                            label='Database role after metadata escalation attempt')
        check(actual_role == 'sales', 'Editable user metadata changed authoritative database permissions.')
        own_after_metadata = self.rows('staff_members?select=*', sales['access_token'])
        check(len(own_after_metadata) == 1 and own_after_metadata[0]['user_id'] == sales['user_id'],
              'Editable Auth metadata escalated cross-member access.')
        body = {'target_user_id': sales['user_id'], 'new_role': 'admin', 'new_active': True, 'new_display_name': 'Unauthorized'}
        for name in ('sales', 'marketing', 'admin', 'outsider', 'disabled'):
            status, _, _ = self.request('POST', '/rest/v1/rpc/update_staff_member', token=accounts[name]['access_token'], data=body)
            check(status in (401, 403), 'Role RPC accepted a nonadministrator or pre-MFA caller.')
        self.passed_check('Direct role writes, editable Auth metadata escalation and pre-MFA administrator mutations are denied')

        admin = accounts['admin']
        self.enroll_admin(admin)
        data, _ = self.expect_request('POST', '/rest/v1/rpc/app_is_admin', token=admin['access_token'], data={}, label='aal2 administrator discovery')
        check(data is True, 'Verified administrator session was not authorized by the database.')
        all_members = self.rows('staff_members?select=*', admin['access_token'])
        check({a['user_id'] for a in accounts.values() if a['role']} <= {a['user_id'] for a in all_members},
              'aal2 administrator could not read managed staff members.')
        self.passed_check('Real TOTP enrollment and challenge produce database-authorized aal2 administrator session')

        changed_name = 'Local acceptance updated sales'
        self.expect_request('POST', '/rest/v1/rpc/update_staff_member', token=admin['access_token'],
                            data={'target_user_id': sales['user_id'], 'new_role': 'sales', 'new_active': True, 'new_display_name': changed_name},
                            label='Authorized staff change')
        changed = self.rows('staff_members?user_id=eq.' + sales['user_id'], admin=True)
        check(changed[0]['display_name'] == changed_name and changed[0]['role'] == 'sales', 'Authorized staff mutation did not persist.')
        audit = self.rows('audit_log?entity_id=eq.' + sales['user_id'], admin['access_token'])
        check(any(event.get('actor_user_id') == admin['user_id'] for event in audit), 'Authorized staff mutation produced no attributable audit event.')
        self.passed_check('Authorized staff changes persist and create administrator-attributed audit history')

        for token in (sales['access_token'], accounts['marketing']['access_token'], admin['aal1_access_token']):
            rows = self.rows('audit_log?select=*', token)
            check(rows == [], 'Nonadministrator read privileged audit history.')
        status, _, _ = self.request('POST', '/rest/v1/audit_log', token=admin['access_token'],
                                    data={'action': 'forged', 'entity_type': 'staff', 'entity_id': sales['user_id'], 'changes': {}})
        check(status in (401, 403), 'Even an administrator must not forge audit rows directly.')
        status, _, _ = self.request('POST', '/rest/v1/rpc/update_staff_member', token=admin['access_token'],
                                    data={'target_user_id': admin['user_id'], 'new_role': 'sales', 'new_active': False, 'new_display_name': 'Self change'})
        check(status in (400, 401, 403), 'Administrator self-permission mutation was accepted.')
        self.passed_check('Audit writes and administrator self-membership changes are protected')

        revocation_admin = accounts['mfa_revocation']
        captured_admin_token = self.enroll_admin(revocation_admin)
        self.expect_request('DELETE', '/auth/v1/factors/' + revocation_admin['totp_factor_id'],
                            token=captured_admin_token, statuses=(200, 204), label='Real TOTP factor unenrollment')
        revocation_admin['factor_unenrolled'] = True
        revocation_admin['session_aal'] = 'aal1'
        is_admin, _ = self.expect_request('POST', '/rest/v1/rpc/app_is_admin', token=captured_admin_token, data={},
                                         label='Replayed aal2 token after factor removal')
        check(is_admin is False, 'A captured aal2 token retained administrator access after factor removal.')
        rows = self.rows('staff_members?select=*', captured_admin_token)
        check(len(rows) == 1 and rows[0]['user_id'] == revocation_admin['user_id'],
              'Factor removal left cross-member administrator reads available.')
        self.passed_check('Removing a real MFA factor revokes captured aal2 administrator privileges')

        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=')
        object_path = f'acceptance/{self.run_id}/pixel.png'
        storage_path = '/storage/v1/object/staff-media/' + object_path
        self.expect_request('POST', storage_path, token=accounts['marketing']['access_token'], raw=png,
                            headers={'Content-Type': 'image/png', 'x-upsert': 'false'}, statuses=(200, 201), label='Marketing private media upload')
        self.fixture['objects'].append({'bucket': 'staff-media', 'path': object_path, 'sha256': hashlib.sha256(png).hexdigest(),
                                        'base64_body': base64.b64encode(png).decode(), 'owner_user_id': accounts['marketing']['user_id']})
        self.save()
        download = '/storage/v1/object/authenticated/staff-media/' + object_path
        for token in (accounts['marketing']['access_token'], admin['access_token']):
            _, body = self.expect_request('GET', download, token=token, label='Authorized private object read')
            check(hashlib.sha256(body).digest() == hashlib.sha256(png).digest(), 'Private media bytes changed after upload.')
        for token in (None, sales['access_token'], accounts['outsider']['access_token'], accounts['disabled']['access_token'], admin['aal1_access_token']):
            status, _, body = self.request('GET', download, token=token)
            check(status not in (200, 201) and body != png, 'Unauthorized identity read a private media object.')
        status, _, _ = self.request('GET', '/storage/v1/object/public/staff-media/' + object_path)
        check(status != 200, 'Private bucket allowed an anonymous public-object read.')
        status, _, _ = self.request('POST', '/storage/v1/object/staff-media/acceptance/' + self.run_id + '/unsafe.svg',
                                    token=accounts['marketing']['access_token'], raw=b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                                    headers={'Content-Type': 'image/svg+xml', 'x-upsert': 'false'})
        check(status in (400, 415, 422), 'Storage accepted a disallowed executable media type.')
        self.passed_check('Private Storage grants Marketing and aal2 Admin while denying Sales, anonymous and aal1 Admin')

        invited_email = f'invited.{self.run_id}@butterfly.test'
        invitation = {'email': invited_email, 'role': 'sales', 'display_name': 'Local invited sales'}
        origin = {'Origin': 'http://127.0.0.1:5173'}
        for token, allowed in ((None, (401,)), (sales['access_token'], (403,)), (admin['aal1_access_token'], (403,))):
            status, _, _ = self.request('POST', '/functions/v1/invite-staff', token=token, data=invitation, headers=origin)
            check(status in allowed, f'Invitation access gate did not return its required unauthorized outcome (HTTP {status}).')
        status, _, _ = self.request('POST', '/functions/v1/invite-staff', token=admin['access_token'], data=invitation,
                                    headers={'Origin': 'https://untrusted.example.invalid'})
        check(status == 403, 'Invitation function accepted an untrusted browser origin.')
        result, _ = self.expect_request('POST', '/functions/v1/invite-staff', token=admin['access_token'], data=invitation,
                                       headers=origin, statuses=(201,), label='Authorized staff invitation')
        check(result.get('email_sent') is True and bool(result.get('user_id')), 'Invitation did not confirm local email delivery.')
        link = self.find_email_link(invited_email, 'invite')
        invitation_token = self.verify_email_link(link)
        invited_password = 'Invite9!' + secrets.token_urlsafe(24)
        self.expect_request('PUT', '/auth/v1/user', token=invitation_token, data={'password': invited_password}, label='Invited account password setup')
        invited_account = {'user_id': result['user_id'], 'email': invited_email, 'password': invited_password, 'role': 'sales', 'active': True}
        self.fixture['accounts']['invited'] = invited_account
        self.sign_in(invited_account)
        invited_rows = self.rows('staff_members?select=*', invited_account['access_token'])
        check(len(invited_rows) == 1 and invited_rows[0]['role'] == 'sales', 'Invited staff could not establish assigned database membership.')
        self.passed_check('Invitation authorization, local email callback, password setup and invited login work end to end')

        recovery = accounts['recovery']
        self.expect_request('POST', '/auth/v1/recover?redirect_to=' + quote('http://127.0.0.1:5173/staff/', safe=''),
                            data={'email': recovery['email']}, label='Password recovery request')
        reset_token = self.verify_email_link(self.find_email_link(recovery['email'], 'recovery'))
        old_password = recovery['password']
        recovery['password'] = 'Reset9!' + secrets.token_urlsafe(24)
        self.expect_request('PUT', '/auth/v1/user', token=reset_token, data={'password': recovery['password']}, label='Recovered password update')
        status, _, _ = self.request('POST', '/auth/v1/token?grant_type=password', data={'email': recovery['email'], 'password': old_password})
        check(status in (400, 401, 422), 'Old password remained usable after successful recovery.')
        self.sign_in(recovery)
        self.passed_check('Password reset is delivered locally and replaces the old password')

        session, _ = self.expect_request('POST', '/auth/v1/token?grant_type=refresh_token',
                                        data={'refresh_token': recovery['refresh_token']}, label='Real session refresh')
        refreshed_token = session.get('access_token')
        refresh_token = session.get('refresh_token')
        check(bool(refreshed_token and refresh_token), 'Refresh did not return a usable session.')
        self.expect_request('POST', '/auth/v1/logout?scope=global', token=refreshed_token, statuses=(200, 204), label='Real logout')
        status, _, _ = self.request('POST', '/auth/v1/token?grant_type=refresh_token', data={'refresh_token': refresh_token})
        check(status in (400, 401, 403), 'Logged-out refresh token could create another session.')
        check(self.rows('staff_members?select=*', refreshed_token) == [],
              'A captured access token retained data access after logout.')
        role, _ = self.expect_request('POST', '/rest/v1/rpc/app_staff_role', token=refreshed_token, data={}, label='Logged-out token authorization check')
        check(role is None, 'A captured logged-out access token retained a staff role.')
        self.passed_check('Real refresh works; logout invalidates refresh credentials and captured-token data access')

        check(bool(self.jwt_secret), 'Local JWT signing fixture is required to exercise real short-lived token expiry.')
        token_parts = sales['access_token'].split('.')
        payload = json.loads(base64.urlsafe_b64decode(token_parts[1] + '=' * (-len(token_parts[1]) % 4)))
        payload['iat'] = int(time.time())
        payload['exp'] = int(time.time()) + 2
        header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b'=')
        encoded_payload = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).rstrip(b'=')
        signed = header + b'.' + encoded_payload
        short_token = (signed + b'.' + base64.urlsafe_b64encode(hmac.new(self.jwt_secret.encode(), signed, hashlib.sha256).digest()).rstrip(b'=')).decode()
        before = self.rows('staff_members?select=*', short_token)
        check(len(before) == 1, 'Short-lived local JWT was not valid before expiry.')
        time.sleep(3)
        deadline = time.monotonic() + 35
        while True:
            status, _, _ = self.request('GET', '/rest/v1/staff_members?select=*', token=short_token)
            if status == 401 or time.monotonic() >= deadline:
                break
            check(status == 200, 'Expiry check returned an unexpected API failure.')
            # Some JWT verifiers allow clock skew. Test the same genuine token
            # across expiry and bounded skew rather than fabricating a failure.
            time.sleep(1)
        check(status == 401, 'The API accepted a genuinely expired short-lived local JWT.')
        self.passed_check('A valid local JWT expires and is rejected by the actual data API')

        self.expect_request('POST', '/rest/v1/rpc/update_staff_member', token=admin['access_token'],
                            data={'target_user_id': invited_account['user_id'], 'new_role': 'sales', 'new_active': False,
                                  'new_display_name': 'Disabled invited local user'}, label='Deactivate fixture staff member')
        check(self.rows('staff_members?select=*', invited_account['access_token']) == [],
              'Membership deactivation did not deny the still-valid user token.')
        invited_account['active'] = False
        self.passed_check('Live membership deactivation denies data access before JWT expiry')

        # Keep ordinary Sales fixture signed in for subsequent browser and recovery checks.
        self.sign_in(sales)
        self.save()
        return {'local_only': True, 'run_id': self.run_id, 'passed_count': len(self.passed), 'passed': self.passed,
                'fixture_file': str(self.fixture_path), 'retained_for_browser_and_recovery': True,
                'production_backend_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', default='/workspace/.butterfly-private/local-supabase.json')
    parser.add_argument('--fixtures', default='/workspace/.butterfly-private/backend-fixtures.json')
    parser.add_argument('--report', default='/workspace/.butterfly-private/backend-report.json')
    args = parser.parse_args()
    acceptance = None
    try:
        config = json.loads(Path(args.credentials).read_text())
        acceptance = Acceptance(config, args.fixtures)
        private_json(args.report, {'status': 'running', 'run_id': acceptance.run_id, 'local_only': True,
                                   'passed_count': 0, 'production_backend_verified': False})
        report = acceptance.run()
        report['status'] = 'passed'
        private_json(args.report, report)
    except Exception as error:
        # Omit exception payloads for library/fixture errors: they may contain secrets.
        message = str(error) if isinstance(error, CheckFailed) else type(error).__name__ + '; inspect local setup privately.'
        try:
            private_json(args.report, {'status': 'failed', 'run_id': acceptance.run_id if acceptance else None,
                                      'local_only': True, 'passed_count': len(acceptance.passed) if acceptance else 0,
                                      'passed': acceptance.passed if acceptance else [], 'error': message,
                                      'production_backend_verified': False})
        except (CheckFailed, OSError):
            pass
        print('FAIL ' + message, flush=True)
        return 1
    print(json.dumps({'passed_count': report['passed_count'], 'local_only': True, 'production_backend_verified': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
