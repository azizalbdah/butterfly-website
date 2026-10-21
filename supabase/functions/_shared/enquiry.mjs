import {createPricingModel} from '../../../assets/pricing.mjs';

export class ValidationError extends Error {name='ValidationError';}
const reject=message=>{throw new ValidationError(message);};
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export const validUUID=value=>typeof value==='string'&&uuid.test(value);
function object(value,allowed,label){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!allowed.includes(key)))reject('Invalid '+label+'.');
 return value;
}
function text(value,label,maximum,required=false,lines=false){
 if(value===undefined||value===null)value='';
 if(typeof value!=='string'||value.length>maximum||(lines?/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/:/[\x00-\x1F\x7F]/).test(value))reject('Check '+label+'.');
 const result=value.normalize('NFKC').trim();
 if(result.length>maximum)reject('Check '+label+'.');
 if(required&&!result)reject(label+' is required.');
 return result;
}
function number(value,label,min,max,integer=false){
 if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max||(integer&&!Number.isInteger(value)))reject('Check '+label+'.');
 return value;
}
function boolean(value,label,fallback=false){if(value===undefined)return fallback;if(typeof value!=='boolean')reject('Check '+label+'.');return value;}
function choice(value,values,label,fallback=''){if(value===undefined)value=fallback;if(typeof value!=='string'||!values.includes(value))reject('Check '+label+'.');return value;}
export function normalizePhone(value){
 const raw=text(value,'phone number',40);
 if(!raw)return '';
 if(!/^\+?[0-9 ()-]+$/.test(raw))reject('Enter a valid phone number.');
 let phone=raw.replace(/[ ()-]/g,'');
 if(phone.startsWith('00'))phone='+'+phone.slice(2);
 else if(!phone.startsWith('+'))phone=phone.length===8?'+965'+phone:'+'+phone;
 if(!/^\+[1-9][0-9]{7,14}$/.test(phone))reject('Enter a valid phone number.');
 return phone;
}
export function normalizeEmail(value){
 const email=text(value,'email address',254).toLowerCase();
 if(email&&!/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}$/.test(email))reject('Enter a valid email address.');
 return email;
}
export function kuwaitDay(date=new Date()){
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en',{timeZone:'Asia/Kuwait',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date).map(p=>[p.type,p.value]));
 return parts.year+'-'+parts.month+'-'+parts.day;
}
function eventDate(value,today){
 const date=text(value,'event date',10);
 if(!date)return '';
 if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||Number.isNaN(Date.parse(date+'T00:00:00Z'))||new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date||date<today)reject('Choose today or a valid future event date.');
 return date;
}
const packageIDs=['signature','grand','prestige','coffee30','coffee50','coffee100','coffee150','coffee200'];
const addonIDs=['canapes','tiramisu','delight','bites','artistic','chocolateHalf','chocolateKg','biscuits','staff','barista','captain'];
const savouryIDs=['vine','tarts','sable','canapes','other'];
const towerIDs=['','eclair','macaron','madeleine','chocolate'];
export function normalizeSubmission(body,today=kuwaitDay()){
 object(body,['action','request_key','kind','catalogue_revision','customer','service','event_date','event_time','venue','notes','selection','corporate','website'],'submission');
 if(body.action!=='submit'||!validUUID(body.request_key)||!validUUID(body.catalogue_revision))reject('Invalid submission reference.');
 if(text(body.website,'website',100))reject('Submission validation failed.');
 const kind=choice(body.kind,['catering','corporate'],'enquiry type');
 const service=choice(body.service,kind==='corporate'?['corporate']:['hospitality','wedding','coffee'],'service');
 const customer=object(body.customer,['name','phone','email','company'],'contact');
 const contact={name:text(customer.name,'contact name',120,kind==='corporate').replace(/\s+/g,' '),phone:normalizePhone(customer.phone),email:normalizeEmail(customer.email),company:text(customer.company,'company',160,kind==='corporate').replace(/\s+/g,' ')};
 if(!contact.phone&&!contact.email)reject('A phone number or email address is required.');
 const time=text(body.event_time,'event time',5);
 if(time&&!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(time))reject('Check event time.');
 const result={kind,service,catalogue_revision:body.catalogue_revision.toLowerCase(),customer:contact,
  event_date:eventDate(body.event_date,today),event_time:time,venue:text(body.venue,'area or venue',240,kind==='catering'),notes:text(body.notes,'notes',4000,false,true)};
 if(kind==='corporate'){
  if(body.selection!==undefined)reject('Unexpected package choices.');
  const request=object(body.corporate,['quantity','interest'],'corporate request');
  result.corporate={quantity:number(request.quantity,'quantity',1,100000,true),interest:choice(request.interest,['cheesecake','branded','gifting','event','bespoke'],'interest')};
  return result;
 }
 if(body.corporate!==undefined)reject('Unexpected corporate fields.');
 const request=object(body.selection,['guests','hours','min_towers','package_id','extras','savouries','towers','team_select','extra_towers','personalisation','personal_text','artistic_choice','occasion','coffee_style','coffee_hours','tray_style'],'package choices');
 const extras=object(request.extras??{},addonIDs,'add-ons');
 const savouries=request.savouries??[];const towers=request.towers??[];
 if(!Array.isArray(savouries)||savouries.length>5||new Set(savouries).size!==savouries.length||savouries.some(id=>!savouryIDs.includes(id)))reject('Check savoury selections.');
 if(!Array.isArray(towers)||towers.length>3||towers.some(id=>!towerIDs.includes(id)))reject('Check tower choices.');
 const coffeeHours=request.coffee_hours===undefined||request.coffee_hours===null||request.coffee_hours===''?null:number(request.coffee_hours,'requested coffee hours',1,24);
 result.selection={guests:number(request.guests,'guest count',1,400,true),hours:number(request.hours??4,'service hours',4,8),
  min_towers:number(request.min_towers??0,'tower requirement',0,3,true),package_id:request.package_id===null||request.package_id===undefined?'':choice(request.package_id,['',...packageIDs],'package'),
  extras:Object.fromEntries(addonIDs.map(id=>[id,number(extras[id]??0,'add-on quantity',0,99,true)])),savouries,towers,
  team_select:boolean(request.team_select,'team selection'),extra_towers:boolean(request.extra_towers,'extra towers'),
  personalisation:choice(request.personalisation,['later','name','initials','logo'],'personalisation','later'),personal_text:text(request.personal_text,'personalisation text',500),
  artistic_choice:text(request.artistic_choice,'artistic preference',500),occasion:choice(request.occasion,['','reception','wedding','private','corporate','other'],'occasion'),
  coffee_style:choice(request.coffee_style,['mixed','hot','cold','later'],'coffee style','mixed'),coffee_hours:coffeeHours,
  tray_style:choice(request.tray_style,['butterfly','own'],'tray style','butterfly')};
 if(service==='coffee'&&Object.values(result.selection.extras).some(n=>n!==0))reject('Coffee packages do not include hospitality add-ons.');
 return result;
}

export function calculateEnquirySnapshot(submitted,catalogue,revision,version){
 const base={schema:1,catalogue_revision:revision,catalogue_version:version,currency:'KWD'};
 if(submitted.kind==='corporate')return {...base,source:'tailored_corporate_request',requires_custom_quote:true,total_fils:null,quantity:submitted.corporate.quantity};
 const model=createPricingModel(catalogue);const selected=submitted.selection;const coffee=submitted.service==='coffee';
 let quote;
 if(selected.package_id){
  const pack=(coffee?model.coffeePackages:model.packages).find(p=>p.id===selected.package_id);
  if(!pack)reject('Choose a package for the selected service.');
  quote=coffee?model.coffeeQuote(pack,selected.guests):model.packageQuote(pack,selected.guests,selected.hours);
  if(!quote||(!coffee&&pack.towers<selected.min_towers))reject('This package does not fit the requested capacity or towers.');
 }else quote=model.recommendService(submitted.service,selected.guests,selected.min_towers,selected.hours);
 if(!quote)return {...base,source:'tailored_catering_request',requires_custom_quote:true,total_fils:null,inputs:structuredClone(selected),service:submitted.service};
 if(!coffee&&(selected.savouries.length>quote.package.selections||(!selected.team_select&&selected.savouries.length!==quote.package.selections)))reject('Choose the included savoury selections or ask our team to choose.');
 const extra=model.extrasTotal(selected.extras,submitted.service);
 const extras=model.addons.filter(addon=>selected.extras[addon.id]>0).map(addon=>({...addon,quantity:selected.extras[addon.id],line_fils:Math.round(addon.price*1000)*selected.extras[addon.id]}));
 return {...base,source:'published_catalogue',service:submitted.service,requires_custom_quote:Boolean(selected.extra_towers),
  total_fils:Math.round((quote.total+extra)*1000),base_fils:Math.round(quote.package.price*1000),guest_extension_fils:Math.round(quote.guestCost*1000),
  extra_hours_fils:Math.round(quote.hourCost*1000),addons_fils:Math.round(extra*1000),guest_blocks:quote.blocks,extra_hours:quote.extraHours,
  package:structuredClone(quote.package),choices:{savouries:model.savouries.filter(choice=>selected.savouries.includes(choice.id)),towers:coffee?[]:selected.towers.slice(0,quote.package.towers).filter(Boolean).map(id=>model.towers.find(choice=>choice.id===id))},extras,inputs:structuredClone(selected),rules:structuredClone(catalogue.rules),
  unpriced_options:selected.extra_towers?['additional_towers']:[]};
}
