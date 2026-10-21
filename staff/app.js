import { createClient } from '@supabase/supabase-js';
import {createEditor} from './editor.js';
import {createCRM} from './crm.js';

const root = document.querySelector('#app');
const memoryStorage = new Map();
const storage = {
  getItem(name) { try { return localStorage.getItem(name); } catch { return memoryStorage.get(name) ?? null; } },
  setItem(name,value) { try { localStorage.setItem(name,value); } catch { memoryStorage.set(name,value); } },
  removeItem(name) { try { localStorage.removeItem(name); } catch { /* Restricted storage uses memory. */ } memoryStorage.delete(name); },
};
let lang = storage.getItem('butterfly-staff-language') === 'ar' ? 'ar' : 'en';
let section = 'overview';
let user = null;
let member = null;
let members = [];
let mode = 'login';
let message = null;
try {
  if(sessionStorage.getItem('butterfly-staff-logout-warning')){
    message={text:lang==='ar'?'تم تسجيل الخروج من هذا المتصفح. تعذّر تأكيد إلغاء الجلسة على الخادم.':'Signed out on this browser. Server session revocation could not be confirmed.',type:'error'};
    sessionStorage.removeItem('butterfly-staff-logout-warning');
  }
} catch { /* Session storage is optional. */ }
let busy = false;
let checking = true;
let factor = null;
let assurance = null;
let refreshVersion = 0;
let staffLoadFailed = false;
const initialHash = new URLSearchParams(location.hash.slice(1));
let passwordCallback = ['invite', 'recovery'].includes(initialHash.get('type'));
const t = (en, ar) => lang === 'ar' ? ar : en;
const roleLabel = (role) => ({admin:t('Administrator','مدير'),sales:t('Sales','المبيعات'),marketing:t('Marketing','التسويق')})[role] || t('Staff','موظف');
const url = import.meta.env.VITE_SUPABASE_URL || '';
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || '';

function usablePublicConfig() {
  try {
    const parsed = new URL(url);
    const local = ['127.0.0.1', 'localhost'].includes(parsed.hostname);
    if (!(parsed.protocol === 'https:' || (local && parsed.protocol === 'http:')) || parsed.username || parsed.password || !key || key.startsWith('sb_secret_')) return false;
    if (key.split('.').length === 3) {
      const payload = JSON.parse(atob(key.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));
      if (payload.role !== 'anon') return false;
    }
    return true;
  } catch { return false; }
}

const configured = usablePublicConfig();
const client = configured ? createClient(url, key, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, storageKey: 'butterfly-staff-auth', storage },
}) : null;
const editor=createEditor({client,h,t,getMember:()=>member,rerender:()=>render()});
const crm=createCRM({client,h,t,getMember:()=>member,getMembers:()=>members,rerender:()=>render()});

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (name.startsWith('on')) el.addEventListener(name.slice(2).toLowerCase(), value);
    else if (name === 'class') el.className = value;
    else if (name === 'checked' || name === 'disabled' || name === 'required') el[name] = Boolean(value);
    else if (value !== null && value !== undefined) el.setAttribute(name, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function field(id, label, options = {}) {
  const {hint, ...attrs} = options;
  const input = h('input', {id, name:id, ...attrs});
  return h('div', {class:'field'}, h('label', {for:id}, label), input, hint && h('small', {}, hint));
}

function select(id, label, entries, value) {
  const input = h('select', {id, name:id}, entries.map(([key,label]) => h('option',{value:key},label)));
  input.value = value;
  return h('div',{class:'field'},h('label',{for:id},label),input);
}

function button(label, action, secondary = false) {
  return h('button', {type:'button',class:'button' + (secondary?' secondary':''),onclick:action,disabled:busy}, label, h('span',{'aria-hidden':'true'},'↗'));
}

function submitButton(label) {
  return h('button',{type:'submit',class:'button',disabled:busy},busy?t('Please wait…','يرجى الانتظار…'):label,h('span',{'aria-hidden':'true'},'↗'));
}

function notify(text, type = 'success') { message = {text,type}; }
function alertBox() { return message && h('p',{class:'message '+message.type,role:message.type==='error'?'alert':'status','aria-live':'polite'},message.text); }

function switchMode(next) { mode=next; message=null; render(); document.querySelector('main h2')?.focus(); }

function header() {
  return h('header',{class:'masthead'},
    h('div',{class:'brand-block'},h('a',{href:'/staff/',class:'brand','aria-label':t('Butterfly staff home','الرئيسية لموظفي بترفلاي')},'Butterfly'),h('span',{class:'brand-divider','aria-hidden':'true'}),h('span',{class:'eyebrow'},t('Staff workspace','مساحة الموظفين'))),
    h('div',{class:'masthead-actions'},h('div',{class:'language-switch','aria-label':t('Language','اللغة')},
      ...['en','ar'].flatMap((code,i)=>[i?h('span',{'aria-hidden':'true'},'/'):null,h('button',{type:'button','aria-pressed':String(lang===code),'aria-label':code==='en'?'English':'العربية',onclick:()=>{lang=code;storage.setItem('butterfly-staff-language',lang);render();}},code==='en'?'EN':'ع')])
    ),user&&h('button',{type:'button',class:'text-button signout',onclick:logout,disabled:busy},t('Sign out','تسجيل الخروج'))));
}

function footer() {
  return h('footer',{class:'footer'},h('span',{},`© ${new Date().getFullYear()} Butterfly`),h('span',{class:'secure-mark'},t('Private staff access','وصول خاص للموظفين')),h('span',{class:'eyebrow'},t('Made with care in Kuwait','صُنع بعناية في الكويت')));
}

function intro() {
  return h('section',{class:'intro'},h('span',{class:'eyebrow muted'},t('The people behind the details','الأشخاص خلف كل تفصيل')),h('h1',{},t('A considered space.\nFor our team.','مساحة بعناية.\nلفريقنا.')),h('p',{class:'lead'},t('A private workspace for the people who bring Butterfly experiences to life.','مساحة خاصة بالفريق الذي يمنح تجارب بترفلاي روحها.')),h('div',{class:'intro-rule'}),h('p',{class:'intro-note'},t('Access is by invitation. Your work and customer information stay protected by your assigned permissions.','الدخول بدعوة فقط. تبقى أعمالك وبيانات العملاء محمية وفق صلاحياتك المحددة.')));
}

function authCard() {
  if (!configured) return h('section',{class:'access-card'},h('span',{class:'eyebrow muted'},t('Secure setup','الإعداد الآمن')),h('h2',{tabindex:'-1'},t('Connection required','يلزم إعداد الاتصال')),h('p',{class:'card-copy'},t('Staff access is unavailable until this preview is connected to its approved Supabase project. Ask the workspace administrator to complete secure configuration.','الوصول للموظفين غير متاح حتى ربط هذه المعاينة بمشروع Supabase المعتمد. اطلب من المسؤول إكمال الإعداد الآمن.')));
  if (user && passwordCallback) return passwordCard();
  if (user && member?.role === 'admin' && assurance !== 'aal2') return mfaCard();
  if (user && !member) return h('section',{class:'access-card'},h('span',{class:'eyebrow muted'},t('Staff access','دخول الموظفين')),h('h2',{tabindex:'-1'},t('Access unavailable','الوصول غير متاح')),alertBox(),h('p',{class:'card-copy'},t('This account does not have active staff access. Contact the Butterfly administrator.','لا يملك هذا الحساب صلاحية موظف نشطة. تواصل مع مسؤول بترفلاي.')),button(t('Sign out','تسجيل الخروج'),logout));
  if (mode === 'reset') return resetCard();
  const form = h('form',{class:'form',onsubmit:login},
    field('email',t('Work email','البريد الإلكتروني للعمل'),{type:'email',autocomplete:'username',required:true,maxlength:254,dir:'ltr'}),
    field('password',t('Password','كلمة المرور'),{type:'password',autocomplete:'current-password',required:true,maxlength:256}),
    submitButton(t('Sign in','تسجيل الدخول')));
  return h('section',{class:'access-card'},h('span',{class:'eyebrow muted'},t('Welcome to Butterfly','مرحبًا بك في بترفلاي')),h('h2',{tabindex:'-1'},t('Staff sign in','دخول الموظفين')),h('p',{class:'card-copy'},t('Use your invited work account to continue.','استخدم حساب العمل الذي تمت دعوته للمتابعة.')),alertBox(),form,
    h('div',{class:'form-footer'},h('button',{type:'button',class:'text-button',onclick:()=>switchMode('reset')},t('Forgot your password?','نسيت كلمة المرور؟')),h('span',{class:'eyebrow muted'},t('Invitation only','بدعوة فقط'))),
    h('p',{class:'privacy-note'},t('For authorised Butterfly staff. Customer ordering remains available on the public website.','للموظفين المخولين في بترفلاي. يظل طلب العملاء متاحًا على الموقع العام.')));
}

function resetCard() {
  return h('section',{class:'access-card'},h('span',{class:'eyebrow muted'},t('Account recovery','استعادة الحساب')),h('h2',{tabindex:'-1'},t('Reset your password','إعادة تعيين كلمة المرور')),h('p',{class:'card-copy'},t('Enter your invited work email. If it can receive a reset, we will send a secure link.','أدخل بريد العمل الذي تمت دعوته. إذا كان مؤهلًا للاستعادة، ستصلك رسالة برابط آمن.')),alertBox(),h('form',{class:'form',onsubmit:requestReset},field('email',t('Work email','البريد الإلكتروني للعمل'),{type:'email',autocomplete:'email',dir:'ltr',required:true,maxlength:254}),submitButton(t('Send reset link','إرسال رابط الاستعادة'))),h('div',{class:'form-footer'},h('button',{type:'button',class:'text-button',onclick:()=>switchMode('login')},t('Back to sign in','العودة لتسجيل الدخول'))));
}

function passwordCard() {
  const passwordHint=t('Use a unique password with at least 12 characters, including uppercase and lowercase letters and a number.','استخدم كلمة مرور فريدة من 12 حرفًا على الأقل، تشمل أحرفًا إنجليزية كبيرة وصغيرة ورقمًا.');
  return h('section',{class:'access-card'},h('span',{class:'eyebrow muted'},t('Secure your account','حماية حسابك')),h('h2',{tabindex:'-1'},t('Choose a password','اختر كلمة مرور')),h('p',{class:'card-copy'},passwordHint),alertBox(),h('form',{class:'form',onsubmit:savePassword},field('new-password',t('New password','كلمة المرور الجديدة'),{type:'password',autocomplete:'new-password',required:true,minlength:12,maxlength:256,pattern:'(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9]).{12,256}',title:passwordHint}),field('confirm-password',t('Confirm password','تأكيد كلمة المرور'),{type:'password',autocomplete:'new-password',required:true,minlength:12,maxlength:256}),submitButton(t('Save password','حفظ كلمة المرور'))));
}

function mfaCard() {
  const enrolling = factor?.totp;
  const qr = enrolling ? (factor.totp.qr_code.startsWith('data:image/svg+xml;') ? factor.totp.qr_code : 'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent(factor.totp.qr_code)) : '';
  return h('section',{class:'access-card'},h('span',{class:'eyebrow muted'},t('Administrator security','أمان المسؤول')),h('h2',{tabindex:'-1'},enrolling?t('Set up verification','إعداد التحقق'):t('Verify it’s you','أكّد هويتك')),h('p',{class:'card-copy'},t('Administrators must verify with an authenticator before accessing staff management or private records.','على المسؤول تأكيد هويته بتطبيق المصادقة قبل الوصول لإدارة الموظفين أو البيانات الخاصة.')),alertBox(),
    enrolling&&h('div',{},h('p',{class:'mfa-detail'},t('Scan this code in your authenticator, or enter the setup key. Keep it private.','امسح الرمز بتطبيق المصادقة أو أدخل مفتاح الإعداد. احتفظ به بسرية.')),h('img',{class:'qr',src:qr,alt:t('Private authenticator setup QR code','رمز إعداد المصادقة الخاص')}),h('code',{class:'recovery-key'},factor.totp.secret)),
    factor ? h('form',{class:'form',onsubmit:verifyMfa},field('totp',t('Six-digit verification code','رمز التحقق المكوّن من ستة أرقام'),{type:'text',class:'code-input',inputmode:'numeric',pattern:'[0-9]{6}',minlength:6,maxlength:6,autocomplete:'one-time-code',required:true,dir:'ltr'}),submitButton(t('Verify and continue','تحقّق وتابع'))) : button(t('Set up authenticator','إعداد تطبيق المصادقة'),enrollMfa),
    h('p',{class:'privacy-note'},t('If you have lost access to your authenticator, contact the account owner through an approved recovery channel.','إذا فقدت الوصول لتطبيق المصادقة، تواصل مع مالك الحساب عبر قناة الاستعادة المعتمدة.')));
}

function accountGrid() {
  const items = [[t('Account','الحساب'),user.email],[t('Permissions','الصلاحيات'),roleLabel(member.role)],[t('Session security','أمان الجلسة'),assurance==='aal2'?t('Authenticator verified','تم التحقق بالمصادقة'):t('Signed in securely','تم تسجيل الدخول بأمان')]];
  return h('dl',{class:'account-grid'},items.map(([label,value])=>h('div',{class:'account-item'},h('dt',{},label),h('dd',{},value))));
}

function inviteCard() {
  return h('aside',{class:'panel invite-card'},h('span',{class:'eyebrow muted'},t('By invitation','عن طريق الدعوة')),h('h3',{},t('Welcome a team member','دعوة عضو إلى الفريق')),h('p',{class:'card-copy'},t('Invite an authorised colleague. They will receive a secure email to set up their account.','ادعُ زميلًا مخولًا. ستصله رسالة آمنة لإعداد حسابه.')),h('form',{class:'form',onsubmit:invite},field('invite-name',t('Full name','الاسم الكامل'),{required:true,minlength:2,maxlength:100,autocomplete:'off'}),field('invite-email',t('Work email','البريد الإلكتروني للعمل'),{type:'email',dir:'ltr',required:true,maxlength:254,autocomplete:'off'}),select('invite-role',t('Role','الدور'),['sales','marketing','admin'].map(r=>[r,roleLabel(r)]),'sales'),submitButton(t('Send invitation','إرسال الدعوة'))));
}

function memberRow(person) {
  const self = person.user_id === user.id;
  const name = h('input',{class:'inline-input',value:person.display_name,'aria-label':t('Staff name','اسم الموظف'),disabled:self,maxlength:100});
  const role = h('select',{class:'inline-select','aria-label':t('Staff role','دور الموظف'),disabled:self},['admin','sales','marketing'].map(r=>h('option',{value:r},roleLabel(r))));
  role.value=person.role;
  const active = h('input',{type:'checkbox',checked:person.active,disabled:self,'aria-label':t('Active access','وصول نشط')});
  return h('tr',{},h('td',{},name,self&&h('p',{class:'mfa-detail'},t('Your account','حسابك'))),h('td',{},role),h('td',{},h('label',{class:'status-check'},active,t('Active','نشط'))),h('td',{},self?h('span',{class:'muted'},'—'):h('button',{type:'button',class:'small-button',disabled:busy,onclick:()=>updateMember(person.user_id,name.value,role.value,active.checked)},t('Save','حفظ'))));
}

function adminArea() {
  return [h('div',{class:'section-head'},h('div',{},h('h2',{},t('Your team','فريقك')),h('p',{},t('Manage invitations and assigned access. Changes are recorded securely.','إدارة الدعوات والصلاحيات المحددة. تُسجّل التغييرات بأمان.'))),h('span',{class:'member-count'},`${members.length} ${t('accounts','حسابات')}`)),
    h('div',{class:'staff-layout'},staffLoadFailed?h('div',{class:'panel'},h('p',{class:'card-copy'},t('The staff list could not be loaded. Your session or permissions may have changed.','تعذّر تحميل قائمة الموظفين. ربما تغيرت الجلسة أو الصلاحيات.')),button(t('Check access again','التحقق من الوصول مجددًا'),()=>refresh())):h('div',{class:'staff-table-wrap'},h('table',{},h('thead',{},h('tr',{},[t('Name','الاسم'),t('Role','الدور'),t('Access','الوصول'),t('Action','الإجراء')].map(label=>h('th',{scope:'col'},label)))),h('tbody',{},members.map(memberRow)))),inviteCard())];
}

function workspaceNavigation(){
 const tabs=member.role==='marketing'?[['content',t('Website editor','محرر الموقع')]]:[['overview',t('Overview','نظرة عامة')],['enquiries',t('Enquiries','الاستفسارات')],['customers',t('Customers','العملاء')],...(member.role==='admin'?[['content',t('Website editor','محرر الموقع')],['catalogue',t('Packages','الباقات')],['team',t('Team','الفريق')]]:[])];
 return h('nav',{class:'workspace-nav','aria-label':t('Workspace modules','وحدات مساحة العمل')},tabs.map(([key,label])=>h('button',{type:'button',class:'small-button',id:'nav-'+key,disabled:editor.busy||crm.busy,'aria-current':section===key?'page':null,onclick:()=>{if(editor.busy||crm.busy||section===key)return;section=key;if(['content','catalogue'].includes(key))editor.open(key);else if(key!=='team')crm.open(key);render();}},label)));
}

function workspace() {
  return h('main',{id:'main',class:'stage workspace'},h('div',{class:'workspace-heading'},h('div',{},h('span',{class:'eyebrow muted'},t('Butterfly · Staff access','بترفلاي · دخول الموظفين')),h('h1',{},t('Welcome, ','مرحبًا، ')+member.display_name),h('p',{class:'caption'},t('Your private account and assigned access.','حسابك الخاص والصلاحيات المحددة لك.'))),h('span',{class:'role-badge'},roleLabel(member.role))),alertBox(),h('details',{class:'account-summary'},h('summary',{},t('Account and security','الحساب والأمان')),accountGrid()),workspaceNavigation(),
    (['overview','enquiries','customers'].includes(section)&&['admin','sales'].includes(member.role))?crm.render():((section==='content'&&['admin','marketing'].includes(member.role))||(section==='catalogue'&&member.role==='admin'))?editor.render():member.role==='admin'?adminArea():h('section',{class:'empty-state'},h('span',{class:'eyebrow muted'},t('Your workspace','مساحتك')),h('h2',{},t('Your access is ready.','وصولك جاهز.')),h('p',{},t('You are signed in with your assigned staff role. No customer or content modules are available in this release.','أنت مسجّل بصلاحيات الموظف المحددة لك. وحدات العملاء والمحتوى غير متاحة في هذا الإصدار.'))),
    h('div',{class:'section-head'},h('div',{},h('h3',{},t('Account security','أمان الحساب')),h('p',{},t('Keep your password unique. Never share access or verification codes.','استخدم كلمة مرور فريدة. لا تشارك بيانات الدخول أو رموز التحقق.'))),h('button',{type:'button',class:'text-button',onclick:sendOwnReset,disabled:busy},t('Request password reset','طلب إعادة تعيين كلمة المرور'))));
}

function render() {
  const active=document.activeElement;const focusId=active?.id;const start=active?.selectionStart;const end=active?.selectionEnd;
  document.documentElement.lang=lang;
  document.documentElement.dir=lang==='ar'?'rtl':'ltr';
  document.title=t('Butterfly | Staff access','بترفلاي | دخول الموظفين');
  root.setAttribute('aria-busy',String(checking||busy));
  const content=checking?h('main',{id:'main',class:'loading',role:'status'},t('Checking secure access…','جارٍ التحقق من الوصول الآمن…')):
    user&&member&&!passwordCallback&&(member.role!=='admin'||assurance==='aal2')?workspace():h('main',{id:'main',class:'stage auth-layout'},intro(),authCard());
  root.replaceChildren(header(),content,footer());
  if(focusId){const next=document.getElementById(focusId);if(next){next.focus({preventScroll:true});if(start!==null&&start!==undefined){try{next.setSelectionRange(start,end);}catch{/* Numeric fields have no text selection. */}}}}
}

async function act(action) {
  if(busy)return;
  busy=true;message=null;
  for(const el of root.querySelectorAll('button[type=submit]'))el.disabled=true;
  try { await action(); }
  catch { notify(t('The request could not be completed securely. Please try again.','تعذّر إكمال الطلب بأمان. حاول مجددًا.'),'error'); }
  finally {busy=false;render();}
}

async function login(event) {
  event.preventDefault();
  const data=new FormData(event.currentTarget);
  await act(async()=>{
    const {error}=await client.auth.signInWithPassword({email:String(data.get('email')).trim(),password:String(data.get('password'))});
    if(error){notify(t('We couldn’t sign you in. Check your details or request a password reset.','تعذّر تسجيل الدخول. تحقّق من بياناتك أو اطلب استعادة كلمة المرور.'),'error');return;}
    await refresh();
  });
}

async function logout() {
  await act(async()=>{
    // End access on this browser even if remote revocation is unavailable.
    const result=await Promise.race([
      client.auth.signOut({scope:'local'}).catch(()=>({error:true})),
      new Promise(resolve=>setTimeout(()=>resolve({error:true}),4000)),
    ]);
    await client.auth.stopAutoRefresh();
    for(const name of ['butterfly-staff-auth','butterfly-staff-auth-user','butterfly-staff-auth-code-verifier'])storage.removeItem(name);
    if(result.error){try{sessionStorage.setItem('butterfly-staff-logout-warning','1');}catch{/* Optional notice. */}}
    user=null;member=null;members=[];factor=null;assurance=null;passwordCallback=false;mode='login';section='overview';editor.clear();crm.clear();
    // A fresh document also discards in-memory tokens and outstanding client refresh work.
    location.replace(location.origin+import.meta.env.BASE_URL);
  });
}

async function requestReset(event) {
  event.preventDefault();
  const email=String(new FormData(event.currentTarget).get('email')).trim();
  await act(async()=>{
    const {error}=await client.auth.resetPasswordForEmail(email,{redirectTo:location.origin+import.meta.env.BASE_URL});
    if(error){notify(t('Password recovery is unavailable right now. Please try again later.','استعادة كلمة المرور غير متاحة حاليًا. حاول لاحقًا.'),'error');return;}
    notify(t('If this email is eligible, a secure reset link will arrive shortly.','إذا كان البريد مؤهلًا للاستعادة، سيصلك رابط آمن قريبًا.'));
  });
}

async function sendOwnReset() {
  await act(async()=>{
    const {error}=await client.auth.resetPasswordForEmail(user.email,{redirectTo:location.origin+import.meta.env.BASE_URL});
    if(error)throw error;
    notify(t('A secure reset link has been requested for your work email.','تم طلب رابط استعادة آمن لبريد العمل.'));
  });
}

async function savePassword(event) {
  event.preventDefault();
  const data=new FormData(event.currentTarget);
  const password=String(data.get('new-password'));
  if(password!==data.get('confirm-password')){notify(t('The passwords do not match.','كلمتا المرور غير متطابقتين.'),'error');render();return;}
  await act(async()=>{
    const {error}=await client.auth.updateUser({password});
    if(error){notify(t('The password could not be changed. Request a fresh reset link and try again.','تعذّر تغيير كلمة المرور. اطلب رابط استعادة جديدًا وحاول مجددًا.'),'error');return;}
    passwordCallback=false;
    history.replaceState(null,'',location.pathname);
    notify(t('Your password has been updated.','تم تحديث كلمة المرور.'));
    await refresh();
  });
}

async function enrollMfa() {
  await act(async()=>{
    const {data:existing,error:listError}=await client.auth.mfa.listFactors();
    if(listError)throw listError;
    for(const previous of existing.all.filter(item=>item.factor_type==='totp'&&item.status==='unverified')){
      const {error}=await client.auth.mfa.unenroll({factorId:previous.id});
      if(error)throw error;
    }
    const {data,error}=await client.auth.mfa.enroll({factorType:'totp',friendlyName:'Butterfly staff authenticator'});
    if(error)throw error;
    factor=data;
  });
}

async function verifyMfa(event) {
  event.preventDefault();
  const code=String(new FormData(event.currentTarget).get('totp'));
  await act(async()=>{
    const {error}=await client.auth.mfa.challengeAndVerify({factorId:factor.id,code});
    if(error){notify(t('The verification code was not accepted. Try the current code from your authenticator.','لم يُقبل رمز التحقق. جرّب الرمز الحالي من تطبيق المصادقة.'),'error');return;}
    factor=null;
    await refresh();
  });
}

async function invite(event) {
  event.preventDefault();
  const data=new FormData(event.currentTarget);
  await act(async()=>{
    const {error}=await client.functions.invoke('invite-staff',{body:{email:String(data.get('invite-email')).trim(),display_name:String(data.get('invite-name')).trim(),role:data.get('invite-role')}});
    if(error){notify(t('The invitation could not be sent. Check your permissions and try again.','تعذّر إرسال الدعوة. تحقّق من صلاحياتك وحاول مجددًا.'),'error');return;}
    notify(t('Invitation sent. The colleague must complete account setup before signing in.','أُرسلت الدعوة. يجب أن يكمل الزميل إعداد الحساب قبل تسجيل الدخول.'));
    await loadMembers();
  });
}

async function updateMember(id,name,role,active) {
  await act(async()=>{
    const {error}=await client.rpc('update_staff_member',{target_user_id:id,new_role:role,new_active:active,new_display_name:name.trim()});
    if(error){notify(t('Access could not be updated. Recheck your session and permissions.','تعذّر تحديث الوصول. تحقّق من جلستك وصلاحياتك.'),'error');return;}
    notify(t('Staff access updated.','تم تحديث وصول الموظف.'));
    await loadMembers();
  });
}

async function loadMembers() {
  const {data,error}=await client.from('staff_members').select('user_id,display_name,role,active,created_at,updated_at').order('display_name');
  staffLoadFailed=Boolean(error);
  members=error?[]:data;
}

async function refresh() {
  const version=++refreshVersion;
  if(!client){checking=false;render();return;}
  const {data:{user:verified},error}=await client.auth.getUser();
  if(version!==refreshVersion)return;
  if(error||!verified){
    user=null;member=null;members=[];assurance=null;factor=null;editor.clear();crm.clear();
    checking=false;
    if(error&&passwordCallback){passwordCallback=false;notify(t('This secure link has expired or is no longer valid. Request a new invitation or reset link.','انتهت صلاحية الرابط الآمن أو لم يعد صالحًا. اطلب دعوة أو رابط استعادة جديدًا.'),'error');}
    render();return;
  }
  if(user?.id!==verified.id){section='overview';editor.clear();crm.clear();}
  user=verified;
  const {data:own,error:memberError}=await client.from('staff_members').select('user_id,display_name,role,active').eq('user_id',user.id).maybeSingle();
  if(version!==refreshVersion)return;
  const previousRole=member?.role;
  member=memberError||!own?.active?null:own;
  if(previousRole!==member?.role){editor.clear();crm.clear();section=member?.role==='marketing'?'content':'overview';}
  if(!member){editor.clear();crm.clear();members=[];assurance=null;factor=null;checking=false;render();return;}
  const {data:level,error:levelError}=await client.auth.mfa.getAuthenticatorAssuranceLevel();
  if(version!==refreshVersion)return;
  assurance=levelError?null:level.currentLevel;
  if(member.role==='admin'&&assurance==='aal2'){
    // The database also checks the live session, including revoked MFA/session state.
    const {data:authorised,error:adminError}=await client.rpc('app_is_admin');
    if(version!==refreshVersion)return;
    if(adminError||!authorised){assurance='aal1';members=[];editor.clear();crm.clear();}
  }
  if(member.role==='admin'&&assurance!=='aal2'&&!passwordCallback){
    const {data:list,error:listError}=await client.auth.mfa.listFactors();
    if(version!==refreshVersion)return;
    if(listError){factor=null;notify(t('Security verification is unavailable. Please try again.','التحقق الأمني غير متاح. حاول مجددًا.'),'error');}
    else {factor=list.totp.find(f=>f.status==='verified')||factor;}
  }else if(member.role==='admin'&&assurance==='aal2'){await loadMembers();}
  else members=[];
  if(member?.role==='marketing'&&editor.kind!=='content'){section='content';editor.open('content');}
  if(member?.role==='marketing'&&section==='content'&&!editor.busy){editor.ensure?.();}
  if(member&&['admin','sales'].includes(member.role)&&!passwordCallback&&(member.role!=='admin'||assurance==='aal2')&&['overview','enquiries','customers'].includes(section)){if(crm.active!==section)crm.open(section);else crm.poll();}
  checking=false;render();
}

if(client){
  client.auth.onAuthStateChange((event)=>{
    if(event==='PASSWORD_RECOVERY'){passwordCallback=true;}
    if(event==='SIGNED_OUT'){editor.clear();crm.clear();section='overview';user=null;member=null;members=[];factor=null;assurance=null;passwordCallback=false;}
    // Auth callbacks run under a client lock; schedule subsequent client calls outside it.
    setTimeout(()=>refresh(),0);
  });
  setInterval(()=>{if(document.visibilityState==='visible'&&user&&!busy)refresh();},60000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&!busy)refresh();});
}
render();
refresh();
