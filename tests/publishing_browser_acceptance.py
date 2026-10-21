#!/usr/bin/env python3
"""Real private editor and configured anonymous website browser acceptance."""
import argparse
import base64
import json
from pathlib import Path
import secrets
import time
import traceback
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
from backend_acceptance import private_json,check,totp

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--fixtures',default='/workspace/.butterfly-private/publishing-fixtures.json')
 parser.add_argument('--report',default='/workspace/.butterfly-private/publishing-browser-report.json')
 parser.add_argument('--base',default='http://127.0.0.1:5173/staff/')
 parser.add_argument('--public-base',default='http://127.0.0.1:8002')
 args=parser.parse_args()
 for value in (args.base,args.public_base):check(urlsplit(value).hostname in ('127.0.0.1','localhost'),'Browser acceptance requires local endpoints.')
 fixtures=json.loads(Path(args.fixtures).read_text());accounts=fixtures['accounts'];passed=[];errors=[];hosts=set()
 private_json(args.report,{'status':'running','passed_count':0,'local_only':True})
 def record(name):passed.append(name);print('PASS '+name,flush=True)
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
   context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
   context.on('page',lambda page:page.on('pageerror',lambda error:errors.append(type(error).__name__)))
   context.on('request',lambda request:hosts.add(urlsplit(request.url).hostname))
   page=context.new_page()
   def login(account):
    page.goto(args.base,wait_until='networkidle');page.locator('#email').fill(account['email']);page.locator('#password').fill(account['password']);page.get_by_role('button',name='Sign in',exact=False).click()
   def signout():
    with page.expect_navigation(wait_until='networkidle'):page.get_by_role('button',name='Sign out',exact=True).click()
   def save():
    page.get_by_role('button',name='Save draft',exact=True).click();expect(page.get_by_role('status')).to_contain_text('Draft saved',timeout=20000)
   def publish():
    page.get_by_role('button',name='Publish saved draft',exact=True).click();expect(page.get_by_role('status')).to_contain_text('Published.',timeout=20000)
   def module(name):
    page.get_by_role('button',name=name,exact=True).click();expect(page.locator('.editor-fields')).to_be_visible(timeout=20000)
   login(accounts['marketing']);expect(page.get_by_role('heading',name='Website editor',exact=True)).to_be_visible(timeout=20000)
   expect(page.locator('.editor-fields')).to_be_visible(timeout=20000)
   check(page.get_by_role('button',name='Publish saved draft',exact=True).count()==0,'Marketing has publishing controls.')
   check(page.get_by_role('button',name='Packages',exact=True).count()==0,'Marketing has price editor controls.')
   field=fixtures['site_test']['text_field'];marker='Browser draft '+secrets.token_hex(4)+' <img src=x onerror="window.__draftExecuted=true">';arabic='مسودة خاصة للمعاينة'
   page.locator('#'+field+'-en').fill(marker);page.locator('#'+field+'-ar').fill(arabic);save();page.reload(wait_until='networkidle')
   expect(page.locator('#'+field+'-en')).to_have_value(marker,timeout=20000)
   record('Marketing edits both languages and saved drafts persist after a real reload')
   page.get_by_role('button',name='Preview draft',exact=True).click();frame=page.frame_locator('iframe.site-preview')
   expect(frame.locator('[data-site-text="'+field+'"]')).to_have_text(marker)
   check(frame.locator('script,noscript,iframe,object,embed').count()==0,'Draft preview retained executable or tracking elements.')
   check(frame.locator('img[src=x]').count()==0,'Draft text became HTML.')
   check(frame.locator('body').evaluate("el=>getComputedStyle(el).backgroundColor") not in ('rgba(0, 0, 0, 0)','transparent'),'Draft preview CSS did not load.')
   record('Private website preview renders the real layout with safe text and without scripts or tracking')
   page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='العربية',exact=True).click()
   expect(page.locator('html')).to_have_attribute('dir','rtl');expect(page.frame_locator('iframe.site-preview').locator('html')).to_have_attribute('dir','rtl')
   check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Arabic editor overflows mobile width.')
   page.get_by_role('button',name='English',exact=True).click();page.set_viewport_size({'width':1440,'height':1000})
   record('Editor and draft preview support Arabic/English, RTL and mobile width')
   signout();login(accounts['admin']);expect(page.locator('#totp')).to_be_visible(timeout=15000)
   verified=accounts['admin'].get('mfa_verified_at',0)
   if int(time.time())//30==int(verified)//30:time.sleep(31-time.time()%30)
   page.locator('#totp').fill(totp(accounts['admin']['totp_secret']));page.get_by_role('button',name='Verify and continue',exact=False).click()
   expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible(timeout=15000)
   module('Packages');page.locator('#coffeePackages-coffee30-price').fill('135');save()
   public_context=browser.new_context(reduced_motion='reduce')
   public_context.route('**/*',lambda route:route.continue_() if urlsplit(route.request.url).hostname in ('127.0.0.1','localhost') else route.abort())
   public=public_context.new_page();public.on('pageerror',lambda error:errors.append(type(error).__name__))
   def coffee_total():
    public.goto(args.public_base+'/catering.html',wait_until='networkidle');public.wait_for_function('Boolean(window.ButterflyCalculator)');return public.evaluate("ButterflyCalculator.model.recommendCoffee(30).total")
   check(coffee_total()==125,'Unpublished package draft changed public calculator prices.')
   public.locator('[data-lang=en]').click();expect(public).to_have_title('Butterfly Catering | Hospitality, weddings & coffee')
   public.locator('[data-lang=ar]').click();expect(public).to_have_title('كيترنق بترفلاي | ضيافة وأعراس وقهوة')
   public.locator('[data-lang=en]').click()
   publish();check(coffee_total()==135,'Public calculator did not receive the published catalogue price.')
   record('Admin package draft stays private until publication updates the configured public calculator')
   module('Website editor');expect(page.locator('#'+field+'-en')).to_have_value(marker)
   publish();public.goto(args.public_base+'/',wait_until='networkidle');public.wait_for_function('Boolean(window.ButterflyPublished.snapshot)')
   if public.locator('html').get_attribute('lang')!='en':public.locator('#langBtn').click()
   expect(public.locator('[data-site-text="'+field+'"]')).to_have_text(marker)
   check(public.evaluate('window.__draftExecuted===undefined'),'Published text executed as HTML.')
   public.locator('#langBtn').click();expect(public.locator('[data-site-text="'+field+'"]')).to_have_text(arabic)
   record('Admin content publication reaches anonymous visitors in both languages without executing markup')
   image=fixtures['site_test']['image_field']
   png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')
   page.locator('#'+image+'-upload').set_input_files({'name':'browser-photo.png','mimeType':'image/png','buffer':png})
   expect(page.get_by_role('status')).to_contain_text('Photo uploaded privately',timeout=20000);save();publish()
   public.reload(wait_until='networkidle');public.wait_for_function('Boolean(window.ButterflyPublished.snapshot)')
   public_photo=public.locator('[data-site-image="'+image+'"]');expect(public_photo).to_have_attribute('src',__import__('re').compile(r'/functions/v1/site-media\?name='))
   public_photo.scroll_into_view_if_needed();public_photo.evaluate('(img)=>img.complete&&img.naturalWidth>0 || new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;})')
   record('Real browser photo upload stays private until publication serves the verified image bytes')
   # Restore via normal version history, preserving every intervening revision.
   page.get_by_text('Version history',exact=True).click();page.locator('#history-version').select_option('10000000-0000-4000-8000-000000000003')
   page.get_by_role('button',name='Use version as a new draft',exact=True).click();expect(page.get_by_role('status')).to_contain_text('Version loaded',timeout=15000);save();publish()
   module('Packages');page.get_by_text('Version history',exact=True).click();page.locator('#history-version').select_option('10000000-0000-4000-8000-000000000002')
   page.get_by_role('button',name='Use version as a new draft',exact=True).click();expect(page.get_by_role('status')).to_contain_text('Version loaded',timeout=15000);save();publish();check(coffee_total()==125,'Version-history restore did not restore the approved package price.')
   record('Version history restores content and prices through new audited drafts and publications')
   module('Website editor');page.get_by_role('button',name='Preview draft',exact=True).click()
   page.screenshot(path=str(Path(args.fixtures).parent/'staff-editor-local.png'),full_page=True);(Path(args.fixtures).parent/'staff-editor-local.png').chmod(0o600)
   check(not errors,'Uncaught JavaScript errors occurred in the editor or public pages.')
   check(hosts<={'127.0.0.1','localhost',None},'Private editor made an external network request.')
   record('No uncaught JavaScript errors or external private-screen tracking requests')
   signout();browser.close()
  report={'status':'passed','passed_count':len(passed),'passed':passed,'local_only':True,'mock_authentication':False,'production_deployed':False};private_json(args.report,report);return 0
 except Exception as error:
  # Playwright call logs can contain account passwords and callback tokens.
  private_json(args.report,{'status':'failed','passed_count':len(passed),'passed':passed,'error_type':type(error).__name__,'failure_line':next((frame.lineno for frame in reversed(traceback.extract_tb(error.__traceback__)) if frame.filename==__file__),None),'local_only':True})
  print('FAIL publishing browser acceptance ('+type(error).__name__+'); inspect the preview privately.',flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
