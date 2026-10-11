"""Standalone calibration and precision-recall diagnostics."""
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter
from sklearn.metrics import precision_recall_curve


def write_diagnostics(labels, probabilities, output_dir: Path):
    labels, probabilities = np.asarray(labels), np.asarray(probabilities)
    precision, recall, _ = precision_recall_curve(labels, probabilities)
    # Equal-population bins are useful for this extremely imbalanced source.
    bins = []
    for indices in np.array_split(np.argsort(probabilities, kind='stable'), min(10, len(labels))):
        bins.append({'mean_predicted_probability': float(probabilities[indices].mean()),
                     'observed_fraud_rate': float(labels[indices].mean()),
                     'transactions': len(indices)})
    calibration = pd.DataFrame(bins)
    calibration.to_csv(output_dir/'calibration_bins.csv', index=False)
    pd.DataFrame({'recall': recall, 'precision': precision}).to_csv(output_dir/'precision_recall.csv', index=False)
    figure = Figure(figsize=(11, 4), layout='constrained')
    pr, cal = figure.subplots(1, 2)
    pr.step(recall, precision, where='post')
    pr.set(title='Held-out precision-recall', xlabel='Recall', ylabel='Precision',
           xlim=(0,1), ylim=(0,1))
    cal.plot([0,1], [0,1], linestyle='--', color='gray', label='Ideal calibration')
    cal.plot(calibration.mean_predicted_probability, calibration.observed_fraud_rate,
             marker='o', label='Equal-population bins')
    cal.set(title='Held-out calibration', xlabel='Mean predicted probability',
            ylabel='Observed fraud rate', xlim=(0,1), ylim=(0,1))
    cal.legend()
    figure.savefig(output_dir/'model_diagnostics.svg')
    # Separate, legible charts for the responsive Pages dashboard.
    pr_figure = Figure(figsize=(5.2, 3.6), layout='constrained')
    pr_axis = pr_figure.subplots()
    pr_axis.step(recall, precision, where='post', color='#006b61', linewidth=2)
    pr_axis.axhline(labels.mean(), linestyle='--', color='#687787', label='Prevalence baseline')
    pr_axis.set(xlabel='Recall', ylabel='Precision', xlim=(0, 1), ylim=(0, 1))
    pr_axis.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    pr_axis.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    pr_axis.legend(frameon=False, fontsize=9)
    pr_axis.grid(axis='y', alpha=.15)
    pr_figure.savefig(output_dir/'precision_recall.svg')

    cal_figure = Figure(figsize=(5.2, 3.6), layout='constrained')
    cal_axis = cal_figure.subplots()
    limit = min(1.0, max(.01, float(calibration[['mean_predicted_probability', 'observed_fraud_rate']].max().max()) * 1.15))
    cal_axis.plot([0, limit], [0, limit], linestyle='--', color='#687787', label='Ideal calibration')
    cal_axis.plot(calibration.mean_predicted_probability, calibration.observed_fraud_rate,
                  marker='o', color='#006b61', label='Observed groups')
    cal_axis.set(xlabel='Predicted fraud probability', ylabel='Observed fraud rate', xlim=(0, limit), ylim=(0, limit))
    cal_axis.xaxis.set_major_formatter(PercentFormatter(1))
    cal_axis.yaxis.set_major_formatter(PercentFormatter(1))
    cal_axis.legend(frameon=False, fontsize=9)
    cal_axis.grid(axis='y', alpha=.15)
    cal_figure.savefig(output_dir/'calibration.svg')
