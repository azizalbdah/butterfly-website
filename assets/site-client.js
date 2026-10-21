/* Published content only. Never accepts a draft identifier or staff credentials. */
(function () {
 'use strict';
 const config=window.BUTTERFLY_PUBLIC_CONFIG||{};
 const page=location.pathname.split('/').pop()?.replace('.html','')||'index';
 let snapshot=null;
 const safeURL=(value)=>{
  if(typeof value!=='string'||/[\u0000-\u0020\\]/.test(value))return null;
  if(value.startsWith('published:')){
   const name=value.slice(10);
   return /^[a-f0-9]{64}\.(png|jpg|webp|avif)$/.test(name)&&config.supabaseUrl?config.supabaseUrl+'/functions/v1/site-media?name='+name:null;
  }
  try{const url=new URL(value,location.href);return ['https:','tel:','mailto:'].includes(url.protocol)||url.origin===location.origin?value:null;}catch{return null;}
 };
 function text(el,value){el.replaceChildren(...value.split('\n').flatMap((part,i)=>i?[document.createElement('br'),document.createTextNode(part)]:[document.createTextNode(part)]));}
 function apply(){
  if(!snapshot)return;
  const lang=document.documentElement.lang==='ar'?'ar':'en';
  const fields=snapshot.content.fields;
  document.querySelectorAll('[data-site-text]').forEach(el=>{
   const v=fields[el.dataset.siteText];if(!v)return;
   el.dataset.en=v.en;el.dataset.ar=v.ar;text(el,v[lang]);
  });
  document.querySelectorAll('[data-site-link]').forEach(el=>{
   const value=safeURL(fields[el.dataset.siteLink]?.url);if(value)el.setAttribute('href',value);
   if(el.target==='_blank')el.rel='noopener noreferrer';
  });
  document.querySelectorAll('[data-site-image]').forEach(el=>{
   const v=fields[el.dataset.siteImage];if(!v)return;
   const value=safeURL(v.url);if(value&&el.getAttribute('src')!==value)el.src=value;
   el.alt=v['alt_'+lang];el.dataset.altEn=v.alt_en;el.dataset.altAr=v.alt_ar;
  });
  document.querySelectorAll('[data-site-seo]').forEach(el=>{
   const v=fields[el.dataset.siteSeo];if(!v)return;
   if(el.tagName==='TITLE')document.title=v[lang];else el.setAttribute('content',v[lang]);
  });
 }
 window.ButterflySiteReady=(async()=>{
  try{
   let result;
   if(config.supabaseUrl&&config.publishableKey){
    const url=new URL(config.supabaseUrl);
    if(url.username||url.password||!(url.protocol==='https:'||(url.protocol==='http:'&&['localhost','127.0.0.1'].includes(url.hostname))))throw new Error('Invalid public endpoint');
    if(config.publishableKey.startsWith('sb_secret_'))throw new Error('Invalid public key');
    if(config.publishableKey.split('.').length===3){const part=config.publishableKey.split('.')[1];const claims=JSON.parse(atob(part.replace(/-/g,'+').replace(/_/g,'/')));if(claims.role!=='anon')throw new Error('Invalid public key');}
    const response=await fetch(url.origin+'/rest/v1/rpc/get_published_site',{method:'POST',credentials:'omit',headers:{apikey:config.publishableKey,'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(8000),cache:'no-store'});
    if(!response.ok)throw new Error('Published site unavailable');
    result=await response.json();
   }else{
    const [content,catalogue]=await Promise.all(['content','catalogue'].map(async kind=>{const r=await fetch('assets/'+kind+'-baseline.json');if(!r.ok)throw new Error('Baseline unavailable');return r.json();}));
    result={content:content.content,catalogue,content_revision:null,catalogue_revision:null,configured:false};
   }
   if(result?.content?.schema!==1||result?.catalogue?.schema!==1)throw new Error('Invalid published site');
   result.configured=Boolean(config.supabaseUrl&&config.publishableKey);
   snapshot=result;apply();
   new MutationObserver(apply).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
   document.dispatchEvent(new CustomEvent('butterfly:published',{detail:{contentRevision:result.content_revision,catalogueRevision:result.catalogue_revision}}));
   return result;
  }catch{
   document.documentElement.dataset.publishedStatus='unavailable';
   return null;
  }
 })();
 window.ButterflyPublished={get snapshot(){return snapshot;},apply,safeURL,page};
})();
