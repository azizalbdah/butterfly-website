#!/usr/bin/env python3
"""Real local anonymous intake, CRM permissions, financial history and metrics."""
import argparse
import concurrent.futures
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import secrets
import time
import uuid
from backend_acceptance import Acceptance,CheckFailed,check,private_json

ORIGIN={'Origin':'http://127.0.0.1:8003'}

class CRM(Acceptance):
 def rpc(self,name,body,token=None,statuses=(200,204)):
  return self.expect_request('POST','/rest/v1/rpc/'+name,token=token,data=body,statuses=statuses,label='CRM action '+name)[0]
 def enquiry(self,receipt,token):return self.rows('enquiries?receipt=eq.'+receipt,token)[0]
 def payload(self,phone=None,name='Local CRM acceptance',service='coffee',guests=30,kind='catering',company=''):
  phone=phone or '+9659'+str(secrets.randbelow(10000000)).zfill(7)
  body={'action':'submit','request_key':str(uuid.uuid4()),'kind':kind,'service':service,'catalogue_revision':self.site['catalogue_revision'],
   'customer':{'name':name,'phone':phone,'email':'','company':company},'event_date':'','event_time':'','venue':'Local acceptance venue','notes':'Local integration acceptance '+self.run_id,'website':''}
  if kind=='corporate':body['corporate']={'quantity':50,'interest':'gifting'}
  else:body['selection']={'guests':guests,'hours':4,'min_towers':0,'package_id':None,'extras':{},'savouries':[],'towers':[],'team_select':True,'extra_towers':False,'personalisation':'later','coffee_style':'mixed','tray_style':'butterfly'}
  return body
 def submit(self,body,statuses=(200,201)):
  return self.expect_request('POST','/functions/v1/submit-enquiry',headers=ORIGIN,data=body,statuses=statuses,label='Validated anonymous website submission')[0]
 def assign(self,enquiry,who,admin):
  return self.rpc('assign_enquiry',{'target_id':enquiry['id'],'assignee_id':who,'expected_version':enquiry['version']},admin)
 def update(self,enquiry,token,**changes):
  body={'target_id':enquiry['id'],'expected_version':enquiry['version'],'new_status':enquiry['status'],
   'new_next_action':enquiry['next_action'],'new_follow_up_at':enquiry['follow_up_at'],'new_loss_reason':enquiry['loss_reason'],'change_note':None}
  body.update(changes);return self.rpc('update_enquiry',body,token)
 def run(self):
  accounts={name:self.create_user(name,role,active) for name,role,active in [('admin','admin',True),('sales','sales',True),('sales_other','sales',True),('marketing','marketing',True),('disabled','sales',False),('outsider',None,True),('recovery','sales',True),('ui_enroll','admin',True)]}
  for account in accounts.values():self.sign_in(account)
  self.enroll_admin(accounts['admin']);a=accounts['admin']['access_token'];s=accounts['sales']['access_token'];other=accounts['sales_other']['access_token'];m=accounts['marketing']['access_token']
  self.site=self.rpc('get_published_site',{})
  # Reset only disposable local rate counters; never delete enquiries or people.
  self.expect_request('DELETE','/rest/v1/crm_rate_limits?limit_key=not.is.null',admin=True,statuses=(200,204),label='Reset local acceptance rate counters')
  first=self.payload();receipt=self.submit(first)['receipt'];enquiry=self.enquiry(receipt,a)
  check(enquiry['status']=='new' and enquiry['assigned_to'] is None,'Anonymous submission skipped triage.')
  check(enquiry['price_snapshot']['total_fils']==125000,'Server did not compute the approved 125 KD coffee estimate.')
  check(enquiry['price_snapshot']['catalogue_revision']==self.site['catalogue_revision'],'Published catalogue version was not retained.')
  check('request_key' not in enquiry['request_details'],'Staff-visible request details exposed the submission capability.')
  hospitality=self.payload(service='hospitality');hospitality['selection']['extras']={'canapes':1}
  hospitality_row=self.enquiry(self.submit(hospitality)['receipt'],a)
  check(hospitality_row['price_snapshot']['total_fils']==497000,'Server did not compute 475 + 22 KD hospitality/add-on estimate.')
  self.passed_check('Anonymous intake saves New enquiries with server-calculated immutable published-price snapshots')

  invalid=[]
  value=copy.deepcopy(first);value['request_key']=str(uuid.uuid4());value['total_fils']=1;invalid.append(value)
  value=copy.deepcopy(first);value['request_key']=str(uuid.uuid4());value['assigned_to']=accounts['sales']['user_id'];invalid.append(value)
  value=copy.deepcopy(first);value['request_key']=str(uuid.uuid4());value['customer']['phone']='not-a-phone';invalid.append(value)
  value=copy.deepcopy(first);value['request_key']=str(uuid.uuid4());value['selection']['guests']=401;invalid.append(value)
  value=copy.deepcopy(first);value['request_key']=str(uuid.uuid4());value['selection']['extras']={'unknown':1};invalid.append(value)
  value=copy.deepcopy(first);value['request_key']=str(uuid.uuid4());value['event_date']='2000-01-01';invalid.append(value)
  value=copy.deepcopy(first);value['request_key']=str(uuid.uuid4());value['website']='spam';invalid.append(value)
  for value in invalid:check(self.request('POST','/functions/v1/submit-enquiry',headers=ORIGIN,data=value)[0]==422,'Invalid intake or client-supplied price/assignment was accepted.')
  check(self.request('POST','/functions/v1/submit-enquiry',headers={'Origin':'https://unapproved.invalid'},data=first)[0]==403,'Unapproved public origin was accepted.')
  check(self.request('POST','/functions/v1/submit-enquiry',headers=ORIGIN,raw=b'x'*32769)[0] in (413,415),'Oversized or non-JSON submission was accepted.')
  self.passed_check('Validation rejects forged prices/assignment, invalid contact/dates/choices, bots and unapproved origins')

  duplicate=self.submit(first);check(duplicate['receipt']==receipt and duplicate['duplicate'] is True,'Identical retry created a duplicate enquiry.')
  changed=copy.deepcopy(first);changed['notes']='Different request with the same key'
  check(self.request('POST','/functions/v1/submit-enquiry',headers=ORIGIN,data=changed)[0]==409,'A reused submission key changed an existing enquiry.')
  race=self.payload()
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(self.submit,[race,race]))
  check(results[0]['receipt']==results[1]['receipt'],'Concurrent retries created different enquiries.')
  self.passed_check('Idempotency protects ordinary and simultaneous retries without exposing private records')

  for table in ('enquiries','customers','companies','quotations','bookings','enquiry_activities','enquiry_submissions','crm_rate_limits'):
   check(self.request('GET','/rest/v1/'+table+'?select=*')[0] in (401,403),'Anonymous identity can read private CRM data.')
  for name in ('sales','sales_other','marketing','disabled','outsider'):
   token=accounts[name]['access_token']
   check(self.rows('enquiries?receipt=eq.'+receipt,token)==[],'A non-assignee read an unassigned enquiry.')
   check(self.rows('customers?id=eq.'+enquiry['customer_id'],token)==[],'A non-assignee read customer contact details.')
  check(self.rows('enquiries?receipt=eq.'+receipt,accounts['admin']['aal1_access_token'])==[],'Administrator aal1 can read CRM records.')
  for name in ('admin','sales','marketing'):
   check(self.request('GET','/rest/v1/enquiry_submissions?select=*',token=accounts[name]['access_token'])[0] in (401,403),'Staff can read public submission capabilities.')
  for method,path,data in [('POST','enquiries',{}),('PATCH','enquiries?id=eq.'+enquiry['id'],{'assigned_to':accounts['sales']['user_id']}),('POST','enquiry_activities',{'enquiry_id':enquiry['id'],'event_type':'booking_confirmed','actor_label':'Forged'})]:
   check(self.request(method,'/rest/v1/'+path,token=s,data=data)[0] in (401,403),'A raw client write bypassed CRM actions.')
  self.passed_check('Direct API permissions protect unassigned/customer/company data and hide submission capabilities')

  enquiry=self.assign(enquiry,accounts['sales']['user_id'],a)
  check(len(self.rows('enquiries?id=eq.'+enquiry['id'],s))==1,'Assigned Sales cannot read their enquiry.')
  check(len(self.rows('customers?id=eq.'+enquiry['customer_id'],s))==1,'Assigned Sales cannot read their customer.')
  for token in (other,m,accounts['outsider']['access_token'],accounts['disabled']['access_token'],accounts['admin']['aal1_access_token']):
   check(self.request('POST','/rest/v1/rpc/add_enquiry_note',token=token,data={'target_id':enquiry['id'],'note_text':'Unauthorized note'})[0]==403,'Wrong-role/assignee wrote an enquiry note.')
  check(self.request('POST','/rest/v1/rpc/assign_enquiry',token=s,data={'target_id':enquiry['id'],'assignee_id':accounts['sales_other']['user_id'],'expected_version':enquiry['version']})[0]==403,'Sales reassigned their record.')
  past=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
  enquiry=self.update(enquiry,s,new_status='contacted',new_next_action='Call about the confirmed guest count',new_follow_up_at=past)
  self.rpc('add_enquiry_note',{'target_id':enquiry['id'],'note_text':'Internal <img src=x onerror="window.__crmExecuted=true"> note'},s)
  check(self.request('POST','/rest/v1/rpc/update_enquiry',token=s,data={'target_id':enquiry['id'],'expected_version':1,'new_status':'new'})[0]==409,'A stale staff edit overwrote newer work.')
  check(self.request('POST','/rest/v1/rpc/update_enquiry',token=s,data={'target_id':enquiry['id'],'expected_version':enquiry['version'],'new_status':'lost'})[0]==400,'Lost status did not require a reason.')
  self.passed_check('Assignment boundaries, follow-ups, append-only notes, loss reasons and concurrent edits are enforced')

  open_result=self.submit({'action':'whatsapp_open_requested','request_key':first['request_key']},statuses=(202,))
  check(open_result['message_sent_verified'] is False,'WhatsApp opening claimed a sent message.')
  current=self.enquiry(receipt,a);check(current['status']=='contacted','Opening WhatsApp changed the pipeline stage.')
  check(self.rows('quotations?enquiry_id=eq.'+enquiry['id'],a)==[] and self.rows('bookings?enquiry_id=eq.'+enquiry['id'],a)==[],'WhatsApp opening created a quotation or booking.')
  self.passed_check('WhatsApp opening is a separate activity and never infers message, quotation or booking confirmation')

  quote=self.rpc('record_quotation_sent',{'target_id':enquiry['id'],'quote_reference':'LOCAL-Q-'+self.run_id,'sent_channel':'whatsapp'},s)
  enquiry=self.enquiry(receipt,s)
  check(enquiry['status']=='quotation_sent' and quote['amount_fils']==125000,'Recording an actual quotation lost its price or pipeline state.')
  booking=self.rpc('confirm_booking',{'target_id':enquiry['id'],'booking_reference':'LOCAL-B-'+self.run_id,'expected_version':enquiry['version'],'approved_quote_id':quote['id']},s)
  check(booking['amount_fils']==125000,'Booking did not preserve the issued quotation price.')
  enquiry=self.enquiry(receipt,s);check(enquiry['status']=='confirmed','Explicit booking action did not confirm the enquiry.')
  for table,row in [('enquiries',enquiry),('quotations',quote),('bookings',booking)]:
   snapshot=copy.deepcopy(row['price_snapshot']);snapshot['total_fils']=1
   check(self.request('PATCH','/rest/v1/'+table+'?id=eq.'+row['id'],admin=True,data={'price_snapshot':snapshot})[0] in (400,403),'Even a privileged API credential rewrote a financial snapshot.')
  self.passed_check('Quotation and booking actions are explicit and financial snapshots cannot be rewritten through APIs')

  custom=self.payload(guests=300);custom_row=self.enquiry(self.submit(custom)['receipt'],a);custom_row=self.assign(custom_row,accounts['sales']['user_id'],a)
  check(custom_row['price_snapshot']['total_fils'] is None and custom_row['price_snapshot']['requires_custom_quote'],'Above-capacity request acquired an invented standard price.')
  check(self.request('POST','/rest/v1/rpc/record_quotation_sent',token=s,data={'target_id':custom_row['id'],'quote_reference':'UNAPPROVED','sent_channel':'email'})[0]==403,'Sales priced a tailored request without administrator approval.')
  approved=self.rpc('approve_quotation',{'target_id':custom_row['id'],'quote_reference':'TAILORED-'+self.run_id,'total_fils':200000,'approval_reason':'Local approval of a tailored service'},a)
  self.rpc('record_quotation_sent',{'target_id':custom_row['id'],'quote_reference':approved['reference'],'sent_channel':'email','approved_quote_id':approved['id']},s)
  custom_row=self.enquiry(custom_row['receipt'],s)
  custom_booking=self.rpc('confirm_booking',{'target_id':custom_row['id'],'booking_reference':'TAILORED-B-'+self.run_id,'expected_version':custom_row['version'],'approved_quote_id':approved['id']},s)
  check(custom_booking['amount_fils']==200000,'Tailored booking lost the approved manual snapshot.')
  self.passed_check('Custom quotations require MFA-admin price approval before Sales can issue or confirm them')

  grouping=self.payload(name='Local known contact');one=self.enquiry(self.submit(grouping)['receipt'],a)
  second=copy.deepcopy(grouping);second['request_key']=str(uuid.uuid4());second['notes']='Another related enquiry';two=self.enquiry(self.submit(second)['receipt'],a)
  check(one['customer_id']==two['customer_id'],'Exact named contact did not group related enquiries.')
  different=copy.deepcopy(grouping);different['request_key']=str(uuid.uuid4());different['customer']['name']='Different person sharing a phone';three=self.enquiry(self.submit(different)['receipt'],a)
  check(three['customer_id']!=one['customer_id'],'A shared phone merged unrelated people.')
  unnamed=self.payload(name='');u1=self.enquiry(self.submit(unnamed)['receipt'],a);unnamed['request_key']=str(uuid.uuid4());u2=self.enquiry(self.submit(unnamed)['receipt'],a)
  check(u1['customer_id']!=u2['customer_id'],'Unnamed contacts were automatically merged.')
  corporate=self.payload(kind='corporate',service='corporate',company='Local Company '+self.run_id)
  corp=self.enquiry(self.submit(corporate)['receipt'],a);check(corp['company_id'] is not None,'Corporate enquiry has no company record.')
  company_variant=copy.deepcopy(corporate);company_variant['request_key']=str(uuid.uuid4());company_variant['customer']['company']='Unrelated Company '+self.run_id
  corp_other=self.enquiry(self.submit(company_variant)['receipt'],a);check(corp_other['company_id']!=corp['company_id'],'Unrelated companies sharing a contact were merged.')
  self.passed_check('Exact named contacts group enquiries while shared phones, unnamed people and different companies remain separate')

  customer=self.rows('customers?id=eq.'+enquiry['customer_id'],s)[0]
  updated=self.rpc('update_customer',{'target_id':customer['id'],'expected_version':customer['version'],'new_name':'Checked local CRM customer','new_phone':customer['phone'],'new_email':customer['email'],'verified_contact':True},s)
  check(updated['contact_verified'] is True,'Assigned customer update did not persist.')
  check(self.rows('enquiries?id=eq.'+enquiry['id'],s)[0]['contact_snapshot']==enquiry['contact_snapshot'],'Customer edits rewrote original submitted contact details.')
  company=self.rows('companies?id=eq.'+corp['company_id'],a)[0]
  check(self.request('POST','/rest/v1/rpc/update_company',token=s,data={'target_id':company['id'],'expected_version':company['version'],'new_name':'Unauthorized','new_phone':company['phone'],'new_email':company['email'],'verified_contact':True})[0]==403,'Sales rewrote company-wide contact details.')
  self.rpc('update_company',{'target_id':company['id'],'expected_version':company['version'],'new_name':company['name'],'new_phone':company['phone'],'new_email':company['email'],'verified_contact':True},a)
  self.passed_check('Scoped customer edits preserve submitted history and company-wide changes require administrator MFA')

  # Manual corrections preserve originals and cannot link to an inaccessible person.
  one=self.assign(one,accounts['sales']['user_id'],a);three=self.assign(three,accounts['sales']['user_id'],a)
  check(self.request('POST','/rest/v1/rpc/link_enquiry_customer',token=other,data={'target_id':three['id'],'target_customer_id':one['customer_id'],'expected_version':three['version'],'link_reason':'Denied correction'})[0]==403,'Unassigned Sales corrected a customer link.')
  linked=self.rpc('link_enquiry_customer',{'target_id':three['id'],'target_customer_id':one['customer_id'],'expected_version':three['version'],'link_reason':'Staff checked that both requests concern the same person'},s)
  check(linked['customer_id']==one['customer_id'] and linked['contact_snapshot']==three['contact_snapshot'],'Customer correction changed the original contact snapshot.')
  history=self.rpc('list_customer_activity',{'target_id':one['customer_id']},s)
  check(any(item['event_type']=='customer_linked' for item in history),'Customer history omitted the manual correction.')
  check(self.rpc('list_customer_activity',{'target_id':one['customer_id']},other)==[],'Customer activity RPC bypassed assignee scope.')
  check(self.rpc('list_enquiries',{'search_query':receipt},other)==[],'Search RPC bypassed assignee scope.')
  person=self.rows('customers?id=eq.'+one['customer_id'],a)[0]
  company_person=self.rpc('link_customer_company',{'target_customer_id':person['id'],'target_company_id':company['id'],'expected_version':person['version']},a)
  check(company_person['company_id']==company['id'] and self.enquiry(one['receipt'],a)['company_id']==company['id'],'Administrator company linking did not update related enquiries.')
  self.passed_check('Manual customer/company corrections preserve originals and scoped search/history APIs deny other assignees')

  # Confirmed bookings close, cancel and reopen through explicit audited actions.
  custom_row=self.enquiry(custom_row['receipt'],s)
  custom_row=self.update(custom_row,s,new_status='completed')
  check(self.rows('bookings?id=eq.'+custom_booking['id'],s)[0]['status']=='completed','Completing work did not complete its booking.')
  check(self.request('POST','/rest/v1/rpc/update_enquiry',token=s,data={'target_id':custom_row['id'],'expected_version':custom_row['version'],'new_status':'confirmed','change_note':'Denied Sales reopening'})[0] in (400,403),'Sales reopened completed work.')
  custom_row=self.update(custom_row,a,new_status='confirmed',change_note='Administrator verified work needs reopening')
  custom_row=self.update(custom_row,s,new_status='lost',new_loss_reason='Customer cancelled the confirmed service')
  check(self.rows('bookings?id=eq.'+custom_booking['id'],s)[0]['status']=='cancelled','Cancelling a confirmed enquiry left its booking active.')
  self.passed_check('Completion, administrator reopening and cancellation update booking state without repricing history')

  # Publish a new price, verify new capture uses it, then restore the approved baseline.
  head=self.rows('site_document_heads?kind=eq.catalogue',a)[0];changed_catalogue=copy.deepcopy(self.site['catalogue']);changed_catalogue['coffeePackages'][0]['price']=135
  self.rpc('save_site_draft',{'document_kind':'catalogue','new_payload':changed_catalogue,'expected_draft_id':head['draft_id']},a)
  head=self.rows('site_document_heads?kind=eq.catalogue',a)[0]
  self.rpc('publish_site_document',{'document_kind':'catalogue','revision_id':head['draft_id'],'expected_published_id':head['published_id']},a)
  check(self.submit(first)['receipt']==receipt,'A saved request could not retry after catalogue publication.')
  stale=self.payload();check(self.request('POST','/functions/v1/submit-enquiry',headers=ORIGIN,data=stale)[0]==409,'Stale catalogue input silently acquired a new price.')
  self.site=self.rpc('get_published_site',{});new_price=self.enquiry(self.submit(self.payload())['receipt'],a)
  check(new_price['price_snapshot']['total_fils']==135000,'New enquiry did not use the authoritative new price.')
  check(self.rows('bookings?id=eq.'+booking['id'],a)[0]['amount_fils']==125000,'Publishing recalculated an existing booking.')
  head=self.rows('site_document_heads?kind=eq.catalogue',a)[0];baseline=json.loads((Path(__file__).resolve().parents[1]/'assets/catalogue-baseline.json').read_text())
  self.rpc('save_site_draft',{'document_kind':'catalogue','new_payload':baseline,'expected_draft_id':head['draft_id']},a)
  head=self.rows('site_document_heads?kind=eq.catalogue',a)[0];self.rpc('publish_site_document',{'document_kind':'catalogue','revision_id':head['draft_id'],'expected_published_id':head['published_id']},a)
  self.site=self.rpc('get_published_site',{})
  self.passed_check('Catalogue publication affects new requests only; stale submissions reject and old enquiries/quotes/bookings retain their prices')

  # Database metrics are compared with actual visible records and Kuwait dates.
  overview=self.rpc('get_crm_overview',{},a);rows=self.rows('enquiries?select=id,status,follow_up_at',a);quotes=self.rows('quotations?select=sent_at',a);bookings=self.rows('bookings?select=status',a)
  check(overview['received']==len(rows),'Overview received count is not based on real records.')
  check(overview['quotations_sent']==sum(q['sent_at'] is not None for q in quotes),'Overview quotation count is not based on sent records.')
  check(overview['confirmed_bookings']==sum(b['status'] in ('confirmed','completed') for b in bookings),'Overview booking count is not based on confirmed bookings.')
  check(sum(overview['pipeline'].values())==overview['received'],'Pipeline counts disagree with stored enquiries.')
  empty=self.rpc('get_crm_overview',{'date_from':'2000-01-01','date_to':'2000-01-02'},a)
  check(empty['received']==empty['overdue']==empty['quotations_sent']==empty['confirmed_bookings']==0,'Empty date range showed invented metrics.')
  check(self.request('POST','/rest/v1/rpc/get_crm_overview',token=m,data={})[0]==403,'Marketing can view CRM metrics.')
  self.passed_check('Actual overview, pipeline and date-filtered empty states agree with stored enquiries, quotations and bookings')
  boundary=[]
  for stamp in ('2001-01-01T20:59:59Z','2001-01-01T21:00:00Z'):
   value=self.enquiry(self.submit(self.payload())['receipt'],a);boundary.append(value)
   self.expect_request('PATCH','/rest/v1/enquiries?id=eq.'+value['id'],admin=True,data={'created_at':stamp},statuses=(200,204),label='Set isolated local Kuwait boundary fixture')
  for day,row in (('2001-01-01',boundary[0]),('2001-01-02',boundary[1])):
   counts=self.rpc('get_crm_overview',{'date_from':day,'date_to':day},a)
   listed=self.rpc('list_enquiries',{'date_from':day,'date_to':day},a)
   check(counts['received']==1 and len(listed)==1 and listed[0]['id']==row['id'],'Metrics/list date filters use UTC instead of Kuwait midnight.')
  self.passed_check('Kuwait midnight boundaries are inclusive/exclusive consistently in real overview and enquiry searches')


  # Contact limit is tested under real parallel transactions.
  rate=self.payload();requests=[]
  for i in range(4):item=copy.deepcopy(rate);item['request_key']=str(uuid.uuid4());item['notes']='Concurrent rate probe '+str(i);requests.append(item)
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
   statuses=list(pool.map(lambda body:self.request('POST','/functions/v1/submit-enquiry',headers=ORIGIN,data=body)[0],requests))
  check(statuses.count(201)==3 and statuses.count(429)==1,'Concurrent contact submissions bypassed the real rate limit.')
  bucket='all:'+str(int(time.time())//60)
  self.expect_request('POST','/rest/v1/crm_rate_limits?on_conflict=limit_key',admin=True,data={'limit_key':bucket,'request_count':40,'expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()},headers={'Prefer':'resolution=merge-duplicates'},statuses=(200,201),label='Prepare isolated global-limit fixture')
  check(self.request('POST','/functions/v1/submit-enquiry',headers=ORIGIN,data=self.payload())[0]==429,'Global submission budget was bypassed.')
  self.expect_request('DELETE','/rest/v1/crm_rate_limits?limit_key=not.is.null',admin=True,statuses=(200,204),label='Release local acceptance rate budget')
  self.passed_check('Atomic contact and global budgets limit anonymous submissions, including concurrent requests')

  # Reassignment immediately removes the previous Sales token's access.
  moved=self.assign(hospitality_row,accounts['sales']['user_id'],a);moved=self.assign(moved,accounts['sales_other']['user_id'],a)
  check(self.rows('enquiries?id=eq.'+moved['id'],s)==[] and len(self.rows('enquiries?id=eq.'+moved['id'],other))==1,'Reassignment did not move access immediately.')
  self.fixture['crm']={'receipt':receipt,'assigned_enquiry':enquiry['id'],'other_enquiry':moved['id'],'custom_receipt':custom_row['receipt'],
   'quotation_id':quote['id'],'booking_id':booking['id'],'booking_amount_fils':125000,'company_id':corp['company_id'],
   'catalogue_revision_at_capture':enquiry['catalogue_revision'],'submission_key':first['request_key']}
  self.save()
  self.passed_check('Reassignment revokes old access immediately and retains recovery fixtures without deleting later records')
  return {'status':'passed','passed_count':len(self.passed),'passed':self.passed,'local_only':True,'production_deployed':False}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--credentials',default='/workspace/.butterfly-private/local-supabase.json');parser.add_argument('--fixtures',default='/workspace/.butterfly-private/crm-fixtures.json');parser.add_argument('--report',default='/workspace/.butterfly-private/crm-report.json');args=parser.parse_args()
 suite=CRM(json.loads(Path(args.credentials).read_text()),args.fixtures);private_json(args.report,{'status':'running','passed_count':0,'local_only':True})
 try:report=suite.run()
 except Exception as error:
  message=str(error) if isinstance(error,CheckFailed) else type(error).__name__+'; inspect the local setup privately.'
  private_json(args.report,{'status':'failed','passed_count':len(suite.passed),'passed':suite.passed,'error':message,'local_only':True});print('FAIL '+message);return 1
 private_json(args.report,report);print('PASS '+str(report['passed_count'])+' CRM API acceptance groups');return 0

if __name__=='__main__':raise SystemExit(main())
