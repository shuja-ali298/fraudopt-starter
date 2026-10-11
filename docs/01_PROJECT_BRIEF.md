# FraudOpt — Project Brief

**Document ID:** FO-BRF-001  
**Version:** 1.0  
**Prepared:** 11 October 2026  
**Status:** Approved as a working portfolio specification; not a production-bank design  
**Project type:** End-to-end data science, decision optimisation, automated data engineering and model governance  
**Related documents:** [Requirements](02_PROJECT_REQUIREMENTS.md) · [Technical Design](03_TECHNICAL_DESIGN.md)

---

## 1. Executive summary

**FraudOpt** is a reproducible research-to-decision portfolio application that develops rare-event fraud classifiers and compares **capacity-constrained intervention strategies**. Instead of stopping at an ROC curve, it asks a business question: *which transactions should a fraud team review, under a finite case-handling budget, to maximise the expected benefit while avoiding unnecessary disruption to legitimate customers?*

The product uses **two separate datasets with separate purposes**:

1. **Historical labelled payment modelling:** OpenML dataset **43627**, containing **284,807 anonymised European card transactions** over approximately two days in September 2013, of which **492 are labelled fraud**. The snapshot is used to train models, calibrate probabilities, test review-allocation rules and evaluate illustrative decisions. It is **not a continuous feed**.
2. **Automated public-complaint intelligence:** The US Consumer Financial Protection Bureau (CFPB) **Consumer Complaint Database**, filtered to the money-transfer-related product category. An unattended ingestion retrieves recently published complaint records, validates a changing CSV source contract, deduplicates records and produces complaint trend outputs. These are **complaints, not verified bank fraud cases**, and they must **never** become labels or transaction-level features in the European card model.

The prototype already has a Python CLI, strict ingestion, a chronological train/calibrate/select/test approach, baseline and challenger models, a top-K review simulator, SQLite complaint storage and GitHub Actions schedules. The project roadmap expands this into an interactive, auditable, resilient decision-support product.

### What a successful demonstration looks like

A reviewer clones the repository, runs tests, downloads the historic labelled sample, trains two models, opens a versioned report and can answer:

- How rare is fraud in the evaluated period, and why is accuracy not the right headline metric?
- Does the selected model outperform a transparent baseline on **held-out chronological observations**?
- Which transactions would be reviewed at a chosen daily capacity, and why?
- How do expected-value ranking and risk-only ranking compare under explicit hypothetical costs?
- Which assumptions are speculative, and what would be required to estimate genuine prevented fraud losses?
- Can the independent CFPB trend ingestion run unattended and recover from duplicate records or source changes?

## 2. Business context and rationale

A fraud model operates in a decision-making system, not in an isolated notebook. Fraud operations must contend with low base rates, costly false alerts, finite investigator capacity, delayed outcomes, changing behaviour, data-quality problems and formal review. A high-scoring model can still be operationally counterproductive if it allocates scarce reviews to low-value cases or treats a model prediction as proof of wrongdoing.

FraudOpt therefore links four disciplines:

- **Statistical modelling:** rare-event detection, appropriate performance measures, probability calibration and time-aware testing.
- **Decision analytics:** expected benefit, constrained investigation capacity and customer-friction assumptions.
- **Engineering:** validated, repeatable extraction, transformations, scheduled jobs, persistence and tests.
- **Governance and communication:** lineage, clearly labelled simulation assumptions, reproducible artefacts and stakeholder-readable reports.

The target use case matches work performed by a bank's economic-crime, fraud analytics, risk governance and customer-operations functions. This is a **portfolio simulation**, not a deployed financial-services control or a claim about any bank's internal systems.

## 3. Problem statement

**Current analytical gap:** Fraud-classification demonstrations commonly optimise a mathematical metric without turning scores into decisions subject to operational constraints. At the same time, pipelines that repeatedly download a fixed benchmark do not demonstrate how live data sources are maintained or governed.

**Proposed solution:** Deliver an open, testable application that (a) builds time-aware fraud models, (b) compares review-selection policies under a simulated budget, and (c) autonomously refreshes a separate public complaint trend feed with explicit provenance.

**Central decision question:** *Given model scores, case values, a simulated intervention effectiveness and a daily investigation limit, how should a team rank potential reviews to maximise expected incremental benefit?*

## 4. Objectives, measurable outcomes and guardrails

| ID | Objective | Proposed evidence of success | Status |
|---|---|---|---|
| O-01 | Deliver reproducible rare-event modelling | Baseline and challenger, documented chronological split, repeatable reports | Implemented in starter; verify with real download |
| O-02 | Avoid contaminating evaluation | No training or model selection on the final test period | Implemented split; expand tests and audit |
| O-03 | Connect predictions to decisions | Compare risk-only top-K with expected-value top-K within capacity | Implemented as simplified simulation |
| O-04 | Establish autonomous public-data ingestion | Scheduled CSV retrieval, schema checks, retries and complaint-ID upserts | Implemented; cloud runtime not yet live-verified |
| O-05 | Preserve cumulative complaint history | Durable storage across ephemeral scheduled runners | Conditional: requires configuring Azure Blob |
| O-06 | Produce trustworthy governance evidence | Source manifest, data profile, evaluation report, documented cost assumptions | Basic outputs implemented; formal pack planned |
| O-07 | Help stakeholders inspect trade-offs | Working interactive dashboard with sensitivity controls | Planned |
| O-08 | Demonstrate operational robustness | Tests for schema change, bad labels, duplicate IDs, source outages, schedule errors | Partial; further hardening planned |

**Proposed release-quality criteria** (these are targets, not measured results): all automated tests pass; a clean runner completes the historical pipeline; review selections obey configured per-day capacity; user-facing cost outputs identify unknown currency and counterfactual assumptions; public trend refresh is idempotent; every scheduled run has a retrievable status and report.

**Non-negotiable claims policy:** Do not say the project detects modern UK scams, measures real prevented loss, models authentic investigation capacity or accesses live card transactions. The current evidence does not support those claims.

## 5. Users and stakeholders

| Persona | Main need | Questions FraudOpt should answer |
|---|---|---|
| Fraud strategy analyst | Select an effective intervention policy | Which transactions are reviewed; how does capacity change the outcome? |
| Fraud operations manager | Protect limited case-handling resources | How many reviews, false alerts and detected frauds are expected under the strategy? |
| Data scientist / model developer | Build and validate rare-event models | Which model wins on selection data; how does it perform out of time? |
| Model-risk reviewer | Challenge methods and assumptions | Where did data originate; what were the boundaries, versions and limitations? |
| Engineering reviewer | Trust automation and correctness | Are data downloads validated, jobs repeatable and failures observable? |
| Hiring manager / GitHub reviewer | Assess technical judgement rapidly | Can I execute it, inspect evidence and see why design choices matter? |

## 6. In-scope capabilities

### Current baseline (starter repository)

- Download a published OpenML Parquet snapshot and retain `Time`, `V1`–`V28`, `Amount`, `Class`.
- Validate schema, numeric data, finite values, nonnegative amounts/time, valid labels and expected snapshot dimensions.
- Rename key fields into snake_case; add a deterministic log-amount feature; preserve temporal order.
- Produce a manifest including SHA-256 hash, row count and fraud count, plus a descriptive data-quality report.
- Split data into chronologically ordered train (roughly 55%), calibration (15%), selection (15%) and test (15%) segments.
- Fit a standardised, class-weighted logistic-regression baseline and histogram gradient-boosting challenger.
- Apply separate-period sigmoid calibration, select using Average Precision and evaluate the untouched test period.
- Rank possible reviews by fraud score or illustrative expected value, under capacity per simulated day.
- Ingest public CFPB CSV over an overlapping rolling date range; normalise selected fields; upsert by complaint ID into SQLite; export daily counts.
- Trigger ingestion and modelling commands from scheduled GitHub Actions definitions and optionally sync SQLite to Azure Blob.

### Target capabilities (subsequent increments)

- Dashboard showing precision-recall, calibration, capacity frontier, cost sensitivity, policy comparisons and plain-language insights.
- Run registry with code version, source hash, model hash, policy assumptions, test metrics and execution timestamp.
- Robust complaint backfills and schedule health reporting, including alerts on source failures.
- Stronger statistical uncertainty analysis and, where supported, label-maturity-aware replay and change monitoring.
- A documented model validation pack, decision logs and reviewed limitations.
- Optional cloud-native authentication instead of connection-string credentials.

## 7. Out of scope and boundaries

- Real-time transaction authorisation, blocking or customer communication.
- Fraud or scam accusation about identifiable individuals.
- Direct integration with a bank, payment processor or confidential transaction store.
- Claiming population-representative fraud prevalence from two days of old anonymised payments.
- Joining CFPB complaint records to card transactions or turning complaint keywords into verified fraud labels.
- Robust APP scam, mule-network or beneficiary-behaviour detection: those fields do not exist in the current modelling dataset.
- A validated business-value estimate: actual intervention effectiveness, causal prevented loss, investigator costs and monetary units are unknown.
- Automatically retraining on genuinely new confirmed transaction labels: no such feed has been sourced.

## 8. Data products and interpretation

| Data product | Source and frequency | Intended use | Key restrictions |
|---|---|---|---|
| Historical card sample | OpenML #43627; fixed snapshot | Classification and simulated policy research | 2013, ~2 days; PCA-anonymised; no unique transaction ID or actual calendar date |
| Clean card table | Derived locally on each baseline build | Features and chronological partitions | Never silently drop anomalies/duplicate-looking rows |
| Fraud model report | Weekly scheduled rebuild, or on demand | Reproducible benchmarking | Rebuilds same data unless source is deliberately updated |
| Recent complaint records | CFPB; database generally updated daily | Independent public-trend monitoring | Publication lag, US coverage, changing taxonomies, reporting bias |
| Complaint trend aggregate | Daily after successful ingestion | Counts by received date, optionally issue category | Not fraud prevalence; counts can be revised |

**Source facts verified 11 October 2026:** OpenML documents the 284,807 / 492 counts and field meanings. CFPB release notes show **September 2026 removal of public complaint narratives** and **July 2026 restriction of filtered exports to CSV with a 100,000-record limit**. The proposed ingestion uses CSV, not narratives.

## 9. Product workflow and key scenarios

### Scenario A — Model-development demonstration

The developer runs a historical ingestion and quality-profile job, then runs training. The pipeline checks all fields, creates a reproducible split, fits and calibrates two models, chooses a model from selection-period results and produces a separate test report. It exports prediction scores and policy comparisons. A reviewer can reproduce the same results locally from the same source and code.

### Scenario B — Fraud review budget exercise

A strategy analyst supplies a nonnegative daily capacity and explicit hypothetical review cost, false-alert friction cost and intervention effectiveness. FraudOpt compares ranking by fraud probability against ranking by estimated incremental benefit. It returns review counts, fraud captured, false reviews, precision, recall and a **simulated** utility measure. The analyst can see limitations and challenge the assumptions.

### Scenario C — Daily complaint data refresh

A scheduled process requests a rolling 90-day CFPB CSV window, normalises public labels, validates the date and product filters, revisits previously seen complaint IDs and updates durable storage if configured. It emits a timestamped trend file and health status. A failed source contract must fail visibly, not silently publish misleading trends.

### Scenario D — Audit and challenge

A reviewer selects a run and can locate the source metadata, transformations, split definitions, model and calibration choices, policy parameters, selected metrics, assumptions, limitations and stored artefacts. The planned dashboard and reporting pack make the evidence navigable without depending on notebook execution.

## 10. Delivery approach and indicative timeline

These estimates assume one developer with working Python, SQL and applied-ML knowledge. Workstreams may overlap. They are planning ranges rather than delivery promises.

| Increment | Deliverables | Effort |
|---|---|---:|
| 0. Stabilise starter | Fix weekly workflow ordering, test both remote endpoints in CI, verify persisted storage | 6–10 hours |
| 1. Data and model quality | Additional validation, run manifest, diagnostic plots, error handling, stronger split tests | 10–16 hours |
| 2. Decision-analysis depth | Capacity sweeps, cost sensitivity, ranker diagnostics, uncertainty and ablations | 15–24 hours |
| 3. Stakeholder dashboard | Streamlit/Plotly interactive controls, metrics, explanations and exports | 12–20 hours |
| 4. Operationalisation and governance | Durable history, job status, alerts, model card, documented validation | 12–20 hours |
| **Total remaining** | **Beyond existing starter** | **55–90 hours** |

**Milestone gates:** (G1) pipelines reproducible and source-compatible; (G2) honest model evaluation; (G3) policy obeys constraints; (G4) scheduled outputs persist and failures are surfaced; (G5) reviewer can understand outputs and limitations.

## 11. Major assumptions and risks

| Risk | Impact | Mitigation / decision |
|---|---|---|
| Old, highly anonymised data | Limited fraud typology, feature interpretability and external validity | Treat as methodology demonstration, not production evidence |
| 492 positive outcomes | Unstable estimates in late chronological splits | Show split class counts; report uncertainty; resist excessive model complexity |
| No actual intervention outcomes | Prevented-loss metric is hypothetical | Label it simulated; vary assumptions; no causal claims |
| Unknown denomination of `Amount` | Monetary costs may be misinterpreted | Use **amount units**, not £/$, until a valid unit is established |
| CFPB API and headers change | Scheduled download can fail | Schema checks, retries, visible alerts and contract tests |
| CFPB complaints are selected/delayed | Invalid inference about fraud prevalence | Keep data products separate; show coverage and lag caveats |
| GitHub Actions not continuously live | Missed schedules and ephemeral storage | Verify runs; durable external storage; monitor failed schedules |
| Azure secret handling | Credential exposure | Secrets manager; eventual managed identity/OIDC; do not commit credentials |
| Current weekly workflow order | Fresh runner can fail before data download | Repair `profile` ordering before enabling schedule |

## 12. Portfolio and interview value

FraudOpt should make it easy to discuss hypotheses, rare-event modelling, model-risk governance, software engineering and business decisions together. The primary showcase artefacts are: a concise architecture graphic, tested data contracts, chronological model comparisons, a capacity-versus-benefit chart, a robust scheduled run log, and a model card acknowledging uncertainty.

For each graph, the README should state: *what decision does this support; how was the figure calculated; and what should not be inferred?*

## 13. Current known defects / open decisions

1. **Workflow defect to fix before first scheduled model run:** `.github/workflows/weekly-model.yml` currently executes `fraudopt profile` before any `fraudopt ingest-model`. A fresh runner has no `data/creditcard_clean.csv.gz`. The order must be ingestion → profile → train.
2. **Endpoint verification:** Remote downloads were not live-executed in the original build environment. Treat source schema and endpoint compatibility as externally documented but requiring smoke tests from an internet-connected runner.
3. **Storage durability:** Without configured Azure Blob, scheduled complaint runs generate rolling-window reports but do not maintain a cumulative SQLite history across runner lifetimes.
4. **Extended backfills:** A 90-day rolling receipt-date window cannot discover a complaint newly published today whose `Date received` is older than 90 days. Design occasional longer backfills if cumulative completeness matters.
5. **Model refresh:** Weekly retraining demonstrates scheduled reproducibility but is not learning from new bank fraud outcomes.

## 14. References and verification

- [OpenML #43627 dataset description](https://www.openml.org/search?id=43627&type=data) and [machine-readable metadata](https://www.openml.org/api/v1/json/data/43627) — data schema, volumes, class meaning and 2013 coverage.
- [CFPB Consumer Complaint Database](https://www.consumerfinance.gov/data-research/consumer-complaints/) and [published-data caveats](https://www.consumerfinance.gov/complaint/data-use/) — source meaning, update/publication and limitations.
- [CFPB API field reference](https://cfpb.github.io/api/ccdb/fields.html) and [release notes](https://cfpb.github.io/api/ccdb/release-notes.html) — field definitions and 2026 format changes.
- [CFPB search API specification](https://github.com/cfpb/ccdb5-api/blob/main/swagger-config.yaml) — date/product/format request parameters.
- [GitHub Actions scheduling](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) — default-branch requirement, delayed jobs and inactivity disablement.
- [scikit-learn model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html) — precision-recall / Average Precision.

**Document-control note:** Status labels refer to inspection of the `fraudopt-starter.zip` supplied in this conversation, not to evidence that remote production services have been executed.
