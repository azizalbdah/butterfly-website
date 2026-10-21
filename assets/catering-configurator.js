/* Butterfly calculator. Uses the published catalogue when configured. */
(async function (global) {
'use strict';
const form=document.getElementById('configForm');form.inert=true;form.setAttribute('aria-busy','true');
const [pricing,site,enquiries] = await Promise.all([import('./pricing.mjs'), global.ButterflySiteReady,import('./enquiry-client.mjs')]);
if (!site?.catalogue) {
 const status=document.createElement('p');status.setAttribute('role','alert');
 status.textContent='Package estimates are temporarily unavailable. Please contact Butterfly. تعذّر تحميل أسعار الباقات مؤقتًا. يرجى التواصل مع بترفلاي.';
 document.getElementById('configForm').before(status);
 form.inert=true;form.setAttribute('aria-busy','false');
 return;
}
const model=pricing.createPricingModel(site.catalogue);
const {packages,coffeePackages,serviceTypes,addons,savouries,towers,validGuests,guestBlocks,hourRate,packageQuote,coffeeQuote,recommend,recommendCoffee,recommendService,extrasTotal}=model;
global.ButterflyCalculator={model,catalogueRevision:site.catalogue_revision};
const $=id=>document.getElementById(id);
let lang='ar',stage=1,currentService='',manual=null,lastPackage=null,result=null,recommended=null;
const state={savouries:[],towers:['','',''],extras:Object.fromEntries(addons.map(a=>[a.id,0]))};
const tr=(en,ar)=>lang==='ar'?ar:en;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>new Intl.NumberFormat(lang==='ar'?'ar-KW':'en-KW',{maximumFractionDigits:3}).format(n)+' '+tr('KD','د.ك');
const label=o=>o[lang];
const isCoffee=()=>currentService==='coffee';
const serviceName=()=>{const s=serviceTypes.find(s=>s.id===currentService);return s?label(s):'';};
const guests=()=>Number($('guestCount').value);
const requestedHours=()=>Number($('serviceHours').value);
const activePackages=()=>isCoffee()?coffeePackages:packages;
const totalExtras=()=>extrasTotal(state.extras,currentService);
const activeAddons=()=>isCoffee()?[]:addons.filter(a=>state.extras[a.id]);
const countLabel=(n,en,ar)=>n+' '+tr(en,ar);
function choiceText(id){const el=$(id);return el.selectedOptions[0]?.textContent||'';}
function option(value,en,ar,current){return '<option value="'+esc(value)+'"'+(value===current?' selected':'')+'>'+esc(tr(en,ar))+'</option>';}
function clearDraft(){$('formStatus').replaceChildren();}
function scrollToStep(id){$(id).scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});}
function showStage(next){stage=next;update();const id=next===1?'serviceStep':next===2?'guestStep':'packages';$(id).querySelector('h2').focus({preventScroll:true});scrollToStep(id);}
function selectService(value){
 if(!serviceTypes.some(s=>s.id===value))return;
 if(currentService!==value){
  currentService=value;manual=null;lastPackage=null;state.savouries=[];state.towers=['','',''];
  state.extras=Object.fromEntries(addons.map(a=>[a.id,0]));
  $('towerNeed').value='0';$('serviceHours').value='4';$('coffeeHours').value='';
  $('occasion').value=value==='wedding'?'wedding':'';
  $('extraTowers').checked=false;renderAddons();
 }
 document.querySelectorAll('input[name="serviceType"]').forEach(el=>el.checked=el.value===value);
 update();
}
function stepper(a){return '<div class="addon"><div><label for="add-'+a.id+'">'+esc(label(a))+'</label><p>'+esc(tr(a.unitEn,a.unitAr))+' <span aria-hidden="true">·</span> '+money(a.price)+'</p></div><div class="quantity"><button type="button" data-adjust="'+a.id+'" data-delta="-1" aria-label="'+esc(tr('Remove one: ','تقليل: ')+label(a))+'" '+(!state.extras[a.id]?'disabled':'')+'>−</button><input type="number" id="add-'+a.id+'" data-addon="'+a.id+'" value="'+state.extras[a.id]+'" min="0" max="99" step="1" inputmode="numeric" aria-label="'+esc(tr('Quantity: ','عدد الإضافات: ')+label(a))+'"><button type="button" data-adjust="'+a.id+'" data-delta="1" aria-label="'+esc(tr('Add one: ','إضافة: ')+label(a))+'" '+(state.extras[a.id]>=99?'disabled':'')+'>+</button></div></div>';}
function renderAddons(){for(const group of ['food','service'])$(group+'Addons').innerHTML=addons.filter(a=>a.group===group).map(stepper).join('');}
function coffeeTeam(p){
 return tr(p.baristas+' '+(p.baristas===1?'professional barista':'professional baristas')+(p.helpers?' + 1 helper':''),p.baristas===1?'باريستا محترف واحد'+(p.helpers?' + مساعد واحد':''):'2 باريستا + مساعد واحد');
}
function packageDetails(p){
 const rows=p.service==='coffee'?[
  [tr('Package capacity','سعة الباقة'),countLabel(p.guests,'guests','ضيفًا')],
  [tr('Coffee team','فريق القهوة'),coffeeTeam(p)],
  [tr('Drink menu & cup allowance','المشروبات وعدد الأكواب'),tr('Confirmed in your booking proposal','تُحدد في عرض الحجز')],
  [tr('Service duration','مدة الخدمة'),tr('Confirmed in your booking proposal','تُحدد في عرض الحجز')],
  [tr('Setup before the event','التجهيز قبل المناسبة'),tr('1 separate hour','ساعة منفصلة')],
  [tr('Personalisation','التخصيص'),tr('Subject to availability, quoted separately','بحسب التوافر وبعرض منفصل')]
 ]:[
  [tr('Savouries & canapés','الموالح والكانابيه'),countLabel(p.savouries,'pieces','قطعة')+' · '+countLabel(p.trays,'trays','صوانٍ')],
  [tr('Savoury selections','أصناف الموالح'),p.selections+' '+tr('selections · 2 trays each','أصناف · صينيتان لكل صنف')],
  [tr('Medium towers','الأبراج المتوسطة'),String(p.towers)],
  [tr('Mini tiramisu','ميني تيراميسو'),countLabel(p.tiramisu,'pieces','قطعة')],
  [tr('Mini Delight cakes','ميني ديلايت كيك'),countLabel(p.delight,'pieces','قطعة')],
  [tr('Personalised artistic pieces','قطع فنية مخصصة'),countLabel(p.artistic,'pieces','قطعة')],
  [tr('Assorted chocolate tray','محتوى صينية الشوكولاتة'),p.chocolate+' '+tr('kg','كغم')],
  [tr('Welcome drinks','مشروبات ترحيبية'),String(p.drinks)],
  [tr('Hot / cold coffee — total cups','قهوة ساخنة / باردة — إجمالي الأكواب'),String(p.coffee)],
  [tr('Arabic coffee & tea','قهوة عربية وشاي'),tr('Included','مشمول')],
  [tr('Hospitality team','فريق الضيافة'),p.staff+' '+tr('hospitality staff','موظفات ضيافة')+' · '+p.baristas+' '+tr(p.baristas===1?'barista':'baristas','باريستا')+(p.captains?' · 1 '+tr('event captain','مشرف مناسبة'):'')],
  [tr('Service + setup','الخدمة والتجهيز'),p.hours+' '+tr('service hours + 1 setup hour','ساعات خدمة + ساعة تجهيز')]
 ];
 return rows.map(([a,b])=>'<div><dt>'+esc(a)+'</dt><dd>'+esc(b)+'</dd></div>').join('');
}
function renderFlow(){
 const ready=stage===3,coffee=isCoffee(),valid=validGuests(guests());
 $('serviceStep').hidden=stage!==1;$('guestStep').hidden=stage!==2;$('packages').hidden=!ready;
 $('selectionSection').hidden=!ready;$('addonsSection').hidden=!ready||coffee;$('quote').hidden=!ready;
 $('hospitalityPreferences').hidden=coffee;$('hospitalityChoices').hidden=coffee||!result;
 $('artisticField').hidden=coffee;$('personalisationNote').hidden=coffee;$('coffeePersonalisationNote').hidden=!coffee;
 $('trayField').hidden=coffee;$('coffeeHoursField').hidden=!coffee;
 $('serviceNext').disabled=!currentService;$('guestNext').disabled=!valid;
 $('guestError').hidden=!$('guestCount').value||valid;
 $('guestServiceLabel').textContent=serviceName();
 $('guestHelp').textContent=coffee?tr('Coffee packages cover 30, 50, 100, 150 or 200 guests. We select the next suitable size; above 200 guests, our team confirms feasibility and a separate quote.','باقات القهوة لـ30 أو 50 أو 100 أو 150 أو 200 ضيف. نختار العدد المناسب التالي، ولأكثر من 200 ضيف يؤكد الفريق إمكانية التنفيذ وعرضًا منفصلًا.'):tr('Hospitality packages begin at 30 guests. Larger occasions, including weddings for up to 400 guests, receive a tailored proposal.','تبدأ باقات الضيافة من 30 ضيفًا. للمناسبات الأكبر والأعراس لغاية 400 ضيف نجهز عرضًا خاصًا.');
 $('resultSelection').textContent=serviceName()+' · '+countLabel(guests(),'guests','ضيفًا');
 $('packagesIntro').textContent=coffee?tr('Your coffee package is selected for your guest count. Compare the approved sizes below.','باقة القهوة حسب عدد ضيوفك. يمكنك مقارنة الباقات المعتمدة أدناه.'):tr('The recommended hospitality package covers your guests. You can refine towers and service hours below.','باقة الضيافة المرشحة تغطي عدد ضيوفك. يمكنك تعديل الأبراج ومدة الخدمة أدناه.');
 $('selectionIntro').textContent=coffee?tr('Share your personalisation preference, if needed. Any coffee station customisation is quoted separately.','شاركنا تفضيل التخصيص إن رغبت. تخصيص ستيشن القهوة بعرض سعر منفصل.'):result?tr('Choose your savouries, included towers and personal touches, or let our team guide the details.','اختر الموالح والأبراج المشمولة والتفاصيل الشخصية، أو اتركها لفريقنا.'):tr('Share your personalisation preferences. Our team confirms the menu, quantities, presentation and prices in your tailored proposal.','شاركنا تفضيلات التخصيص. يؤكد فريقنا المنيو والكميات والتقديم والأسعار في عرض مناسبتك الخاص.');
 $('personalisationNote').textContent=result&&!coffee?tr('Choose one item from the current Artistic Pieces collection. Personalisation of included pieces is complimentary; artwork and availability are confirmed before production. Share logo files with our team on WhatsApp.','اختر صنفًا واحدًا من مجموعة القطع الفنية الحالية. تخصيص القطع المشمولة مجاني، وتُعتمد إمكانية التنفيذ والتصميم قبل الإنتاج. أرسل ملفات الشعار لفريقنا عبر واتساب.'):tr('Personalisation, quantities and presentation are confirmed in your tailored proposal.','تُحدد تفاصيل التخصيص والكميات والتقديم في عرض مناسبتك الخاص.');
 $('quoteStepNumber').textContent=coffee?'05':'06';
 $('occasion').disabled=currentService==='wedding';
 $('equipmentNote').textContent=coffee?tr('Butterfly coffee equipment and stations remain company property and are collected after the event. Please provide suitable space, electricity and equipment access.','تبقى معدات القهوة ومحطاتها ملكًا لبترفلاي وتُسترجع بعد المناسبة. يرجى توفير مساحة مناسبة وكهرباء وإمكانية وصول لنقل المعدات.'):tr('Butterfly trays and equipment are used for the event and collected after service. Your own tray must be suitable for the chocolate selection.','تُستخدم صواني ومعدات بترفلاي أثناء المناسبة وتُسترجع بعد الخدمة. عند استخدام صينيتك الخاصة، يؤكد الفريق ملاءمتها لتشكيلة الشوكولاتة.');
 document.querySelectorAll('[data-progress]').forEach(el=>{if(Number(el.dataset.progress)===stage)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});
 $('mobileTotal').hidden=!ready;
}
function renderPackages(){
 const n=guests(),coffee=isCoffee(),minTowers=Number($('towerNeed').value);
 $('packageCards').classList.toggle('coffee-packages',coffee);
 $('packageCards').innerHTML=activePackages().map(p=>{
  const q=coffee?coffeeQuote(p,n):packageQuote(p,n,requestedHours());
  const eligible=!!q&&(coffee||p.towers>=minTowers),selected=result?.package.id===p.id,isRec=recommended?.package.id===p.id;
  const towerText=!coffee?(p.towers===1?tr('1 medium tower','برج متوسط واحد'):p.towers===2?tr('2 medium towers','برجان متوسطان'):tr('3 medium towers','3 أبراج متوسطة'))+' · '+p.hours+' '+tr('service hours','ساعات خدمة'):'';
  return '<article class="package-card '+(selected?'selected':'')+'"><div class="card-top"><span class="eyebrow">'+esc(coffee?tr(p.name,'ضيافة القهوة'):p.name)+'</span>'+(isRec?'<span class="recommend-badge">'+tr('Our recommendation','ترشيحنا لك')+'</span>':'')+'</div><h3>'+countLabel(p.guests,'guests','ضيفًا')+'</h3><p class="package-price">'+money(p.price)+'</p><p class="mini">'+esc(coffee?coffeeTeam(p):towerText)+'</p><button type="button" class="btn '+(selected?'':'outline')+'" data-package="'+p.id+'" aria-pressed="'+selected+'" '+(!eligible?'disabled':'')+'>'+tr(selected?'Selected':eligible?'Choose package':'Does not fit these choices',selected?'الباقة المختارة':eligible?'اختر الباقة':'لا تناسب هذه الاختيارات')+'</button>'+(!coffee&&eligible&&q.blocks?'<p class="mini">'+tr('With guest extension: ','مع زيادة الضيوف: ')+money(p.price+q.guestCost)+'</p>':'')+'</article>';
 }).join('');
}
function renderChoices(){
 const p=result?.package,coffee=isCoffee(),custom=stage===3&&validGuests(guests())&&!p;
 $('includedSection').hidden=!p;$('customSection').hidden=!custom;
 if(custom){
  $('customEyebrow').textContent=coffee?tr('A COFFEE PROPOSAL','عرض خاص للقهوة'):tr('WEDDINGS & LARGE EVENTS','الأعراس والمناسبات الكبرى');
  $('customHeading').textContent=tr('A proposal made for your occasion.','عرض يصمم لمناسبتك.');
  $('customCopy').textContent=coffee?tr('For more than 200 guests, our team confirms coffee station capacity, staffing, service duration and availability before quoting.','لأكثر من 200 ضيف، يؤكد فريقنا سعة ستيشن القهوة والفريق ومدة الخدمة والتوافر قبل تقديم السعر.'):tr('For occasions beyond standard package capacity, including weddings for up to 400 guests, our team plans the menu, towers, presentation and staffing around your venue.','للمناسبات التي تتجاوز سعة الباقات، ومنها الأعراس لغاية 400 ضيف، ينسق فريقنا المنيو والأبراج والتقديم وفريق الضيافة حسب المكان.');
  $('customNote').textContent=tr('Share your preferences below. Your event price is quoted separately.','أكمل تفضيلاتك أدناه. يُحدد سعر مناسبتك بعرض منفصل.');
 }
 if(!p)return;
 $('includedHeading').textContent=coffee?tr(p.name,'ضيافة القهوة'):tr(p.name,p.ar+' ريسبشن');
 $('includedDetails').innerHTML=packageDetails(p);
 $('baseQuantities').textContent=coffee?tr('Coffee-only service for up to '+p.guests+' guests, with the team listed below.','خدمة قهوة فقط لغاية '+p.guests+' ضيفًا، مع الفريق الموضح أدناه.'):tr('The quantities below are the base package for '+p.guests+' guests. '+(result.blocks?'Guest-extension quantities will be agreed with our team.':'Additional food selections are shown separately in your summary.'),'الكميات أدناه للباقة الأساسية لـ'+p.guests+' شخصًا. '+(result.blocks?'تُؤكد كميات زيادة الضيوف مع فريقنا.':'تظهر إضافات المأكولات بشكل مستقل في ملخصك.'));
 $('includedNote').textContent=coffee?tr('The booking proposal confirms drinks, cup allowance, service duration and any additional charges. Food, chocolate trays and towers are not included in coffee-only packages.','يُحدد عرض الحجز المشروبات وعدد الأكواب ومدة الخدمة وأي رسوم إضافية. لا تشمل باقات القهوة فقط المأكولات أو صواني الشوكولاتة أو الأبراج.'):tr('Chocolate weight is the content of the serving tray. Coffee cups are the combined hot and cold total. Dessert bites and printed coffee biscuit tags are optional add-ons.','وزن الشوكولاتة هو محتوى الصينية نفسها. أكواب القهوة إجمالي الساخن والبارد معًا. ديزرت بايتس وبسكويت تاق القهوة إضافات مستقلة.');
 if(coffee)return;
 const team=$('teamSelect').checked;$('savouryOptions').hidden=team;$('savouryCount').hidden=team;
 $('savouryCount').textContent=tr('Selected savoury types: ','الأصناف المختارة: ')+state.savouries.length+' / '+p.selections;
 $('savouryOptions').innerHTML=savouries.map(s=>'<label class="check-option"><input type="checkbox" data-savoury="'+s.id+'" '+(state.savouries.includes(s.id)?'checked':'')+' '+(!state.savouries.includes(s.id)&&state.savouries.length>=p.selections?'disabled':'')+'><span>'+esc(label(s))+'</span></label>').join('');
 $('towerOptions').innerHTML=Array.from({length:p.towers},(_,i)=>'<div class="field"><label for="tower-'+i+'">'+tr('Medium tower ','البرج المتوسط ')+(i+1)+'</label><select id="tower-'+i+'" data-tower="'+i+'">'+option('','Decide with our team','أحدد مع الفريق',state.towers[i])+towers.map(t=>option(t.id,t.en,t.ar,state.towers[i])).join('')+'</select></div>').join('');
}
function renderSummary(){
 const n=guests(),valid=validGuests(n),ready=stage===3,p=result?.package,coffee=isCoffee(),extra=totalExtras(),custom=ready&&valid&&!p;
 $('submitQuote').disabled=!ready||!valid;
 $('summaryTotalLabel').hidden=!ready;$('priceLines').hidden=!ready;$('summaryPersonalisation').hidden=!ready;
 $('summaryService').textContent=currentService?serviceName():'';
 $('summaryName').textContent=!ready?tr(stage===1?'Start with your service':'Tell us your guest count',stage===1?'ابدأ بنوع الخدمة':'حدد عدد ضيوفك'):p?(coffee?tr(p.name,'ضيافة القهوة'):p.name):tr('A tailored proposal','عرض يناسب مناسبتك');
 $('summaryPrice').textContent=ready?(p?money(result.total+extra):tr('Custom quotation','عرض سعر خاص')):'';
 $('mobilePrice').textContent=ready?(p?money(result.total+extra):tr('Custom quotation','عرض سعر خاص')):'';
 $('summaryGuests').textContent=ready&&valid?countLabel(n,'guests','ضيفًا'):tr('Service → guests → your package','نوع الخدمة ← عدد الضيوف ← الباقة المناسبة');
 const lines=[];
 if(p){lines.push([coffee?tr('Coffee package for '+p.guests+' guests','باقة قهوة لـ'+p.guests+' ضيفًا'):p.name,money(p.price)]);if(result.blocks)lines.push([tr('Guest extension: +','زيادة الضيوف: +')+(result.blocks*10),money(result.guestCost)]);if(result.extraHours)lines.push([tr('Additional service: ','خدمة إضافية: ')+result.extraHours+' '+tr('hour(s)','ساعة'),money(result.hourCost)]);}
 if(ready)for(const a of activeAddons())lines.push([label(a)+' × '+state.extras[a.id],money(a.price*state.extras[a.id])]);
 $('priceLines').innerHTML=lines.map(([a,b])=>'<div><dt>'+esc(a)+'</dt><dd>'+esc(b)+'</dd></div>').join('');
 $('summaryNotice').textContent=!ready?tr('Choose the service and guest count to see your recommendation and estimate.','اختر نوع الخدمة وعدد الضيوف لتظهر الباقة المناسبة والسعر التقديري.'):coffee?(p?tr('Base coffee package estimate. Drink menu, cup allowance, service duration and any extra charges are confirmed in the booking proposal.','سعر تقديري لباقة القهوة الأساسية. تُؤكد المشروبات وعدد الأكواب ومدة الخدمة وأي رسوم إضافية في عرض الحجز.'):tr('Our team checks capacity and availability before preparing your coffee proposal.','يتحقق فريقنا من السعة والتوافر قبل تجهيز عرض القهوة.')):p?tr('Estimated package and selected add-ons. Availability, extended service and venue-specific charges are confirmed before booking.','سعر تقديري للباقة والإضافات المختارة. يُؤكد التوفر وتمديد الخدمة وأي رسوم خاصة بالموقع قبل الحجز.'):tr('The base event price is quoted by our team. Any priced add-ons below are separate and are not the total event price.','يحدد فريقنا سعر المناسبة الأساسي. الإضافات المسعرة أدناه مستقلة ولا تمثل السعر الإجمالي للمناسبة.');
 $('summaryPersonalisation').textContent=coffee?tr('Coffee station personalisation is quoted separately.','تخصيص ستيشن القهوة بعرض سعر منفصل.'):p?tr('Personalisation of included artistic pieces is complimentary.','تخصيص القطع الفنية المشمولة مجاني.'):tr('Customisation details are agreed in your proposal.','تُحدد تفاصيل التخصيص في عرض مناسبتك.');
 $('summaryAction').textContent=tr(ready?'Complete my enquiry ↗':stage===1?'Choose my service ↗':'Enter my guests ↗',ready?'أكمل تفاصيل طلبي ↗':stage===1?'اختر نوع الخدمة ↗':'حدد عدد الضيوف ↗');
 $('summaryAction').href=ready?'#quote':stage===1?'#serviceStep':'#guestStep';
 $('pricedAddons').hidden=!custom||!extra;$('pricedAddons').textContent=tr('Priced add-ons only: ','الإضافات المسعرة فقط: ')+money(extra);
 $('unpricedNote').hidden=!ready||coffee||!$('extraTowers').checked;$('extensionNote').hidden=coffee||!p||!result.blocks;
 $('capacityNote').textContent=coffee?(p?tr('Covers up to '+p.guests+' guests. '+(n<p.guests?'This is the smallest approved coffee package that covers your guest count.':'The drink menu and cup allowance are confirmed in your proposal.'),'تغطي حتى '+p.guests+' ضيفًا. '+(n<p.guests?'هذه أصغر باقة قهوة معتمدة تغطي عدد ضيوفك.':'تُحدد المشروبات وعدد الأكواب في عرض الحجز.')):tr('Coffee requests above 200 guests require a separate capacity check and proposal.','طلبات القهوة لأكثر من 200 ضيف تتطلب تأكيد السعة وعرضًا منفصلًا.')):p?tr('Covers up to '+result.capacity+' guests. '+(result.blocks?'Guest extensions are charged in groups of 10 at 125 KD per group.':'Personalisation of included artistic pieces is complimentary.'),'تغطي حتى '+result.capacity+' ضيفًا. '+(result.blocks?'تُضاف زيادة الضيوف بمجموعات من 10 أشخاص بسعر 125 د.ك للمجموعة.':'تخصيص القطع الفنية المشمولة مجاني.')):tr('Hospitality beyond the standard package capacities is quoted separately, including weddings for up to 400 guests.','الضيافة التي تتجاوز سعة الباقات بعرض منفصل، ومنها الأعراس لغاية 400 ضيف.');
 $('recommendationReason').textContent=p?(manual?tr('Your selected package.','الباقة التي اخترتها.'):coffee?tr('Smallest approved coffee package covering your guest count.','أصغر باقة قهوة معتمدة تغطي عدد ضيوفك.'):tr('Lowest estimated price among hospitality packages meeting your guest count and preferences.','أقل سعر تقديري بين باقات الضيافة التي تلبي عدد ضيوفك وتفضيلاتك.')):tr('Your choices need a tailored proposal.','اختياراتك تحتاج عرضًا خاصًا.');
 $('hoursNote').textContent=p&&!coffee?tr('Includes '+p.hours+' service hours and 1 setup hour. '+(result.extraHours?result.extraHours+' additional hour(s) at '+hourRate(n)+' KD per hour.':'No additional service hours charged.'),'تشمل '+p.hours+' ساعات خدمة وساعة تجهيز. '+(result.extraHours?result.extraHours+' ساعة إضافية بسعر '+hourRate(n)+' د.ك للساعة.':'لا توجد رسوم ساعات خدمة إضافية.')):tr('Service duration and team are confirmed in your tailored proposal.','تُحدد مدة الخدمة والفريق في عرض مناسبتك الخاص.');
}
function update(reset=false){
 if(reset)manual=null;
 recommended=stage===3?recommendService(currentService,guests(),Number($('towerNeed').value),requestedHours()):null;
 const chosen=manual&&activePackages().find(p=>p.id===manual);
 const manualQuote=chosen?(isCoffee()?coffeeQuote(chosen,guests()):chosen.towers>=Number($('towerNeed').value)?packageQuote(chosen,guests(),requestedHours()):null):null;
 if(manual&&!manualQuote)manual=null;
 result=stage===3?(manualQuote||recommended):null;
 const id=result?.package.id||null;
 if(id!==lastPackage){state.savouries=[];state.towers=['','',''];lastPackage=id;$('selectionError').hidden=true;}
 renderFlow();renderPackages();renderChoices();renderSummary();clearDraft();
}
function language(next){
 lang=next;document.documentElement.lang=lang;document.documentElement.dir=lang==='ar'?'rtl':'ltr';
 document.querySelectorAll('[data-en]').forEach(el=>el.textContent=el.dataset[lang]);
 document.querySelectorAll('[data-lang]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.lang===lang)));
 document.querySelectorAll('[data-alt-en]').forEach(el=>el.alt=el.dataset[lang==='ar'?'altAr':'altEn']);
 document.querySelectorAll('[data-aria-en]').forEach(el=>el.setAttribute('aria-label',el.dataset[lang==='ar'?'ariaAr':'ariaEn']));
 document.title=tr('Butterfly Catering | Hospitality, weddings & coffee','كيترنق بترفلاي | ضيافة وأعراس وقهوة');
 try{localStorage.setItem('bf-lang',lang)}catch(e){}
 renderAddons();update();
}
function message(){
 const p=result?.package,n=guests(),coffee=isCoffee(),extra=totalExtras();
 const lines=[tr('Hello, I would like to enquire about Butterfly Catering.','السلام عليكم، أرغب بالاستفسار عن كيترنق بترفلاي.'),tr('Service: ','نوع الخدمة: ')+serviceName(),tr('Occasion: ','نوع المناسبة: ')+(choiceText('occasion')&&$('occasion').value?choiceText('occasion'):tr('To be discussed','يحدد مع الفريق')),tr('Guests: ','عدد الضيوف: ')+n];
 if(coffee){
  if(p)lines.push(tr('Coffee package: ','باقة القهوة: ')+p.guests+' '+tr('guests','ضيفًا')+' — '+money(p.price),tr('Coffee team: ','فريق القهوة: ')+coffeeTeam(p));
  else lines.push(tr('Custom coffee proposal requested. Capacity, availability and price to be confirmed.','مطلوب عرض خاص للقهوة. يُؤكد الفريق السعة والتوافر والسعر.'));
  lines.push(tr('Preferred service hours: ','مدة خدمة القهوة المطلوبة: ')+($('coffeeHours').value?$('coffeeHours').value+' '+tr('hours','ساعات'):tr('To be confirmed in proposal','تُحدد في العرض')),tr('Drink menu, cup allowance, service duration and any extension charges to be confirmed in the booking proposal. One separate setup hour is included.','تُحدد المشروبات وعدد الأكواب ومدة الخدمة وأي رسوم تمديد في عرض الحجز. تشمل الخدمة ساعة تجهيز منفصلة.'),tr('Coffee station personalisation is subject to availability and a separate quotation.','تخصيص ستيشن القهوة بحسب التوافر وبعرض سعر مستقل.'));
 }else{
  lines.push(tr('Service hours requested: ','ساعات الخدمة المطلوبة: ')+requestedHours());
  if(p){
   lines.push(tr('Package: ','الباقة: ')+p.name+' — '+money(p.price),tr('Base package quantities: ','كميات الباقة الأساسية: ')+p.guests+' '+tr('guests','شخصًا'),tr('Savouries: ','الموالح: ')+p.savouries+' '+tr('pieces','قطعة')+' / '+p.trays+' '+tr('trays','صوانٍ'),tr('Savoury selections: ','أصناف الموالح: ')+($('teamSelect').checked?tr('Team recommendation ('+p.selections+' selections)','اقتراح الفريق ('+p.selections+' أصناف)'):state.savouries.map(id=>label(savouries.find(s=>s.id===id))).join('، ')),tr('Medium towers: ','الأبراج المتوسطة: ')+state.towers.slice(0,p.towers).map((id,i)=>(i+1)+'. '+(id?label(towers.find(t=>t.id===id)):tr('Discuss with team','يحدد مع الفريق'))).join(' / '),tr('Desserts: ','الحلويات: ')+p.tiramisu+' '+tr('mini tiramisu','ميني تيراميسو')+' + '+p.delight+' '+tr('Mini Delight','ميني ديلايت')+' + '+p.artistic+' '+tr('personalised artistic pieces','قطع فنية مخصصة'),tr('Chocolate tray content: ','محتوى صينية الشوكولاتة: ')+p.chocolate+' '+tr('kg','كغم'),tr('Beverages: ','المشروبات: ')+p.drinks+' '+tr('welcome drinks','مشروبات ترحيبية')+' / '+p.coffee+' '+tr('coffee cups in total','أكواب قهوة إجمالًا')+' / '+tr('Arabic coffee & tea','قهوة عربية وشاي'),tr('Base team: ','الفريق الأساسي: ')+p.staff+' '+tr('hospitality staff','موظفات ضيافة')+' + '+p.baristas+' '+tr(p.baristas===1?'barista':'baristas','باريستا')+(p.captains?' + 1 '+tr('event captain','مشرف مناسبة'):''),tr('Included service / setup: ','الخدمة / التجهيز المشمول: ')+p.hours+' / 1 '+tr('hours','ساعات'));
   if(result.blocks)lines.push(tr('Guest extension: ','زيادة الضيوف: ')+(result.blocks*10)+' — '+money(result.guestCost)+'; '+tr('extension quantities to be confirmed','تُؤكد كميات الزيادة مع الفريق'));
   if(result.extraHours)lines.push(tr('Additional service hours: ','ساعات خدمة إضافية: ')+result.extraHours+' — '+money(result.hourCost));
  }else lines.push(tr('Custom hospitality proposal requested. Base event price to be quoted.','مطلوب عرض خاص للضيافة. السعر الأساسي للمناسبة يحدد مع الفريق.'),tr('Minimum towers requested: ','الحد الأدنى للأبراج المطلوبة: ')+($('towerNeed').value==='0'?tr('Team recommendation','اقتراح الفريق'):$('towerNeed').value));
  const active=activeAddons();lines.push(tr('Add-ons: ','الإضافات: ')+(active.length?'':tr('None','بدون')));
  for(const a of active)lines.push('- '+label(a)+' ('+tr(a.unitEn,a.unitAr)+') × '+state.extras[a.id]+' = '+money(a.price*state.extras[a.id]));
  if($('extraTowers').checked)lines.push(tr('Additional towers requested — separate quotation, excluded from estimate.','مطلوب أبراج إضافية بعرض منفصل، غير مشمولة في السعر التقديري.'));
  lines.push(tr('Artistic selection: ','صنف القطع الفنية: ')+($('artisticChoice').value.trim()||tr('Discuss current collection','يحدد من المجموعة الحالية مع الفريق')),tr('Chocolate tray: ','صينية الشوكولاتة: ')+choiceText('trayStyle'));
 }
 lines.push(p?tr('Estimated package + selected add-ons: ','السعر التقديري للباقة والإضافات: ')+money(result.total+extra):coffee?tr('Event price: custom quotation','سعر المناسبة: عرض خاص'):tr('Priced add-ons only (not event total): ','الإضافات المسعرة فقط (ليست إجمالي المناسبة): ')+money(extra),tr('Coffee preference: ','اختيار القهوة: ')+choiceText('coffeeStyle'),tr('Personalisation: ','التخصيص: ')+choiceText('personalisation')+($('personalText').value.trim()?' — '+$('personalText').value.trim():''),tr('Date: ','التاريخ: ')+($('eventDate').value||tr('To be confirmed','لم يحدد بعد')),tr('Service start time: ','وقت بدء الخدمة: ')+($('eventTime').value||tr('To be confirmed','لم يحدد بعد')),tr('Area / venue: ','المنطقة / المكان: ')+$('venue').value.trim(),tr('Contact name: ','اسم مسؤول التواصل: ')+($('contactName').value.trim()||tr('Not provided','لم يحدد')),tr('Service must finish by 11:00 PM unless otherwise agreed in writing.','تنتهي الخدمة بحلول الساعة 11 مساءً ما لم يتم الاتفاق كتابيًا على خلاف ذلك.'),tr('Notes / allergies: ','ملاحظات / حساسية غذائية: ')+($('notes').value.trim()||tr('None provided','لم تذكر')),tr('Please confirm availability, final selections, any extra charges and booking terms. This is an enquiry, not a confirmed booking.','يرجى تأكيد التوفر والاختيارات النهائية وأي رسوم إضافية وشروط الحجز. هذا استفسار وليس حجزًا مؤكدًا.'));
 return lines.join('\n');
}
function nextGuests(){if(!validGuests(guests())){$('guestCount').reportValidity();$('guestCount').focus();return;}showStage(3);}
$('serviceNext').addEventListener('click',()=>{if(currentService)showStage(2);});
$('guestNext').addEventListener('click',nextGuests);
$('guestBack').addEventListener('click',()=>showStage(1));
$('editService').addEventListener('click',()=>showStage(1));
$('editGuests').addEventListener('click',()=>showStage(2));
$('configForm').addEventListener('submit',async e=>{
 e.preventDefault();
 if(stage===1){if(currentService)showStage(2);return;}
 if(stage===2){nextGuests();return;}
 if(!validGuests(guests())){showStage(2);$('guestCount').focus();return;}
 if(!$('configForm').reportValidity())return;
 if(result&&!isCoffee()&&!$('teamSelect').checked&&state.savouries.length!==result.package.selections){$('selectionError').hidden=false;$('teamSelect').focus();return;}
 $('selectionError').hidden=true;
 if(!$('venue').value.trim()){$('venue').setCustomValidity(tr('Please enter the area or venue.','يرجى إدخال المنطقة أو المكان.'));$('venue').reportValidity();return;}
 const url='https://wa.me/96566363741?text='+encodeURIComponent(message());
 if(site.configured){
  const customer=enquiries.contactDetails('contactName');if(!customer)return;
  await enquiries.saveAndOfferWhatsApp({form:$('configForm'),status:$('formStatus'),whatsappURL:url,
   payload:{kind:'catering',service:currentService,customer,event_date:$('eventDate').value,event_time:$('eventTime').value,venue:$('venue').value.trim(),notes:$('notes').value.trim(),
    selection:{guests:guests(),hours:requestedHours(),min_towers:Number($('towerNeed').value),package_id:result?.package.id||null,extras:{...state.extras},savouries:[...state.savouries],towers:isCoffee()?[]:state.towers.slice(0,result?.package.towers||3),team_select:$('teamSelect').checked,extra_towers:$('extraTowers').checked,
     personalisation:$('personalisation').value,personal_text:$('personalText').value.trim(),artistic_choice:$('artisticChoice').value.trim(),occasion:$('occasion').value,coffee_style:$('coffeeStyle').value,coffee_hours:$('coffeeHours').value?Number($('coffeeHours').value):null,tray_style:$('trayStyle').value}},
   onWhatsApp:()=>{if(typeof global.fbq==='function')global.fbq('trackCustom','CateringEnquiryClick',{source:'catering_configurator',service:currentService});}});
  return;
 }
 window.open(url,'_blank','noopener,noreferrer');
 const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=tr('Open your prepared message on WhatsApp. Send it to request confirmation.','افتح رسالتك المجهزة في واتساب وأرسلها لطلب التأكيد.');$('formStatus').replaceChildren(a);
 if(typeof global.fbq==='function')global.fbq('trackCustom','CateringEnquiryClick',{source:'catering_configurator',service:currentService});
});
$('configForm').addEventListener('input',clearDraft);
$('configForm').addEventListener('change',clearDraft);
$('venue').addEventListener('input',e=>e.target.setCustomValidity(''));
for(const id of ['guestCount','towerNeed','serviceHours'])$(id).addEventListener(id==='guestCount'?'input':'change',()=>update(true));
$('teamSelect').addEventListener('change',()=>{$('selectionError').hidden=true;renderChoices();});
$('extraTowers').addEventListener('change',renderSummary);
document.addEventListener('change',e=>{
 if(e.target.matches('input[name="serviceType"]'))selectService(e.target.value);
 if(e.target.matches('[data-tower]'))state.towers[Number(e.target.dataset.tower)]=e.target.value;
 if(e.target.matches('[data-savoury]')&&result&&!isCoffee()){const id=e.target.dataset.savoury;if(e.target.checked&&!state.savouries.includes(id)&&state.savouries.length<result.package.selections)state.savouries.push(id);else if(!e.target.checked)state.savouries=state.savouries.filter(s=>s!==id);renderChoices();}
 if(e.target.matches('[data-addon]')&&!isCoffee()){const val=Number(e.target.value);state.extras[e.target.dataset.addon]=Number.isInteger(val)?Math.max(0,Math.min(99,val)):0;renderAddons();renderSummary();}
});
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-package],[data-adjust],[data-quick-guests]');if(!b)return;
 if(b.dataset.package&&stage===3){manual=b.dataset.package;update();}
 if(b.dataset.adjust&&!isCoffee()){const id=b.dataset.adjust;if(!Object.hasOwn(state.extras,id))return;state.extras[id]=Math.max(0,Math.min(99,state.extras[id]+Number(b.dataset.delta)));const input=$('add-'+id);input.value=state.extras[id];const container=b.closest('.quantity');container.querySelector('[data-delta="-1"]').disabled=state.extras[id]===0;container.querySelector('[data-delta="1"]').disabled=state.extras[id]===99;renderSummary();clearDraft();}
 if(b.dataset.quickGuests){selectService(b.dataset.quickOccasion==='wedding'?'wedding':'hospitality');$('guestCount').value=b.dataset.quickGuests;showStage(2);}
});
document.querySelectorAll('[data-lang]').forEach(b=>b.addEventListener('click',()=>language(b.dataset.lang)));
const parts=new Intl.DateTimeFormat('en',{timeZone:'Asia/Kuwait',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
const dm=Object.fromEntries(parts.map(p=>[p.type,p.value]));$('eventDate').min=dm.year+'-'+dm.month+'-'+dm.day;
$('year').textContent=new Date().getFullYear();try{if(localStorage.getItem('bf-lang')==='en')lang='en';}catch(e){}
if(site.configured)enquiries.mountContactFields(form,'contactName');
language(lang);
form.inert=false;form.setAttribute('aria-busy','false');
if('IntersectionObserver'in window&&!matchMedia('(prefers-reduced-motion:reduce)').matches){document.documentElement.classList.add('motion');const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('visible');io.unobserve(e.target);}}),{threshold:.04});document.querySelectorAll('.reveal').forEach(el=>io.observe(el));}
})(typeof window!=='undefined'?window:globalThis);
