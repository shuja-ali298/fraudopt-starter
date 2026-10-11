"""Standalone calibration and precision-recall diagnostics."""
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
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
