import {createClient} from '@supabase/supabase-js';
import {normalizeSubmission,calculateEnquirySnapshot,validUUID,ValidationError} from '../_shared/enquiry.mjs';
const url=Deno.env.get('SUPABASE_URL')??'';
const key=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')??'';
const rateSecret=Deno.env.get('BUTTERFLY_ENQUIRY_RATE_SECRET')??'';
const origins=(Deno.env.get('BUTTERFLY_PUBLIC_ORIGINS')??'').split(',').map(v=>v.trim()).filter(Boolean);
function configured(){return url&&key&&rateSecret.length>=32&&origins.length>0&&origins.every(value=>{try{const u=new URL(value);return u.origin===value&&!u.username&&!u.password&&(u.protocol==='https:'||(u.protocol==='http:'&&['127.0.0.1','localhost'].includes(u.hostname)));}catch{return false;}});}
function response(status:number,body:Record<string,unknown>,origin?:string){return new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store','Vary':'Origin','X-Content-Type-Options':'nosniff',...(origin?{'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Headers':'apikey,content-type,x-client-info','Access-Control-Allow-Methods':'POST,OPTIONS'}:{})}});}
const hex=(bytes:ArrayBuffer)=>Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
Deno.serve(async(request:Request)=>{
 const origin=request.headers.get('Origin')??'';
 if(!configured())return response(503,{error:'Enquiry submissions are not configured.'});
 if(!origins.includes(origin))return response(403,{error:'Origin is not allowed.'});
 if(request.method==='OPTIONS')return response(200,{},origin);
 if(request.method!=='POST')return response(405,{error:'Use POST.'},origin);
 if(request.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!=='application/json')return response(415,{error:'Use application/json.'},origin);
 let body:Record<string,unknown>;
 try{
  const reader=request.body?.getReader();if(!reader)throw new Error();const chunks:Uint8Array[]=[];let size=0;
  while(true){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;if(size>32768){await reader.cancel();return response(413,{error:'Submission is too large.'},origin);}chunks.push(part.value);}
  const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  body=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  if(!body||typeof body!=='object'||Array.isArray(body))throw new Error();
 }catch{return response(400,{error:'A JSON enquiry is required.'},origin);}
 const server=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
 if(body.action==='whatsapp_open_requested'){
  if(!validUUID(body.request_key)||Object.keys(body).some(k=>!['action','request_key'].includes(k)))return response(422,{error:'Invalid request.'},origin);
  const {error}=await server.rpc('record_website_whatsapp_open',{request_key:body.request_key});
  return error?response(503,{error:'The event could not be recorded.'},origin):response(202,{accepted:true,message_sent_verified:false},origin);
 }
 try{
  const submitted=normalizeSubmission(body);
  const fingerprint=hex(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(submitted))));
  const {data:existing,error:lookupError}=await server.rpc('lookup_website_enquiry',{request_key:body.request_key,request_fingerprint:fingerprint});
  if(lookupError)return response(lookupError.code==='PT409'?409:503,{error:lookupError.code==='PT409'?'This submission changed. Review the form before starting a new enquiry.':'Enquiry service is unavailable.'},origin);
  if(existing)return response(200,existing,origin);
  const {data:site,error:siteError}=await server.rpc('get_published_site');
  if(siteError||!site?.catalogue)return response(503,{error:'Published package information is unavailable.'},origin);
  if(site.catalogue_revision!==submitted.catalogue_revision)return response(409,{error:'Package prices changed. Refresh and review your estimate before submitting.'},origin);
  const {data:revision,error:revisionError}=await server.from('site_revisions').select('version').eq('id',site.catalogue_revision).single();
  if(revisionError)return response(503,{error:'Published package version is unavailable.'},origin);
  const snapshot=calculateEnquirySnapshot(submitted,site.catalogue,site.catalogue_revision,revision.version);
  const contact=submitted.customer.phone?'phone:'+submitted.customer.phone:'email:'+submitted.customer.email;
  const hmacKey=await crypto.subtle.importKey('raw',new TextEncoder().encode(rateSecret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const rateKey=hex(await crypto.subtle.sign('HMAC',hmacKey,new TextEncoder().encode(contact)));
  const {data,error}=await server.rpc('capture_website_enquiry',{request_key:body.request_key,request_fingerprint:fingerprint,contact_rate_key:rateKey,catalogue_id:site.catalogue_revision,submitted,pricing:snapshot});
  if(error){
   const status=error.code==='PT409'?409:error.code==='PT429'?429:503;
   return response(status,{error:status===409?'Package prices or submission details changed. Review before retrying.':status===429?'Too many enquiries. Please try again later or contact Butterfly.':'Your enquiry could not be saved. Please try again.'},origin);
  }
  return response(data.duplicate?200:201,data,origin);
 }catch(error){
  if(error instanceof ValidationError)return response(422,{error:error.message},origin);
  return response(503,{error:'Enquiry service is temporarily unavailable.'},origin);
 }
});
