from __future__ import annotations
import argparse
import json
from pathlib import Path
from fraudopt.openml_source import ingest_openml
from fraudopt.complaints import ingest_cfpb
from fraudopt.model import run_training
from fraudopt.cloud import sync
from fraudopt.profiling import profile_model_source


def main():
    p = argparse.ArgumentParser(description="FraudOpt: ingest, train, report")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("ingest-model")
    a.add_argument("--refresh", action="store_true")
    b = sub.add_parser("ingest-complaints")
    b.add_argument("--lookback-days", type=int, default=90)
    c = sub.add_parser("train")
    c.add_argument("--capacity-per-day", type=int, default=50)
    c.add_argument("--review-cost", type=float, default=10.0)
    c.add_argument("--friction-cost", type=float, default=15.0)
    c.add_argument("--effectiveness", type=float, default=0.7)
    c.add_argument("--selection-metric", choices=["average_precision", "policy_utility"], default="average_precision")
    profile = sub.add_parser("profile")
    d = sub.add_parser("cloud")
    d.add_argument("direction", choices=["pull", "push"])
    for cmd in (a, b, c, d, profile):
        cmd.add_argument("--root", type=Path, default=Path("."))
    args = p.parse_args()
    data = args.root / "data"
    outputs = args.root / "outputs"
    if args.command == "ingest-model":
        print(ingest_openml(data, refresh=args.refresh))
    elif args.command == "ingest-complaints":
        print(json.dumps(ingest_cfpb(data, lookback_days=args.lookback_days), indent=2))
    elif args.command == "train":
        path = ingest_openml(data)
        print(json.dumps(run_training(path, outputs, capacity_per_day=args.capacity_per_day,
                                      review_cost=args.review_cost, friction_cost=args.friction_cost,
                                      effectiveness=args.effectiveness, selection_metric=args.selection_metric), indent=2))
    elif args.command == "profile":
        print(json.dumps(profile_model_source(data, outputs), indent=2))
    else:
        sync(args.direction, data)

if __name__ == "__main__":
    main()
