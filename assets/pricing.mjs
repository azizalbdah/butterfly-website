// Shared calculation rules. Published catalogue data is supplied by the caller.
export function createPricingModel(catalogue) {
const {packages,coffeePackages,serviceTypes,addons,savouries,towers,rules}=structuredClone(catalogue);
function validGuests(n){return Number.isInteger(n)&&n>=1&&n<=rules.guestLimit;}
function guestBlocks(p,n){return Math.max(0,Math.ceil((n-p.guests)/rules.guestBlockSize));}
function hourRate(n){return n<=rules.hourRateGuestThreshold?rules.hourRateSmall:rules.hourRateLarge;}
function packageQuote(p,n,hours=4){
 if(!validGuests(n)||n>p.max||!Number.isFinite(hours)||hours<rules.minHours||hours>rules.maxHours)return null;
 const blocks=guestBlocks(p,n),extraHours=Math.max(0,hours-p.hours);
 return {package:p,blocks,capacity:p.guests+blocks*rules.guestBlockSize,guestCost:blocks*rules.guestBlockPrice,extraHours,hourCost:extraHours*hourRate(n),total:p.price+blocks*rules.guestBlockPrice+extraHours*hourRate(n)};
}
function recommend(n,minTowers=0,hours=4){
 if(!validGuests(n))return null;
 const candidates=packages.filter(p=>p.towers>=minTowers).map(p=>packageQuote(p,n,hours)).filter(Boolean);
 return candidates.sort((a,b)=>a.total-b.total||a.package.guests-b.package.guests)[0]||null;
}
function coffeeQuote(p,n){
 if(!validGuests(n)||n>p.guests)return null;
 return {package:p,capacity:p.guests,total:p.price,blocks:0,guestCost:0,extraHours:0,hourCost:0};
}
function recommendCoffee(n){
 if(!validGuests(n))return null;
 const p=coffeePackages.find(p=>p.guests>=n);
 return p?coffeeQuote(p,n):null;
}
function recommendService(service,n,minTowers=0,hours=4){
 if(service==='coffee')return recommendCoffee(n);
 return ['hospitality','wedding'].includes(service)?recommend(n,minTowers,hours):null;
}
function extrasTotal(qty,service='hospitality'){
 if(service==='coffee')return 0;
 return addons.reduce((sum,a)=>sum+a.price*(Number.isInteger(qty[a.id])&&qty[a.id]>0?qty[a.id]:0),0);
}
const model={packages,coffeePackages,serviceTypes,addons,savouries,towers,validGuests,guestBlocks,hourRate,packageQuote,coffeeQuote,recommend,recommendCoffee,recommendService,extrasTotal};

return model;
}
