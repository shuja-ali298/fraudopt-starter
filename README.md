# FraudOpt — Automated data ingestion and fraud decision-optimisation starter

> A transparent, reproducible portfolio build: labelled card fraud modelling plus **separate** daily US consumer-complaint trend ingestion. Both sources are public; they are **not linked at customer or transaction level**.

## What this package does

1. Downloads the *historical* 2013 European card transaction dataset from [OpenML dataset #43627](https://www.openml.org/search?id=43627&type=data). It uses the **direct OpenML Parquet file** to preserve the `Time` column (which OpenML metadata marks as an ignored training attribute). No Kaggle credentials are needed.
2. Validates its `Time`, `V1`–`V28`, `Amount` and `Class` schema; rejects bad values; renames to snake_case; creates `log_amount`; retains chronology; writes a source hash and a data-quality report.
3. Chronologically splits the data **55% train / 15% calibration / 15% model+policy selection / 15% untouched test** (cut boundaries keep equal timestamps together). Trains two models and fits sigmoid calibration on a separate period. Selects a model using validation Average Precision by default, or validation simulated policy utility with `--selection-metric policy_utility`.
4. Compares **top-K by risk** against **top-K by expected review benefit** under a per-simulated-day review capacity. Generates predictions, metrics, model joblib and simulated policy results.
5. Every day (after you upload it to GitHub) runs a CFPB CSV ingestion of a 90-day overlapping window of public money-transfer complaints. It checks the **current documented CSV format**, uses retry/backoff, normalises published column headers, rejects a silently changed schema, and deduplicates/upserts by `complaint_id` into SQLite. Reports complaint counts and *issue text matching*; these are **not confirmed fraud labels**.
6. GitHub Actions schedules these data/model jobs without you manually re-downloading files. Artifacts are uploaded after runs. For **persistent complaint history across ephemeral cloud runners**, configure an **optional** Azure Blob connection string.

## Source facts and schema

### Model dataset (immutable snapshot)

- Dataset: OpenML #43627, `credit-card-fraud-detection`, originally 2013.
- Known snapshot: **284,807 rows; 492 `Class=1` frauds** (about 0.173%).
- `Time`: seconds elapsed since first transaction; *not a timestamp or date*.
- `V1` through `V28`: anonymised numeric PCA scores (meaning of individual components is not public).
- `Amount`: numeric amount, **currency not specified** for decisioning cost claims.
- `Class`: binary target (`1` fraud, `0` non-fraud).
- Validation strictly checks source version, schema, NaNs/infinities, negative amounts, valid binary class and target count. **No automatic row deletion** for duplicates or outliers. Only uses `V1`–`V28` and `log_amount` as ML inputs; time is used for chronological splitting and capacity grouping.

**Source**: https://www.openml.org/api/v1/json/data/43627 ; direct file: https://data.openml.org/datasets/0004/43627/dataset_43627.pq

### Daily complaint trend source (changing public record)

- CFPB Consumer Complaint Database, products currently matching `Money transfer, virtual currency, or money service`.
- CSV export query parameters include `date_received_min`, `date_received_max`, `product` and `format=csv`. Live CSV responses include both boundary dates, despite the API documentation describing the maximum as exclusive. The client sends the last included day as the maximum to preserve its internal `[start, end)` windows.
- Export columns supported: `Complaint ID`, `Date received`, `Product`, `Issue`, optionally `Sub-issue`, `State`. Their API-style snake_case names are supported too.
- No complaint narratives are required/stored. CFPB removed public narratives in 2026. JSON export is retired; this client explicitly uses CSV. Exports reaching 100,000 rows are split by date; a single day that still reaches the limit fails loudly instead of silently truncating.
- `potential_fraud_issue = 1` only when the published `Issue` or `Sub-issue` category matches an explicit fraud/scam/unauthorised/identity-theft term. This is a *taxonomy indicator*, **not proof of fraud**.
- Complaints are not a representative sample of financial transactions, nor are they linked to the European card dataset. They cannot serve as fraud labels or direct features for this classifier.
- Upsert by complaint ID; recent 90 days are replayed to capture delayed publications/edits. Updates published today with original complaint dates **over 90 days old will not be captured** unless you extend the lookback or periodically backfill.

**Sources**: https://cfpb.github.io/api/ccdb/fields.html and https://cfpb.github.io/api/ccdb/release-notes.html

## Quick start

Use Python 3.11. In a terminal:

```bash
git clone <your-fraudopt-repository-url>
cd fraudopt-starter
python3.11 -m venv .venv311
source .venv311/bin/activate        # Windows: .venv311\\Scripts\\activate
python -m pip install -r requirements-pipeline.txt
python -m pip install --no-deps -e .
python -m pytest -q

# 1) Downloads and cleans the historical labelled dataset (~284k records)
fraudopt ingest-model
fraudopt profile

# 2) Trains models, calibrates, selects strategy; writes outputs/
fraudopt train --capacity-per-day 50

# Optional: select by validation policy utility with explicit simulation assumptions
fraudopt train --selection-metric policy_utility --review-cost 10 --friction-cost 15 --effectiveness 0.7

# 3) Downloads 90-day rolling CFPB complaint trend data now
fraudopt ingest-complaints --lookback-days 90
```

The first model download needs internet access and may take time. Files under `data/` and `outputs/` are intentionally gitignored. Weekly GitHub Actions runs retrain **on the same historical data**; they do not magically receive new fraud labels.

## Turn on no-manual-refresh scheduling

1. Create a GitHub repository, commit and push the code to the **default branch**. Verify Actions are enabled for the repository.
2. `.github/workflows/daily-data.yml` schedules a CFPB refresh every day at **05:17 UTC**. `.github/workflows/weekly-model.yml` runs a reproducible historic-model build Sundays at **06:43 UTC**.
3. Go to the GitHub repository **Actions** tab. Run each workflow once using **Run workflow** to confirm the remote sources are accessible in GitHub-hosted runners. Check `Artifacts` on each run for `complaint_daily_trends.csv` and the saved model/report. Scheduled runs can be delayed or disabled on inactive repositories.
4. Without Azure configured, each run is still **automated** and produces a fresh rolling-window CSV; however, the GitHub-hosted runner does not retain a cumulative SQLite database. GitHub Actions artifacts are temporary (our workflows retain them for 30–60 days).
5. **Optional durable storage**: create a private Azure Blob container named `fraudopt-data`, then in GitHub **Settings → Secrets and variables → Actions**, add `AZURE_STORAGE_CONNECTION_STRING` for a connection string allowed to read/write only that container. The daily workflow pulls and restores `complaints.sqlite`, processes the overlap, then uploads the updated SQLite store. Do not add credentials to the repository. For a stronger deployment, prefer managed identity/OIDC rather than long-lived keys.

**Note**: A repository Actions schedule isn't active until you publish the workflow to GitHub; merely downloading this starter ZIP does not schedule anything. Model updates only matter when genuinely new labelled transactions become available.

## Outputs

```text
outputs/
├── source_profile.json          # real source QA / distribution review
├── model.joblib                 # chosen estimator + sigmoid calibrator
├── model_report.json            # train/calibration/selection/test and policy metrics
├── test_predictions.csv.gz      # held-out predictions with review flags
├── model_diagnostics.svg       # held-out precision-recall and calibration plots
├── calibration_bins.csv        # equal-population calibration bins
├── precision_recall.csv        # full held-out precision-recall curve
└── complaint_daily_trends.csv   # updated public complaint counts by day

data/
├── creditcard_openml_43627.pq   # canonical raw source snapshot (do not commit)
├── creditcard_clean.csv.gz      # cleaned source (do not commit)
├── creditcard_manifest.json     # provenance and SHA-256
└── complaints.sqlite           # deduplicated complaints (persistent if Azure configured)
```

## Modelling methodology and honesty checks

**Baseline**: standardised logistic regression with balanced training weights. **Challenger**: histogram gradient boosting. Both are post-hoc calibrated on a time-separated calibration period using sigmoid/Platt scaling. The selection period picks the highest Average Precision candidate by default. `--selection-metric policy_utility` instead selects by validation simulated net benefit under the supplied costs and capacity. Reports include each candidate's validation policy utility and Brier score. Cost sensitivity varies review cost and effectiveness on the selection period only; these scenarios do not select settings on the test period. All reported *test* results come from a later, untouched time period.

Simulated intervention value for a payment of amount `A`, estimated fraud probability `p`, intervention effectiveness `e`, review cost `c`, and false-positive friction cost `f`:

```
expected_utility = p * A * e - c - (1 - p) * f
```

The optimiser reviews up to `K` payments with positive expected benefit **per simulated day**, comparing with a risk-score-only top-K comparator. Test reporting evaluates `actual_fraud * amount * effectiveness`, less assumed costs. This is a **counterfactual illustrative simulator**, not measured prevented losses. The amount denomination, the effectiveness of interventions and customer friction are assumptions. Review capacity is a simulation parameter. This is an offline batch simulation: ranking sees every transaction in each elapsed-day bucket before selecting reviews. Each bucket touched by the selection/test period receives the full capacity, even when the period covers only part of that day. Reports include each period's observed time span. These results do not establish performance for a sequential live review queue; hourly budgets or an arrival-order policy require a separate simulation.

**Known limitations**: Only ~2 days of historic transactions; no real customer/account identifiers; no beneficiary network, modern scam typologies, recorded interventions, action propensities, true investigation labels or confirmed counterfactuals. Statistical intervals, drift monitoring, exposure-adjusted costs and practical fraud strategies should be added before calling this production-like model assurance.

## What to add in the next iteration

- Interactive dashboard and capacity/cost frontier (standalone PR and calibration plots are already generated).
- More sophisticated action policies: approve/review/hold with effectiveness and capacity per action.
- Uncertainty analysis and conditional calibration.
- Reporting on delayed labels and decision strategy drift **once a suitable labelled stream exists**.
- Separate real credit-card fraud vs scam models where reliable source data permits it.

## Security and rights

This repository downloads public research data but does not redistribute the original dataset. Treat `model.joblib` as an untrusted deserialisation format when shared by others: load only an artefact you built yourself. Credentials are read from environment variables; never place secrets in commits. Review dataset and API terms before broader redistribution or commercial use.

## Development and reproducibility

`requirements-pipeline.txt` pins runtime, test and optional cloud dependencies for Python 3.11. Pull-request and push CI run the tests with this lock; scheduled jobs use the same environment. Model reports record the Python version, key dependency versions and SHA-256 of the exact cleaned input. Regenerate the lock deliberately under Python 3.11 after reviewing dependency updates:

Generated requirement files use `.txt` names so Dependabot includes them in its
temporary update workspace. `.python-version` and the project's minimum Python
version align dependency updates with the tested Python 3.11 environment.

```bash
python -m pip install pip-tools
pip-compile --extra test --extra cloud --strip-extras --no-emit-index-url --output-file requirements-pipeline.txt pyproject.toml
```

A successful complaint refresh reports its inclusive start, exclusive end, and `ingestion_complete`. The lookback includes today and exactly the requested number of calendar days. Header-only CSV exports represent valid empty windows; blank response bodies fail. Azure restores are staged and checked for SQLite integrity and required columns before replacing local data. OpenML refreshes validate the downloaded snapshot before replacing the raw cache.

The project folder has a dedicated local Git repository; no remote is configured automatically. Generated environments, package metadata, datasets, model outputs and Finder metadata are ignored. Use Python 3.11 and the locked environment above rather than an unrelated system installation.

## Local dashboard

The Streamlit app reads existing reports in `outputs/`; it does not download data, retrain models, or load joblib files. Install the optional dashboard environment and launch from the project folder:

```bash
source .venv311/bin/activate
python -m pip install -r requirements-dashboard.txt
python -m pip install --no-deps -e .
python -m streamlit run app.py
```

- **Model performance:** held-out AP, ROC AUC, Brier score, prevalence, PR/calibration charts, model selection evidence, chronology, provenance and report export.
- **Review strategy:** configurable daily capacity, review/friction costs and effectiveness; comparison of risk-only and positive expected-value reviews; capacity utilisation, capacity frontier and downloadable decisions/scenario reports. All benefit values are simulated in dataset amount units. Exploring test outcomes must not be used to claim a newly tuned strategy has untouched evaluation.
- **Complaint trends:** independent received-date counts, fraud/scam issue-category matches, date filtering and CSV export. Publication lag and reporting bias limit interpretation; missing dates remain gaps rather than assumed zeros.

The **Local data** selector is restricted to pipeline outputs, the demonstration snapshot, and an optional administrator-configured folder. Set `FRAUDOPT_OUTPUT_DIR` before launching Streamlit to use another trusted output folder, including extracted GitHub workflow artifacts. Visitors cannot enter arbitrary server paths, and report symlinks cannot escape their approved folder. Cache keys include file size and modification time; **Reload outputs** clears cached data. File timestamps indicate local modification only, not a verified successful ingestion. Missing model outputs do not prevent reading complaint trends.

Dashboard dependencies have their own Python 3.11 lock, constrained by the pipeline lock. Update it deliberately with:

```bash
pip-compile --extra dashboard --extra test --extra cloud --constraint requirements-pipeline.txt --strip-extras --no-emit-index-url --output-file requirements-dashboard.txt pyproject.toml
```

## First hosted demonstration

The tracked `dashboard_data/` folder contains a fixed demonstration snapshot of
`model_report.json`, `test_predictions.csv.gz`, and `complaint_daily_trends.csv`.
The app uses local `outputs/` when predictions are available; otherwise it uses
this snapshot and displays a snapshot notice. `requirements.txt` points hosting
to the tested dashboard dependency lock.

Deploy on Streamlit Community Cloud with this GitHub repository, branch `main`,
entrypoint `app.py`, and Python **3.11** in Advanced settings. The snapshot is
not automatically refreshed by scheduled workflows. To refresh it deliberately:

```bash
cp outputs/model_report.json outputs/test_predictions.csv.gz outputs/complaint_daily_trends.csv dashboard_data/
git add dashboard_data
git commit -m "Refresh dashboard demonstration snapshot"
git push
```

Local pipeline outputs and remote GitHub Actions artifacts are separate: download
remote artifacts before copying them if the hosted snapshot should use those runs.
An automatically refreshed deployment requires a connection to artifact or object
storage; that integration is not part of this first demonstration deployment.

## GitHub Pages dashboard

A static HTML/CSS/JavaScript version is in `web/`. The browser recalculates review
policies from saved probabilities; Python is only used during the build to
validate the snapshot and create chart/data assets. Streamlit remains available
locally and on its existing host.

To publish:

1. In GitHub **Settings → Pages → Build and deployment**, set **Source** to
   **GitHub Actions**.
2. Commit and push `web/`, `scripts/build_pages.py`, `tests/test_pages.py`,
   `.github/workflows/pages.yml`, `.gitignore`, and this README.
3. Open **Actions → Deploy dashboard to GitHub Pages** and run it on `main`,
   or let the matching push start it. The workflow builds `_site/` and publishes
   only that static directory. The deployment reports the actual Pages URL.

For this repository the expected project URL is
`https://shuja-ali298.github.io/fraudopt-starter/`.
The Pages site uses the committed `dashboard_data/` snapshot, not live workflow
artifacts. Refresh the three snapshot files and commit them to publish new data.
All assets use relative URLs, so repository-subdirectory hosting works.

Local build and preview:

```bash
source .venv311/bin/activate
python scripts/build_pages.py
python -m http.server 8000 --directory _site
```

Open `http://localhost:8000`. Opening the HTML directly as a `file://` URL does
not support the JSON fetch. Generated `_site/` files are ignored; the Actions
workflow rebuilds them. Interactive exports include scenario assumptions and
selected review flags. No joblib models, complaint databases or credentials
are included in the Pages artifact.

## Security controls

Actions are pinned to verified full commit SHAs; checkout does not retain Git
credentials. Pages builds with read-only repository permissions and deploys in a
separate job with Pages/OIDC permissions, restricted to `main`. Optional Azure
credentials are available only to the cloud pull/push steps; Azure authentication
remains optional.

The Security checks workflow audits both dependency locks and runs CodeQL for
Python and JavaScript on pushes, pull requests and a weekly schedule. Dependabot
checks Python dependencies and Action pins weekly. Review its PRs and regenerate
related locks together when needed; do not automatically merge security updates
without tests. Credential files are ignored, including `.env.*`, Streamlit secrets
and common private-key formats. The Pages dashboard uses a same-origin Content
Security Policy and avoids inline scripts/styles.

These repository settings still require an owner to configure on GitHub:

- Protect `main` using a ruleset: require the Tests check, block force pushes and
  branch deletion. Require CodeQL and dependency-audit checks after their first
  successful runs. For a solo maintainer, do not require another person's approval
  unless a reviewer is available. CODEOWNERS identifies the maintainer for
  workflow, dependency and build-script changes; it only enforces review when
  matching repository settings are enabled.
- Restrict the `github-pages` environment's deployment branches to `main`.
- Enable secret scanning, push protection and Dependabot alerts/security updates
  in the repository's Security settings where available.
- Use advanced CodeQL setup for the committed workflow. If GitHub default CodeQL
  setup is already enabled, disable it before using this workflow to avoid
  competing configurations.

A vulnerability audit is time-sensitive and cannot guarantee the absence of
unknown vulnerabilities. Ignoring a secret does not remove it from existing Git
history; rotate any exposed credential before cleaning history.
