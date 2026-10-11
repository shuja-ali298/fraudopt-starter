from datetime import date
import sqlite3
import numpy as np
import pandas as pd
import pytest
from pyarrow import ArrowInvalid
from fraudopt import complaints, openml_source
from fraudopt.cloud import restore_database
from fraudopt.policy import select_reviews, evaluate_policy


class Response:
    def __init__(self, content): self.content = content
    def raise_for_status(self): pass
    def iter_content(self, chunk_size): yield self.content


class Session:
    def __init__(self, content): self.content = content
    def get(self, *args, **kwargs): return Response(self.content)
    def mount(self, *args): pass


def csv_body(day, ids):
    return ('Complaint ID,Date received,Product,Issue\n' + ''.join(
        f'{i},{day},"{complaints.PRODUCT}",Fraud\n' for i in ids)).encode()


def test_empty_export_requires_headers():
    start, end = date(2026, 10, 1), date(2026, 10, 2)
    with pytest.raises(ValueError, match='Blank'):
        complaints.fetch_window(Session(b''), start, end)
    assert complaints.fetch_window(Session(csv_body(start, [])), start, end).empty


def test_export_cap_splits_and_single_day_fails(monkeypatch):
    monkeypatch.setattr(complaints, 'EXPORT_CAP', 2)
    class SplittingSession:
        def get(self, url, params, timeout):
            start, end = params['date_received_min'], params['date_received_max']
            ids = [1, 2] if end == '2026-10-02' and start == '2026-10-01' else [start]
            return Response(csv_body(start, ids))
    result = complaints.fetch_window(SplittingSession(), date(2026,10,1), date(2026,10,3))
    assert len(result) == 2
    with pytest.raises(ValueError, match='single-day'):
        complaints.fetch_window(Session(csv_body('2026-10-01', [1,2])), date(2026,10,1), date(2026,10,2))


def test_revised_complaint_updates_and_complete_window(tmp_path):
    first = complaints.ingest_cfpb(tmp_path/'data', 1, date(2026,10,1), Session(csv_body('2026-10-01', [7])))
    assert first['window_start'] == '2026-10-01' and first['ingestion_complete']
    body = csv_body('2026-10-01', [7]).replace(b'Fraud', b'Payment processing')
    complaints.ingest_cfpb(tmp_path/'data', 1, date(2026,10,1), Session(body))
    with sqlite3.connect(tmp_path/'data'/'complaints.sqlite') as conn:
        assert conn.execute('SELECT COUNT(*),SUM(potential_fraud_issue) FROM complaints').fetchone() == (1,0)


def test_cloud_restore_preserves_good_database_on_failure(tmp_path):
    source, dest = tmp_path/'source.sqlite', tmp_path/'dest.sqlite'
    complaints.connect_db(source).close()
    restore_database(source.read_bytes(), dest)
    before = dest.read_bytes()
    with pytest.raises(sqlite3.DatabaseError): restore_database(b'broken', dest)
    assert dest.read_bytes() == before
    assert not dest.with_suffix('.restore').exists()


def test_failed_openml_refresh_preserves_cache(tmp_path, monkeypatch):
    raw = tmp_path/'creditcard_openml_43627.pq'
    clean = tmp_path/'creditcard_clean.csv.gz'
    raw.write_bytes(b'previous raw'); clean.write_bytes(b'previous clean')
    monkeypatch.setattr(openml_source.requests, 'Session', lambda: Session(b'invalid parquet'))
    monkeypatch.setattr(openml_source.pd, 'read_parquet', lambda path: pd.DataFrame({'bad': [1]}))
    with pytest.raises(ValueError, match='missing'): openml_source.ingest_openml(tmp_path, refresh=True)
    assert raw.read_bytes() == b'previous raw' and clean.read_bytes() == b'previous clean'


@pytest.mark.parametrize('kwargs', [{'review_cost': np.nan}, {'friction_cost': np.inf},
                                  {'capacity_per_day': 1.5}, {'capacity_per_day': True}])
def test_invalid_policy_constraints(kwargs):
    with pytest.raises(ValueError): select_reviews([.5], [10], [0], **kwargs)


@pytest.mark.parametrize('selected,labels,amounts', [([1],[.5],[10]), ([1],[1,0],[10]),
    ([[1]],[[1]],[[10]]), ([1],[1],[np.nan]), ([2],[1],[10])])
def test_invalid_policy_evaluation(selected, labels, amounts):
    with pytest.raises(ValueError): evaluate_policy(selected, labels, amounts, 10,15,.7)


def test_corrupt_parquet_refresh_preserves_cache(tmp_path, monkeypatch):
    raw = tmp_path/'creditcard_openml_43627.pq'
    raw.write_bytes(b'original')
    monkeypatch.setattr(openml_source.requests, 'Session', lambda: Session(b'not parquet'))
    with pytest.raises(ArrowInvalid, match='Parquet|parquet'):
        openml_source.ingest_openml(tmp_path, refresh=True)
    assert raw.read_bytes() == b'original'


def test_offline_capacity_has_explicit_partial_day_semantics():
    selected = select_reviews([.9,.8,.7], [100,100,100], [86399,86400,86401],
                              capacity_per_day=1, rank_by='risk')
    assert selected.tolist() == [True, True, False]


def test_failed_window_does_not_overwrite_previous_report(tmp_path):
    complaints.ingest_cfpb(tmp_path/'data', 1, date(2026,10,1), Session(csv_body('2026-10-01', [7])))
    report = tmp_path/'outputs'/'complaint_daily_trends.csv'
    before = report.read_bytes()
    with pytest.raises(ValueError, match='Blank'):
        complaints.ingest_cfpb(tmp_path/'data', 1, date(2026,10,1), Session(b''))
    assert report.read_bytes() == before
