from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from fraudopt.dashboard import validate_predictions, validate_trends, compare_policies


def test_decisions_use_scores_not_labels_and_respect_capacity():
    df = pd.DataFrame({'elapsed_seconds':[0,1,86400], 'amount':[100,200,50],
                       'true_label':[1,0,1], 'fraud_risk':[.9,.8,.01]})
    df = validate_predictions(df)
    results, decisions = compare_policies(df,1,10,15,.7)
    flipped = df.assign(true_label=1-df.true_label)
    _, other = compare_policies(flipped,1,10,15,.7)
    assert decisions.review_risk.equals(other.review_risk)
    assert decisions.review_expected_value.equals(other.review_expected_value)
    assert results.loc['Risk only','reviews']==2
    assert results.loc['Expected value','reviews']==1
    empty,_ = compare_policies(df,0,10,15,.7)
    assert empty.reviews.sum()==0 and empty.capacity_utilisation.sum()==0


def test_invalid_output_rejected():
    with pytest.raises(ValueError,match='missing'):
        validate_predictions(pd.DataFrame({'amount':[1]}))
    with pytest.raises(ValueError,match='cannot exceed'):
        validate_trends(pd.DataFrame({'date_received':['2026-10-01'],'complaint_count':[1], 'potential_fraud_issue_count':[2]}))


@pytest.fixture
def app_outputs(tmp_path, monkeypatch):
    output = tmp_path/'outputs'; output.mkdir()
    monkeypatch.setenv('FRAUDOPT_OUTPUT_DIR', str(output))
    pd.DataFrame({'elapsed_seconds':[0,1,86400,86401], 'amount':[100,200,50,100],
                  'true_label':[1,0,1,0],'fraud_risk':[.9,.8,.01,.02]}).to_csv(output/'test_predictions.csv.gz',index=False,compression='gzip')
    (output/'model_report.json').write_text(json.dumps({'chosen_model':'gradient_boosting'}))
    pd.DataFrame({'date_received':['2026-10-01','2026-10-03'], 'complaint_count':[5,4], 'potential_fraud_issue_count':[2,1]}).to_csv(output/'complaint_daily_trends.csv',index=False)
    return output


def get_app(output):
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
    return app


def test_pages_and_zero_capacity(app_outputs):
    app=get_app(app_outputs)
    assert not app.exception
    app.radio[0].set_value('Review strategy').run()
    assert not app.exception
    app.number_input[0].set_value(0).run()
    assert not app.exception
    app.radio[0].set_value('Complaint trends').run()
    assert not app.exception
    assert app.metric[0].value=='9'


def test_missing_model_does_not_block_complaints(app_outputs):
    (app_outputs/'test_predictions.csv.gz').unlink()
    app=get_app(app_outputs)
    assert not app.exception and app.info
    app.radio[0].set_value('Complaint trends').run()
    assert not app.exception and app.metric[0].value=='9'


def test_malformed_data_shows_error(app_outputs):
    pd.DataFrame({'amount':[1]}).to_csv(app_outputs/'test_predictions.csv.gz',index=False,compression='gzip')
    app=get_app(app_outputs)
    assert not app.exception and app.error


def test_report_paths_reject_other_directories_and_symlinks(tmp_path):
    from fraudopt.dashboard import report_path
    allowed = tmp_path/'reports'; allowed.mkdir()
    outside = tmp_path/'private'; outside.mkdir()
    secret = outside/'model_report.json'; secret.write_text('{"private":true}')
    assert report_path(allowed,'model_report.json',[allowed]) == allowed/'model_report.json'
    with pytest.raises(ValueError,match='approved'):
        report_path(outside,'model_report.json',[allowed])
    with pytest.raises(ValueError,match='inside'):
        report_path(allowed,'../private/model_report.json',[allowed])
    (allowed/'model_report.json').symlink_to(secret)
    with pytest.raises(ValueError,match='inside'):
        report_path(allowed,'model_report.json',[allowed])


def test_streamlit_blocks_symlinked_report_without_disclosing_path(app_outputs, tmp_path):
    (app_outputs/'model_report.json').unlink()
    private=tmp_path/'private-report.json'; private.write_text('{"secret":"not for display"}')
    (app_outputs/'model_report.json').symlink_to(private)
    app=get_app(app_outputs)
    assert not app.exception
    # Optional report is denied; valid prediction and complaint views still work.
    assert 'not for display' not in str(app)
    assert app.metric[0].label=='Average precision'
