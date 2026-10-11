'use strict';
const $=id=>document.getElementById(id);
const number=x=>Number(x).toLocaleString(undefined,{maximumFractionDigits:2});
const pct=x=>(x*100).toFixed(1)+'%';
let data, scenario, comparison, frontier, complaintView;
function escapeText(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function table(headers,rows){return '<div class="table-wrap"><table><thead><tr>'+headers.map(h=>'<th scope="col">'+escapeText(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+escapeText(c)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';}
function metrics(target,items){$(target).innerHTML=items.map(([label,value])=>'<div class="metric"><span>'+escapeText(label)+'</span><strong>'+escapeText(value)+'</strong></div>').join('');}
function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const link=document.createElement('a');link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csv(headers,rows){const field=x=>'"'+String(x??'').replaceAll('"','""')+'"';return [headers,...rows].map(r=>r.map(field).join(',')).join('\n');}
function chart(target,series,xLabel,yLabel){
  const points=series.flatMap(s=>s.values).filter(v=>v[1]!==null&&Number.isFinite(v[1]));
  if(!points.length){$(target).textContent='No observations in this range.';return;}
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(0,...ys),ymax=Math.max(0,...ys);
  if(xmin===xmax)xmax=xmin+1;if(ymin===ymax)ymax=ymin+1;
  const X=x=>70+(x-xmin)/(xmax-xmin)*700,Y=y=>300-(y-ymin)/(ymax-ymin)*245;
  let svg='<svg viewBox="0 0 820 360" role="img" aria-label="'+escapeText(yLabel+' by '+xLabel)+'"><path d="M70 45V300H780" fill="none" stroke="#b2c2ce"/>';
  for(let i=0;i<5;i++){const v=ymin+(ymax-ymin)*i/4;svg+='<line x1="70" x2="780" y1="'+Y(v)+'" y2="'+Y(v)+'" stroke="#e9eef2"/><text x="60" y="'+(Y(v)+4)+'" text-anchor="end" font-size="11" fill="#526575">'+number(v)+'</text>';}
  series.forEach(s=>{let path='',last=null;s.values.forEach(([x,y])=>{if(y===null){last=null;return;}path+=(last===null?'M':'L')+X(x)+','+Y(y);last=x;});svg+='<path d="'+path+'" fill="none" stroke="'+s.color+'" stroke-width="2.5"/>';});
  const isDate=xLabel==='Received date',formatX=x=>isDate?new Date(x).toISOString().slice(0,10):number(x);
  svg+='<text x="70" y="322" font-size="11">'+formatX(xmin)+'</text><text x="780" y="322" text-anchor="end" font-size="11">'+formatX(xmax)+'</text><text x="425" y="347" text-anchor="middle" font-size="12">'+escapeText(xLabel)+'</text><text x="70" y="24" font-size="12">'+escapeText(yLabel)+'</text></svg><div class="legend">'+series.map((s,i)=>'<span class="series-'+i+'">● '+escapeText(s.name)+'</span>').join('')+'</div>';
  $(target).innerHTML=svg;
}
function model(){const r=data.report,m=r.untouched_test_metrics;
  metrics('model-metrics',[['Average precision',m.average_precision.toFixed(3)],['ROC AUC',m.roc_auc.toFixed(3)],['Brier score',m.brier_score.toFixed(6)],['Fraud prevalence',(m.fraud_prevalence*100).toFixed(3)+'%']]);
  $('model-summary').textContent=`Selected model: ${r.chosen_model.replaceAll('_',' ')}. Selection criterion: ${r.selection_metric}. ${number(data.predictions.length)} held-out transactions.`;
  $('candidates').innerHTML=table(['Candidate','Selection AP','ROC AUC','Brier score'],Object.entries(r.candidates_selection_only).map(([n,v])=>[n.replaceAll('_',' '),v.average_precision.toFixed(3),v.roc_auc.toFixed(3),v.brier_score.toFixed(6)]));
  $('periods').innerHTML=table(['Period','Transactions','Fraud labels','Observed hours'],Object.entries(r.period_rows).map(([n,v])=>[n,number(v),r.period_fraud[n],number((r.period_time_ranges?.[n]?.observed_span_seconds??0)/3600)]));
  $('provenance').textContent=JSON.stringify(r.reproducibility,null,2);
  const a=r.simulated_policy_assumptions;
  $('capacity').value=a.capacity_per_simulated_day;$('cost').value=a.review_cost_amount_units;$('friction').value=a.false_review_friction_amount_units;$('effect').value=a.intervention_effectiveness;
}
function strategy(){
  if(!$('controls').reportValidity())return;
  try{
    scenario={capacity:Number($('capacity').value),cost:Number($('cost').value),friction:Number($('friction').value),effectiveness:Number($('effect').value)};
    const {capacity,cost,friction,effectiveness}=scenario;
    comparison=FraudPolicy.compare(data.predictions,capacity,cost,friction,effectiveness);
    $('strategy-error').textContent='';
    $('policy-table').innerHTML=table(['Strategy','Reviews','Fraud found','False reviews','Precision','Recall','Capacity used','Simulated benefit (amount units)'],comparison.results.map(r=>[r.rank==='risk'?'Risk only':'Expected value',r.reviews,r.fraud_found,r.false_reviews,pct(r.precision),pct(r.fraud_recall),pct(r.capacity_utilisation),number(r.simulated_net_benefit_amount_units)]));
    const diff=comparison.results[1].simulated_net_benefit_amount_units-comparison.results[0].simulated_net_benefit_amount_units;
    $('policy-insight').textContent=`Expected-value ranking changes simulated benefit by ${diff>=0?'+':''}${number(diff)} amount units versus risk-only ranking. Compare recall and false reviews alongside benefit.`;
    frontier=[...new Set([0,10,25,50,100,250,500,capacity])].sort((a,b)=>a-b).map(k=>({capacity:k,results:FraudPolicy.compare(data.predictions,k,cost,friction,effectiveness).results}));
    chart('frontier',[{name:'Risk only',color:'#142b3f',values:frontier.map(f=>[f.capacity,f.results[0].simulated_net_benefit_amount_units])},{name:'Expected value',color:'#007b73',values:frontier.map(f=>[f.capacity,f.results[1].simulated_net_benefit_amount_units])}],'Reviews per simulated day','Simulated net benefit (amount units)');
    decisions();
  }catch(e){$('strategy-error').className='error';$('strategy-error').textContent=e.message;}
}
function decisions(){const rank=$('review-strategy').value,r=comparison.results.find(x=>x.rank===rank);
  const indices=data.predictions.map((_,i)=>i).filter(i=>r.selected[i]);
  indices.sort((a,b)=>(rank==='risk'?data.predictions[b][3]-data.predictions[a][3]:comparison.ev[b]-comparison.ev[a])||a-b);
  $('decisions').innerHTML=table(['Elapsed seconds','Amount','Label','Fraud probability','Expected benefit'],indices.slice(0,100).map(i=>{const p=data.predictions[i];return [number(p[0]),number(p[1]),p[2],p[3].toFixed(5),number(comparison.ev[i])];}));
}
function complaints(){const start=$('from').value,end=$('to').value;
  if(start>end){$('complaint-summary').textContent='Choose an end date on or after the start date.';return;}
  complaintView=data.complaints.filter(r=>r.date>=start&&r.date<=end);
  const count=complaintView.reduce((n,r)=>n+r.count,0),matches=complaintView.reduce((n,r)=>n+r.matches,0);
  metrics('complaint-metrics',[['Published complaints',number(count)],['Issue-category matches',number(matches)],['Matching share',count?pct(matches/count):'—']]);
  const byDate=new Map(complaintView.map(r=>[r.date,r])),all=[];
  for(let t=Date.parse(start);t<=Date.parse(end);t+=86400000){const r=byDate.get(new Date(t).toISOString().slice(0,10));all.push([t,r]);}
  chart('complaint-chart',[{name:'All complaints',color:'#142b3f',values:all.map(([t,r])=>[t,r?r.count:null])},{name:'Fraud/scam issue matches',color:'#007b73',values:all.map(([t,r])=>[t,r?r.matches:null])}],'Received date','Published complaint count');
  $('complaint-summary').textContent=`Latest received date in this snapshot: ${data.complaints.at(-1).date}. Received date is not a last-success timestamp.`;
}
function show(page){document.querySelectorAll('main section').forEach(s=>s.hidden=s.id!==page);document.querySelectorAll('[data-page]').forEach(b=>{if(b.dataset.page===page)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});history.replaceState(null,'','#'+page);}
async function init(){try{
  const response=await fetch('./data.json',{cache:'no-cache'});if(!response.ok)throw new Error('Dashboard data could not be loaded.');data=await response.json();
  model();strategy();
  if(data.complaints.length){const first=data.complaints[0].date,last=data.complaints.at(-1).date;['from','to'].forEach(id=>{$(id).min=first;$(id).max=last;});$('from').value=first;$('to').value=last;complaints();}else{$('complaint-summary').textContent='No complaint observations in this snapshot.';$('from').disabled=true;$('to').disabled=true;}
  $('build-date').textContent='Site built '+new Date(data.built_at_utc).toLocaleString()+'. Build time is not source freshness.';
  $('status').textContent='';show(['model','strategy','complaints'].includes(location.hash.slice(1))?location.hash.slice(1):'model');
  document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.page)));
  $('controls').addEventListener('submit',e=>{e.preventDefault();strategy();});$('review-strategy').addEventListener('change',decisions);
  ['from','to'].forEach(id=>$(id).addEventListener('change',complaints));
  $('download-model').onclick=()=>download('model_report.json',JSON.stringify(data.report,null,2),'application/json');
  $('download-scenario').onclick=()=>download('scenario_report.json',JSON.stringify({assumptions:scenario,input_sha256:data.report.reproducibility?.sha256_clean_file,results:comparison.results.map(({selected,...r})=>r)},null,2),'application/json');
  $('download-decisions').onclick=()=>download('scenario_decisions.csv',csv(['elapsed_seconds','amount','true_label','fraud_risk','expected_review_benefit','review_risk','review_expected_value'],data.predictions.map((r,i)=>[...r,comparison.ev[i],comparison.results[0].selected[i],comparison.results[1].selected[i]])),'text/csv');
  $('download-frontier').onclick=()=>download('capacity_frontier.csv',csv(['capacity','risk_only_benefit','expected_value_benefit'],frontier.map(f=>[f.capacity,...f.results.map(r=>r.simulated_net_benefit_amount_units)])),'text/csv');
  $('download-complaints').onclick=()=>download('complaint_trends_selected.csv',csv(['date_received','complaint_count','potential_fraud_issue_count'],(complaintView||[]).map(r=>[r.date,r.count,r.matches])),'text/csv');
}catch(e){$('status').className='error';$('status').textContent=e.message+' Please check that the Pages build completed successfully.';}}
init();
