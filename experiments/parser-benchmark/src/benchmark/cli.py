from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from benchmark.config import build_plan, load_config, quality_gates
from benchmark.dataset import dataset_sha256, load_jsonl
from benchmark.evaluator import evaluate_case, evaluation_to_dict
from benchmark.report import write_reports
from benchmark.runner import run_live

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Russian grocery parser benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("dry-run", help="Show benchmark matrix without API calls")
    dry_run.add_argument("--dataset", default="data/dev.jsonl")
    dry_run.add_argument("--mode", choices=["production", "parity"], default="production")
    dry_run.add_argument("--config", default="benchmark_config.yaml")
    dry_run.add_argument("--provider", action="append", default=None)

    fixture = subparsers.add_parser("evaluate-fixture", help="Evaluate gold-as-prediction fixture")
    fixture.add_argument("--dataset", default="data/dev.jsonl")
    fixture.add_argument("--config", default="benchmark_config.yaml")
    fixture.add_argument("--out", default="results/fixture")

    schema = subparsers.add_parser("write-schema", help="Regenerate JSON Schema")
    schema.add_argument("--out", default="schemas/shopping_list.schema.json")

    live = subparsers.add_parser("run", help="Run configured providers against a dataset")
    live.add_argument("--dataset", default="data/dev.jsonl")
    live.add_argument("--mode", choices=["production", "parity"], default="production")
    live.add_argument("--config", default="benchmark_config.yaml")
    live.add_argument("--out", default="results/live")
    live.add_argument("--limit", type=int, default=None)
    live.add_argument("--provider", action="append", default=None)

    args = parser.parse_args()
    if args.command == "dry-run":
        run_dry_run(args)
    elif args.command == "evaluate-fixture":
        run_fixture(args)
    elif args.command == "write-schema":
        from benchmark.models import write_schema

        write_schema(ROOT / args.out)
    elif args.command == "run":
        asyncio.run(run_benchmark(args))


def run_dry_run(args: argparse.Namespace) -> None:
    config = load_config(ROOT / args.config)
    cases = load_jsonl(ROOT / args.dataset)
    plan = _filter_plan(build_plan(config, mode=args.mode), args.provider)
    calls = len(cases) * len(plan) * config["benchmark"]["default_runs"]

    print(f"dataset={args.dataset}")
    print(f"dataset_sha256={dataset_sha256(ROOT / args.dataset)}")
    print(f"cases={len(cases)}")
    print(f"mode={args.mode}")
    print(f"planned_api_calls={calls}")
    for item in plan:
        model = _display_model(item.model)
        pricing = "complete" if item.pricing_complete else "missing"
        print(
            f"{item.provider}: model={model}, prompt={item.prompt}, "
            f"response_mode={item.response_mode}, pricing={pricing}"
        )


def run_fixture(args: argparse.Namespace) -> None:
    config = load_config(ROOT / args.config)
    cases = load_jsonl(ROOT / args.dataset)
    rows = []
    for case in cases:
        evaluation = evaluate_case(
            gold=case.gold,
            prediction=case.gold,
            evaluator_metadata=case.evaluator_metadata,
        )
        row = {
            "id": case.id,
            "category": case.category,
            **evaluation_to_dict(evaluation),
        }
        rows.append(row)
    summary = write_reports(ROOT / args.out, rows, quality_gates(config))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


async def run_benchmark(args: argparse.Namespace) -> None:
    config = load_config(ROOT / args.config)
    cases = load_jsonl(ROOT / args.dataset)
    plan = _filter_plan(build_plan(config, mode=args.mode), args.provider)
    rows = await run_live(
        cases=cases,
        plan=plan,
        config=config,
        prompts_dir=ROOT / "prompts",
        out_dir=ROOT / args.out,
        limit=args.limit,
    )
    summary = write_reports(ROOT / args.out, rows, quality_gates(config))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _filter_plan(plan, providers):
    if not providers:
        return plan
    selected = set(providers)
    return [item for item in plan if item.provider in selected]


def _display_model(model: str | None) -> str:
    if not model:
        return "<unset>"
    if model.startswith("gpt://"):
        parts = model.split("/")
        return f"gpt://<folder>/{parts[-1]}"
    return model


if __name__ == "__main__":
    main()
