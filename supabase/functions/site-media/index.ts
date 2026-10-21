// Anonymous reads are limited to immutable photos referenced by a publication.
import {createClient} from '@supabase/supabase-js';
const url=Deno.env.get('SUPABASE_URL')??'';
const key=Deno.env.get('SUPABASE_ANON_KEY')??'';
const service=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')??'';
const types:Record<string,string>={png:'image/png',jpg:'image/jpeg',webp:'image/webp',avif:'image/avif'};
Deno.serve(async(request:Request)=>{
 const headers={'X-Content-Type-Options':'nosniff','Access-Control-Allow-Origin':'*','Referrer-Policy':'no-referrer'};
 if(request.method!=='GET')return new Response('Use GET.',{status:405,headers});
 const name=new URL(request.url).searchParams.get('name')??'';
 if(!/^[a-f0-9]{64}\.(png|jpg|webp|avif)$/.test(name))return new Response('Not found.',{status:404,headers});
 const client=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
 const {data:published,error}=await client.rpc('is_site_media_published',{object_name:name});
 if(error||published!==true)return new Response('Not found.',{status:404,headers:{...headers,'Cache-Control':'no-store'}});
 const server=createClient(url,service,{auth:{persistSession:false,autoRefreshToken:false}});
 const {data:file,error:fileError}=await server.storage.from('site-media').download(name);
 if(fileError||!file)return new Response('Not found.',{status:404,headers});
 return new Response(file,{headers:{...headers,'Content-Type':types[name.split('.').pop()!],'Cache-Control':'public,max-age=31536000,immutable'}});
});
