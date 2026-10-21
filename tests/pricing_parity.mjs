// Compare the shared engine against the actual preserved release, not a copy.
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {createPricingModel} from '../assets/pricing.mjs';

const original=execFileSync('git',['show','ad8cda04dc84c70dbf3a4f1fbc12f711d4fd35bd:assets/catering-configurator.js'],{encoding:'utf8'});
const context={module:{exports:{}},console};
vm.runInNewContext(original,context);
const old=context.module.exports;
const catalogue=JSON.parse(readFileSync(new URL('../assets/catalogue-baseline.json',import.meta.url)));
const current=createPricingModel(catalogue);
const compare=(a,b)=>assert.equal(JSON.stringify(a),JSON.stringify(b));
let cases=0;
for(let guests=0;guests<=401;guests++){
 for(let hours=4;hours<=8;hours+=0.5){
  for(let towers=0;towers<=4;towers++){
   for(const service of ['hospitality','wedding','coffee']){
    compare(current.recommendService(service,guests,towers,hours),old.recommendService(service,guests,towers,hours));cases++;
   }
  }
 }
 for(const p of old.packages){compare(current.packageQuote(p,guests,4),old.packageQuote(p,guests,4));cases++;}
}
for(const n of [-1,NaN,Infinity,0.5,401])compare(current.recommend(n),old.recommend(n));
for(const hours of [0,3,9,NaN,Infinity])compare(current.packageQuote(catalogue.packages[0],30,hours),old.packageQuote(old.packages[0],30,hours));
for(const service of ['hospitality','wedding','coffee'])for(const quantity of [0,1,2,99,-1,1.5]){
 const extras=Object.fromEntries(catalogue.addons.map(a=>[a.id,quantity]));
 compare(current.extrasTotal(extras,service),old.extrasTotal(extras,service));cases++;
}
assert.equal(current.recommendService('coffee',30).total,125);
assert.equal(current.recommendService('hospitality',30).total,475);
assert.equal(current.recommendService('hospitality',30).total+current.extrasTotal({canapes:1}),497);
assert.equal(current.recommendService('coffee',201),null);
console.log(`PASS ${cases} pricing parity cases against the preserved calculator`);
