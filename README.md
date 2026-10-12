# FraudOpt

FraudOpt compares how a fraud team could use a limited investigation budget. It shows the trade-off between finding more fraud cases, reviewing genuine payments and focusing on larger potential losses.

[Open the dashboard](https://shuja-ali298.github.io/fraudopt-starter/)

## What it does

The dashboard compares two approaches:

- **Prioritise fraud risk:** review the payments most likely to be fraudulent.
- **Prioritise financial impact:** also consider payment size, investigation costs and assumed loss reduction.

You can change the investigation capacity and cost assumptions, compare the results, and download a summary. A separate page tracks public consumer complaints about money transfers.

Behind the dashboard, Python checks the data, trains two models and tests them on a later period of transactions. GitHub Actions runs the data jobs and publishes the results to GitHub Pages.

## Data and limitations

The card-payment data comes from [OpenML](https://www.openml.org/search?id=43627&type=data): 284,807 anonymised European transactions from 2013, including 492 labelled fraud cases. It covers roughly two days and does not represent current fraud activity.

The complaint data comes from the US [Consumer Financial Protection Bureau](https://www.consumerfinance.gov/data-research/consumer-complaints/). Categories mentioning fraud or scams are reported concerns, not confirmed fraud cases. These records are separate from the card-payment model.

This is a portfolio project, not a live fraud control. Costs and loss reduction are assumptions, and the payment dataset does not specify a currency. The financial figures illustrate a comparison; they do not measure money saved.

## Run locally

Use Python 3.11. From a terminal:

```bash
git clone https://github.com/shuja-ali298/fraudopt-starter.git
cd fraudopt-starter
python3.11 -m venv .venv311
source .venv311/bin/activate
python -m pip install -r requirements-dashboard.txt
python -m pip install --no-deps -e .

python scripts/build_pages.py
python -m http.server 8000 --directory _site
```

Open **http://localhost:8000**. The preview uses the included example data. Keep the terminal running; press **Ctrl+C** to stop the server.

On Windows, use `py -3.11 -m venv .venv311` and activate with `.venv311\Scripts\Activate.ps1` in PowerShell.

The earlier Streamlit version is also available with `python -m streamlit run app.py`.

## Generate new results

With the environment activated:

```bash
fraudopt ingest-model
fraudopt profile
fraudopt train --capacity-per-day 50
fraudopt ingest-complaints --lookback-days 90
python scripts/build_pages.py --source outputs
```

Downloads and the complaint database go in `data/`. Reports, predictions and charts go in `outputs/`. These folders are excluded from Git apart from their placeholder files.

Run the tests with:

```bash
python -m pytest -q
```

## Automatic updates

GitHub Actions refreshes complaints daily and rebuilds the model weekly. Successful runs on `main` trigger a dashboard update. The weekly job uses the same historical card dataset, so it does not introduce new fraud labels.

If recent workflow results are unavailable, the dashboard uses the included example files and labels them accordingly. Azure is optional; without persistent storage, hosted complaint jobs keep a rolling window rather than cumulative database history.

## Where to find things

- `fraudopt/` — data checks, modelling and review calculations.
- `web/` — the GitHub Pages dashboard.
- `scripts/` — dashboard builds and workflow-result downloads.
- `tests/` — automated checks.
- `docs/` — the project brief, requirements and technical design.

See [SECURITY.md](SECURITY.md) for security controls and repository settings.
