/* Public enquiry saving and the separate, optional WhatsApp action. */
const submissions=new WeakMap();
const t=(en,ar)=>document.documentElement.lang==='ar'?ar:en;
export function isConfigured(){const c=window.BUTTERFLY_PUBLIC_CONFIG;return Boolean(c?.supabaseUrl&&c?.publishableKey);}
function translated(tag,en,ar){const el=document.createElement(tag);el.dataset.en=en;el.dataset.ar=ar;el.textContent=t(en,ar);return el;}
export function mountContactFields(form,anchorID){
 if(!isConfigured()||form.querySelector('#enquiryPhone'))return;
 const anchor=document.getElementById(anchorID).closest('.field');
 function field(id,type,en,ar,autocomplete){
  const container=document.createElement('div');container.className='field';
  const label=translated('label',en,ar);label.htmlFor=id;
  const input=document.createElement('input');input.id=id;input.name=id;input.type=type;input.autocomplete=autocomplete;input.dir='ltr';input.maxLength=type==='tel'?40:254;
  if(type==='tel')input.placeholder='+965…';
  input.addEventListener('input',()=>{input.setCustomValidity('');document.getElementById('enquiryPhone').setCustomValidity('');});
  container.append(label,input);return container;
 }
 const phone=field('enquiryPhone','tel','Phone number','رقم الهاتف','tel');
 const email=field('enquiryEmail','email','Email address','البريد الإلكتروني','email');
 const note=translated('p','Provide a phone number or email so our team can respond. Saving an enquiry does not confirm a booking.','أدخل رقم هاتف أو بريدًا إلكترونيًا ليتواصل فريقنا معك. حفظ الاستفسار لا يعني تأكيد الحجز.');note.className='field full mini enquiry-contact-note';
 anchor.after(phone,email,note);
 const original=form.querySelector('button[type=submit]');
 if(original){
  original.hidden=true;
  const save=translated('button','Save enquiry','حفظ الاستفسار');save.id='saveEnquiry';save.type='submit';save.className=original.className;save.disabled=original.disabled;
  original.before(save);new MutationObserver(()=>{save.disabled=original.disabled;}).observe(original,{attributes:true,attributeFilter:['disabled']});
 }
}
export function contactDetails(nameID,companyID=null){
 const phone=document.getElementById('enquiryPhone');const email=document.getElementById('enquiryEmail');
 if(!phone||!email)return null;
 phone.setCustomValidity('');email.setCustomValidity('');
 if(!phone.value.trim()&&!email.value.trim())phone.setCustomValidity(t('Enter a phone number or email address.','أدخل رقم هاتف أو بريدًا إلكترونيًا.'));
 else if(phone.value.trim()&&!/^\+?[0-9 ()-]{7,40}$/.test(phone.value.trim()))phone.setCustomValidity(t('Enter a valid phone number, including its country code.','أدخل رقم هاتف صحيحًا مع مفتاح الدولة.'));
 if(!phone.reportValidity()||!email.reportValidity()){(phone.validity.valid?email:phone).focus();return null;}
 return {name:document.getElementById(nameID).value.trim(),phone:phone.value.trim(),email:email.value.trim(),company:companyID?document.getElementById(companyID).value.trim():''};
}
function statusMessage(status){
 if(status===409)return t('Package information changed. Refresh this page and review your choices before submitting again.','تغيّرت معلومات الباقات. حدّث الصفحة وراجع خياراتك قبل الإرسال مجددًا.');
 if(status===422)return t('Check your contact details, event date and package choices. Your enquiry was not saved.','تحقّق من بيانات الاتصال وتاريخ المناسبة وخيارات الباقة. لم يُحفظ الاستفسار.');
 if(status===429)return t('Too many enquiries were submitted recently. Please try later or contact Butterfly.','تم إرسال استفسارات كثيرة مؤخرًا. حاول لاحقًا أو تواصل مع بترفلاي.');
 return t('We could not confirm that your enquiry was saved. Try again to check the same submission, or contact Butterfly.','تعذّر تأكيد حفظ الاستفسار. حاول مجددًا للتحقق من نفس الاستفسار، أو تواصل مع بترفلاي.');
}
async function post(body){
 const config=window.BUTTERFLY_PUBLIC_CONFIG;
 const response=await fetch(config.supabaseUrl+'/functions/v1/submit-enquiry',{method:'POST',credentials:'omit',cache:'no-store',headers:{apikey:config.publishableKey,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
 let data;try{data=await response.json();}catch{data=null;}
 return {response,data};
}
export async function saveAndOfferWhatsApp({form,status,payload,whatsappURL,onWhatsApp}){
 const signature=JSON.stringify(payload);let pending=submissions.get(form);
 if(!pending||pending.signature!==signature){pending={signature,key:crypto.randomUUID()};submissions.set(form,pending);}
 if(pending.busy)return;
 pending.busy=true;form.inert=true;form.setAttribute('aria-busy','true');
 const progress=document.createElement('p');progress.setAttribute('role','status');progress.textContent=t('Saving your enquiry…','جارٍ حفظ الاستفسار…');form.before(progress);status.replaceChildren();
 try{
  const site=await window.ButterflySiteReady;
  if(!site?.catalogue_revision)throw new Error();
  const {response,data}=await post({...payload,action:'submit',request_key:pending.key,catalogue_revision:site.catalogue_revision,website:''});
  if(!response.ok||!/^BF-\d{6}-[A-F0-9]{10}$/.test(data?.receipt||'')){
   const message=document.createElement('p');message.setAttribute('role','alert');message.textContent=statusMessage(response.status);status.replaceChildren(message);return;
  }
  const canonicalField=location.pathname.endsWith('business.html')?'business-link-080':'catering-link-125';
  const publishedDestination=site.content.fields[canonicalField]?.url;
  try{
   const contact=new URL(publishedDestination);const draft=new URL(whatsappURL);
   const allowed=contact.protocol==='https:'&&((contact.hostname==='wa.me'&&/^\/[0-9]{7,15}\/?$/.test(contact.pathname))||(contact.hostname==='api.whatsapp.com'&&contact.pathname==='/send'&&/^[0-9]{7,15}$/.test(contact.searchParams.get('phone')||'')));
   if(!allowed)whatsappURL=null;else{contact.searchParams.set('text',draft.searchParams.get('text')||'');whatsappURL=contact.href;}
  }catch{whatsappURL=null;}
  const saved=document.createElement('p');saved.setAttribute('role','status');saved.className='enquiry-saved';saved.dataset.receipt=data.receipt;
  saved.textContent=t('Enquiry saved. Reference: ','تم حفظ الاستفسار. الرقم المرجعي: ')+data.receipt;
  const explanation=document.createElement('p');explanation.textContent=t('Our team will review availability and contact you. This is not a confirmed booking. WhatsApp is a separate optional step; send your message there.','سيراجع فريقنا التوفر ويتواصل معك. هذا ليس حجزًا مؤكدًا. واتساب خطوة اختيارية منفصلة؛ أرسل رسالتك هناك.');
  const link=document.createElement('a');link.id='openEnquiryWhatsApp';link.href=whatsappURL;link.target='_blank';link.rel='noopener noreferrer';link.className='btn';link.textContent=t('Open prepared WhatsApp message ↗','فتح رسالة واتساب المجهّزة ↗');
  const original=form.querySelector('button[type=submit][hidden]');if(original?.dataset.siteText){link.dataset.siteText=original.dataset.siteText;link.dataset.en=original.dataset.en;link.dataset.ar=original.dataset.ar;link.textContent=t(original.dataset.en,original.dataset.ar);}
  link.addEventListener('click',event=>{
   event.preventDefault();window.open(whatsappURL,'_blank','noopener,noreferrer');
   // This records only a request to open a link, never delivery or quotation status.
   post({action:'whatsapp_open_requested',request_key:pending.key}).catch(()=>{});onWhatsApp?.();
  });
  if(whatsappURL)status.replaceChildren(saved,explanation,link);else{explanation.textContent=t('Our team will review availability and contact you. This is not a confirmed booking.','سيراجع فريقنا التوفر ويتواصل معك. هذا ليس حجزًا مؤكدًا.');status.replaceChildren(saved,explanation);}
 }catch{
  const message=document.createElement('p');message.setAttribute('role','alert');message.textContent=statusMessage(0);status.replaceChildren(message);
 }finally{pending.busy=false;form.inert=false;form.setAttribute('aria-busy','false');progress.remove();}
}
