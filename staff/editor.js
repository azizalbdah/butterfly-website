import homeTemplate from '../index.html?raw';
import businessTemplate from '../business.html?raw';
import cateringTemplate from '../catering.html?raw';
import linksTemplate from '../links.html?raw';
import fontURL from '../fonts/HV-Simplicite-Bold.otf?url';
import {createPricingModel} from '../assets/pricing.mjs';

const templates={index:homeTemplate,business:businessTemplate,catering:cateringTemplate,links:linksTemplate};
const images=import.meta.glob('../images/*',{query:'?url',import:'default',eager:true});
const labels={price:['Price (KD)','السعر (د.ك)'],guests:['Base guests','عدد الضيوف الأساسي'],max:['Maximum guests','الحد الأقصى للضيوف'],hours:['Included hours','الساعات المشمولة'],name:['English name','الاسم بالإنجليزية'],en:['English label','النص بالإنجليزية'],ar:['Arabic label','النص بالعربية'],towers:['Towers','الأبراج'],selections:['Savoury selections','أصناف الموالح'],savouries:['Savoury pieces','قطع الموالح'],trays:['Trays','الصواني'],tiramisu:['Tiramisu pieces','قطع التيراميسو'],delight:['Delight pieces','قطع ديلايت'],artistic:['Artistic pieces','القطع الفنية'],chocolate:['Chocolate (kg)','الشوكولاتة (كغم)'],drinks:['Welcome drinks','مشروبات الترحيب'],coffee:['Coffee cups','أكواب القهوة'],baristas:['Baristas','الباريستا'],staff:['Hospitality staff','موظفو الضيافة'],captains:['Event captains','مشرفو المناسبة'],helpers:['Helpers','المساعدون'],unitEn:['English unit','الوحدة بالإنجليزية'],unitAr:['Arabic unit','الوحدة بالعربية']};

export function createEditor({client,h,t,getMember,rerender}){
 const state={kind:'content',page:'index',head:null,payload:null,definitions:[],history:[],historyHasMore:false,busy:false,dirty:false,notice:null,preview:false,cssBlobs:[],cache:new Map(),blobs:new Map(),calculator:{service:'hospitality',guests:30,hours:4}};
 const canPublish=()=>getMember()?.role==='admin';
 const show=(message,error=false)=>{state.notice={message,error};};
 async function run(action){
  if(state.busy)return;state.busy=true;state.notice=null;rerender();
  try{await action();}catch{show(t('This action failed. Check your connection and access, then try again.','تعذّر تنفيذ العملية. تحقّق من الاتصال والصلاحيات ثم حاول مجددًا.'),true);}
  finally{state.busy=false;rerender();}
 }
 async function media(){
  for(const blob of state.blobs.values())URL.revokeObjectURL(blob);state.blobs.clear();
  if(state.kind!=='content')return;
  for(const value of Object.values(state.payload.fields)){
   if(!value.url?.startsWith('private:')||state.blobs.has(value.url))continue;
   const {data,error}=await client.storage.from('staff-media').download(value.url.slice(8));
   if(!error&&data)state.blobs.set(value.url,URL.createObjectURL(data));
  }
 }
 async function load(){
  const {data:head,error}=await client.from('site_document_heads').select('*').eq('kind',state.kind).single();
  if(error)throw error;
  const [{data:revision,error:revisionError},{data:history,error:historyError}]=await Promise.all([
   client.from('site_revisions').select('*').eq('id',head.draft_id).single(),
   client.from('site_revisions').select('id,version,operation,created_at,parent_id').eq('kind',state.kind).order('version',{ascending:false}).limit(40),
  ]);
  if(revisionError||historyError)throw new Error();
  state.head=head;state.payload=structuredClone(revision.payload);state.history=history;state.historyHasMore=history.length===40;state.dirty=false;state.cache.delete(state.kind);
  if(state.kind==='content'&&!state.definitions.length){
   const {data,error}=await client.from('site_field_definitions').select('*').order('id');if(error)throw error;state.definitions=data;
  }
  await media();
 }
 function open(kind){
  if(state.busy)return;
  if(state.payload&&state.dirty)state.cache.set(state.kind,{payload:structuredClone(state.payload),head:state.head,history:state.history,historyHasMore:state.historyHasMore,page:state.page});
  state.kind=kind;state.head=null;state.payload=null;state.preview=false;
  const cached=state.cache.get(kind);
  run(async()=>{if(cached){Object.assign(state,cached);state.dirty=true;await media();show(t('Your unsaved edits are restored.','تمت استعادة تعديلاتك غير المحفوظة.'));}else await load();});
 }
 function change(){state.dirty=true;state.preview=false;const publish=document.querySelector('[data-action=publish]');if(publish)publish.disabled=true;}
 const action=(label,fn,secondary=false)=>h('button',{type:'button',class:secondary?'small-button':'button',disabled:state.busy,onclick:fn},label);
 function input(id,label,value,oninput,{type='text',max=6000,min=0,step='1',markDirty=true}={}){
  const node=h(type==='textarea'?'textarea':'input',{id,name:id,type:type==='textarea'?null:type,value:type==='textarea'?null:value,rows:type==='textarea'?3:null,maxlength:type==='number'?null:max,min:type==='number'?min:null,max:type==='number'?max:null,step:type==='number'?step:null,oninput:event=>{oninput(event.target.value);if(markDirty)change();}});
  if(type==='textarea')node.value=value;
  return h('div',{class:'field'},h('label',{for:id},label),node);
 }
 async function save(){await run(async()=>{
  const {error}=await client.rpc('save_site_draft',{document_kind:state.kind,new_payload:state.payload,expected_draft_id:state.head.draft_id});
  if(error){show(['40001','PT409'].includes(error.code)?t('Another editor saved first. Reload the latest draft before saving. Your changes are still visible.','حفظ محرر آخر قبلك. حمّل أحدث مسودة قبل الحفظ. تعديلاتك ما زالت ظاهرة.'):t('Draft validation failed. Check both languages, links, capacities and prices.','فشل التحقق من المسودة. راجع اللغتين والروابط والسعات والأسعار.'),true);return;}
  await load();show(t('Draft saved. The public website has not changed.','تم حفظ المسودة. لم يتغير الموقع العام.'));
 });}
 async function publish(){await run(async()=>{
  if(state.dirty){show(t('Save your draft before publishing.','احفظ المسودة قبل النشر.'),true);return;}
  const {error}=await client.functions.invoke('publish-site',{body:{document_kind:state.kind,revision_id:state.head.draft_id,expected_published_id:state.head.published_id}});
  if(error){show(t('Publishing was rejected. The website remains on its last publication. Reload and check your draft and permissions.','رُفض النشر. يبقى الموقع على آخر نسخة منشورة. أعد التحميل وراجع المسودة والصلاحيات.'),true);return;}
  await load();show(t('Published. Visitors now receive this version.','تم النشر. تظهر هذه النسخة للزوار الآن.'));
 });}
 async function upload(field,file){await run(async()=>{
  const extension={'image/png':'png','image/jpeg':'jpg','image/webp':'webp','image/avif':'avif'}[file?.type];
  if(!extension||file.size>5242880){show(t('Choose a PNG, JPG, WebP or AVIF photo up to 5 MB.','اختر صورة PNG أو JPG أو WebP أو AVIF بحجم أقصى 5 ميغابايت.'),true);return;}
  const {data:{user},error:userError}=await client.auth.getUser();if(userError||!user)throw new Error();
  const name=user.id+'/'+crypto.randomUUID()+'.'+extension;
  const {error}=await client.storage.from('staff-media').upload(name,file,{contentType:file.type,upsert:false});if(error)throw error;
  state.payload.fields[field.id].url='private:'+name;change();await media();
  show(t('Photo uploaded privately. Save the draft; it becomes public only after an administrator publishes.','تم رفع الصورة بشكل خاص. احفظ المسودة؛ تظهر للزوار فقط بعد نشر المسؤول.'));
 });}
 function photoURL(value){
  if(value.startsWith('private:'))return state.blobs.get(value)||'';
  if(value.startsWith('published:'))return new URL('/functions/v1/site-media?name='+value.slice(10),import.meta.env.VITE_SUPABASE_URL).href;
  return images['../'+value]||'';
 }
 function contentFields(){
  return state.definitions.filter(d=>d.page===state.page).map(d=>{
   const value=state.payload.fields[d.id];
   return h('fieldset',{class:'editor-field','data-field-id':d.id},h('legend',{},d.label),
    (d.kind==='text'||d.kind==='seo')?[input(d.id+'-en',t('English','الإنجليزية'),value.en,v=>value.en=v,{type:'textarea'}),input(d.id+'-ar',t('Arabic','العربية'),value.ar,v=>value.ar=v,{type:'textarea'})]:
    d.kind==='link'?input(d.id+'-url',t('Link or contact destination','الرابط أو وجهة الاتصال'),value.url,v=>value.url=v,{max:2000}):[
     photoURL(value.url)&&h('img',{class:'editor-photo',src:photoURL(value.url),alt:value.alt_en}),
     h('div',{class:'field'},h('label',{for:d.id+'-upload'},t('Replace photo (private draft)','استبدال الصورة (مسودة خاصة)')),h('input',{id:d.id+'-upload',type:'file',accept:'image/png,image/jpeg,image/webp,image/avif',disabled:state.busy,onchange:event=>{const file=event.target.files?.[0];if(file)upload(d,file);}})),
     input(d.id+'-alt-en',t('English photo description','وصف الصورة بالإنجليزية'),value.alt_en,v=>value.alt_en=v,{max:500}),input(d.id+'-alt-ar',t('Arabic photo description','وصف الصورة بالعربية'),value.alt_ar,v=>value.alt_ar=v,{max:500}),
    ]);
  });
 }
 function packageFields(){
  return [['packages',t('Hospitality and wedding packages','باقات الضيافة والأعراس')],['coffeePackages',t('Coffee packages','باقات القهوة')],['addons',t('Add-ons','الإضافات')],['serviceTypes',t('Services','الخدمات')],['savouries',t('Savoury selections','أصناف الموالح')],['towers',t('Tower choices','أنواع الأبراج')]].map(([group,title])=>
   h('section',{},h('h3',{},title),h('div',{class:'package-edit-grid'},state.payload[group].map(row=>h('fieldset',{class:'editor-field'},h('legend',{},row.name||row.en||row.id),Object.entries(row).filter(([key])=>!['id','service','group'].includes(key)).map(([key,value])=>input(group+'-'+row.id+'-'+key,labels[key]?t(...labels[key]):key,value,v=>row[key]=typeof value==='number'?(v===''?NaN:Number(v)):v,{type:typeof value==='number'?'number':'text',max:typeof value==='number'?100000:300,step:['price','chocolate'].includes(key)?'0.001':'1'})))))));
 }
 function previewDocument(){
  state.cssBlobs.forEach(url=>URL.revokeObjectURL(url));state.cssBlobs=[];
  const documentCopy=new DOMParser().parseFromString(templates[state.page],'text/html');
  const lang=document.documentElement.lang==='ar'?'ar':'en';
  documentCopy.documentElement.lang=lang;documentCopy.documentElement.dir=lang==='ar'?'rtl':'ltr';
  documentCopy.querySelectorAll('script,noscript,iframe,object,embed,base,link,meta[http-equiv]').forEach(node=>node.remove());
  documentCopy.querySelectorAll('*').forEach(node=>{
   for(const attr of [...node.attributes])if(attr.name.startsWith('on')||['srcset','ping','action','formaction','poster','style'].includes(attr.name))node.removeAttribute(attr.name);
   if(node.tagName==='A')node.removeAttribute('href');
   if(['INPUT','SELECT','BUTTON','TEXTAREA'].includes(node.tagName))node.setAttribute('disabled','');
  });
  for(const d of state.definitions.filter(d=>d.page===state.page)){
   const node=documentCopy.querySelector('[data-site-'+d.kind+'="'+d.id+'"]');const value=state.payload.fields[d.id];if(!node)continue;
   if(d.kind==='text')node.replaceChildren(...value[lang].split('\n').flatMap((part,i)=>i?[documentCopy.createElement('br'),documentCopy.createTextNode(part)]:[documentCopy.createTextNode(part)]));
   if(d.kind==='image'){node.setAttribute('src',photoURL(value.url));node.setAttribute('alt',value['alt_'+lang]);}
   if(d.kind==='seo'){if(node.tagName==='TITLE')node.textContent=value[lang];else node.setAttribute('content',value[lang]);}
  }
  documentCopy.querySelectorAll('img').forEach(node=>{if(!node.hasAttribute('data-site-image'))node.remove();});
  documentCopy.querySelectorAll('style').forEach(node=>{const css=node.textContent.replace(/@import[^;]+;/g,'').replace(/url\([^)]*\)/g,match=>/\.otf/i.test(match)?'url('+new URL(fontURL,location.href).href+')':'none');const url=URL.createObjectURL(new Blob([css],{type:'text/css'}));state.cssBlobs.push(url);const link=documentCopy.createElement('link');link.rel='stylesheet';link.href=url;node.replaceWith(link);});
  const policy=documentCopy.createElement('meta');policy.httpEquiv='Content-Security-Policy';
  const apiOrigin=new URL(import.meta.env.VITE_SUPABASE_URL).origin;
  policy.content=`default-src 'none'; style-src blob:; img-src ${location.origin} ${apiOrigin} blob: data:; font-src ${location.origin}; base-uri 'none'; form-action 'none'`;
  documentCopy.head.prepend(policy);
  return '<!DOCTYPE html>'+documentCopy.documentElement.outerHTML;
 }
 function packagePreview(){
  const model=createPricingModel(state.payload);const q=model.recommendService(state.calculator.service,state.calculator.guests,0,state.calculator.hours);
  return h('section',{class:'panel'},h('h3',{},t('Preview package recommendation','معاينة الباقة المقترحة')),
   h('div',{class:'editor-toolbar'},h('label',{},t('Service','الخدمة'),h('select',{id:'preview-service',onchange:e=>{state.calculator.service=e.target.value;rerender();}},state.payload.serviceTypes.map(s=>h('option',{value:s.id,selected:s.id===state.calculator.service?'selected':null},t(s.en,s.ar))))),
    input('preview-guests',t('Guests','الضيوف'),state.calculator.guests,v=>{state.calculator.guests=Number(v);},{type:'number',min:1,max:400,markDirty:false}),
    input('preview-hours',t('Service hours','ساعات الخدمة'),state.calculator.hours,v=>{state.calculator.hours=Number(v);},{type:'number',min:4,max:8,markDirty:false}),action(t('Calculate preview','احسب المعاينة'),()=>rerender(),true)),
   h('p',{role:'status'},q?`${q.package.name} · ${q.total.toFixed(3)} ${t('KD estimate','د.ك تقديريًا')}`:t('A tailored quotation is required for these choices.','يلزم عرض مخصص لهذه الخيارات.')));
 }
 function render(){
  if(!state.payload)return h('section',{class:'panel'},h('h2',{},t('Loading editor…','جارٍ تحميل المحرر…')),state.notice&&h('p',{role:'alert'},state.notice.message),action(t('Retry','حاول مجددًا'),()=>run(load),true));
  const historySelect=h('select',{id:'history-version','aria-label':t('Saved version','النسخة المحفوظة')},state.history.map(r=>h('option',{value:r.id},`v${r.version} · ${{seed:t('Imported original','النسخة الأصلية'),draft:t('Draft','مسودة'),publication:t('Published','منشورة')}[r.operation]} · ${new Date(r.created_at).toLocaleString(document.documentElement.lang==='ar'?'ar-KW':'en-KW',{timeZone:'Asia/Kuwait'})}`)));
  return h('section',{class:'site-editor'},h('div',{class:'section-head'},h('div',{},h('h2',{},state.kind==='content'?t('Website editor','محرر الموقع'):t('Packages and prices','الباقات والأسعار')),h('p',{},t('Drafts are private. Only an administrator can publish a saved version.','المسودات خاصة. يستطيع المسؤول فقط نشر نسخة محفوظة.')))),
   state.notice&&h('p',{class:'message '+(state.notice.error?'error':'success'),role:state.notice.error?'alert':'status'},state.notice.message),
   h('div',{class:'editor-toolbar'},action(t('Save draft','حفظ المسودة'),save),canPublish()&&h('button',{type:'button',class:'button','data-action':'publish',disabled:state.busy||state.dirty,onclick:publish},t('Publish saved draft','نشر المسودة المحفوظة')),action(t('Reload latest draft','تحميل أحدث مسودة'),()=>run(load),true),action(t('Preview draft','معاينة المسودة'),()=>{state.preview=!state.preview;rerender();},true)),
   h('p',{class:'mfa-detail'},state.kind==='content'?t('Saving keeps changes private. Publishing releases all pages in the saved website draft; review each changed page first.','يحفظ التعديل بشكل خاص. ينشر الزر جميع صفحات مسودة الموقع المحفوظة؛ راجع كل صفحة معدّلة أولًا.'):t('Publishing updates the complete package catalogue. Earlier prices remain in version history.','يحدّث النشر قائمة الباقات كاملة. تبقى الأسعار السابقة في سجل النسخ.')),
   state.kind==='content'&&h('div',{class:'editor-toolbar'},...Object.keys(templates).map(page=>h('button',{type:'button',class:'small-button','aria-pressed':String(state.page===page),onclick:()=>{state.page=page;rerender();}},({index:t('Home','الرئيسية'),business:t('Corporate','الشركات'),catering:t('Catering','الكيترنق'),links:t('Links','الروابط')})[page]))),
   state.preview&&(state.kind==='content'?h('iframe',{class:'site-preview',title:t('Private draft preview','معاينة المسودة الخاصة'),sandbox:'allow-same-origin',srcdoc:previewDocument()}):packagePreview()),
   h('details',{class:'panel history'},h('summary',{},t('Version history','سجل النسخ')),historySelect,state.historyHasMore&&action(t('Load older versions','تحميل نسخ أقدم'),()=>run(async()=>{
    const {data,error}=await client.from('site_revisions').select('id,version,operation,created_at,parent_id').eq('kind',state.kind).lt('version',state.history.at(-1).version).order('version',{ascending:false}).limit(40);if(error)throw error;state.history.push(...data);state.historyHasMore=data.length===40;
   }),true),action(t('Use version as a new draft','استخدام النسخة كمسودة جديدة'),()=>run(async()=>{
    const {data,error}=await client.from('site_revisions').select('payload').eq('id',historySelect.value).single();if(error)throw error;
    state.payload=structuredClone(data.payload);change();await media();show(t('Version loaded into the editor. Save it to create a new draft; history remains intact.','تم تحميل النسخة في المحرر. احفظها لإنشاء مسودة جديدة؛ يبقى السجل محفوظًا.'));
   }),true)),
   h('div',{class:'editor-fields'},state.kind==='content'?contentFields():packageFields()));
 }
 return {open,render,ensure(){if(!state.payload&&!state.busy)open('content');},clear(){state.cache.clear();state.cssBlobs.forEach(url=>URL.revokeObjectURL(url));state.cssBlobs=[];for(const blob of state.blobs.values())URL.revokeObjectURL(blob);state.blobs.clear();state.payload=null;state.head=null;state.history=[];state.notice=null;},get kind(){return state.kind;},get busy(){return state.busy;}};
}
