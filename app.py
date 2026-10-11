"""Run locally with: python -m streamlit run app.py."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from matplotlib.figure import Figure
from sklearn.metrics import precision_recall_curve, average_precision_score, roc_auc_score, brier_score_loss

from fraudopt.dashboard import validate_predictions, validate_trends, compare_policies, report_path

ROOT = Path(__file__).resolve().parent
OUTPUT_LOCATIONS = {'Pipeline outputs': ROOT/'outputs', 'Demonstration snapshot': ROOT/'dashboard_data'}
if os.environ.get('FRAUDOPT_OUTPUT_DIR'):
    OUTPUT_LOCATIONS['Configured outputs'] = Path(os.environ['FRAUDOPT_OUTPUT_DIR']).expanduser().resolve()
ALLOWED_DIRECTORIES = [*OUTPUT_LOCATIONS.values(), ROOT/'data']
st.set_page_config(page_title='FraudOpt | Decision analytics', page_icon='📊', layout='wide')
st.markdown('''<style>
.block-container {padding-top: 2rem; max-width: 1400px;}
[data-testid="stMetric"] {border: 1px solid #dce3ed; border-radius: 10px; padding: 16px;}
</style>''', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def read_csv(path, modified_ns, size):
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def read_json(path, modified_ns, size):
    return json.loads(Path(path).read_text())


def load_file(directory, name, kind='csv', required=True):
    try:
        path = report_path(directory, name, ALLOWED_DIRECTORIES)
    except ValueError:
        if required:
            st.error('Report access was blocked. Choose an approved data source.')
        return None
    if not path.exists():
        if required:
            st.info(f'{name} is unavailable. Generate it with the pipeline or copy it from a workflow artifact into this output folder.')
        return None
    try:
        stat = path.stat()
        reader = read_json if kind == 'json' else read_csv
        return reader(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, pd.errors.ParserError):
        st.error(f'Could not read {name}. Check its format and access permissions.')
        return None


def freshness(directory, filename):
    try:
        path = report_path(directory, filename, ALLOWED_DIRECTORIES)
    except ValueError:
        return
    if path.exists():
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        st.caption(f'Local file modified: {modified:%d %b %Y, %H:%M UTC}. This is a file timestamp, not proof of a successful scheduled run.')


def predictions(directory):
    raw = load_file(directory, 'test_predictions.csv.gz')
    if raw is None:
        st.code('fraudopt train --capacity-per-day 50', language='bash')
        return None
    try:
        return validate_predictions(raw)
    except ValueError as exc:
        st.error(f'Invalid predictions: {exc}')
        return None


def download_csv(label, frame, filename):
    st.download_button(label, frame.to_csv(index=False).encode(), filename, 'text/csv')


def model_page(directory):
    st.header('Executive overview')
    st.write('Compare fraud coverage, investigation workload and illustrative financial value.')
    st.caption('Historical 2013 card-payment example; this is not a live fraud control.')
    report = load_file(directory, 'model_report.json', 'json', required=False)
    df = predictions(directory)
    if df is None:
        return
    y, p = df.true_label, df.fraud_risk
    if y.nunique() < 2:
        st.error('Both classes are required for model performance charts.')
        return
    defaults = report.get('simulated_policy_assumptions', {}) if isinstance(report, dict) else {}
    capacity = int(defaults.get('capacity_per_simulated_day', 50))
    review = float(defaults.get('review_cost_amount_units', 10))
    friction = float(defaults.get('false_review_friction_amount_units', 15))
    effect = float(defaults.get('intervention_effectiveness', .7))
    outcomes, decisions = compare_policies(df, capacity, review, friction, effect)
    risk, impact = outcomes.loc['Risk only'], outcomes.loc['Expected value']
    st.caption(f'{len(df):,} payments · {int(y.sum())} fraud cases · Daily investigation capacity: {capacity}')
    st.subheader('What the results show')
    st.write(f"Financial-impact reviews require {int(impact.reviews)} investigations and flag "
             f"{int(impact.false_reviews)} genuine payments, compared with {int(risk.reviews)} "
             f"investigations and {int(risk.false_reviews)} genuine payments for fraud-risk reviews. "
             f"They identify {int(impact.fraud_found)} fraud cases, compared with {int(risk.fraud_found)}.")
    net_risk = risk.simulated_net_benefit_amount_units
    net_impact = impact.simulated_net_benefit_amount_units
    if net_risk > 0 and net_impact != net_risk:
        difference = (net_impact - net_risk) / net_risk
        st.write(f"The illustrative net value is {abs(difference):.1%} {'higher' if difference > 0 else 'lower'} under the saved assumptions.")
    else:
        st.write(f'Illustrative net value: {net_impact:,.2f} for financial-impact reviews and {net_risk:,.2f} for fraud-risk reviews.')
    fraud_amount = df.loc[y == 1, 'amount'].sum()
    for column, key, name, flag in zip(st.columns(2), ['Risk only','Expected value'],
                                     ['Prioritise fraud risk','Prioritise financial impact'],
                                     ['review_risk','review_expected_value']):
        outcome = outcomes.loc[key]
        reviewed_amount = decisions.loc[(decisions.true_label == 1) & decisions[flag], 'amount'].sum()
        with column:
            st.subheader(name)
            st.dataframe(pd.DataFrame({
                'Business outcome': ['Fraud cases identified','Share of fraud amount reviewed','Investigations required','Genuine payments flagged','Illustrative net value'],
                'Result': [f'{int(outcome.fraud_found)} of {int(y.sum())} ({outcome.fraud_recall:.0%})',
                           f'{reviewed_amount/fraud_amount:.1%}' if fraud_amount else '—',
                           str(int(outcome.reviews)),str(int(outcome.false_reviews)),
                           f'{outcome.simulated_net_benefit_amount_units:,.2f}']
            }), hide_index=True, width='stretch')
    st.caption('Currency is unspecified. Financial value uses the sample amounts and hypothetical costs and loss reduction; it is not verified money saved.')
    st.write('The choice is the balance between broader fraud coverage, investigation effort and unnecessary reviews of genuine payments. Adjust the example assumptions in Review options.')
    with st.expander('Supporting model validation — for specialist review'):
        cols = st.columns(4)
        cols[0].metric('Average precision', f'{average_precision_score(y,p):.3f}')
        cols[1].metric('ROC AUC', f'{roc_auc_score(y,p):.3f}')
        cols[2].metric('Brier score', f'{brier_score_loss(y,p):.6f}')
        cols[3].metric('Fraud prevalence', f'{y.mean():.3%}')
        st.caption(f'{len(df):,} held-out transactions · {int(y.sum()):,} fraud labels · '
                   f'{(df.elapsed_seconds.max()-df.elapsed_seconds.min())/3600:.2f} hours observed. '
                   'Average precision measures ranking; Brier score measures probability error (lower is better).')
        if isinstance(report, dict):
            st.write(f"**Selected model:** {report.get('chosen_model','Unrecorded').replace('_',' ').title()} · "
                     f"**Selection criterion:** {report.get('selection_metric','Unrecorded')}")
            candidates = report.get('candidates_selection_only', {})
            if candidates:
                with st.expander('Candidate comparison on the selection period'):
                    st.dataframe(pd.DataFrame(candidates).T, width='stretch')
                    st.caption('Candidate selection results are from an earlier period; only the chosen model is evaluated here on test data.')
        left, right = st.columns(2)
        precision, recall, _ = precision_recall_curve(y,p)
        fig = Figure(figsize=(6,4), layout='constrained')
        ax = fig.subplots()
        ax.step(recall, precision, where='post', label='Selected model')
        ax.axhline(y.mean(), color='gray', linestyle='--', label='Prevalence baseline')
        ax.set(xlabel='Recall', ylabel='Precision', xlim=(0,1), ylim=(0,1), title='Precision-recall')
        ax.legend()
        left.pyplot(fig)
        bins = []
        for idx in np.array_split(np.argsort(p.to_numpy(), kind='stable'), min(10,len(df))):
            bins.append({'Predicted probability': p.iloc[idx].mean(), 'Observed fraud rate': y.iloc[idx].mean(), 'Transactions': len(idx)})
        cal = pd.DataFrame(bins)
        fig = Figure(figsize=(6,4), layout='constrained')
        ax = fig.subplots()
        ax.plot([0,1],[0,1], '--', color='gray', label='Ideal calibration')
        ax.plot(cal['Predicted probability'],cal['Observed fraud rate'], 'o-', label='Equal-population bins')
        limit = min(1, max(.01, cal[['Predicted probability','Observed fraud rate']].max().max()*1.2))
        ax.set(xlabel='Mean predicted probability', ylabel='Observed fraud rate', xlim=(0,limit), ylim=(0,limit), title='Calibration (zoomed)')
        ax.legend()
        right.pyplot(fig)
        st.caption('Calibration uses 10 equal-population bins. Few positive labels make these estimates uncertain; confidence intervals are not yet available.')
        with st.expander('Chronology and provenance'):
            if isinstance(report,dict):
                counts = pd.DataFrame({'Transactions': report.get('period_rows',{}), 'Fraud labels': report.get('period_fraud',{})})
                st.dataframe(counts, width='stretch')
                st.json(report.get('reproducibility',{}))
            manifest = load_file(directory.parent/'data', 'creditcard_manifest.json', 'json', required=False)
            if manifest:
                st.json(manifest)
            st.write('Features are anonymous PCA components and log amount. Elapsed seconds preserve chronology; they are not calendar timestamps. Weekly builds reuse this fixed historical dataset.')
        freshness(directory,'test_predictions.csv.gz')
        if isinstance(report,dict):
            st.download_button('Download model report', json.dumps(report,indent=2), 'model_report.json', 'application/json')


def strategy_page(directory):
    st.header('Review options')
    st.caption('Compare investigation capacity and example costs. Currency is unspecified; the value figures are illustrations, not measured savings.')
    df = predictions(directory)
    if df is None:
        return
    report = load_file(directory,'model_report.json','json',required=False)
    defaults = report.get('simulated_policy_assumptions',{}) if isinstance(report,dict) else {}
    controls = st.columns(4)
    capacity = controls[0].number_input('Daily investigation capacity', min_value=0, max_value=10000, value=int(defaults.get('capacity_per_simulated_day',50)), step=10)
    review = controls[1].number_input('Cost per investigation', min_value=0.0, value=float(defaults.get('review_cost_amount_units',10)), step=1.0)
    friction = controls[2].number_input('Extra cost for a genuine payment', min_value=0.0, value=float(defaults.get('false_review_friction_amount_units',15)), step=1.0)
    effect = controls[3].slider('Assumed loss reduction (%)', 0, 100, round(float(defaults.get('intervention_effectiveness',.7))*100), 5) / 100
    st.caption('Ranking sees the entire elapsed-day bucket. Each touched bucket gets full capacity, including partial days. Changing assumptions explores held-out outcomes; it does not select or retrain a model.')
    comparison, decisions = compare_policies(df,capacity,review,friction,effect)
    names = {'Risk only':'Prioritise fraud risk', 'Expected value':'Prioritise financial impact'}
    display = comparison.rename(index=names, columns={'reviews':'Investigations','fraud_found':'Fraud cases found','false_reviews':'Genuine payments flagged', 'fraud_recall':'Share of fraud cases found','precision':'Fraud among reviewed payments','simulated_net_benefit_amount_units':'Illustrative net value', 'available_reviews':'Investigation capacity','capacity_utilisation':'Capacity used'})
    st.dataframe(display.style.format({'Share of fraud cases found':'{:.1%}','Fraud among reviewed payments':'{:.1%}','Capacity used':'{:.1%}','Illustrative net value':'{:,.2f}'}), width='stretch')
    delta = comparison.loc['Expected value','simulated_net_benefit_amount_units'] - comparison.loc['Risk only','simulated_net_benefit_amount_units']
    st.write(f'Financial-impact reviews change illustrative net value by **{delta:+,.2f}** compared with fraud-risk reviews under these assumptions. Consider fraud cases found, genuine payments flagged and investigation workload alongside this figure.')
    st.subheader('Fraud found at different investigation capacities')
    capacities = sorted(set([0,10,25,50,100,250,500,int(capacity)]))
    frontier = []
    for k in capacities:
        results,_ = compare_policies(df,k,review,friction,effect)
        frontier.append({'Daily investigation capacity':k, **results.simulated_net_benefit_amount_units.to_dict()})
    frontier = pd.DataFrame(frontier)
    st.line_chart(frontier.set_index('Daily investigation capacity'), x_label='Daily investigation capacity', y_label='Simulated net benefit (amount units)')
    st.caption('Offline sensitivity on the same held-out sample. Choosing a capacity after viewing test outcomes would require a fresh evaluation period for an unbiased performance claim.')
    with st.expander('Inspect review decisions'):
        strategy = st.selectbox('Show reviewed payments for', ['Expected value','Risk only'], format_func=names.get)
        flag = 'review_expected_value' if strategy=='Expected value' else 'review_risk'
        reviewed = decisions.loc[decisions[flag]].sort_values('expected_review_benefit' if strategy=='Expected value' else 'fraud_risk', ascending=False,kind='stable')
        st.dataframe(reviewed.head(500),width='stretch')
        st.caption('Rows have no real customer/transaction identifiers. True labels are used only to evaluate the simulation, never to rank reviews. Preview limited to 500 rows; export includes all observations.')
    st.latex(r'EV = p A e - c - (1-p) f')
    download_csv('Download scenario decisions',decisions,'scenario_decisions.csv')
    assumptions = {'capacity_per_simulated_day':capacity,'review_cost_amount_units':review,'friction_cost_amount_units':friction,'effectiveness':effect,'evaluation':'Exploratory held-out simulation','input_sha256': report.get('reproducibility',{}).get('sha256_clean_file') if isinstance(report,dict) else None,'results':comparison.reset_index().to_dict('records')}
    st.download_button('Download scenario report',json.dumps(assumptions,indent=2),'scenario_report.json','application/json')
    download_csv('Download capacity frontier',frontier,'capacity_frontier.csv')


def complaint_page(directory):
    st.header('Consumer complaints')
    st.caption('These consumer reports provide external context. They are not confirmed fraud cases and are separate from the card-payment analysis.')
    raw = load_file(directory,'complaint_daily_trends.csv')
    if raw is None:
        st.code('fraudopt ingest-complaints --lookback-days 90',language='bash')
        return
    try:
        df = validate_trends(raw)
    except ValueError as exc:
        st.error(f'Invalid complaint trends: {exc}')
        return
    if df.empty:
        st.info('This export contains no complaint observations.')
        return
    chosen = st.date_input('Received-date range', value=(df.date_received.min().date(),df.date_received.max().date()), min_value=df.date_received.min().date(),max_value=df.date_received.max().date())
    if len(chosen)!=2:
        st.info('Select both a start and end date.')
        return
    view = df.loc[df.date_received.between(pd.Timestamp(chosen[0]),pd.Timestamp(chosen[1]))].copy()
    total, matched = int(view.complaint_count.sum()), int(view.potential_fraud_issue_count.sum())
    cols = st.columns(3)
    cols[0].metric('Published complaints', f'{total:,}')
    cols[1].metric('Reports about fraud-related concerns',f'{matched:,}')
    cols[2].metric('Share of complaints flagged',f'{matched/total:.1%}' if total else '—')
    chart = view.set_index('date_received')[['complaint_count','potential_fraud_issue_count']].rename(columns={'complaint_count':'All complaints','potential_fraud_issue_count':'Fraud/scam issue matches'})
    # Preserve missing days as gaps; absence from an aggregate is not evidence of zero.
    chart = chart.reindex(pd.date_range(chosen[0],chosen[1],freq='D'))
    chart.index.name = 'Received date'
    st.line_chart(chart,x_label='Received date', y_label='Published complaint count')
    st.caption('Counts use received date, not publication date. Recent days may be incomplete due to publication delays. Replayed windows can revise counts; missing dates are not filled with zero.')
    with st.expander('Source and interpretation'):
        st.write('CFPB Consumer Complaint Database, filtered to “Money transfer, virtual currency, or money service”. Issue/sub-issue categories match fraud, scam, scammed, unauthorised/unauthorized or identity theft. No narratives are used. Complaints are self-selected and cannot establish population fraud rates or explain card-model performance.')
    freshness(directory,'complaint_daily_trends.csv')
    st.caption(f'Latest received date in the loaded export: {df.date_received.max():%d %b %Y}. A received date is not a last-success timestamp.')
    st.dataframe(view.rename(columns={'potential_fraud_issue_count':'issue_category_matches'}),width='stretch',hide_index=True)
    download_csv('Download selected complaint trends',view,'complaint_trends_selected.csv')


st.sidebar.title('FraudOpt')
st.sidebar.caption('Historical models and complaint trends')
page = st.sidebar.radio('Explore', ['Model performance','Review strategy','Complaint trends'], format_func={'Model performance':'Executive overview','Review strategy':'Review options','Complaint trends':'Consumer complaints'}.get)
with st.sidebar.expander('Local data'):
    default_location = ('Configured outputs' if 'Configured outputs' in OUTPUT_LOCATIONS else
                        'Pipeline outputs' if (ROOT/'outputs'/'test_predictions.csv.gz').exists() else
                        'Demonstration snapshot')
    location = st.selectbox('Data source', list(OUTPUT_LOCATIONS), index=list(OUTPUT_LOCATIONS).index(default_location))
    if st.button('Reload outputs'):
        st.cache_data.clear()
st.sidebar.caption('Portfolio research · historical card model · independent public complaint feed')
directory = OUTPUT_LOCATIONS[location]
if directory.resolve() == (ROOT/'dashboard_data').resolve():
    st.info('Demonstration snapshot. These results do not refresh automatically from scheduled workflows.')
st.title('FraudOpt')
st.caption('Historical fraud model results and review strategy comparisons.')
{'Model performance':model_page,'Review strategy':strategy_page,'Complaint trends':complaint_page}[page](directory)
st.divider()
st.caption('Research prototype. Historical 2013 transactions do not establish performance on modern fraud. Simulation assumptions and complaint category matches require careful interpretation.')
