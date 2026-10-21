#!/usr/bin/env python3
"""Browser acceptance against real local Stage B accounts; no mocked login."""
import argparse
import base64
import hashlib
import hmac
import html
import json
from pathlib import Path
import re
import secrets
import struct
import time
from urllib.parse import urlsplit, urlencode, parse_qs, quote
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect


def totp(secret):
    raw = base64.b32decode(secret.upper() + '=' * (-len(secret) % 8))
    digest = hmac.new(raw, struct.pack('>Q', int(time.time()) // 30), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000).zfill(6)


def local_mail_link(recipient, expected_type):
    """Inspect only the local test mail sink, never a real email account."""
    for _ in range(12):
        with urlopen('http://127.0.0.1:54324/api/v1/search?' + urlencode({'query': 'to:' + recipient}), timeout=5) as response:
            messages = json.load(response).get('messages', [])
        for message in messages:
            with urlopen('http://127.0.0.1:54324/api/v1/message/' + quote(message['ID'], safe=''), timeout=5) as response:
                full = json.load(response)
            text = html.unescape((full.get('HTML') or '') + '\n' + (full.get('Text') or ''))
            for candidate in re.findall(r'https?://[^\s<>"\']+', text):
                parsed = urlsplit(candidate)
                if parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost') and parsed.path == '/auth/v1/verify' and parse_qs(parsed.query).get('type') == [expected_type]:
                    return candidate
        time.sleep(1)
    raise AssertionError('Expected local test email was not captured.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', default='/workspace/.butterfly-private/backend-fixtures.json')
    parser.add_argument('--base', default='http://127.0.0.1:5173/staff/')
    args = parser.parse_args()
    parsed = urlsplit(args.base)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        parser.error('Use the real local preview only.')
    fixtures = json.loads(Path(args.fixtures).read_text())
    accounts = fixtures['accounts']
    passed = []
    hosts = set()
    errors = []

    def record(name):
        passed.append(name)
        print('PASS ' + name, flush=True)

    def sign_out(tab):
        # Logout deliberately replaces the document to discard in-memory tokens.
        # Wait for that navigation before testing reload/persistence.
        with tab.expect_navigation(wait_until='networkidle'):
            tab.get_by_role('button', name='Sign out', exact=True).first.click()

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                    args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(type(error).__name__))
        page.on('request', lambda request: hosts.add(urlsplit(request.url).hostname))
        page.goto(args.base, wait_until='networkidle')
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible()
        assert page.locator('script[src*="facebook"], script[src*="google-analytics"], script[src*="gtag"]').count() == 0
        assert page.locator('form').count() == 1
        record('Private login renders without signup or marketing pixels')

        page.get_by_role('button', name='العربية', exact=True).click()
        expect(page.locator('html')).to_have_attribute('lang', 'ar')
        expect(page.locator('html')).to_have_attribute('dir', 'rtl')
        page.reload(wait_until='networkidle')
        expect(page.locator('html')).to_have_attribute('lang', 'ar')
        page.get_by_role('button', name='English', exact=True).click()
        expect(page.locator('html')).to_have_attribute('dir', 'ltr')
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.keyboard.press('Tab')
        assert page.evaluate("document.activeElement !== document.body")
        record('Arabic/English, RTL, persistence, mobile width and keyboard focus work')

        sales = accounts['sales']
        page.locator('#email').fill(sales['email'])
        page.locator('#password').fill(sales['password'])
        page.get_by_role('button', name='Sign in', exact=False).click()
        expect(page.get_by_role('heading', name='Your access is ready.', exact=True)).to_be_visible(timeout=15000)
        assert page.locator('#invite-email').count() == 0
        expect(page.get_by_text('Sales', exact=True).first).to_be_visible()
        page.reload(wait_until='networkidle')
        expect(page.get_by_role('heading', name='Your access is ready.', exact=True)).to_be_visible(timeout=15000)
        record('Real Sales login persists after reload and exposes no staff management')

        sign_out(page)
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible(timeout=15000)
        page.reload(wait_until='networkidle')
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible()
        record('Logout clears persisted browser access')

        page.locator('#email').fill(sales['email'])
        page.locator('#password').fill(sales['password'])
        page.get_by_role('button', name='Sign in', exact=False).click()
        expect(page.get_by_role('heading', name='Your access is ready.', exact=True)).to_be_visible(timeout=15000)
        page.route('**/auth/v1/logout*', lambda route: route.abort())
        sign_out(page)
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible(timeout=15000)
        assert page.evaluate("localStorage.getItem('butterfly-staff-auth')") is None
        expect(page.get_by_role('alert')).to_contain_text('Server session revocation could not be confirmed')
        page.unroute('**/auth/v1/logout*')
        page.reload(wait_until='networkidle')
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible()
        record('Failed logout transport still clears local access and reports unconfirmed server revocation')

        page.locator('#email').fill(accounts['outsider']['email'])
        page.locator('#password').fill(accounts['outsider']['password'])
        page.get_by_role('button', name='Sign in', exact=False).click()
        expect(page.get_by_role('heading', name='Access unavailable', exact=True)).to_be_visible(timeout=15000)
        assert page.locator('#invite-email').count() == 0
        sign_out(page)
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible(timeout=15000)
        record('A genuine Auth user without staff membership is denied the workspace')

        page.set_viewport_size({'width': 1440, 'height': 1000})
        admin = accounts['admin']
        page.locator('#email').fill(admin['email'])
        page.locator('#password').fill(admin['password'])
        page.get_by_role('button', name='Sign in', exact=False).click()
        expect(page.get_by_role('heading', name='Verify it’s you', exact=True)).to_be_visible(timeout=15000)
        assert page.locator('#invite-email').count() == 0
        # Avoid reusing the TOTP time step already consumed by API enrollment.
        verified_at = admin.get('mfa_verified_at', 0)
        if int(time.time()) // 30 == int(verified_at) // 30:
            time.sleep(31 - (time.time() % 30))
        page.locator('#totp').fill(totp(admin['totp_secret']))
        page.get_by_role('button', name='Verify and continue', exact=False).click()
        expect(page.get_by_role('heading', name='Your team', exact=True)).to_be_visible(timeout=15000)
        expect(page.locator('#invite-email')).to_be_visible()
        expect(page.locator('tbody tr')).not_to_have_count(0)
        record('Real administrator password login stays gated until TOTP verification')
        page.reload(wait_until='networkidle')
        expect(page.get_by_role('heading', name='Your team', exact=True)).to_be_visible(timeout=15000)
        record('Verified administrator session and real staff list persist after reload')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.get_by_role('button', name='العربية', exact=True).click()
        expect(page.get_by_role('heading', name='فريقك', exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        expect(page.locator('#invite-email')).to_be_visible()
        page.get_by_role('button', name='English', exact=True).click()
        page.set_viewport_size({'width': 1440, 'height': 1000})
        record('Authenticated administrator controls support Arabic, RTL and mobile width')

        invited_email = 'browser.' + fixtures['run_id'] + '.' + secrets.token_hex(4) + '@butterfly.test'
        page.locator('#invite-name').fill('Browser invitation acceptance')
        page.locator('#invite-email').fill(invited_email)
        page.locator('#invite-role').select_option('sales')
        page.get_by_role('button', name='Send invitation', exact=False).click()
        expect(page.get_by_role('status')).to_contain_text('Invitation sent', timeout=15000)
        invite_link = local_mail_link(invited_email, 'invite')
        invited_context = browser.new_context()
        invited_page = invited_context.new_page()
        invited_page.on('pageerror', lambda error: errors.append(type(error).__name__))
        invited_page.on('request', lambda request: hosts.add(urlsplit(request.url).hostname))
        invited_page.goto(invite_link, wait_until='networkidle')
        expect(invited_page.get_by_role('heading', name='Choose a password', exact=True)).to_be_visible(timeout=15000)
        invited_password = 'BrowserInvite9!' + secrets.token_urlsafe(20)
        invited_page.locator('#new-password').fill(invited_password)
        invited_page.locator('#confirm-password').fill(invited_password)
        invited_page.get_by_role('button', name='Save password', exact=False).click()
        expect(invited_page.get_by_role('heading', name='Your access is ready.', exact=True)).to_be_visible(timeout=15000)
        assert invited_page.evaluate('location.hash') == ''
        sign_out(invited_page)
        expect(invited_page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible(timeout=15000)
        invited_context.close()
        record('Real administrator UI invitation, CORS, local email callback and initial password setup work')

        # No production/customer records are loaded or included in screenshots.
        screenshot = Path(args.fixtures).parent / 'staff-admin-local.png'
        page.screenshot(path=str(screenshot), full_page=True)
        screenshot.chmod(0o600)
        sign_out(page)
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible(timeout=15000)

        first_mfa = accounts['ui_enroll']
        page.locator('#email').fill(first_mfa['email'])
        page.locator('#password').fill(first_mfa['password'])
        page.get_by_role('button', name='Sign in', exact=False).click()
        expect(page.get_by_role('button', name='Set up authenticator', exact=False)).to_be_visible(timeout=15000)
        with page.expect_response(lambda response: response.request.method == 'POST' and urlsplit(response.url).path == '/auth/v1/factors') as first_enrollment:
            page.get_by_role('button', name='Set up authenticator', exact=False).click()
        first_factor = first_enrollment.value.json()['id']
        expect(page.get_by_role('heading', name='Set up verification', exact=True)).to_be_visible()
        page.wait_for_function("document.querySelector('.qr')?.complete && document.querySelector('.qr')?.naturalWidth > 0")
        page.reload(wait_until='networkidle')
        expect(page.get_by_role('button', name='Set up authenticator', exact=False)).to_be_visible(timeout=15000)
        with page.expect_response(lambda response: response.request.method == 'POST' and urlsplit(response.url).path == '/auth/v1/factors') as second_enrollment, page.expect_response(lambda response: response.request.method == 'DELETE' and urlsplit(response.url).path == '/auth/v1/factors/' + first_factor) as removal:
            page.get_by_role('button', name='Set up authenticator', exact=False).click()
        assert removal.value.ok
        assert second_enrollment.value.json()['id'] != first_factor
        page.wait_for_function("document.querySelector('.qr')?.complete && document.querySelector('.qr')?.naturalWidth > 0")
        setup_secret = page.locator('.recovery-key').inner_text()
        page.locator('#totp').fill(totp(setup_secret))
        page.get_by_role('button', name='Verify and continue', exact=False).click()
        expect(page.get_by_role('heading', name='Your team', exact=True)).to_be_visible(timeout=15000)
        page.reload(wait_until='networkidle')
        expect(page.get_by_role('heading', name='Your team', exact=True)).to_be_visible(timeout=15000)
        record('First administrator MFA enrollment survives abandoned setup with decoded QR and verified access')
        sign_out(page)
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible(timeout=15000)
        page.get_by_role('button', name='Forgot your password?', exact=True).click()
        expect(page.get_by_role('heading', name='Reset your password', exact=True)).to_be_visible()
        page.locator('#email').fill(sales['email'])
        page.get_by_role('button', name='Send reset link', exact=False).click()
        expect(page.get_by_role('status')).to_be_visible(timeout=15000)
        reset_link = local_mail_link(sales['email'], 'recovery')
        page.goto(reset_link, wait_until='networkidle')
        expect(page.get_by_role('heading', name='Choose a password', exact=True)).to_be_visible(timeout=15000)
        replacement_password = 'BrowserRecovery9!' + secrets.token_urlsafe(20)
        page.locator('#new-password').fill(replacement_password)
        page.locator('#confirm-password').fill(replacement_password)
        page.get_by_role('button', name='Save password', exact=False).click()
        expect(page.get_by_role('heading', name='Your access is ready.', exact=True)).to_be_visible(timeout=15000)
        assert page.evaluate('location.hash') == ''
        sales['password'] = replacement_password
        private_path = Path(args.fixtures)
        private_path.write_text(json.dumps(fixtures, indent=2))
        private_path.chmod(0o600)
        sign_out(page)
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible(timeout=15000)
        page.locator('#email').fill(sales['email'])
        page.locator('#password').fill(replacement_password)
        page.get_by_role('button', name='Sign in', exact=False).click()
        expect(page.get_by_role('heading', name='Your access is ready.', exact=True)).to_be_visible(timeout=15000)
        sign_out(page)
        expect(page.get_by_role('heading', name='Staff sign in', exact=True)).to_be_visible(timeout=15000)
        record('Real password reset email, callback, password update and fresh password login work')

        assert not errors
        assert hosts <= {'127.0.0.1', 'localhost', None}
        record('No uncaught JavaScript errors or external tracking/network destinations')
        browser.close()

    report = {'passed_count': len(passed), 'passed': passed, 'local_only': True,
              'mock_authentication': False, 'production_backend_verified': False}
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    try:
        result = main()
    except Exception as error:
        # Browser call logs can contain entered passwords or private token URLs.
        print('FAIL browser acceptance (' + type(error).__name__ + '); inspect the local preview privately.', flush=True)
        result = 1
    raise SystemExit(result)
