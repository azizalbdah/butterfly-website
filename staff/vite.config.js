import { defineConfig, loadEnv } from 'vite';
import { fileURLToPath } from 'node:url';

function publicConfig(mode) {
  const values=loadEnv(mode,process.cwd(),'VITE_');
  const url=values.VITE_SUPABASE_URL||'';
  const key=values.VITE_SUPABASE_PUBLISHABLE_KEY||'';
  if(key.startsWith('sb_secret_'))throw new Error('Privileged credentials cannot be used in public staff configuration.');
  if(key.split('.').length===3){
    let payload;
    try{payload=JSON.parse(Buffer.from(key.split('.')[1],'base64url').toString());}
    catch{throw new Error('Public staff configuration contains an invalid key.');}
    if(payload.role!=='anon')throw new Error('Only a public or anon key can be used in the staff browser build.');
  }
  if(!url)return null;
  let parsed;
  try{parsed=new URL(url);}catch{throw new Error('Staff API URL is invalid.');}
  const local=['localhost','127.0.0.1'].includes(parsed.hostname);
  if(parsed.username||parsed.password||!(parsed.protocol==='https:'||(local&&parsed.protocol==='http:')))throw new Error('Staff API URL must use verified HTTPS, or loopback HTTP for local preview.');
  return parsed.origin;
}

export default defineConfig(({mode,command})=>{
 const origin=publicConfig(mode);
 const connections=["'self'",origin,origin?.replace(/^http/,'ws'),...(command==='serve'?['ws://127.0.0.1:5173','ws://localhost:5173']:[])].filter(Boolean).join(' ');
 const policy=`default-src 'none'; base-uri 'none'; object-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src ${connections}; form-action 'self'`;
 const headers={
   'X-Frame-Options':'DENY',
   'Content-Security-Policy':policy+"; frame-ancestors 'none'",
   'Referrer-Policy':'no-referrer',
   'X-Content-Type-Options':'nosniff',
 };
 return {
  base: '/staff/',
  plugins:[{name:'private-staff-csp',transformIndexHtml(html){return html.replace(/(<meta http-equiv="Content-Security-Policy" content=")[^"]+/,`$1${policy}`);}}],
  server: {
    fs: {
      allow: [fileURLToPath(new URL('.', import.meta.url)),fileURLToPath(new URL('../fonts', import.meta.url))],
      deny: ['.env','.env.*','*.{crt,pem}','**/.env*','**/.git/**','**/supabase/**','**/.temp/**','**/docker.env'],
    },
    headers,
  },
  preview: {headers},
  build: { sourcemap: false, target: 'es2022' },
 };
});
