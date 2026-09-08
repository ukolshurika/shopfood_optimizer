from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def aggregate_evaluations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    if count == 0:
        return {
            "case_count": 0,
            "schema_valid_rate": 0.0,
            "item_recall": 0.0,
            "item_precision": 0.0,
            "quantity_value_accuracy": 0.0,
            "quantity_unit_accuracy": 0.0,
            "package_semantics_accuracy": 0.0,
            "whole_order_exact_match": 0.0,
            "critical_error_rate": 0.0,
            "critical_error_counts": {},
            "p95_latency_ms": None,
            "total_cost_usd": None,
            "mean_cost_per_order": None,
            "cost_per_1k_orders": None,
            "cost_per_1k_exact_matches": None,
        }
    total_critical = sum(len(row["critical_errors"]) for row in rows)
    critical_counts = Counter(error for row in rows for error in row["critical_errors"])
    total_gold = sum(row["gold_items"] for row in rows)
    costs = [row["cost_usd"] for row in rows if row.get("cost_usd") is not None]
    exact_matches = sum(row["whole_order_exact_match"] for row in rows)
    total_cost = sum(costs) if len(costs) == count else None
    return {
        "case_count": count,
        "schema_valid_rate": mean(row["schema_valid"] for row in rows),
        "item_recall": mean(row["item_recall"] for row in rows),
        "item_precision": mean(row["item_precision"] for row in rows),
        "quantity_value_accuracy": mean(row["quantity_value_accuracy"] for row in rows),
        "quantity_unit_accuracy": mean(row["quantity_unit_accuracy"] for row in rows),
        "package_semantics_accuracy": mean(row["package_semantics_accuracy"] for row in rows),
        "whole_order_exact_match": mean(row["whole_order_exact_match"] for row in rows),
        "critical_error_rate": total_critical / total_gold if total_gold else 0.0,
        "critical_error_counts": dict(sorted(critical_counts.items())),
        "p95_latency_ms": _percentile([row["latency_ms"] for row in rows if row.get("latency_ms") is not None], 95),
        "total_cost_usd": total_cost,
        "mean_cost_per_order": total_cost / count if total_cost is not None and count else None,
        "cost_per_1k_orders": total_cost * 1000 / count if total_cost is not None and count else None,
        "cost_per_1k_exact_matches": total_cost * 1000 / exact_matches if total_cost is not None and exact_matches else None,
    }


def gate_failures(summary: dict[str, Any], gates: dict[str, float]) -> list[str]:
    failures: list[str] = []
    for metric, threshold in gates.items():
        value = summary[metric]
        if metric == "critical_error_rate":
            if value > threshold:
                failures.append(f"{metric}={value:.4f} > {threshold:.4f}")
        elif value < threshold:
            failures.append(f"{metric}={value:.4f} < {threshold:.4f}")
    return failures


def write_reports(out_dir: Path, rows: list[dict[str, Any]], gates: dict[str, float]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = aggregate_evaluations(rows)
    failures = gate_failures(summary, gates)
    summary["passes_quality_gate"] = not failures
    summary["gate_failures"] = failures

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (out_dir / "evaluated_cases.jsonl").open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out_dir / "summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)
    (out_dir / "report.md").write_text(_markdown_report(summary), encoding="utf-8")
    return summary


def _markdown_report(summary: dict[str, Any]) -> str:
    status = "YES" if summary["passes_quality_gate"] else "NO"
    lines = [
        "# Parser Benchmark Fixture Report",
        "",
        f"Passes quality gate: {status}",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in summary.items():
        if key in {"passes_quality_gate", "gate_failures"}:
            continue
        lines.append(f"| {key} | {value} |")
    if summary["gate_failures"]:
        lines.extend(["", "## Gate Failures", ""])
        lines.extend(f"- {failure}" for failure in summary["gate_failures"])
    return "\n".join(lines) + "\n"


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = min(round((percentile / 100) * (len(sorted_values) - 1)), len(sorted_values) - 1)
    return sorted_values[index]
