#!/usr/bin/env python3
"""Real local publishing APIs, media isolation and concurrent editing boundaries."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import secrets
import uuid
from backend_acceptance import Acceptance,CheckFailed,check,private_json

ROOT=Path(__file__).resolve().parents[1]
ORIGIN={'Origin':'http://127.0.0.1:5173'}

class Publishing(Acceptance):
 def rpc(self,name,body,token=None,statuses=(200,)):
  return self.expect_request('POST','/rest/v1/rpc/'+name,token=token,data=body,statuses=statuses,label='Publishing RPC '+name)[0]
 def head(self,kind,token):return self.rows('site_document_heads?kind=eq.'+kind,token)[0]
 def save_draft(self,kind,payload,token,head=None):
  head=head or self.head(kind,token)
  return self.rpc('save_site_draft',{'document_kind':kind,'new_payload':payload,'expected_draft_id':head['draft_id']},token)
 def publish(self,kind,token,head=None):
  head=head or self.head(kind,token)
  return self.expect_request('POST','/functions/v1/publish-site',token=token,headers=ORIGIN,
   data={'document_kind':kind,'revision_id':head['draft_id'],'expected_published_id':head['published_id']},label='Real publication function')[0]
 def run(self):
  accounts={name:self.create_user(name,role,active) for name,role,active in [('admin','admin',True),('marketing','marketing',True),('sales','sales',True),('disabled','marketing',False),('outsider',None,True)]}
  for account in accounts.values():self.sign_in(account)
  admin=accounts['admin'];self.enroll_admin(admin);a=admin['access_token'];m=accounts['marketing']['access_token'];s=accounts['sales']['access_token']
  baseline=json.loads((ROOT/'assets/content-baseline.json').read_text());catalogue=json.loads((ROOT/'assets/catalogue-baseline.json').read_text())
  # Tests operate on this local development publication only; reset through normal
  # append-only save/publish APIs so a previous failed run remains recoverable.
  published=self.rpc('get_published_site',{})
  for kind,payload in [('content',baseline['content']),('catalogue',catalogue)]:
   if published[kind]!=payload:self.save_draft(kind,payload,a);self.publish(kind,a)
  published=self.rpc('get_published_site',{})
  check(published['content']==baseline['content'] and published['catalogue']==catalogue,'Imported public content/catalogue differ from the preserved release.')
  check(len(self.rows('site_field_definitions?select=id',m))==len(baseline['definitions']),'Not all designated fields were imported.')
  self.passed_check('Preserved bilingual content, photos, links, SEO and package catalogue are imported exactly')

  for table in ('site_revisions','site_document_heads','site_field_definitions','site_templates','site_published_media'):
   status,_,_=self.request('GET','/rest/v1/'+table+'?select=*')
   check(status in (401,403),'Anonymous direct table access was permitted: '+table)
  check(self.rows('site_revisions?select=id',s)==[],'Sales can read private revision history.')
  check(self.rows('site_document_heads?select=kind',m)==[{'kind':'content'}],'Marketing can read package draft heads.')
  for token in (None,s,accounts['disabled']['access_token'],accounts['outsider']['access_token'],admin['aal1_access_token']):
   status,_,_=self.request('POST','/rest/v1/rpc/save_site_draft',token=token,data={'document_kind':'content','new_payload':baseline['content'],'expected_draft_id':self.head('content',a)['draft_id']})
   check(status in (401,403),'Unauthorized identity saved a content draft.')
  status,_,_=self.request('POST','/rest/v1/rpc/save_site_draft',token=m,data={'document_kind':'catalogue','new_payload':catalogue,'expected_draft_id':self.head('catalogue',a)['draft_id']})
  check(status==403,'Marketing changed prices.')
  self.passed_check('Anonymous, Sales, inactive, outsider and pre-MFA Admin cannot access private drafts or mutate documents')

  field=next(d for d in baseline['definitions'] if d['kind']=='text' and d['page']=='index')
  image=next(d for d in baseline['definitions'] if d['kind']=='image' and d['page']=='index')
  link=next(d for d in baseline['definitions'] if d['kind']=='link')
  draft=copy.deepcopy(baseline['content']);draft['fields'][field['id']]['en']='Local draft <img src=x onerror="window.__draftExecuted=true">'
  first_head=self.head('content',m);saved=self.save_draft('content',draft,m,first_head)
  check(self.rpc('get_published_site',{})==published,'Saving a draft changed anonymous published content.')
  status,_,_=self.request('POST','/rest/v1/rpc/save_site_draft',token=m,data={'document_kind':'content','new_payload':baseline['content'],'expected_draft_id':first_head['draft_id']})
  check(status==409,'Concurrent edit rejection did not use HTTP 409.')
  check(self.head('content',m)['draft_id']==saved['id'],'Conflict changed the draft pointer.')
  self.passed_check('Marketing drafts remain private and optimistic concurrency prevents lost updates')

  invalid=[]
  value=copy.deepcopy(draft);value['fields'][link['id']]['url']='javascript:alert(1)';invalid.append(('content',value))
  value=copy.deepcopy(draft);del value['fields'][field['id']]['ar'];invalid.append(('content',value))
  value=copy.deepcopy(draft);value['fields']['unknown-field']={'en':'Unknown','ar':'غير معروف'};invalid.append(('content',value))
  value=copy.deepcopy(catalogue);value['rules']['guestBlockPrice']=1;invalid.append(('catalogue',value))
  value=copy.deepcopy(catalogue);value['packages'][0]['max']=0;invalid.append(('catalogue',value))
  value=copy.deepcopy(catalogue);value['coffeePackages'][1]['guests']=1;invalid.append(('catalogue',value))
  value=copy.deepcopy(catalogue);value['addons'][0]['price']=-1;invalid.append(('catalogue',value))
  for kind,value in invalid:
   head=self.head(kind,a)
   status,_,_=self.request('POST','/rest/v1/rpc/save_site_draft',token=a,data={'document_kind':kind,'new_payload':value,'expected_draft_id':head['draft_id']})
   check(status==400,'Invalid content, link, shape, rule or price was saved.')
   check(self.head(kind,a)==head,'Rejected payload changed a document pointer.')
  self.passed_check('Database validation rejects executable links, missing languages, unknown fields, invalid capacities and changed pricing rules')

  for token in (None,s,m,admin['aal1_access_token'],accounts['disabled']['access_token']):
   head=self.head('content',a)
   status,_,_=self.request('POST','/functions/v1/publish-site',token=token,headers=ORIGIN,data={'document_kind':'content','revision_id':head['draft_id'],'expected_published_id':head['published_id']})
   check(status in (401,403),'Unauthorized identity published a document.')
  status,_,_=self.request('POST','/functions/v1/publish-site',token=a,headers={'Origin':'https://unapproved.invalid'},data={})
  check(status==403,'Publisher accepted an unapproved origin.')
  self.passed_check('Publishing Edge function independently requires active Admin MFA and the exact staff origin')

  png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')
  path=accounts['marketing']['user_id']+'/'+str(uuid.uuid4())+'.png'
  self.expect_request('POST','/storage/v1/object/staff-media/'+path,token=m,raw=png,headers={'Content-Type':'image/png'},statuses=(200,201),label='Private draft photo upload')
  draft['fields'][image['id']]['url']='private:'+path
  self.save_draft('content',draft,m)
  orphan=hashlib.sha256(b'orphan-'+secrets.token_bytes(8)).hexdigest()+'.png'
  self.expect_request('POST','/storage/v1/object/site-media/'+orphan,admin=True,raw=png,headers={'Content-Type':'image/png'},statuses=(200,201),label='Stage an unpublished media fixture')
  check(self.request('GET','/functions/v1/site-media?name='+orphan)[0]==404,'Unpublished staged media leaked through the image endpoint.')
  check(self.request('GET','/storage/v1/object/public/site-media/'+orphan)[0]!=200,'Staged media bucket is public.')
  check(self.request('GET','/storage/v1/object/authenticated/staff-media/'+path)[0]!=200,'Private draft photo is readable anonymously.')
  self.passed_check('Private originals and staged copies remain unreadable before successful publication')

  old_head=self.head('content',a);self.publish('content',a,old_head)
  live=self.rpc('get_published_site',{})
  check(live['content']['fields'][field['id']]['en']==draft['fields'][field['id']]['en'],'Publication did not persist designated text.')
  ref=live['content']['fields'][image['id']]['url'];check(ref.startswith('published:'),'Published payload exposed a private Storage path.')
  check('private:' not in json.dumps(live),'Anonymous publication leaked a private photo reference.')
  code,_,body=self.request('GET','/functions/v1/site-media?name='+ref[10:]);check(code==200 and body==png,'Published photo bytes differ.')
  check(self.request('GET','/storage/v1/object/public/site-media/'+ref[10:])[0]!=200,'Private publication bucket unexpectedly permits direct public reads.')
  check(self.request('GET','/functions/v1/site-media?name='+orphan)[0]==404,'Unreferenced staged copy became public.')
  status,_,_=self.request('POST','/rest/v1/rpc/publish_site_document',token=a,data={'document_kind':'content','revision_id':old_head['draft_id'],'expected_published_id':old_head['published_id']})
  check(status==409,'A stale publication replaced a newer publication.')
  for table,path,data in [('site_revisions','?id=eq.'+live['content_revision'],{'payload':draft}),('site_document_heads','?kind=eq.content',{'published_id':old_head['published_id']})]:
   check(self.request('PATCH','/rest/v1/'+table+path,token=a,data=data)[0] in (401,403),'Direct revision/head mutation was permitted.')
  self.passed_check('Atomic publish exposes resolved immutable media while stale publishes and direct history rewrites are denied')

  changed=copy.deepcopy(catalogue);changed['coffeePackages'][0]['price']+=10
  self.save_draft('catalogue',changed,a);self.publish('catalogue',a)
  current=self.rpc('get_published_site',{})
  check(current['catalogue']['coffeePackages'][0]['price']==135,'Published prices are not the authoritative public catalogue.')
  old=self.rows('site_revisions?id=eq.'+published['catalogue_revision']+'&select=payload',a)[0]['payload']
  check(old['coffeePackages'][0]['price']==125,'Publishing altered an older catalogue version.')
  audit=self.rows('audit_log?entity_type=eq.site_revision&select=actor_user_id,action',a)
  check(any(r['actor_user_id']==accounts['marketing']['user_id'] and r['action']=='site.draft' for r in audit),'Marketing draft audit attribution is missing.')
  check(any(r['actor_user_id']==admin['user_id'] and r['action']=='site.publish' for r in audit),'Administrator publication audit attribution is missing.')
  self.passed_check('Published catalogue prices update independently while old versions and human-attributed audit history remain intact')
  # Leave the live local preview on its imported approved baseline; history stays.
  for kind,payload in [('content',baseline['content']),('catalogue',catalogue)]:self.save_draft(kind,payload,a);self.publish(kind,a)
  self.fixture['site_test']={'text_field':field['id'],'image_field':image['id'],'published_media':ref,'orphan_media':orphan}
  self.save()
  return {'status':'passed','passed_count':len(self.passed),'passed':self.passed,'local_only':True,'production_deployed':False}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--credentials',default='/workspace/.butterfly-private/local-supabase.json');parser.add_argument('--fixtures',default='/workspace/.butterfly-private/publishing-fixtures.json');parser.add_argument('--report',default='/workspace/.butterfly-private/publishing-report.json');args=parser.parse_args()
 suite=Publishing(json.loads(Path(args.credentials).read_text()),args.fixtures)
 private_json(args.report,{'status':'running','passed_count':0,'local_only':True})
 try:report=suite.run()
 except Exception as error:
  message=str(error) if isinstance(error,CheckFailed) else type(error).__name__+'; inspect local setup privately.'
  private_json(args.report,{'status':'failed','passed_count':len(suite.passed),'passed':suite.passed,'error':message,'local_only':True});print('FAIL '+message);return 1
 private_json(args.report,report);print('PASS '+str(report['passed_count'])+' publishing API acceptance groups');return 0

if __name__=='__main__':raise SystemExit(main())
