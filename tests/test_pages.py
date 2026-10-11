import json
from pathlib import Path
import pandas as pd
from scripts.build_pages import build


def test_pages_build_uses_only_dashboard_fields(tmp_path):
    source=tmp_path/'snapshot';source.mkdir()
    df=pd.DataFrame({'elapsed_seconds':[0,1,86400,86401], 'amount':[100,200,50,100],
                     'true_label':[1,0,1,0],'fraud_risk':[.9,.8,.01,.02],'extra_private_field':['excluded']*4})
    df.to_csv(source/'test_predictions.csv.gz',index=False,compression='gzip')
    (source/'model_report.json').write_text(json.dumps({'chosen_model':'test'}))
    pd.DataFrame({'date_received':['2026-10-01'],'complaint_count':[5],'potential_fraud_issue_count':[2]}).to_csv(source/'complaint_daily_trends.csv',index=False)
    destination=tmp_path/'site'
    build(source,destination)
    payload=json.loads((destination/'data.json').read_text())
    assert payload['prediction_columns']==['elapsed_seconds','amount','true_label','fraud_risk']
    assert len(payload['predictions'])==4
    assert payload['complaints']==[{'date':'2026-10-01','count':5,'matches':2}]
    assert (destination/'index.html').exists() and (destination/'model_diagnostics.svg').exists()
    assert not list(destination.glob('*.joblib')) and not list(destination.glob('*.sqlite'))
