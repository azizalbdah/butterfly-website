#!/usr/bin/env python3
"""Genuine public submission to private staff workflow; no outbound messages."""
import argparse
from datetime import datetime,timedelta
import json
from pathlib import Path
import secrets
import sys
import time
import traceback
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright,expect
from backend_acceptance import check,private_json,totp

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--fixtures',default='/workspace/.butterfly-private/crm-fixtures.json')
 parser.add_argument('--report',default='/workspace/.butterfly-private/crm-browser-report.json')
 parser.add_argument('--public-base',default='http://127.0.0.1:8003')
 parser.add_argument('--staff-base',default='http://127.0.0.1:5173/staff/')
 args=parser.parse_args()
 for value in (args.public_base,args.staff_base):check(urlsplit(value).hostname in ('localhost','127.0.0.1'),'Use local acceptance endpoints only.')
 fixtures=json.loads(Path(args.fixtures).read_text());accounts=fixtures['accounts'];passed=[];errors=[];private_hosts=set();public_auth=[]
 private_json(args.report,{'status':'running','passed_count':0,'local_only':True})
 def record(name):passed.append(name);print('PASS '+name,flush=True)
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
   public_context=browser.new_context(viewport={'width':1280,'height':900},timezone_id='UTC',reduced_motion='reduce')
   public_context.route('**/*',lambda route:route.continue_() if urlsplit(route.request.url).hostname in ('localhost','127.0.0.1') else route.abort())
   public_context.add_init_script("window.__opened=[];window.open=(url)=>{window.__opened.push(url);return null;};")
   public=public_context.new_page();public.on('pageerror',lambda error:errors.append(type(error).__name__))
   public.on('request',lambda request:public_auth.append(urlsplit(request.url).path) if '/auth/v1/' in request.url else None)
   public.goto(args.public_base+'/catering.html',wait_until='networkidle');public.wait_for_function('Boolean(window.ButterflyCalculator)')
   public.locator('[data-lang=en]').click();public.locator('#service-coffee').check();public.locator('#serviceNext').click();public.locator('#guestCount').fill('30');public.locator('#guestNext').click()
   public.locator('#venue').fill('Local browser venue');name='Local browser customer '+secrets.token_hex(4);public.locator('#contactName').fill(name)
   phone='+9659'+str(secrets.randbelow(10000000)).zfill(7);public.locator('#enquiryPhone').fill(phone)
   check(public.locator('input[type=password]').count()==0,'Public customer journey requires a login.')
   public.locator('#saveEnquiry').click();saved=public.locator('[data-receipt]');expect(saved).to_be_visible(timeout=20000);receipt=saved.get_attribute('data-receipt')
   check(public.evaluate('window.__opened.length')==0,'Saving automatically opened WhatsApp.')
   expect(public.locator('#formStatus')).to_contain_text('not a confirmed booking')
   public.locator('#saveEnquiry').click();expect(saved).to_have_attribute('data-receipt',receipt,timeout=20000)
   record('Public coffee enquiry saves without login, confirms its receipt and retries without opening WhatsApp')
   public.locator('#openEnquiryWhatsApp').click();check(public.evaluate('window.__opened.length')==1,'The optional WhatsApp action did not open the prepared link.')
   record('WhatsApp is an explicit separate step and public saving makes no booking claim')
   public.goto(args.public_base+'/business.html',wait_until='networkidle')
   public.locator('[data-lang=en]').click();company='Local browser company '+secrets.token_hex(4)
   public.locator('#company').fill(company);public.locator('#contact').fill('Local corporate contact');public.locator('#quantity').fill('25');public.locator('#interest').select_option('gifting');public.locator('#enquiryPhone').fill('+9659'+str(secrets.randbelow(10000000)).zfill(7))
   public.locator('#saveEnquiry').click();expect(public.locator('[data-receipt]')).to_be_visible(timeout=20000);corporate_receipt=public.locator('[data-receipt]').get_attribute('data-receipt')
   check(not public_auth,'Public submissions called an authentication endpoint.')
   record('Corporate public form saves validated company/contact enquiries through the genuine backend')

   context=browser.new_context(viewport={'width':1440,'height':1050},timezone_id='UTC',reduced_motion='reduce')
   context.on('request',lambda request:private_hosts.add(urlsplit(request.url).hostname))
   page=context.new_page();page.on('pageerror',lambda error:errors.append(type(error).__name__))
   def login(account,admin=False):
    page.goto(args.staff_base,wait_until='networkidle');page.locator('#email').fill(account['email']);page.locator('#password').fill(account['password']);page.get_by_role('button',name='Sign in',exact=False).click()
    if admin:
     expect(page.locator('#totp')).to_be_visible(timeout=15000)
     # Always use a fresh time step after API or previous browser verification.
     time.sleep(30-(time.time()%30)+.3)
     page.locator('#totp').fill(totp(account['totp_secret']));page.get_by_role('button',name='Verify and continue',exact=False).click()
    expect(page.get_by_role('heading',name='Overview',exact=True)).to_be_visible(timeout=20000);expect(page.locator('.metric-card strong')).to_have_count(4,timeout=20000)
   def logout():
    with page.expect_navigation(wait_until='networkidle'):page.get_by_role('button',name='Sign out',exact=True).click()
   def open_enquiry(reference):
    if page.locator('#nav-enquiries').get_attribute('aria-current')!='page':page.locator('#nav-enquiries').click()
    expect(page.locator('#crm-search')).to_be_visible(timeout=15000);page.locator('#crm-search').fill(reference);page.get_by_role('button',name='Search',exact=True).click()
    target=page.locator('[data-open-enquiry]').first;expect(target).to_be_visible(timeout=15000);target.click();expect(page.locator('#crm-detail-heading')).to_have_text(reference,timeout=15000)
   def notice(text):expect(page.locator('.crm-notice[role=status]')).to_contain_text(text,timeout=20000)
   login(accounts['admin'],True)
   check(int(page.locator('.metric-card strong').first.inner_text())>0,'Overview did not load actual saved enquiries.')
   page.locator('#crm-date-from').fill('2000-01-01');page.locator('#crm-date-to').fill('2000-01-02');page.get_by_role('button',name='Apply dates',exact=True).click()
   expect(page.get_by_role('heading',name='No enquiries in this date range.',exact=True)).to_be_visible(timeout=15000)
   check(all(value=='0' for value in page.locator('.metric-card strong').all_text_contents()),'Empty range displayed sample metrics.')
   page.get_by_role('button',name='All dates',exact=True).click();expect(page.locator('.metric-card strong').first).not_to_have_text('0',timeout=15000)
   record('Real overview counts and date-filtered empty states render after administrator MFA')
   open_enquiry(receipt);enquiry_id=page.locator('[data-detail-enquiry]').get_attribute('data-detail-enquiry')
   page.locator('#crm-assignee').select_option(accounts['sales']['user_id']);page.get_by_role('button',name='Save assignment',exact=True).click();notice('Assignment updated')
   page.locator('#crm-detail-status').select_option('contacted');page.locator('#crm-next-action').fill('Call to review coffee service')
   due=(datetime.now(ZoneInfo('Asia/Kuwait'))-timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M');page.locator('#crm-follow-up').fill(due)
   page.get_by_role('button',name='Save stage and follow-up',exact=True).click();notice('Enquiry and follow-up updated')
   page.locator('#crm-note').fill('Browser note <img src=x onerror="window.__crmExecuted=true">');page.get_by_role('button',name='Add note',exact=True).click();notice('Internal note added')
   check(page.evaluate('window.__crmExecuted===undefined'),'An internal note executed as HTML.')
   expect(page.locator('.activity-list')).to_contain_text('Browser note <img')
   page.get_by_role('button',name='Table view',exact=True).click();expect(page.locator('.crm-table-wrap')).to_be_visible();page.get_by_role('button',name='Board view',exact=True).click();expect(page.locator('.pipeline-column')).to_have_count(6)
   record('Admin assigns actual enquiries and both pipeline views preserve follow-ups and safe internal notes')
   open_enquiry(corporate_receipt);page.locator('#crm-assignee').select_option(accounts['sales']['user_id']);page.get_by_role('button',name='Save assignment',exact=True).click();notice('Assignment updated')
   logout();login(accounts['sales'])
   check(page.locator('#nav-team,#nav-catalogue,#nav-content').count()==0,'Sales has administrator or Marketing modules.')
   open_enquiry(receipt);check(page.locator('#crm-assignee').count()==0,'Sales has assignment controls.')
   page.locator('#crm-quote-reference').fill('BROWSER-Q-'+secrets.token_hex(5));page.get_by_role('button',name='Record quotation sent',exact=True).click();notice('Quotation recorded as sent')
   page.locator('#crm-booking-reference').fill('BROWSER-B-'+secrets.token_hex(5));page.get_by_role('button',name='Record booking confirmation',exact=True).click();notice('Customer booking confirmation recorded')
   expect(page.locator('[data-detail-enquiry]')).to_contain_text('125 KD')
   expect(page.locator('.activity-list')).to_contain_text('Booking confirmed')
   record('Assigned Sales records quotation sending and booking confirmation as separate priced actions')
   page.locator('#crm-detail-status').select_option('completed');page.get_by_role('button',name='Save stage and follow-up',exact=True).click();notice('Enquiry and follow-up updated')
   open_enquiry(corporate_receipt);page.locator('#crm-detail-status').select_option('lost');page.locator('#crm-loss-reason').fill('Customer chose a later occasion');page.get_by_role('button',name='Save stage and follow-up',exact=True).click();notice('Enquiry and follow-up updated')
   expect(page.locator('[data-detail-enquiry]')).to_contain_text('Customer chose a later occasion')
   record('Completed work and lost enquiries persist with the required loss reason')
   page.locator('#nav-customers').click();expect(page.get_by_role('heading',name='Customer records',exact=True)).to_be_visible(timeout=15000)
   page.locator('#crm-customer-search').fill(name);page.get_by_role('button',name='Search contacts',exact=True).click();row=page.locator('[data-customer]').first;expect(row).to_be_visible(timeout=15000);row.get_by_role('button',name='Open record',exact=True).click()
   expect(page.locator('#crm-profile-name')).to_have_value(name,timeout=15000)
   page.locator('#crm-profile-name').fill(name+' checked');page.get_by_role('button',name='Save contact details',exact=True).click();notice('Contact details updated')
   expect(page.locator('.crm-detail')).to_contain_text(receipt)
   page.get_by_role('button',name='Companies',exact=True).click();page.locator('#crm-customer-search').fill(company);page.get_by_role('button',name='Search contacts',exact=True).click();row=page.locator('[data-customer]').first;expect(row).to_be_visible(timeout=15000);row.get_by_role('button',name='Open record',exact=True).click()
   expect(page.locator('.crm-detail')).to_contain_text(corporate_receipt,timeout=15000);check(page.locator('#crm-profile-name').count()==0,'Sales can edit company-wide details.')
   record('Customer and company records show scoped related enquiries and activity while Sales can maintain assigned contacts')
   page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='العربية',exact=True).click();expect(page.locator('html')).to_have_attribute('dir','rtl')
   check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Arabic CRM overflows the mobile viewport.')
   page.locator('#nav-enquiries').click();expect(page.locator('.pipeline-board')).to_be_visible(timeout=15000);page.keyboard.press('Tab');check(page.evaluate('document.activeElement!==document.body'),'Keyboard focus is unavailable.')
   check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Arabic board overflows the mobile viewport.')
   record('CRM supports Arabic/English, RTL, mobile tables/board and keyboard focus')
   page.get_by_role('button',name='English',exact=True).click();page.set_viewport_size({'width':1440,'height':1050});page.locator('#nav-overview').click();expect(page.locator('.metric-card strong')).to_have_count(4)
   path=Path(args.fixtures).parent/'staff-crm-browser.png';page.screenshot(path=str(path));path.chmod(0o600)
   check(not errors,'Uncaught JavaScript errors occurred.')
   check(private_hosts<={'localhost','127.0.0.1',None},'Private CRM made an external tracking/network request.')
   logout();browser.close();record('No uncaught JavaScript errors, mandatory public login or private-screen tracking requests')
  private_json(args.report,{'status':'passed','passed_count':len(passed),'passed':passed,'local_only':True,'mock_authentication':False,'production_deployed':False});return 0
 except Exception as error:
  line=next((frame.lineno for frame in reversed(traceback.extract_tb(error.__traceback__)) if frame.filename==__file__),None)
  private_json(args.report,{'status':'failed','passed_count':len(passed),'passed':passed,'error_type':type(error).__name__,'failure_line':line,'local_only':True})
  print('FAIL CRM browser acceptance ('+type(error).__name__+'); inspect the local preview privately.',flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
