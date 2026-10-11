# FraudOpt — Project Requirements Document (PRD / SRS)

**Document ID:** FO-REQ-001  
**Version:** 1.0  
**Prepared:** 11 October 2026  
**Status:** Baseline requirements and prioritised implementation backlog  
**Companion documents:** [Project Brief](01_PROJECT_BRIEF.md) · [Technical Design](03_TECHNICAL_DESIGN.md)

---

## 1. Purpose and conventions

This document defines **what FraudOpt must do, how it must behave, how correctness will be verified, and what remains to be implemented**. It is intended to support development, testing, code review and portfolio demonstrations. It is not a claim of compliance with a bank's actual controls.

### Requirement terminology

- **MUST**: mandatory for the specified release or capability.
- **SHOULD**: expected unless a documented alternative is chosen.
- **MAY**: optional extension.
- **P0 / P1 / P2**: essential baseline / flagship product / advanced differentiation.
- **Implemented**: directly present in the supplied starter source, but may still require execution against live endpoints.
- **Partial**: part of the capability exists, but acceptance is incomplete.
- **Planned**: no complete implementation observed.
- **Proposed target**: an engineering acceptance criterion, **not** an observed benchmark.

## 2. Product goals and boundaries

### Goals

**G-01 — Analytical rigour:** identify rare positive fraud labels and rank cases using transparent, time-aware statistical methods.

**G-02 — Operational decision support:** compare investigation strategies under explicit capacity and cost/effectiveness assumptions.

**G-03 — Data pipeline automation:** automatically ingest, validate and report independent public complaint data without manually refreshing files.

**G-04 — Model and data governance:** record data provenance, modelling choices, evaluation splits, assumptions, failures and artefact versions.

**G-05 — Stakeholder communication:** explain model and intervention trade-offs clearly to a non-specialist risk or fraud stakeholder.

### Product boundaries

The historical OpenML dataset and the current CFPB complaint database have distinct populations, geographies, meanings and time periods. **No joins, causal inference or shared fraud labels are authorised between them.** Public complaint issue keywords are issue-category indicators, not confirmed fraud outcomes. The platform is non-operational and cannot approve, hold or block payments.

## 3. Stakeholder requirements / user stories

| ID | Persona | User story | Acceptance outcome |
|---|---|---|---|
| US-01 | Data scientist | As a modeller, I want to download a trusted labelled historical dataset reproducibly | Identical source identifiers and validated schema are recorded |
| US-02 | Model-risk reviewer | As a reviewer, I want every result linked to source, code and assumption versions | A complete run manifest and report can be inspected |
| US-03 | Fraud analyst | As an analyst, I want to compare two plausible review policies | Cases, capacity usage and metrics are shown consistently |
| US-04 | Operations manager | As a manager, I want to vary capacity and cost assumptions | The dashboard recomputes an illustrative decision frontier |
| US-05 | Data engineer | As an engineer, I want unattended complaint ingestion with stable identifiers | Scheduled jobs are repeatable and idempotent |
| US-06 | Auditor | As a reviewer, I want source failures and unsupported assumptions surfaced | No silent fallback or unlabeled monetary claims |
| US-07 | Hiring manager | As a reviewer, I want to reproduce a credible end-to-end outcome quickly | A clean-start guide, tests and demonstrable reports are available |

## 4. Functional requirements — data ingestion and storage

### FR-001 — Historical data acquisition (P0; Implemented)

The system MUST retrieve **OpenML dataset ID 43627** from the declared Parquet URL without requiring Kaggle credentials. It MUST preserve the source field `Time` for time-ordered evaluation, alongside `V1`–`V28`, `Amount` and `Class`.

**Acceptance tests:** given an accessible source and fresh data directory, the ingestion command succeeds and outputs the raw Parquet, cleaned dataset and provenance manifest; a missing column raises an explicit error. The known snapshot validation expects 284,807 rows and 492 positives.

### FR-002 — Historical schema contract (P0; Implemented)

The parser MUST require all 31 source fields: `Time`, 28 PCA components, `Amount`, and `Class`. Numeric columns MUST parse as finite values. `Class` MUST contain only 0/1. `Time` and `Amount` MUST not be negative. It MUST reject a zero/implausibly low positive count rather than silently continue.

**Acceptance:** malformed types, NaN/Inf, missing required columns, negative time or amounts, invalid labels and unexpectedly changed source dimensions all fail with actionable errors.

### FR-003 — Historical cleaning and feature transform (P0; Implemented)

The system MUST retain source row count and create:

- `elapsed_seconds` from `Time`;
- `amount` from `Amount`;
- `is_fraud` (`int8`) from `Class`;
- `log_amount = ln(1 + amount)`;
- PCA features `V1`–`V28` unchanged.

Records MUST be sorted stably by elapsed time. Duplicate-looking PCA rows MUST NOT be silently deleted, since the source has no reliable unique transaction ID.

**Acceptance:** transformed schema and deterministic `log_amount` are unit-tested; row-count invariance is asserted.

### FR-004 — Data provenance (P0; Partial)

The ingestion pipeline MUST record source URL, dataset ID, ingestion timestamp in UTC, row count, fraud count and SHA-256 hash of the cleaned file. Later releases SHOULD include a source file hash, exact environment/dependency fingerprint and code revision.

**Acceptance:** a run can be traced unambiguously to its source snapshot and transformation version.

### FR-005 — CFPB scheduled acquisition (P0; Implemented locally; remote unverified)

The system MUST call the published Consumer Complaint Database search API, filtering by `date_received_min`, exclusive `date_received_max`, product category and `format=csv`. The default rolling window MUST cover 90 prior receipt dates plus the current date. The scheduler SHOULD execute every day.

**Acceptance:** requests use the expected parameter names, reject HTTP failure, retry transient conditions, detect invalid HTML/JSON responses and produce a non-empty report when matching records exist.

### FR-006 — CFPB source schema and normalisation (P0; Implemented)

The importer MUST normalise both user-facing CSV headers and supported API-style aliases to:

`complaint_id`, `date_received`, `product`, `issue`, `sub_issue`, `state`, `potential_fraud_issue`.

`complaint_id`, `date_received`, `product` and `issue` are mandatory. Optional `sub_issue` and `state` may be blank. Dates MUST parse and fall within the requested half-open interval. Product MUST match the configured filter. Unknown or missing mandatory headers MUST raise a schema error.

**Acceptance:** contract tests cover both header conventions, incorrect product, invalid dates and absent headers.

### FR-007 — CFPB deduplication and upsert (P0; Implemented)

The repository MUST use **the published complaint identifier** as its durable key; repeated overlapping pulls MUST update existing complaint records rather than create duplicates. SQLite MUST enforce uniqueness with a primary key.

**Acceptance:** importing the same two-row fixture twice leaves exactly two complaint records; updated issue fields replace the earlier stored values.

### FR-008 — CFPB large-window handling (P0; Implemented with caveat)

Filtered CSV exports are subject to a published 100,000-record limit. The importer MUST recursively divide date windows that reach the cap. When a single day still reaches it, the run MUST fail clearly rather than silently truncate. A future version MAY subdivide by additional filters and reconcile IDs.

**Acceptance:** mocked exports at the cap trigger sub-windows; a single-day cap raises an error.

### FR-009 — Durable cumulative complaint history (P1; Conditional / Partial)

A deployment that advertises **cumulative complaint history** MUST restore state before each run and persist it afterwards. The existing Azure Blob option may store `complaints.sqlite`; a deployment without Azure MUST state that the report only reflects that run's rolling window.

**Acceptance:** run twice on clean ephemeral workers with a persistent blob, with overlap and one historical record absent from the second window; both records remain after the second run.

### FR-010 — Long-backfill strategy (P1; Planned)

The product SHOULD implement a periodic extended historical backfill because a newly published complaint can have a receipt date older than 90 days.

**Acceptance:** a configurable long lookback rechecks older partitions, remains deduplicated and documents how far back the record is complete.

### FR-011 — Source-quality profile (P0; Implemented)

The product MUST report missingness, label prevalence, transaction value quantiles and fraud counts by elapsed hour, without inventing actual transaction calendar dates.

**Acceptance:** the profile is created from the cleaned dataset and identifies zero/nonzero missingness and positive-label counts.

## 5. Functional requirements — modelling and evaluation

### FR-012 — Chronological partitions (P0; Implemented)

The project MUST divide chronologically into train, calibration, model/policy selection and untouched test. Approximate target row proportions are 55% / 15% / 15% / 15%, with identical elapsed timestamps assigned to the same partition. Partitions MUST be disjoint and each MUST contain both classes.

**Acceptance:** test that `max(time_previous) < min(time_next)` for all adjoining partitions and that no row falls into more than one partition.

### FR-013 — Baseline and challenger (P0; Implemented)

The system MUST compare at least two distinct classifiers: standardised, class-weighted logistic regression and histogram gradient boosting. Preprocessing fitted from data MUST never see later partitions.

**Acceptance:** both candidate models train on the train partition; the evaluation manifest records selected model, parameters and random seed.

### FR-014 — Independent probability calibration (P0; Implemented)

Candidates MUST calibrate raw probabilities using the calibration partition, not their training or test labels. The current implementation uses sigmoid/Platt scaling.

**Acceptance:** probabilities are in [0,1]; calibration data is separate; test observations do not influence calibrator parameters.

### FR-015 — Selection and untouched testing (P0; Implemented)

Model selection MUST be based on Average Precision from the selection partition. The selected model MUST then be evaluated **once per fixed experiment specification** on the held-out final period, with the distinction between selection and test clearly preserved.

**Acceptance:** test report exposes `candidates_selection_only` and `untouched_test_metrics`. No code branch selects the winner from test outcomes.

### FR-016 — Rare-event evaluation (P0; Partial)

Required minimum metrics: Average Precision, ROC-AUC, Brier score and fraud prevalence, plus review-policy precision and fraud recall. A flagship release SHOULD show precision-recall curves, precision@K, calibration plots and confusion/case-volume metrics. Accuracy alone MUST NOT be the principal KPI.

**Acceptance:** dashboard/artefacts show class baseline, selected-model results, class imbalance and differences between discrimination and calibration.

### FR-017 — Label-maturity safeguard (P2; Planned)

If a future longitudinal labelled source becomes available, the evaluation MUST distinguish decision-time features from outcome-availability time. The current static sample has no label-confirmation timestamps, so a real delayed-label experiment MUST NOT be claimed.

**Acceptance:** synthetic maturity fixture prevents a label published after time `t` from appearing in evaluation available at `t`.

## 6. Functional requirements — optimisation and reporting

### FR-018 — Risk-only review policy (P0; Implemented)

Given a calibrated risk score, elapsed time and capacity `K`, the reference policy MUST select up to the top `K` risk-ranked cases per simulated day. A `K` of zero MUST select none.

**Acceptance:** the number of selected reviews per simulated day never exceeds `K`; ties have reproducible stable ordering.

### FR-019 — Expected-value review policy (P0; Implemented)

The optimiser MUST calculate an illustrative expected incremental benefit per review:

`EV_i = p_i × A_i × e − c_review − (1 − p_i) × c_friction`

where `p_i` is the model probability, `A_i` is the anonymised sample `Amount`, `e` is assumed intervention effectiveness, and costs are specified in **the same arbitrary amount units**. It MUST select up to `K` positive-EV cases per simulated day.

**Acceptance:** negative-benefit reviews are excluded from the expected-value strategy; no capacity violation occurs; invalid probabilities/costs/effectiveness are rejected.

### FR-020 — Simulated realised-value comparison (P0; Implemented)

On the held-out labels, the system MUST calculate simulated comparison figures, including reviews, fraud found, false reviews, policy recall and precision, and an illustrative net-benefit value. It MUST use *simulated* / *hypothetical* labels prominently.

**Acceptance:** report must not label the estimated value 'real money saved' or present it in a specific currency.

### FR-021 — Scenario/sensitivity analysis (P1; Planned)

The analyst SHOULD vary review capacity, investigation cost, customer-friction cost and intervention effectiveness across configured ranges, holding test data fixed for presentation. Recommended future functionality includes uncertainty analysis and a capacity/benefit frontier.

**Acceptance:** each scenario produces the same decisions on repeated identical inputs, respects constraints and shows the assumption values used.

### FR-022 — Stakeholder dashboard (P1; Planned)

A dashboard SHOULD expose sample provenance, rare-event metrics, model choice, review-selection comparison, capacity utilisation and warnings about source limitations. It SHOULD offer CSV and report export and avoid presenting the complaint trend feed as a causal driver of model performance.

**Acceptance:** a reviewer can interpret the chosen strategy and its limitations without reading the model code.

### FR-023 — Complaint trend reporting (P0; Implemented)

The product MUST report `complaint_count` and `potential_fraud_issue_count` by `date_received` from the deduplicated store. The flag MUST mean *published complaint issue text matches a declared keyword rule*, and must not be called a confirmed fraud count.

**Acceptance:** changed issue categorisation produces a corresponding aggregate update after upsert; README states no confirmed labels are implied.

### FR-024 — Audit-ready decision record (P1; Planned)

Every model/policy run SHOULD record source manifests, code revision, train/calibration/selection/test boundaries, model parameters, cost assumptions, selected metrics, warnings and generated artefact hashes.

**Acceptance:** independent review can reproduce a named run from the manifest and code revision.

## 7. Functional requirements — automation and recovery

### FR-025 — Scheduled workflows (P0; Partial, one defect)

`daily-data.yml` SHOULD execute at 05:17 UTC daily; `weekly-model.yml` SHOULD execute Sundays at 06:43 UTC. Schedules MUST be committed to the default branch and Actions enabled. The weekly workflow MUST perform **ingest → profile → train**, not profile first.

**Acceptance:** both workflows complete on clean remote runners; run history shows artefacts and exit statuses. Scheduling is best-effort, not a precise SLA.

### FR-026 — Retry, failure and freshness observability (P1; Partial)

The HTTP clients MUST retry transient 429/5xx failures with bounded attempts. Irrecoverable schema errors MUST fail loudly. The scheduled job SHOULD emit a structured log record for run start/end, source response, row counts, errors and freshness, and SHOULD raise a notification on failure.

**Acceptance:** mocked HTTP 500 then success is retried; consistent malformed CSV fails with actionable error; last-success timestamp is visible.

### FR-027 — Test and release gates (P0/P1; Partial)

Code changes MUST run a unit/integration test suite. Flagship release SHOULD add lint, type checks, scheduled smoke tests, contract fixtures, dependency scanning and a tested clean-install guide.

**Acceptance:** `python -m pytest -q` passes in a fresh environment; failing tests block the CI validation job before report publishing.

## 8. Non-functional requirements

Targets below are **proposed** for a single-developer portfolio environment and are not measured SLAs or bank production standards.

| ID | Requirement | Proposed target / test |
|---|---|---|
| NFR-01 | Reproducibility | Same file hash, code/config version and model seed yield materially identical reported metrics |
| NFR-02 | Correctness | No future observations used in train/calibration/selection; timestamp boundaries disjoint |
| NFR-03 | Ingestion integrity | 100% of accepted stored complaint IDs unique; schema failures block publication |
| NFR-04 | Automation reliability | Every scheduled run ends with explicit pass/fail; failure is observable; no manual file replacement |
| NFR-05 | Data durability | Persistent deployment retains complaint DB across runner restarts; test recovery by restoring from blob |
| NFR-06 | Security | No credentials/data secrets in repo, logs or reports; least-privilege storage access |
| NFR-07 | Performance | On reference laptop, document total pipeline runtime and peak memory; define improvement goal only after baseline |
| NFR-08 | Accessibility/usability | Dashboard controls labelled; chart captions show units, denominators and uncertainty |
| NFR-09 | Maintainability | Typed/public module interfaces, separated concerns, documented CLI, automated tests |
| NFR-10 | Auditability | Each official run has a manifest, input fingerprint, timestamps and artefact references |
| NFR-11 | Data ethics | No customer-identifying data intentionally ingested; no real fraud accusations from keyword labels |
| NFR-12 | Portability | Runs from a clean Python 3.11 environment; optional cloud features fail gracefully when unconfigured |
| NFR-13 | Cost control | Avoid unlimited cloud log storage/long-running services; document expected free/low-cost resource use |
| NFR-14 | Availability caveat | Scheduled GitHub Actions may run late or be disabled due to inactivity; no real-time availability guarantee |

## 9. Source data contracts

### DC-01: Card transaction source

| Field(s) | Source type / rule | Required? | Destination / handling |
|---|---|---|---|
| `Time` | Nonnegative numeric seconds since first event | Yes | `elapsed_seconds`, used for ordering and capacity grouping |
| `V1` … `V28` | Finite numerical PCA components | Yes | Same names, inputs for ML; semantics unknown |
| `Amount` | Nonnegative numeric | Yes | `amount`, plus `log_amount = log1p(amount)` |
| `Class` | Binary 0/1 label | Yes | `is_fraud` int8 |

**Data constraints:** 284,807 records / 492 positives are a pinned snapshot expectation, not a timeless property of all future OpenML versions. Do not deduplicate anonymous rows. Do not convert elapsed seconds to a real date. Do not invent customer/beneficiary identifiers.

### DC-02: CFPB CSV source

| Canonical field | Required? | Source alias(es) | Interpretation |
|---|---|---|---|
| `complaint_id` | Yes | `Complaint ID`, `complaint_id` | Public unique complaint identifier |
| `date_received` | Yes | `Date received`, `date_received` | CFPB receipt date, **not** ingestion timestamp |
| `product` | Yes | `Product`, `product` | Product category; filter must match configured value |
| `issue` | Yes | `Issue`, `issue` | Consumer-selected category/issue, not verified fraud |
| `sub_issue` | No | `Sub-issue`, `sub_issue` | Optional category |
| `state` | No | `State`, `state` | Optional jurisdiction |
| `potential_fraud_issue` | Derived | Regex against `issue`+`sub_issue` | Keyword taxonomy indicator only |

The expected product string in the current code is `Money transfer, virtual currency, or money service`. If CFPB changes it, fail and review the contract rather than silently broadening to unintended products.

### DC-03: Outputs

| Artefact | Required fields / content | Source |
|---|---|---|
| `creditcard_manifest.json` | source, dataset ID, UTC download time, counts, SHA-256 | Historical ingestion |
| `source_profile.json` | feature names, missingness, counts, amount quantiles, elapsed-hour groups | Historical profile |
| `model_report.json` | split counts, selection metrics, winner, untouched test metrics, policy comparisons and caveats | Training |
| `model.joblib` | fitted classifier, calibrator, feature ordering, model name | Training |
| `test_predictions.csv.gz` | elapsed seconds, amount, label, risk, review selections | Held-out evaluation |
| `complaints.sqlite` | unique public IDs and issue/date categories | Daily CFPB ingest |
| `complaint_daily_trends.csv` | received date, complaint count, potential-fraud-issue count | Complaint trend export |

## 10. Analytics definitions and guardrails

- **Fraud prevalence:** confirmed positive labels / total labelled transactions in an evaluated subset.
- **Average Precision (AP):** precision weighted by changes in recall across score thresholds, as implemented by scikit-learn; do not confuse with trapezoidal PR-AUC.
- **Review precision:** labelled fraud reviewed / all reviewed cases.
- **Review recall:** labelled fraud reviewed / all fraud cases in the evaluated set.
- **Case capacity:** maximum number of reviews selected per synthetic day computed by `floor(elapsed_seconds/86400)`.
- **False review:** selected case with `is_fraud = 0` in the historical benchmark. This is not a measured real-customer inconvenience.
- **Simulated net benefit:** assumed prevented amount on reviewed positives minus assumed per-review and false-review costs. It is not causally identified nor currency-denominated.
- **Potential-fraud complaint indicator:** CFPB issue taxonomy matches declared terms. It is not observed criminal activity.

**Statistical guardrails:** report counts of fraud in each split; make any zero-positive split fail; distinguish held-out assessment from tuning; never evaluate a complaint category as a true fraud label.

## 11. Acceptance and UAT scenarios

| Test ID | Scenario | Expected result | Evidence |
|---|---|---|---|
| AT-01 | Historical source missing `Amount` | Fail schema validation | Unit test |
| AT-02 | Raw `Class = 2` or `Amount = -1` | Reject input, no cleaned output published | Unit test |
| AT-03 | Duplicate-looking PCA records | No automatic deduplication | Transform test |
| AT-04 | Equal elapsed timestamps cross split boundary | Entire timestamp assigned to one partition | Split test |
| AT-05 | Calibration attempted on training/test | Prohibited by pipeline structure and regression tests | Model test |
| AT-06 | Daily capacity = 0 | No reviews selected | Policy unit test |
| AT-07 | Invalid probability > 1 | Clear exception | Policy unit test |
| AT-08 | Policy capacity = 20 | <=20 selections on every simulated day | Policy evaluation |
| AT-09 | Expected review value negative | Not selected by EV strategy | Policy unit test |
| AT-10 | Reimport same complaint IDs | No increase in unique complaint count | SQLite test |
| AT-11 | Provider returns HTML instead of CSV | Fail, do not overwrite valid trend report | Integration test |
| AT-12 | CFPB batch hits export cap | Split request or fail explicitly if single-day cap | Integration fixture |
| AT-13 | Fresh scheduled runner executes weekly job | Historical ingestion happens before profiling | Remote workflow smoke test |
| AT-14 | Two remote daily runs with Azure | Historical complaints persist and overlapping records update | Recovery test |
| AT-15 | Complaint text contains keyword | Label is `potential_fraud_issue`, never `is_fraud` | Report terminology test |
| AT-16 | Dashboard varies capacity/cost | Recomputed illustrative metrics; assumptions shown | Manual UAT |
| AT-17 | Reviewer opens official run | Data/code/config versions and warnings retrievable | Traceability UAT |

## 12. Delivery backlog (sequenced)

### Sprint A — Repair and verify the existing starter (P0)

1. Fix weekly workflow: invoke `fraudopt ingest-model` before `fraudopt profile`.
2. Run a remote smoke test of OpenML Parquet and CFPB CSV against the currently published interfaces.
3. Confirm Python 3.11, package installation, tests and scheduled artifact upload in GitHub Actions.
4. Confirm Azure Blob state sync works or explicitly label deployment 'stateless rolling window'.

**Exit:** clean runner produces valid historical model and complaint trend artefacts.

### Sprint B — Stronger modelling evidence (P1)

1. Add explicit checks for data source hashes, partition boundaries and positive counts.
2. Add PR curves, calibration plots, precision@K and class-prior benchmarks.
3. Create a model card and model-selection vs test methodology report.
4. Benchmark training time and memory on a reference environment.

**Exit:** reviewer can reproduce all model claims and identify limitations.

### Sprint C — Capacity and cost sensitivity (P1)

1. Configurable policy parameters rather than constants embedded in `run_training`.
2. Capacity sweep, cost-effectiveness frontier, alternative strategies and policy explainability.
3. Stress scenarios and statistical uncertainty appropriate to the sample size.
4. Tests verifying constraints and independent evaluation.

**Exit:** analytical results can support a defensible *hypothetical* policy recommendation.

### Sprint D — Product and operations (P1/P2)

1. Build Streamlit/Plotly app with charts, filters and exported reports.
2. Add source/run health logs, failure alerts and periodic historical complaint backfills.
3. Write governance notes, architecture decision records and deployment runbook.
4. Consider cloud-native credentials (OIDC/managed identity) and improved storage design.

**Exit:** non-technical reviewer can use and understand the product, and scheduled jobs have recovery procedures.

## 13. Dependencies, risks and decision log

| Dependency or risk | Owner | Consequence | Requirement/control |
|---|---|---|---|
| OpenML source availability | Project maintainer | Ingestion outage or snapshot change | FR-001/002/004, snapshot validation |
| CFPB interface changes | Project maintainer | Empty or invalid daily ingest | FR-005/006/008, contract tests |
| GitHub Actions schedule | Project maintainer | Missed unattended runs | FR-025/026, manual dispatch and monitoring |
| Azure storage configuration | Project maintainer | Loss of cumulative state | FR-009, recovery test |
| Unknown costs/label maturity | Analyst | Misleading estimated benefit | FR-017/019/020, caveat and sensitivity |
| Security of serialized models | Engineer | Unsafe deserialisation | NFR-06, load only trusted joblib artefacts |
| Insufficient historical variety | Model reviewer | Weak external validity | FR-016, explicit limits and future data source review |

## 14. Requirements traceability to the target role

| Job responsibility | FraudOpt deliverables |
|---|---|
| Translate risk questions into measurable analytical work | G-02, US-03/04, FR-019–022 |
| Build reusable pipelines and software | FR-001–011, FR-025–027 |
| Train/test rare-event ML models | FR-012–017 |
| Balance business value, customer impact and capacity | FR-018–022 |
| Monitor data/model quality and business effectiveness | FR-011, FR-016, FR-023, planned monitoring extensions |
| Explain and visualise results | US-04/07, FR-022 and dashboards |
| Document modelling decisions for review | FR-004, FR-024, NFR-10 |
| Cloud exposure | FR-009, FR-025, NFR-05/06 |

Third-party fraud model assurance and advanced GenAI investigation belong to the separate FraudLens project, not to FraudOpt's core scope. Scope discipline is intentional.

## 15. Definition of done

A release is considered complete only when:

- All its MUST requirements and acceptance scenarios pass.
- Source schemas and assumptions are recorded, and the date of remote verification is noted.
- Model and policy artefacts can be regenerated using published commands.
- Test/selection contamination is absent and the final test report is clearly distinct.
- Policy outputs display their simulated nature and unknown amount denomination.
- Deployment documentation states what is and is not durable or scheduled.
- No secrets, raw customer identifiers or inflated claims are present in the repository.
- Known defects are documented, fixed or explicitly blocked from release.

## 16. External references

1. [OpenML dataset metadata 43627](https://www.openml.org/api/v1/json/data/43627).
2. [CFPB complaint data meaning and release caveats](https://www.consumerfinance.gov/complaint/data-use/).
3. [CFPB API fields](https://cfpb.github.io/api/ccdb/fields.html) and [2026 release notes](https://cfpb.github.io/api/ccdb/release-notes.html).
4. [CFPB search API OpenAPI specification](https://github.com/cfpb/ccdb5-api/blob/main/swagger-config.yaml).
5. [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
6. [scikit-learn evaluation metrics](https://scikit-learn.org/stable/modules/model_evaluation.html) and [probability calibration](https://scikit-learn.org/stable/modules/calibration.html).

**Provenance:** Existing-status judgements derive from inspection of the uploaded starter ZIP. The download endpoints and public format statements are supported by official documentation; live download success was not independently verified in the authoring environment.
