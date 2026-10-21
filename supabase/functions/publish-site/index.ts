import {createClient} from '@supabase/supabase-js';

const url=Deno.env.get('SUPABASE_URL')??'';
const key=Deno.env.get('SUPABASE_ANON_KEY')??'';
const serviceKey=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')??'';
const origin=Deno.env.get('BUTTERFLY_STAFF_ORIGIN')??'';
const mime:Record<string,string>={png:'image/png',jpg:'image/jpeg',webp:'image/webp',avif:'image/avif'};
function reply(status:number,data:Record<string,unknown>){return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store','Vary':'Origin','Access-Control-Allow-Origin':origin,'Access-Control-Allow-Headers':'authorization,apikey,content-type,x-client-info','Access-Control-Allow-Methods':'POST,OPTIONS','X-Content-Type-Options':'nosniff'}});}
function imageMatches(bytes:Uint8Array,extension:string){
 const ascii=(start:number,end:number)=>new TextDecoder().decode(bytes.slice(start,end));
 if(extension==='png')return bytes.length>=8&&[137,80,78,71,13,10,26,10].every((n,i)=>bytes[i]===n);
 if(extension==='jpg')return bytes.length>=3&&bytes[0]===255&&bytes[1]===216&&bytes[2]===255;
 if(extension==='webp')return ascii(0,4)==='RIFF'&&ascii(8,12)==='WEBP';
 return bytes.length>=12&&ascii(4,8)==='ftyp'&&['avif','avis'].includes(ascii(8,12));
}
Deno.serve(async(request:Request)=>{
 if(!url||!key||!serviceKey||!origin)return reply(503,{error:'Publishing is not configured.'});
 if(request.headers.get('Origin')!==origin)return reply(403,{error:'Origin is not allowed.'});
 if(request.method==='OPTIONS')return reply(200,{});
 if(request.method!=='POST')return reply(405,{error:'Use POST.'});
 const authorization=request.headers.get('Authorization')??'';
 if(!/^Bearer\s+\S+$/i.test(authorization))return reply(401,{error:'Sign in is required.'});
 const caller=createClient(url,key,{global:{headers:{Authorization:authorization}},auth:{persistSession:false,autoRefreshToken:false}});
 const {data:identity,error:identityError}=await caller.auth.getUser(authorization.replace(/^Bearer\s+/i,''));
 if(identityError||!identity.user)return reply(401,{error:'Session is invalid or expired.'});
 const {data:admin,error:adminError}=await caller.rpc('app_is_admin');
 if(adminError||admin!==true)return reply(403,{error:'Administrator MFA is required.'});
 let body:Record<string,unknown>;
 try{
  if(request.headers.get('Content-Type')?.split(';')[0].trim()!=='application/json')return reply(415,{error:'Use JSON.'});
  const reader=request.body?.getReader();if(!reader)throw new Error();
  let data='';let size=0;const decoder=new TextDecoder('utf-8',{fatal:true});
  while(true){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;if(size>2048){await reader.cancel();return reply(413,{error:'Request is too large.'});}data+=decoder.decode(part.value,{stream:true});}
  data+=decoder.decode();body=JSON.parse(data);
  if(!body||typeof body!=='object'||Array.isArray(body))throw new Error();
 }catch{return reply(400,{error:'A publication request is required.'});}
 const {document_kind,revision_id,expected_published_id}=body;
 if(!['content','catalogue'].includes(String(document_kind))||Object.keys(body).some(k=>!['document_kind','revision_id','expected_published_id'].includes(k))||![revision_id,expected_published_id].every(v=>typeof v==='string'&&/^[a-f0-9-]{36}$/.test(v)))return reply(400,{error:'Invalid publication request.'});
 const {data:draft,error:draftError}=await caller.from('site_revisions').select('payload').eq('id',revision_id).eq('kind',document_kind).maybeSingle();
 if(draftError||!draft)return reply(404,{error:'Draft was not found.'});
 const server=createClient(url,serviceKey,{auth:{persistSession:false,autoRefreshToken:false}});
 const mappings:Record<string,string>={};
 if(document_kind==='content')for(const field of Object.values(draft.payload.fields) as {url?:string}[]){
  const source=field.url;if(!source?.startsWith('private:')||mappings[source])continue;
  const path=source.slice(8);const extension=path.split('.').pop()??'';
  if(!mime[extension])return reply(400,{error:'Invalid draft media.'});
  const {data:file,error:downloadError}=await caller.storage.from('staff-media').download(path);
  if(downloadError||!file||file.size>5242880)return reply(400,{error:'Draft media is missing or exceeds 5 MB.'});
  const bytes=new Uint8Array(await file.arrayBuffer());
  if(!imageMatches(bytes,extension))return reply(400,{error:'Draft photo bytes do not match their image format.'});
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  const name=hash+'.'+extension;
  const {error:uploadError}=await server.storage.from('site-media').upload(name,bytes,{contentType:mime[extension],upsert:false,cacheControl:'31536000'});
  if(uploadError){
   const {data:existing,error:existingError}=await server.storage.from('site-media').download(name);
   if(existingError||!existing)return reply(503,{error:'Media staging failed.'});
   const existingHash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await existing.arrayBuffer())),b=>b.toString(16).padStart(2,'0')).join('');
   if(existingHash!==hash)return reply(503,{error:'Media verification failed.'});
  }
  mappings[source]='published:'+name;
 }
 const {data:publication,error}=await caller.rpc('publish_site_document',{document_kind,revision_id,expected_published_id,media_mappings:mappings});
 if(error)return reply(['40001','PT409'].includes(error.code)?409:400,{error:['40001','PT409'].includes(error.code)?'Document changed. Reload before publishing.':'Publication was rejected.'});
 return reply(200,{id:publication.id,version:publication.version});
});
