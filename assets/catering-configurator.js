/* Butterfly Catering V3.2. Catalogue-approved data, October 2026. */
(function (global) {
'use strict';
const packages = [
 {id:'signature',name:'Signature Reception',ar:'سيغنتشر',guests:30,max:40,price:475,savouries:120,trays:4,selections:2,towers:1,tiramisu:15,delight:15,artistic:15,chocolate:1.25,drinks:35,coffee:35,baristas:1,staff:3,captains:0,hours:4},
 {id:'grand',name:'Grand Reception',ar:'غراند',guests:50,max:70,price:650,savouries:200,trays:6,selections:3,towers:2,tiramisu:25,delight:25,artistic:15,chocolate:2,drinks:55,coffee:55,baristas:1,staff:4,captains:0,hours:4},
 {id:'prestige',name:'Prestige Reception',ar:'بريستيج',guests:75,max:95,price:995,savouries:300,trays:10,selections:5,towers:3,tiramisu:40,delight:40,artistic:30,chocolate:3,drinks:80,coffee:80,baristas:2,staff:5,captains:1,hours:5}
];
const addons = [
 {id:'canapes',en:'Assorted savouries & canapés',ar:'موالح وكانابيه مشكلة',unitEn:'30 pieces',unitAr:'30 قطعة',price:22,group:'food'},
 {id:'tiramisu',en:'Mini tiramisu',ar:'ميني تيراميسو',unitEn:'12 pieces',unitAr:'12 قطعة',price:22,group:'food'},
 {id:'delight',en:'Mini Delight cakes',ar:'ميني ديلايت كيك',unitEn:'12 pieces',unitAr:'12 قطعة',price:28,group:'food'},
 {id:'bites',en:'Dessert bites',ar:'ديزرت بايتس',unitEn:'20 pieces',unitAr:'20 قطعة',price:22,group:'food'},
 {id:'artistic',en:'Personalised artistic pieces',ar:'قطع فنية مخصصة إضافية',unitEn:'15 pieces',unitAr:'15 قطعة',price:25,group:'food'},
 {id:'chocolateHalf',en:'Assorted chocolate',ar:'شوكولاتة مشكلة',unitEn:'0.5 kg',unitAr:'0.5 كغم',price:25,group:'food'},
 {id:'chocolateKg',en:'Assorted chocolate',ar:'شوكولاتة مشكلة',unitEn:'1 kg',unitAr:'1 كغم',price:45,group:'food'},
 {id:'biscuits',en:'Personalised coffee biscuit tags',ar:'بسكويت تاق للقهوة بطباعة مخصصة',unitEn:'12 pieces',unitAr:'12 قطعة',price:7,group:'food'},
 {id:'staff',en:'Additional hospitality staff',ar:'موظفة ضيافة إضافية',unitEn:'1 team member',unitAr:'موظفة واحدة',price:20,group:'service'},
 {id:'barista',en:'Additional barista',ar:'باريستا إضافي',unitEn:'1 barista',unitAr:'باريستا واحد',price:30,group:'service'},
 {id:'captain',en:'Additional event captain',ar:'مشرف مناسبة إضافي',unitEn:'1 event captain',unitAr:'مشرف واحد',price:65,group:'service'}
];
const savouries=[{id:'vine',en:'Vine leaves & musakhan',ar:'ورق عنب ومسخن'},{id:'tarts',en:'Savoury tarts',ar:'تارت مالح'},{id:'sable',en:'Savoury sablé',ar:'موالح سابليه'},{id:'canapes',en:'Assorted canapés',ar:'كانابيه مشكلة'},{id:'other',en:'Another current selection — agree with our team',ar:'صنف آخر من القائمة الحالية — يحدد مع الفريق'}];
const towers=[{id:'eclair',en:'Éclair',ar:'إكلير'},{id:'macaron',en:'Macaron',ar:'ماكرون'},{id:'madeleine',en:'Madeleine',ar:'مادلين'},{id:'chocolate',en:'Chocolate',ar:'شوكولاتة'}];
function validGuests(n){return Number.isInteger(n)&&n>=1&&n<=400;}
function guestBlocks(p,n){return Math.max(0,Math.ceil((n-p.guests)/10));}
function hourRate(n){return n<=50?45:60;}
function packageQuote(p,n,hours){if(!validGuests(n)||n>p.max)return null;const blocks=guestBlocks(p,n);const extraHours=Math.max(0,hours-p.hours);return {package:p,blocks,capacity:p.guests+blocks*10,guestCost:blocks*125,extraHours,hourCost:extraHours*hourRate(n),total:p.price+blocks*125+extraHours*hourRate(n)};}
function recommend(n,minTowers=0,hours=4){if(!validGuests(n))return null;const candidates=packages.filter(p=>p.towers>=minTowers).map(p=>packageQuote(p,n,hours)).filter(Boolean);return candidates.sort((a,b)=>a.total-b.total||a.package.guests-b.package.guests)[0]||null;}
function extrasTotal(qty){return addons.reduce((sum,a)=>sum+a.price*(Number.isInteger(qty[a.id])&&qty[a.id]>0?qty[a.id]:0),0);}
const model={packages,addons,savouries,towers,validGuests,guestBlocks,hourRate,packageQuote,recommend,extrasTotal};
if(typeof module!=='undefined'&&module.exports)module.exports=model;
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);let lang='ar',manual=null,lastPackage=null;
const state={savouries:[],towers:['','',''],extras:Object.fromEntries(addons.map(a=>[a.id,0]))};
let result=null,recommended=null;
const tr=(en,ar)=>lang==='ar'?ar:en;const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>new Intl.NumberFormat(lang==='ar'?'ar-KW':'en-KW',{maximumFractionDigits:3}).format(n)+' '+tr('KD','د.ك');
const label=o=>o[lang];const countLabel=(n,en,ar)=>n+' '+tr(en,ar);
function guests(){return Number($('guestCount').value);}
function requestedHours(){return Number($('serviceHours').value);}
function choiceText(id){const el=$(id);return el.selectedOptions[0]?.textContent||'';}
function option(value,en,ar,current){return '<option value="'+esc(value)+'"'+(value===current?' selected':'')+'>'+esc(tr(en,ar))+'</option>';}
function setText(id,en,ar){$(id).textContent=tr(en,ar);}
function stepper(a){return '<div class="addon"><div><label for="add-'+a.id+'">'+esc(label(a))+'</label><p>'+esc(tr(a.unitEn,a.unitAr))+' <span aria-hidden="true">·</span> '+money(a.price)+'</p></div><div class="quantity"><button type="button" data-adjust="'+a.id+'" data-delta="-1" aria-label="'+esc(tr('Remove one: ','تقليل: ')+label(a))+'" '+(!state.extras[a.id]?'disabled':'')+'>−</button><input type="number" id="add-'+a.id+'" data-addon="'+a.id+'" value="'+state.extras[a.id]+'" min="0" max="99" step="1" inputmode="numeric" aria-label="'+esc(tr('Quantity: ','عدد الإضافات: ')+label(a))+'"><button type="button" data-adjust="'+a.id+'" data-delta="1" aria-label="'+esc(tr('Add one: ','إضافة: ')+label(a))+'" '+(state.extras[a.id]>=99?'disabled':'')+'>+</button></div></div>';}
function renderAddons(){for(const group of ['food','service'])$(group+'Addons').innerHTML=addons.filter(a=>a.group===group).map(stepper).join('');}
function packageDetails(p){const rows=[
 [tr('Savouries & canapés','الموالح والكانابيه'),countLabel(p.savouries,'pieces','قطعة')+' · '+countLabel(p.trays,'trays','صوانٍ')],
 [tr('Savoury selections','أصناف الموالح'),p.selections+' '+tr('selections · 2 trays each','أصناف · صينيتان لكل صنف')],
 [tr('Medium towers','أبراج متوسطة'),String(p.towers)],
 [tr('Mini tiramisu','ميني تيراميسو'),countLabel(p.tiramisu,'pieces','قطعة')],
 [tr('Mini Delight cakes','ميني ديلايت كيك'),countLabel(p.delight,'pieces','قطعة')],
 [tr('Personalised artistic pieces','قطع فنية مخصصة'),countLabel(p.artistic,'pieces','قطعة')],
 [tr('Assorted chocolate tray','محتوى صينية الشوكولاتة'),p.chocolate+' '+tr('kg','كغم')],
 [tr('Welcome drinks','مشروبات ترحيبية'),String(p.drinks)],
 [tr('Hot / cold coffee — total cups','قهوة ساخنة / باردة — إجمالي الأكواب'),String(p.coffee)],
 [tr('Arabic coffee & tea','قهوة عربية وشاي'),tr('Included','مشمول')],
 [tr('Hospitality team','فريق الضيافة'),p.staff+' '+tr('hospitality staff','موظفات ضيافة')+' · '+p.baristas+' '+tr('barista(s)','باريستا')+(p.captains?' · 1 '+tr('event captain','مشرف مناسبة'):'')],
 [tr('Service + setup','الخدمة والتجهيز'),p.hours+' '+tr('service hours + 1 setup hour','ساعات خدمة + ساعة تجهيز')]
 ];return rows.map(r=>'<div><dt>'+esc(r[0])+'</dt><dd>'+esc(r[1])+'</dd></div>').join('');}
function renderPackages(){
 const n=guests(),hours=requestedHours(),minTowers=Number($('towerNeed').value);
 $('packageCards').innerHTML=packages.map(p=>{const q=packageQuote(p,n,hours),eligible=!!q&&p.towers>=minTowers;const selected=result?.package.id===p.id;const isRec=recommended?.package.id===p.id;
 return '<article class="package-card '+(p.id==='grand'?'grand ':'')+(selected?'selected':'')+'"><div class="card-top"><span class="eyebrow">'+esc(p.name)+'</span>'+(isRec?'<span class="recommend-badge">'+tr('Our recommendation','ترشيحنا لك')+'</span>':'')+'</div><h3>'+countLabel(p.guests,'guests','شخصًا')+'</h3><p class="package-price">'+money(p.price)+'</p><p class="mini">'+p.towers+' '+tr('medium tower(s)','أبراج متوسطة')+' · '+p.hours+' '+tr('service hours','ساعات خدمة')+'</p><button type="button" class="btn '+(selected?'':'outline')+'" data-package="'+p.id+'" aria-pressed="'+selected+'" '+(!eligible?'disabled':'')+'>'+tr(selected?'Selected':eligible?'Choose package':'Does not fit these choices',selected?'الباقة المختارة':eligible?'اختر الباقة':'لا تناسب هذه الاختيارات')+'</button>'+(eligible&&q.blocks?'<p class="mini">'+tr('With guest extension: ','مع زيادة الضيوف: ')+money(p.price+q.guestCost)+'</p>':'')+'</article>';
 }).join('');
}
function renderChoices(){
 const p=result?.package,custom=validGuests(guests())&&!p;
 $('includedSection').hidden=!p;$('selectionSection').hidden=!p;$('customSection').hidden=!custom;
 if(!p)return;
 $('includedHeading').textContent=tr(p.name,p.ar+' ريسبشن');$('includedDetails').innerHTML=packageDetails(p);
 $('baseQuantities').textContent=tr('The quantities below are the base package for '+p.guests+' guests. '+(result.blocks?'Guest-extension quantities will be agreed with our team.':'Additional food selections are shown separately in your summary.'),'الكميات أدناه للباقة الأساسية لـ'+p.guests+' شخصًا. '+(result.blocks?'تُؤكد كميات زيادة الضيوف مع فريقنا.':'تظهر إضافات المأكولات بشكل مستقل في ملخصك.'));
 const team=$('teamSelect').checked;$('savouryOptions').hidden=team;
 $('savouryCount').textContent=tr('Selected savoury types: ','الأصناف المختارة: ')+state.savouries.length+' / '+p.selections;
 $('savouryOptions').innerHTML=savouries.map(s=>'<label class="check-option"><input type="checkbox" data-savoury="'+s.id+'" '+(state.savouries.includes(s.id)?'checked':'')+' '+(!state.savouries.includes(s.id)&&state.savouries.length>=p.selections?'disabled':'')+'><span>'+esc(label(s))+'</span></label>').join('');
 $('towerOptions').innerHTML=Array.from({length:p.towers},(_,i)=>'<div class="field"><label for="tower-'+i+'">'+tr('Medium tower ','البرج المتوسط ')+(i+1)+'</label><select id="tower-'+i+'" data-tower="'+i+'">'+option('','Decide with our team','أحدد مع الفريق',state.towers[i])+towers.map(t=>option(t.id,t.en,t.ar,state.towers[i])).join('')+'</select></div>').join('');
}
function renderSummary(){
 const n=guests(),valid=model.validGuests(n),p=result?.package,extra=extrasTotal(state.extras),custom=valid&&!p;
 $('guestError').hidden=valid;$('submitQuote').disabled=!valid;$('mobilePrice').textContent=valid?(p?money(result.total+extra):tr('Custom quotation','عرض سعر خاص')):tr('Choose guest count','حدد عدد الضيوف');
 $('summaryName').textContent=p?p.name:tr(custom?'A tailored event':'Start with your guests',custom?'مناسبة بعرض خاص':'ابدأ بعدد ضيوفك');
 $('summaryPrice').textContent=p?money(result.total+extra):(custom?tr('Custom quotation','عرض سعر خاص'):'—');
 $('summaryGuests').textContent=valid?countLabel(n,'guests','ضيفًا'):tr('Enter 1–400 guests','أدخل عددًا من 1 إلى 400');
 const lines=[];
 if(p){lines.push([p.name,money(p.price)]);if(result.blocks)lines.push([tr('Guest extension: +','زيادة الضيوف: +')+(result.blocks*10),money(result.guestCost)]);if(result.extraHours)lines.push([tr('Additional service: ','خدمة إضافية: ')+result.extraHours+' '+tr('hour(s)','ساعة'),money(result.hourCost)]);}
 for(const a of addons)if(state.extras[a.id])lines.push([label(a)+' × '+state.extras[a.id],money(a.price*state.extras[a.id])]);
 $('priceLines').innerHTML=lines.map(([a,b])=>'<div><dt>'+esc(a)+'</dt><dd>'+esc(b)+'</dd></div>').join('');
 $('summaryNotice').textContent=p?tr('Estimated package and selected add-ons. Availability, extended service and any venue-specific charges are confirmed before booking.','سعر تقديري للباقة والإضافات المختارة. يُؤكد التوفر وتمديد الخدمة وأي رسوم خاصة بالموقع قبل الحجز.'):tr('The base event price is quoted by our team. Any priced add-ons below are separate; they are not the total event price.','يُحدد فريقنا سعر المناسبة الأساسي. الإضافات المسعرة أدناه مستقلة، ولا تمثل السعر الإجمالي للمناسبة.');
 $('pricedAddons').hidden=!custom||!extra;$('pricedAddons').textContent=tr('Priced add-ons only: ','الإضافات المسعرة فقط: ')+money(extra);
 $('unpricedNote').hidden=!$('extraTowers').checked;
 $('extensionNote').hidden=!p||!result.blocks;
 $('capacityNote').textContent=p?tr('Covers up to '+result.capacity+' guests. '+(result.blocks?'Guest extensions are charged in groups of 10 at 125 KD per group.':'Personalisation of the included artistic pieces is complimentary.'),'تغطي حتى '+result.capacity+' ضيفًا. '+(result.blocks?'تُضاف زيادة الضيوف بمجموعات من 10 أشخاص، بسعر 125 د.ك للمجموعة.':'تخصيص القطع الفنية المشمولة في الباقة دون رسوم إضافية.')):tr('For guest counts outside standard package capacities, including events for 100–400 guests, we prepare a tailored proposal.','للأعداد التي تتجاوز سعة الباقات، ومنها مناسبات 100–400 ضيف، نجهز عرضًا خاصًا.');
 const why=p?(manual?tr('Your selected package.','الباقة التي اخترتها.'):tr('Lowest estimated price among packages meeting your guest count, tower preference and service duration.','أقل سعر تقديري بين الباقات التي تلبي عدد ضيوفك واحتياج الأبراج ومدة الخدمة.')):tr('Your choices need a tailored proposal. No standard package price is applied.','اختياراتك تحتاج عرضًا خاصًا؛ لا يُطبق عليها سعر باقة قياسية.');
 $('recommendationReason').textContent=valid?why:'';
 $('hoursNote').textContent=p?tr('Includes '+p.hours+' service hours and 1 setup hour. '+(result.extraHours?result.extraHours+' additional hour(s) at '+hourRate(n)+' KD per hour.':'No additional service hours charged.'),'تشمل '+p.hours+' ساعات خدمة وساعة تجهيز. '+(result.extraHours?result.extraHours+' ساعة إضافية بسعر '+hourRate(n)+' د.ك للساعة.':'لا توجد رسوم ساعات خدمة إضافية.')):tr('Service duration and team are agreed in your custom proposal.','تُحدد مدة الخدمة والفريق ضمن عرض مناسبتك الخاص.');
}
function update(reset=false){
 if(reset)manual=null;const n=guests(),h=requestedHours(),min=Number($('towerNeed').value);recommended=recommend(n,min,h);
 const chosen=manual&&packages.find(p=>p.id===manual);result=chosen&&chosen.towers>=min?packageQuote(chosen,n,h):recommended;
 if(!result)manual=null;
 const id=result?.package.id||null;
 if(id!==lastPackage){state.savouries=[];state.towers=['','',''];lastPackage=id;$('selectionError').hidden=true;}
 renderPackages();renderChoices();renderSummary();$('formStatus').replaceChildren();
}
function language(next){
 lang=next;document.documentElement.lang=lang;document.documentElement.dir=lang==='ar'?'rtl':'ltr';
 document.querySelectorAll('[data-en]').forEach(el=>el.textContent=el.dataset[lang]);
 document.querySelectorAll('[data-lang]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.lang===lang)));
 document.querySelectorAll('[data-alt-en]').forEach(el=>el.alt=el.dataset[lang==='ar'?'altAr':'altEn']);
 document.querySelectorAll('[data-aria-en]').forEach(el=>el.setAttribute('aria-label',el.dataset[lang==='ar'?'ariaAr':'ariaEn']));
 document.title=tr('Butterfly Catering | Find your perfect package','كيترنق بترفلاي | اختر الباقة المناسبة لمناسبتك');
 try{localStorage.setItem('bf-lang',lang)}catch(e){}renderAddons();update();
}
function message(){
 const p=result?.package,n=guests(),extra=extrasTotal(state.extras);const lines=[tr('Hello, I would like to enquire about Butterfly Catering.','السلام عليكم، أرغب بالاستفسار عن كيترنق بترفلاي.'),tr('Occasion: ','نوع المناسبة: ')+choiceText('occasion'),tr('Guests: ','عدد الضيوف: ')+n,tr('Service hours requested: ','ساعات الخدمة المطلوبة: ')+requestedHours()];
 if(p){lines.push(tr('Package: ','الباقة: ')+p.name+' — '+money(p.price),tr('Base package quantities: ','كميات الباقة الأساسية: ')+p.guests+' '+tr('guests','شخصًا'),tr('Savouries: ','الموالح: ')+p.savouries+' '+tr('pieces','قطعة')+' / '+p.trays+' '+tr('trays','صوانٍ'),tr('Savoury selections: ','أصناف الموالح: ')+($('teamSelect').checked?tr('Team recommendation ('+p.selections+' selections)','اقتراح الفريق ('+p.selections+' أصناف)'):state.savouries.map(id=>label(savouries.find(s=>s.id===id))).join('، ')),tr('Medium towers: ','الأبراج المتوسطة: ')+state.towers.slice(0,p.towers).map((id,i)=>(i+1)+'. '+(id?label(towers.find(t=>t.id===id)):tr('Discuss with team','يحدد مع الفريق'))).join(' / '),tr('Desserts: ','الحلويات: ')+p.tiramisu+' '+tr('mini tiramisu','ميني تيراميسو')+' + '+p.delight+' '+tr('Mini Delight','ميني ديلايت')+' + '+p.artistic+' '+tr('personalised artistic pieces','قطع فنية مخصصة'),tr('Chocolate tray content: ','محتوى صينية الشوكولاتة: ')+p.chocolate+' '+tr('kg','كغم'),tr('Beverages: ','المشروبات: ')+p.drinks+' '+tr('welcome drinks','مشروبًا ترحيبيًا')+' / '+p.coffee+' '+tr('coffee cups in total','كوب قهوة إجمالًا')+' / '+tr('Arabic coffee & tea','قهوة عربية وشاي'),tr('Base team: ','الفريق الأساسي: ')+p.staff+' '+tr('hospitality staff','موظفات ضيافة')+' + '+p.baristas+' '+tr('barista(s)','باريستا')+(p.captains?' + 1 '+tr('event captain','مشرف مناسبة'):''),tr('Included service / setup: ','الخدمة / التجهيز المشمول: ')+p.hours+' / 1 '+tr('hours','ساعات'));
 if(result.blocks)lines.push(tr('Guest extension: ','زيادة الضيوف: ')+(result.blocks*10)+' — '+money(result.guestCost)+'; '+tr('extension quantities to be confirmed','تُؤكد كميات الزيادة مع الفريق'));
 if(result.extraHours)lines.push(tr('Additional service hours: ','ساعات خدمة إضافية: ')+result.extraHours+' — '+money(result.hourCost));
 }else lines.push(tr('Custom proposal requested. Base event price to be quoted.','مطلوب عرض خاص. السعر الأساسي للمناسبة يحدد مع الفريق.'),tr('Minimum towers requested: ','الحد الأدنى للأبراج المطلوبة: ')+($('towerNeed').value==='0'?tr('Team recommendation','اقتراح الفريق'):$('towerNeed').value));
 const active=addons.filter(a=>state.extras[a.id]);lines.push(tr('Add-ons: ','الإضافات: ')+(active.length?'':tr('None','بدون إضافات')));for(const a of active)lines.push('- '+label(a)+' ('+tr(a.unitEn,a.unitAr)+') × '+state.extras[a.id]+' = '+money(a.price*state.extras[a.id]));
 if($('extraTowers').checked)lines.push(tr('Additional towers requested — separate quotation, excluded from estimate.','مطلوب أبراج إضافية — بعرض منفصل، غير مشمولة في السعر التقديري.'));
 lines.push(p?tr('Estimated package + selected add-ons: ','السعر التقديري للباقة والإضافات: ')+money(result.total+extra):tr('Priced add-ons only (not event total): ','الإضافات المسعرة فقط (ليست إجمالي المناسبة): ')+money(extra),tr('Coffee preference: ','اختيار القهوة: ')+choiceText('coffeeStyle'),tr('Artistic selection: ','صنف القطع الفنية: ')+($('artisticChoice').value.trim()||tr('Discuss current collection','يحدد من المجموعة الحالية مع الفريق')),tr('Personalisation: ','التخصيص: ')+choiceText('personalisation')+($('personalText').value.trim()?' — '+$('personalText').value.trim():''),tr('Chocolate tray: ','صينية الشوكولاتة: ')+choiceText('trayStyle'),tr('Date: ','التاريخ: ')+($('eventDate').value||tr('To be confirmed','لم يحدد بعد')),tr('Service start time: ','وقت بدء الخدمة: ')+($('eventTime').value||tr('To be confirmed','لم يحدد بعد')),tr('Area / venue: ','المنطقة / المكان: ')+$('venue').value.trim(),tr('Contact name: ','اسم مسؤول التواصل: ')+($('contactName').value.trim()||tr('Not provided','لم يحدد')),tr('Service must finish by 11:00 PM unless otherwise agreed in writing.','تنتهي الخدمة بحلول الساعة 11 مساءً ما لم يتم الاتفاق كتابيًا على خلاف ذلك.'),tr('Notes / allergies: ','ملاحظات / حساسية غذائية: ')+($('notes').value.trim()||tr('None provided','لم تذكر')),tr('Please confirm availability, selections, guest-extension quantities, venue charges and booking terms. This is an enquiry, not a confirmed booking.','يرجى تأكيد التوفر والأصناف وكميات زيادة الضيوف ورسوم الموقع وشروط الحجز. هذا استفسار وليس حجزًا مؤكدًا.'));return lines.join('\n');
}
$('configForm').addEventListener('submit',e=>{
 e.preventDefault();if(!model.validGuests(guests())){$('guestCount').focus();return;}
 if(!$('configForm').reportValidity())return;
 if(result&&!$('teamSelect').checked&&state.savouries.length!==result.package.selections){$('selectionError').hidden=false;$('teamSelect').focus();return;}$('selectionError').hidden=true;
 if(!$('venue').value.trim()){$('venue').setCustomValidity(tr('Please enter the area or venue.','يرجى إدخال المنطقة أو المكان.'));$('venue').reportValidity();return;}
 const url='https://wa.me/96566363741?text='+encodeURIComponent(message());window.open(url,'_blank','noopener,noreferrer');
 const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=tr('Open your prepared message on WhatsApp. Send it to request confirmation.','افتح رسالتك المجهزة في واتساب وأرسلها لطلب التأكيد.');$('formStatus').replaceChildren(a);
 if(typeof global.fbq==='function')global.fbq('trackCustom','CateringEnquiryClick',{source:'catering_configurator'});
});
$('venue').addEventListener('input',e=>e.target.setCustomValidity(''));
for(const id of ['guestCount','towerNeed','serviceHours'])$(id).addEventListener(id==='guestCount'?'input':'change',()=>update(true));
$('teamSelect').addEventListener('change',()=>{$('selectionError').hidden=true;renderChoices();});
$('extraTowers').addEventListener('change',renderSummary);
document.addEventListener('change',e=>{
 if(e.target.matches('[data-tower]'))state.towers[Number(e.target.dataset.tower)]=e.target.value;
 if(e.target.matches('[data-savoury]')){const id=e.target.dataset.savoury;if(e.target.checked&&!state.savouries.includes(id)&&state.savouries.length<result.package.selections)state.savouries.push(id);else if(!e.target.checked)state.savouries=state.savouries.filter(s=>s!==id);renderChoices();}
 if(e.target.matches('[data-addon]')){const val=Number(e.target.value);state.extras[e.target.dataset.addon]=Number.isInteger(val)?Math.max(0,Math.min(99,val)):0;renderAddons();renderSummary();}
});
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-package],[data-adjust],[data-quick-guests]');if(!b)return;
 if(b.dataset.package){manual=b.dataset.package;update();}
 if(b.dataset.adjust){const id=b.dataset.adjust;state.extras[id]=Math.max(0,Math.min(99,state.extras[id]+Number(b.dataset.delta)));const input=$('add-'+id);input.value=state.extras[id];const container=b.closest('.quantity');container.querySelector('[data-delta="-1"]').disabled=state.extras[id]===0;container.querySelector('[data-delta="1"]').disabled=state.extras[id]===99;renderSummary();}
 if(b.dataset.quickGuests){$('guestCount').value=b.dataset.quickGuests;if(b.dataset.quickOccasion)$('occasion').value=b.dataset.quickOccasion;update(true);$('builder').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});}
});
document.querySelectorAll('[data-lang]').forEach(b=>b.addEventListener('click',()=>language(b.dataset.lang)));
const parts=new Intl.DateTimeFormat('en',{timeZone:'Asia/Kuwait',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const dm=Object.fromEntries(parts.map(p=>[p.type,p.value]));$('eventDate').min=dm.year+'-'+dm.month+'-'+dm.day;
$('year').textContent=new Date().getFullYear();try{if(localStorage.getItem('bf-lang')==='en')lang='en'}catch(e){}language(lang);
if('IntersectionObserver'in window&&!matchMedia('(prefers-reduced-motion:reduce)').matches){document.documentElement.classList.add('motion');const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('visible');io.unobserve(e.target)}}),{threshold:.04});document.querySelectorAll('.reveal').forEach(el=>io.observe(el));}
})(typeof window!=='undefined'?window:globalThis);

