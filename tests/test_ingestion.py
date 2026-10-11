import pandas as pd
import pytest
from fraudopt.openml_source import clean_creditcard, PCA_COLUMNS
from fraudopt.complaints import clean_complaints, upsert, connect_db, PRODUCT, fetch_window
from datetime import date


def test_creditcard_schema_and_transformations():
    rows = {f: [0.0, 0.5] for f in PCA_COLUMNS}
    rows.update({"Time": [100, 0], "Amount": [100.0, 0.0], "Class": [1, 0]})
    # cleaning enforces a minimum number of positive observations
    rows = {k: v * 20 for k, v in rows.items()}
    clean = clean_creditcard(pd.DataFrame(rows))
    assert clean.elapsed_seconds.is_monotonic_increasing
    assert clean.log_amount.iloc[0] == 0
    assert clean.is_fraud.sum() == 20
    assert len(clean) == 40


def test_missing_column_fails():
    with pytest.raises(ValueError, match="missing"):
        clean_creditcard(pd.DataFrame({"Time": [0]}))


def test_cfpb_headers_issue_flag_and_idempotent_upsert(tmp_path):
    raw = pd.DataFrame({"Complaint ID": ["007", "008"], "Date received": ["2026-10-01", "2026-10-01"],
                        "Product": [PRODUCT, PRODUCT], "Issue": ["Fraud or scam", "Payment processing"],
                        "Sub-issue": ["", ""], "State": ["NY", "CA"]})
    clean = clean_complaints(raw, date(2026, 10, 1), date(2026, 10, 2))
    assert clean.potential_fraud_issue.tolist() == [1, 0]
    conn = connect_db(tmp_path / "test.sqlite")
    upsert(conn, clean)
    upsert(conn, clean)
    assert conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] == 2
    conn.close()


def test_export_cap_date_split_and_source_headers():
    class Response:
        content = ("Complaint ID,Date received,Product,Issue\n"
                   "7,2026-10-01,\"Money transfer, virtual currency, or money service\",Fraud\n").encode()
        def raise_for_status(self): pass
    class Session:
        def get(self, url, params, timeout):
            assert params["format"] == "csv"
            assert params["date_received_max"] == "2026-10-01"
            return Response()
    result = fetch_window(Session(), date(2026,10,1), date(2026,10,2))
    assert result.iloc[0].potential_fraud_issue == 1
