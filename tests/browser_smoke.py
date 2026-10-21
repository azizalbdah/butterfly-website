import argparse
import json
from urllib.parse import urlsplit, parse_qs
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description='Exercise the restored public baseline locally.')
parser.add_argument('--port', type=int, default=8001)
args = parser.parse_args()
if not 1 <= args.port <= 65535:
    parser.error('Port must be between 1 and 65535.')
BASE = f'http://127.0.0.1:{args.port}'
results = []
missing = set()
errors = []

def passed(name):
    results.append(name)
    print('PASS', name, flush=True)

def setup_page(context):
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('response', lambda response: missing.add(urlsplit(response.url).path)
            if response.status >= 400 and response.url.startswith(BASE) else None)
    page.add_init_script("window.__opened = []; window.open = (url) => { window.__opened.push(url); return null; };")
    return page

def language(page, code):
    if page.locator('#langBtn').count():
        if page.locator('html').get_attribute('lang') != code:
            page.locator('#langBtn').click()
    else:
        page.locator(f'[data-lang={code}]').click()
    expect(page.locator('html')).to_have_attribute('lang', code)
    expect(page.locator('html')).to_have_attribute('dir', 'rtl' if code == 'ar' else 'ltr')

def start_catering(page, service, guests):
    page.goto(BASE + '/catering.html', wait_until='load')
    language(page, 'en')
    page.locator(f'label.service-card:has(#service-{service})').click()
    page.locator('#serviceNext').click()
    expect(page.locator('#guestStep h2')).to_be_focused()
    page.locator('#guestCount').fill(str(guests))
    page.locator('#guestNext').click()
    expect(page.locator('#packages h2')).to_be_focused()

def prepared_message(page):
    href = page.locator('#formStatus a').get_attribute('href')
    opened = page.evaluate('window.__opened')
    assert opened == [href], opened
    parsed = urlsplit(href)
    assert parsed.netloc == 'wa.me' and parsed.path == '/96566363741', href
    return parse_qs(parsed.query)['text'][0]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
    # Keep smoke checks local: suppress optional analytics, external fonts, and outbound navigation.
    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(BASE + '/') else route.abort())
    page = setup_page(context)
    for path in ('/', '/business.html', '/catering.html', '/links.html'):
        response = page.goto(BASE + path, wait_until='load')
        assert response.status == 200
        expect(page.locator('h1')).to_be_visible()
        for image in page.locator('img').all():
            if image.is_visible():
                image.scroll_into_view_if_needed()
        page.wait_for_function("Array.from(document.images).every(img => img.complete && img.naturalWidth > 0)")
        language(page, 'ar')
        language(page, 'en')
        page.reload(wait_until='load')
        expect(page.locator('html')).to_have_attribute('lang', 'en')
        passed(path + ': render, images, EN/AR and persisted language')

    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(BASE + '/', wait_until='load')
    page.locator('#menuBtn').click()
    expect(page.locator('#menuBtn')).to_have_attribute('aria-expanded', 'true')
    expect(page.locator('#drawer')).to_have_attribute('aria-hidden', 'false')
    page.keyboard.press('Escape')
    expect(page.locator('#menuBtn')).to_have_attribute('aria-expanded', 'false')
    passed('Homepage mobile menu opens and closes with Escape')

    page.goto(BASE + '/links.html', wait_until='load')
    page.locator('.menu-btn').click()
    expect(page.locator('.menu-btn')).to_have_attribute('aria-expanded', 'true')
    assert not page.locator('.mobile-nav').evaluate('(nav) => nav.inert')
    page.keyboard.press('Escape')
    expect(page.locator('.menu-btn')).to_have_attribute('aria-expanded', 'false')
    assert page.locator('.mobile-nav').evaluate('(nav) => nav.inert')
    passed('Links mobile menu toggles inert state and closes with Escape')

    page.set_viewport_size({'width': 1440, 'height': 900})
    start_catering(page, 'coffee', 30)
    expect(page.locator('#summaryName')).to_have_text('Coffee Reception')
    expect(page.locator('#summaryPrice')).to_have_text('125 KD')
    expect(page.locator('[data-package=coffee30]')).to_have_attribute('aria-pressed', 'true')
    page.locator('#venue').fill('Environment smoke check venue')
    page.locator('#submitQuote').click()
    message = prepared_message(page)
    assert 'Service: Coffee station only' in message and 'Guests: 30' in message and '125 KD' in message, message
    passed('Coffee wizard, focus movement, 125 KD estimate and WhatsApp draft (captured locally)')

    start_catering(page, 'hospitality', 30)
    expect(page.locator('#summaryName')).to_have_text('Signature Reception')
    expect(page.locator('#summaryPrice')).to_have_text('475 KD')
    page.locator('[data-adjust=canapes][data-delta="1"]').click()
    expect(page.locator('#summaryPrice')).to_have_text('497 KD')
    page.locator('#venue').fill('Environment smoke check venue')
    page.locator('#submitQuote').click()
    message = prepared_message(page)
    assert '497 KD' in message and 'Assorted savouries' in message, message
    passed('Hospitality wizard, 475 KD base, 22 KD addon and 497 KD enquiry draft')

    start_catering(page, 'coffee', 201)
    expect(page.locator('#customSection')).to_be_visible()
    expect(page.locator('#includedSection')).to_be_hidden()
    passed('Coffee over 200 guests uses custom quotation')
    page.locator('#editGuests').click()
    for value in ('0', '401'):
        page.locator('#guestCount').fill(value)
        expect(page.locator('#guestNext')).to_be_disabled()
        expect(page.locator('#guestError')).to_be_visible()
    passed('Invalid guest counts 0 and 401 prevent progression')

    start_catering(page, 'wedding', 300)
    expect(page.locator('#customSection')).to_be_visible()
    expect(page.locator('#occasion')).to_have_value('wedding')
    expect(page.locator('#occasion')).to_be_disabled()
    passed('Wedding with 300 guests requests a tailored proposal')

    page.goto(BASE + '/business.html', wait_until='load')
    language(page, 'en')
    page.locator('#businessForm button[type=submit]').click()
    assert page.evaluate('window.__opened') == []
    assert page.locator('#formStatus a').count() == 0
    page.locator('#company').fill('Environment smoke check company')
    page.locator('#contact').fill('Environment smoke check contact')
    page.locator('#quantity').fill('50')
    page.locator('#interest').select_option('gifting')
    page.locator('#businessForm button[type=submit]').click()
    message = prepared_message(page)
    assert 'Environment smoke check company' in message and 'Estimated quantity: 50' in message, message
    passed('Corporate form rejects missing fields and prepares expected WhatsApp draft')

    assert not errors, errors
    passed('No uncaught JavaScript errors')
    browser.close()

report = {'passed': results, 'expected_fallback_404s': sorted(missing), 'uncaught_js_errors': errors}
print(json.dumps(report, indent=2), flush=True)
print(json.dumps({'passed_groups': len(results), 'fallback_404s': len(missing)}), flush=True)
