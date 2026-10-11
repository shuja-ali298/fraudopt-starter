/* Run with Node in Actions, or JavaScriptCore locally. */
'use strict';
const isNode=typeof require==='function';
const read=isNode?path=>require('node:fs').readFileSync(path,'utf8'):readFile;
if(isNode)require('../_site/policy.js');else load('_site/policy.js');
const source=read('_site/app.js');
if(isNode)new (require('node:vm').Script)(source);else new Function(source);
const data=JSON.parse(read('_site/data.json'));
const assumptions=data.report.simulated_policy_assumptions;
const actual=FraudPolicy.compare(data.predictions,assumptions.capacity_per_simulated_day,
    assumptions.review_cost_amount_units,assumptions.false_review_friction_amount_units,
    assumptions.intervention_effectiveness);
actual.results.forEach((r,i)=>{
    const expected=data.report.policy_test_comparison[i===0?'risk_only_top_k':'expected_value_top_k'];
    Object.keys(expected).forEach(key=>{
        if(Math.abs(r[key]-expected[key])>1e-6)throw new Error(key+' differs from saved Python policy report');
    });
});
const zero=FraudPolicy.compare(data.predictions,0,10,15,.7);
if(zero.results.some(r=>r.reviews!==0||r.capacity_utilisation!==0))throw new Error('Zero capacity failed');
const fixture=[[0,100,1,.9],[1,200,0,.8],[86400,50,1,.01]];
const original=FraudPolicy.compare(fixture,1,10,15,.7);
const flipped=FraudPolicy.compare(fixture.map(r=>[r[0],r[1],1-r[2],r[3]]),1,10,15,.7);
original.results.forEach((r,i)=>{
    if(JSON.stringify(r.selected)!==JSON.stringify(flipped.results[i].selected))throw new Error('Labels influenced selection');
    if(r.reviews>2)throw new Error('Daily capacity exceeded');
});
let rejected=false;
try{FraudPolicy.compare(fixture,1,NaN,15,.7);}catch(e){rejected=true;}
if(!rejected)throw new Error('Nonfinite costs were accepted');
(isNode?console.log:print)('Browser policies match Python report; capacity, label independence, input validation and JS syntax checks passed.');
