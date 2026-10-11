/* Shared browser-only policy calculations. Rows: elapsed seconds, amount, label, score. */
(function(root) {
  'use strict';
  function compare(rows, capacity, cost, friction, effectiveness) {
    if (!Number.isInteger(capacity) || capacity < 0 || ![cost,friction,effectiveness].every(Number.isFinite) || cost < 0 || friction < 0 || effectiveness < 0 || effectiveness > 1) throw new Error('Enter valid nonnegative costs, integer capacity and effectiveness between 0 and 1.');
    const days = new Map();
    rows.forEach((r,i) => {
      if (r.length!==4 || !r.every(Number.isFinite) || r[0]<0 || r[1]<0 || ![0,1].includes(r[2]) || r[3]<0 || r[3]>1) throw new Error('Invalid prediction data.');
      const day=Math.floor(r[0]/86400);
      if (!days.has(day)) days.set(day,[]);
      days.get(day).push(i);
    });
    const ev=rows.map(r=>r[3]*r[1]*effectiveness-cost-(1-r[3])*friction);
    const fraudCount=rows.reduce((n,r)=>n+r[2],0);
    const results=['risk','expected_value'].map(rank=>{
      const selected=Array(rows.length).fill(false);
      days.forEach(indices=>{
        const eligible=indices.filter(i=>rank==='risk'||ev[i]>0);
        eligible.sort((a,b)=>(rank==='risk'?rows[b][3]-rows[a][3]:ev[b]-ev[a])||a-b);
        eligible.slice(0,capacity).forEach(i=>selected[i]=true);
      });
      let reviews=0, fraud=0, falseReviews=0, benefit=0;
      selected.forEach((chosen,i)=>{
        if (!chosen) return;
        reviews++;
        benefit-=cost;
        if (rows[i][2]===1) {fraud++; benefit+=rows[i][1]*effectiveness;} else {falseReviews++;benefit-=friction;}
      });
      const budget=capacity*days.size;
      return {rank,selected,reviews,fraud_found:fraud,false_reviews:falseReviews,precision:reviews?fraud/reviews:0,fraud_recall:fraudCount?fraud/fraudCount:0,capacity_utilisation:budget?reviews/budget:0,available_reviews:budget,simulated_net_benefit_amount_units:Math.round((benefit+Number.EPSILON)*100)/100};
    });
    return {results,ev};
  }
  root.FraudPolicy={compare};
})(globalThis);
