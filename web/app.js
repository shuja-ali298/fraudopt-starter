'use strict';
const $ = id => document.getElementById(id);
const number = x => Number(x).toLocaleString('en-GB', {maximumFractionDigits: 2});
const pct = (x, digits = 1) => (x * 100).toFixed(digits) + '%';
const signed = x => (x > 0 ? '+' : '') + number(x);
const pageNames = {model: 'Executive overview', strategy: 'Review options', complaints: 'Consumer complaints'};
const modelNames = {gradient_boosting: 'Gradient boosting', logistic_regression: 'Logistic regression'};
const scenarioDownloads = ['download-scenario', 'download-decisions', 'download-frontier'];
let data, scenario, comparison, frontier, complaintView;

function escapeText(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
function table(headers, rows) {
  return '<div class="table-wrap"><table><thead><tr>' + headers.map(h => '<th scope="col">' + escapeText(h) + '</th>').join('') + '</tr></thead><tbody>' + rows.map(row => '<tr>' + row.map(c => '<td>' + escapeText(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>';
}
function metrics(target, items) {
  $(target).innerHTML = items.map(([label, value, help = '']) => '<div class="metric"><span class="metric-label">' + escapeText(label) + '</span><strong class="metric-value">' + escapeText(value) + '</strong><span class="metric-help">' + escapeText(help) + '</span></div>').join('');
}
function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement('a');
  link.href = url; link.download = name; document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function csv(headers, rows) {
  const field = x => '"' + String(x ?? '').replaceAll('"', '""') + '"';
  return [headers, ...rows].map(row => row.map(field).join(',')).join('\n');
}
function dateLabel(value, time = false) {
  if (!value) return 'Not recorded';
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return 'Not recorded';
  const options = {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'};
  if (time) Object.assign(options, {hour: '2-digit', minute: '2-digit'});
  return new Intl.DateTimeFormat('en-GB', options).format(parsed) + (time ? ' UTC' : '');
}

function chart(target, series, xLabel, yLabel) {
  const points = series.flatMap(s => s.values).filter(v => v[1] !== null && Number.isFinite(v[1]));
  if (!points.length) { $(target).textContent = 'No records in this date range.'; return; }
  const allX = series.flatMap(s => s.values).map(p => p[0]);
  let xmin = Math.min(...allX), xmax = Math.max(...allX);
  let ymin = Math.min(0, ...points.map(p => p[1])), ymax = Math.max(0, ...points.map(p => p[1]));
  const isDate = xLabel === 'Received date', singleX = xmin === xmax;
  if (singleX) { const half = isDate ? 43200000 : .5; xmin -= half; xmax += half; }
  if (ymin === ymax) ymax = ymin + 1;
  const rawStep = Math.max(1, (ymax - ymin) / 4), magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const step = [1, 2, 5, 10].find(value => value * magnitude >= rawStep) * magnitude;
  ymax = Math.ceil(ymax / step) * step;
  const yTicks = Array.from({length: Math.round((ymax - ymin) / step) + 1}, (_, i) => ymin + step * i);
  const width = Math.max(280, Math.min(900, $(target).clientWidth));
  const right = width - 20, left = 58, plotWidth = right - left;
  const X = x => left + (x - xmin) / (xmax - xmin) * plotWidth;
  const Y = y => 266 - (y - ymin) / (ymax - ymin) * 218;
  const formatX = x => isDate ? new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'short', timeZone: 'UTC'}).format(new Date(x)) : number(x);
  let svg = '<svg viewBox="0 0 ' + width + ' 326" role="img" aria-label="' + escapeText(yLabel + ' by ' + xLabel) + '"><path d="M' + left + ' 40V266H' + right + '" fill="none" stroke="#b2c2ce"/>';
  for (const value of yTicks) {
    const label = Math.abs(value) >= 1000 ? new Intl.NumberFormat('en-GB', {notation: 'compact', maximumFractionDigits: 1}).format(value) : number(value);
    svg += '<line x1="' + left + '" x2="' + right + '" y1="' + Y(value) + '" y2="' + Y(value) + '" stroke="#e9eef2"/><text x="48" y="' + (Y(value) + 4) + '" text-anchor="end" font-size="12" fill="#536577">' + label + '</text>';
  }
  const ticks = singleX ? [(xmin + xmax) / 2] : Array.from({length: width < 480 ? 3 : 5}, (_, i) => xmin + (xmax - xmin) * i / (width < 480 ? 2 : 4));
  ticks.forEach((x, i) => { const anchor = ticks.length === 1 ? 'middle' : i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle'; svg += '<text x="' + X(x) + '" y="288" text-anchor="' + anchor + '" font-size="11" fill="#536577">' + formatX(x) + '</text>'; });
  series.forEach((s, index) => {
    let path = '', connected = false;
    s.values.forEach(([x, y]) => {
      if (y === null || !Number.isFinite(y)) { connected = false; return; }
      path += (connected ? 'L' : 'M') + X(x) + ',' + Y(y); connected = true;
    });
    svg += '<path d="' + path + '" fill="none" stroke="' + s.color + '" stroke-width="2.5"' + (index === 0 ? ' stroke-dasharray="5 3"' : '') + '/>';
    if (s.values.length <= 31) s.values.forEach(([x, y]) => {
      if (y === null || !Number.isFinite(y)) return;
      svg += '<circle cx="' + X(x) + '" cy="' + Y(y) + '" r="3" fill="' + s.color + '"><title>' + escapeText(s.name + ' · ' + formatX(x) + ': ' + number(y)) + '</title></circle>';
    });
  });
  svg += '<text x="' + (left + plotWidth / 2) + '" y="317" text-anchor="middle" font-size="12">' + escapeText(xLabel) + '</text><text x="' + left + '" y="24" font-size="12">' + escapeText(yLabel) + '</text></svg><div class="legend">' + series.map((s, i) => '<span class="series-' + i + '">' + (i === 0 ? '┄ ' : '━ ') + escapeText(s.name) + '</span>').join('') + '</div>';
  $(target).innerHTML = svg;
}

function provenance() {
  const sources = data.provenance?.sources || {model: {mode: 'snapshot'}, complaints: {mode: 'snapshot'}};
  const sourceName = (s, kind) => s.mode === 'workflow_artifact' ? 'Updated results' : kind === 'model' ? 'Historical example' : 'Saved complaint report';
  const refresh = (source, kind) => source.mode === 'workflow_artifact' ? 'updated ' + dateLabel(source.artifact_created_at_utc) : kind === 'model' ? 'historical example' : 'saved report';
  $('source-notice').textContent = 'Analysis: ' + refresh(sources.model, 'model') + ' · Complaints: ' + refresh(sources.complaints, 'complaints');
  $('source-notice').classList.toggle('fallback', Object.values(sources).some(s => s.mode !== 'workflow_artifact'));
  const records = Object.entries(sources).map(([kind, source]) => [kind === 'model' ? 'Card model' : 'Complaints', sourceName(source, kind), source.run_id || '—', dateLabel(source.run_updated_at_utc, true), dateLabel(source.artifact_created_at_utc, true)]);
  $('source-provenance').innerHTML = table(['Source', 'Published data', 'Run', 'Run updated', 'File created'], records);
  $('build-date').textContent = 'Site built ' + dateLabel(data.built_at_utc, true);
}
function setDefaults() {
  const a = data.report.simulated_policy_assumptions;
  $('capacity').value = a.capacity_per_simulated_day; $('cost').value = a.review_cost_amount_units;
  $('friction').value = a.false_review_friction_amount_units;
  $('effect').value = Math.round(a.intervention_effectiveness * 100 * 1e6) / 1e6;
}
function model() {
  const r = data.report, m = r.untouched_test_metrics;
  const frauds = data.predictions.reduce((n, row) => n + row[2], 0);
  metrics('model-metrics', [['Average precision', m.average_precision.toFixed(3), 'Higher is better'], ['ROC AUC', m.roc_auc.toFixed(3), 'Ranking quality · higher is better'], ['Brier score', m.brier_score.toFixed(6), 'Probability error · lower is better'], ['Labelled fraud', number(frauds), pct(m.fraud_prevalence, 3) + ' of ' + number(data.predictions.length) + ' test transactions']]);
  $('pr-baseline-note').textContent = 'Dashed line: test fraud prevalence (' + pct(m.fraud_prevalence, 3) + ').';
  const criterion = r.selection_metric === 'policy_utility' ? 'validation policy benefit' : 'validation average precision';
  const hours = r.period_time_ranges?.test?.observed_span_seconds;
  $('model-summary').textContent = (modelNames[r.chosen_model] || r.chosen_model) + ' · Chosen by ' + criterion + (hours != null ? ' · ' + number(hours / 3600) + ' hours in the test period' : '');
  $('candidates').innerHTML = table(['Model', 'Average precision', 'ROC AUC', 'Brier score'], Object.entries(r.candidates_selection_only).map(([name, values]) => [(modelNames[name] || name) + (name === r.chosen_model ? ' (selected)' : ''), values.average_precision.toFixed(3), values.roc_auc.toFixed(3), values.brier_score.toFixed(6)]));
  $('periods').innerHTML = table(['Period', 'Transactions', 'Fraud labels', 'Duration (hours)'], Object.entries(r.period_rows).map(([name, count]) => [name === 'selection' ? 'Validation' : name[0].toUpperCase() + name.slice(1), number(count), r.period_fraud[name], number((r.period_time_ranges?.[name]?.observed_span_seconds ?? 0) / 3600)]));
  $('provenance').textContent = JSON.stringify(r.reproducibility, null, 2);
  setDefaults();
}
function scenarioValues() {
  return {capacity: Number($('capacity').value), cost: Number($('cost').value), friction: Number($('friction').value), effectiveness: Number($('effect').value) / 100};
}
function markScenarioDirty() {
  const values = scenarioValues();
  const dirty = !scenario || Object.keys(values).some(key => values[key] !== scenario[key]) || !$('controls').checkValidity();
  const message = dirty ? 'Changes not applied. Update results to use these values.' : 'Results match the assumptions above.';
  if ($('scenario-state').textContent !== message) $('scenario-state').textContent = message;
  $('scenario-state').classList.toggle('pending', dirty);
  scenarioDownloads.forEach(id => $(id).disabled = dirty);
}
function sampleFraud() {
  return {cases: data.predictions.reduce((n, row) => n + row[2], 0), amount: data.predictions.reduce((n, row) => n + (row[2] === 1 ? row[1] : 0), 0)};
}
function amountCovered(result) {
  const total = sampleFraud().amount;
  const reviewed = data.predictions.reduce((sum, row, i) => sum + (result.selected[i] && row[2] === 1 ? row[1] : 0), 0);
  return total ? reviewed / total : null;
}
function businessCards(target, results) {
  const total = sampleFraud().cases;
  const labels = ['Prioritise fraud risk', 'Prioritise financial impact'];
  const descriptions = ['Review the payments most likely to be fraudulent.', 'Also consider payment size, investigation costs and assumed loss reduction.'];
  $(target).innerHTML = results.map((r, i) => {
    const covered = amountCovered(r);
    const items = [['Fraud cases identified', r.fraud_found + ' of ' + total + ' (' + pct(r.fraud_recall, 0) + ')'], ['Share of fraud amount reviewed', covered === null ? '—' : pct(covered)], ['Investigations required', number(r.reviews)], ['Genuine payments flagged', number(r.false_reviews)], ['Illustrative net value', number(r.simulated_net_benefit_amount_units)]];
    return '<article class="policy-card' + (i === 1 ? ' expected' : '') + '"><h3>' + labels[i] + '</h3><p>' + descriptions[i] + '</p><dl>' + items.map(([label, value]) => '<dt>' + escapeText(label) + '</dt><dd>' + escapeText(value) + '</dd>').join('') + '</dl></article>';
  }).join('');
}
function takeaway(results) {
  const [risk, impact] = results;
  if (scenario.capacity === 0) return 'At zero investigation capacity, neither option reviews a payment or identifies any fraud cases in this example.';
  const netRisk = risk.simulated_net_benefit_amount_units, netImpact = impact.simulated_net_benefit_amount_units;
  const financial = netImpact === netRisk ? 'Both options have the same illustrative net value.' : netRisk > 0 ? 'Its illustrative net value is ' + pct(Math.abs(netImpact - netRisk) / netRisk) + (netImpact > netRisk ? ' higher' : netImpact < netRisk ? ' lower' : ' unchanged') + '.' : 'Illustrative net value is ' + number(netImpact) + ', compared with ' + number(netRisk) + ' for fraud-risk reviews.';
  return 'The financial-impact option requires ' + impact.reviews + ' investigations and flags ' + impact.false_reviews + ' genuine payments, compared with ' + risk.reviews + ' investigations and ' + risk.false_reviews + ' genuine payments for the fraud-risk option. It identifies ' + impact.fraud_found + ' fraud cases, compared with ' + risk.fraud_found + '. ' + financial;
}
function overview() {
  const a = data.report.simulated_policy_assumptions;
  if (!comparison) {
    scenario = {capacity: a.capacity_per_simulated_day, cost: a.review_cost_amount_units, friction: a.false_review_friction_amount_units, effectiveness: a.intervention_effectiveness};
    comparison = FraudPolicy.compare(data.predictions, scenario.capacity, scenario.cost, scenario.friction, scenario.effectiveness);
  }
  const fraud = sampleFraud(), hours = data.report.period_time_ranges?.test?.observed_span_seconds;
  $('overview-scope').textContent = number(data.predictions.length) + ' payments · ' + fraud.cases + ' fraud cases' + (hours != null ? ' · ' + number(hours / 3600) + ' hours tested' : '') + ' · Current assumptions: ' + scenario.capacity + ' reviews/day and ' + pct(scenario.effectiveness, 0) + ' assumed loss reduction on reviewed fraud.';
  $('executive-takeaway').innerHTML = '<p>' + escapeText(takeaway(comparison.results)) + '</p><p class="muted">This summarises the last applied assumptions. The coverage and workload figures below show what is gained and what is given up.</p>';
  businessCards('overview-cards', comparison.results);
}
function executiveBrief() {
  const [risk, impact] = comparison.results;
  const total = sampleFraud().cases;
  const options = [risk, impact].map((r, i) => [i === 0 ? 'PRIORITISE FRAUD RISK' : 'PRIORITISE FINANCIAL IMPACT', 'Fraud cases identified: ' + r.fraud_found + ' of ' + total, 'Share of fraud amount reviewed: ' + (amountCovered(r) === null ? 'Not available' : pct(amountCovered(r))), 'Investigations: ' + r.reviews, 'Genuine payments flagged: ' + r.false_reviews, 'Illustrative net value: ' + number(r.simulated_net_benefit_amount_units)].join('\n'));
  return ['FraudOpt — executive summary', 'Historical 2013 card-payment example; not a live fraud control.', '', takeaway(comparison.results), '', ...options, '', 'ASSUMPTIONS', 'Daily investigation capacity: ' + scenario.capacity, 'Cost per investigation: ' + scenario.cost, 'Extra cost for reviewing a genuine payment: ' + scenario.friction, 'Assumed loss reduction on reviewed fraud amounts: ' + pct(scenario.effectiveness), '', 'Currency is unspecified. Value uses the sample payment amounts and hypothetical costs; it is not verified money saved.'].join('\n');
}
function strategy() {
  if (!$('controls').reportValidity()) return;
  try {
    const values = scenarioValues();
    const calculated = FraudPolicy.compare(data.predictions, values.capacity, values.cost, values.friction, values.effectiveness);
    scenario = values; comparison = calculated;
    const {capacity, cost, friction, effectiveness} = scenario;
    $('strategy-error').textContent = '';
    const [risk, expected] = comparison.results;
    const diff = expected.simulated_net_benefit_amount_units - risk.simulated_net_benefit_amount_units;
    metrics('policy-metrics', [['Change in illustrative value', signed(diff), 'Financial impact compared with fraud risk'], ['Change in fraud cases found', signed(expected.fraud_found - risk.fraud_found), 'Financial impact compared with fraud risk'], ['Change in investigations', signed(expected.reviews - risk.reviews), 'Financial impact compared with fraud risk']]);
    businessCards('policy-cards', comparison.results); overview();
    $('policy-table').innerHTML = table(['Review approach', 'Investigations', 'Fraud cases found', 'Genuine payments flagged', 'Fraud among reviews', 'Fraud cases covered', 'Capacity used', 'Illustrative value'], comparison.results.map(r => [r.rank === 'risk' ? 'Prioritise fraud risk' : 'Prioritise financial impact', r.reviews, r.fraud_found, r.false_reviews, r.reviews ? pct(r.precision) : '—', pct(r.fraud_recall), pct(r.capacity_utilisation), number(r.simulated_net_benefit_amount_units)]));
    $('policy-insight').textContent = capacity === 0 ? 'No investigations are selected at zero capacity.' : takeaway(comparison.results);
    frontier = [...new Set([0, 10, 25, 50, 100, 250, 500, capacity])].sort((a, b) => a - b).map(k => ({capacity: k, results: FraudPolicy.compare(data.predictions, k, cost, friction, effectiveness).results}));
    drawFrontier();
    decisions(); markScenarioDirty();
  } catch (error) { $('strategy-error').textContent = 'Results could not be calculated. Check the assumptions and try again.'; }
}
function drawFrontier() {
  chart('frontier', [{name: 'Prioritise fraud risk', color: '#172d40', values: frontier.map(f => [f.capacity, f.results[0].fraud_found])}, {name: 'Prioritise financial impact', color: '#006b61', values: frontier.map(f => [f.capacity, f.results[1].fraud_found])}], 'Daily investigation capacity', 'Fraud cases identified');
}
function decisions() {
  const rank = $('review-strategy').value, result = comparison.results.find(r => r.rank === rank);
  const indices = data.predictions.map((_, i) => i).filter(i => result.selected[i]);
  indices.sort((a, b) => (rank === 'risk' ? data.predictions[b][3] - data.predictions[a][3] : comparison.ev[b] - comparison.ev[a]) || a - b);
  $('decisions').innerHTML = indices.length ? table(['Time in sample (seconds)', 'Payment amount', 'Known fraud case', 'Estimated fraud likelihood', 'Estimated review value'], indices.slice(0, 100).map(i => { const row = data.predictions[i]; return [number(row[0]), number(row[1]), row[2], pct(row[3], 3), number(comparison.ev[i])]; })) : '<p class="muted">No transactions selected for this strategy.</p>';
}
function presetRange(days) {
  const first = data.complaints[0].date, last = data.complaints.at(-1).date;
  const start = days === 'all' ? first : new Date(Math.max(Date.parse(first), Date.parse(last) - (Number(days) - 1) * 86400000)).toISOString().slice(0, 10);
  return [start, last];
}
function complaints(preset = null) {
  const start = $('from').value, end = $('to').value;
  const first = data.complaints[0]?.date, last = data.complaints.at(-1)?.date;
  const valid = first && start && end && start <= end && start >= first && end <= last;
  $('date-error').textContent = valid ? '' : first ? 'Choose a start and end date within the available range, with the end on or after the start.' : 'No complaint records are available.';
  $('complaint-results').hidden = !valid;
  $('download-complaints').disabled = !valid;
  if (!valid) { $('complaint-takeaway').hidden = true; complaintView = []; document.querySelectorAll('[data-days]').forEach(button => button.setAttribute('aria-pressed', 'false')); return; }
  $('date-error').textContent = '';
  complaintView = data.complaints.filter(row => row.date >= start && row.date <= end);
  const count = complaintView.reduce((n, row) => n + row.count, 0), matches = complaintView.reduce((n, row) => n + row.matches, 0);
  metrics('complaint-metrics', [['Complaints', complaintView.length ? number(count) : '—', 'Published records in the selected range'], ['Reports about fraud-related concerns', complaintView.length ? number(matches) : '—', 'Based on the complaint’s published category'], ['Share of complaints flagged', count ? pct(matches / count) : '—', 'Share of complaints, not a fraud rate']]);
  const byDate = new Map(complaintView.map(row => [row.date, row])), all = [];
  for (let time = Date.parse(start); time <= Date.parse(end); time += 86400000) all.push([time, byDate.get(new Date(time).toISOString().slice(0, 10))]);
  chart('complaint-chart', [{name: 'All complaints', color: '#172d40', values: all.map(([time, row]) => [time, row ? row.count : null])}, {name: 'Fraud/scam categories', color: '#006b61', values: all.map(([time, row]) => [time, row ? row.matches : null])}], 'Received date', 'Published complaint count');
  $('complaint-takeaway').hidden = false;
  $('complaint-takeaway').innerHTML = '<h2>What these reports tell us</h2><p>' + escapeText(complaintView.length ? number(matches) + ' of ' + number(count) + ' published complaints in this period fall under fraud-related categories, such as scams, identity theft or unauthorised activity. These are topics reported by consumers, not confirmed fraud incidents.' : 'No complaint records are available for these dates.') + '</p><p class="muted">Use this feed to monitor concerns worth investigating. It does not show your organisation’s fraud losses or explain the card-payment results.</p>';
  $('complaint-summary').textContent = dateLabel(start) + ' – ' + dateLabel(end) + ' · ' + complaintView.length + ' recorded dates';
  $('complaint-table').innerHTML = complaintView.length ? table(['Received date', 'Complaints', 'Fraud/scam categories'], complaintView.map(row => [dateLabel(row.date), row.count, row.matches])) : '<p class="muted">No records in this date range. Missing dates are not treated as zero.</p>';
  $('download-complaints').disabled = complaintView.length === 0;
  if (preset === null) preset = ['all', '7', '30'].find(days => { const range = presetRange(days); return range[0] === start && range[1] === end; });
  document.querySelectorAll('[data-days]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.days === preset)));
}
function show(page, focus = false) {
  if (!Object.hasOwn(pageNames, page)) page = 'model';
  document.querySelectorAll('main section').forEach(section => section.hidden = section.id !== page);
  document.querySelectorAll('[data-page]').forEach(button => { if (button.dataset.page === page) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
  document.title = pageNames[page] + ' · FraudOpt';
  if (page === 'model') overview();
  if (page === 'strategy') { if (!frontier) strategy(); else drawFrontier(); }
  if (page === 'complaints') complaints();
  if (focus) $(page + '-title').focus();
}
function currentPage() { return Object.hasOwn(pageNames, location.hash.slice(1)) ? location.hash.slice(1) : 'model'; }
async function init() {
  try {
    const response = await fetch('./data.json', {cache: 'no-cache'});
    if (!response.ok) throw new Error('Data unavailable');
    data = await response.json(); provenance(); model();
    if (data.complaints.length) {
      const first = data.complaints[0].date, last = data.complaints.at(-1).date;
      ['from', 'to'].forEach(id => { $(id).min = first; $(id).max = last; });
      $('from').value = first; $('to').value = last;
    } else {
      ['from', 'to'].forEach(id => $(id).disabled = true);
      document.querySelectorAll('[data-days]').forEach(button => button.disabled = true);
    }
    $('status').textContent = ''; $('content').setAttribute('aria-busy', 'false');
    document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => { if (location.hash !== '#' + button.dataset.page) location.hash = button.dataset.page; else show(button.dataset.page, true); }));
    window.addEventListener('hashchange', () => show(currentPage(), true));
    let resizeTimer;
    window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (currentPage() === 'strategy' && comparison) drawFrontier(); else if (currentPage() === 'complaints') complaints(); }, 100); });
    $('controls').addEventListener('submit', event => { event.preventDefault(); strategy(); });
    ['capacity', 'cost', 'friction', 'effect'].forEach(id => $(id).addEventListener('input', markScenarioDirty));
    $('reset-scenario').addEventListener('click', () => { setDefaults(); strategy(); });
    $('review-strategy').addEventListener('change', decisions);
    ['from', 'to'].forEach(id => $(id).addEventListener('change', () => complaints()));
    document.querySelectorAll('[data-days]').forEach(button => button.addEventListener('click', () => { const range = presetRange(button.dataset.days); $('from').value = range[0]; $('to').value = range[1]; complaints(button.dataset.days); }));
    $('explore-options').onclick = () => { location.hash = 'strategy'; };
    $('download-brief').onclick = () => download('executive_summary.txt', executiveBrief(), 'text/plain');
    $('view-sources').onclick = () => { $('data-sources').open = true; $('data-sources').querySelector('summary').focus(); };
    $('download-provenance').onclick = () => download('source_provenance.json', JSON.stringify(data.provenance || {sources: {model: {mode: 'snapshot'}, complaints: {mode: 'snapshot'}}}, null, 2), 'application/json');
    $('download-model').onclick = () => download('model_report.json', JSON.stringify(data.report, null, 2), 'application/json');
    $('download-scenario').onclick = () => download('scenario_report.json', JSON.stringify({assumptions: scenario, input_sha256: data.report.reproducibility?.sha256_clean_file, results: comparison.results.map(({selected, ...row}) => row)}, null, 2), 'application/json');
    $('download-decisions').onclick = () => download('scenario_decisions.csv', csv(['elapsed_seconds', 'amount', 'true_label', 'fraud_risk', 'expected_review_benefit', 'review_risk', 'review_expected_value'], data.predictions.map((row, i) => [...row, comparison.ev[i], comparison.results[0].selected[i], comparison.results[1].selected[i]])), 'text/csv');
    $('download-frontier').onclick = () => download('capacity_comparison.csv', csv(['daily_capacity', 'risk_fraud_found', 'risk_investigations', 'risk_genuine_flags', 'risk_illustrative_value', 'impact_fraud_found', 'impact_investigations', 'impact_genuine_flags', 'impact_illustrative_value'], frontier.map(row => [row.capacity, ...row.results.flatMap(result => [result.fraud_found, result.reviews, result.false_reviews, result.simulated_net_benefit_amount_units])])), 'text/csv');
    $('download-complaints').onclick = () => download('complaint_trends_selected.csv', csv(['date_received', 'complaint_count', 'potential_fraud_issue_count'], (complaintView || []).map(row => [row.date, row.count, row.matches])), 'text/csv');
    show(currentPage());
  } catch (error) {
    $('content').setAttribute('aria-busy', 'false'); $('status').className = 'error';
    $('status').textContent = 'Results could not be loaded. Try again.';
    $('source-notice').textContent = 'Data unavailable';
    $('retry-load').hidden = false; $('retry-load').onclick = () => location.reload();
  }
}
init();
