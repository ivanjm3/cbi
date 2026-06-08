#!/usr/bin/env python
"""CLI tool to query Bedrock cost tracking data.

Usage:
    python scripts/cost_report.py today
    python scripts/cost_report.py daily 2026-06-04
    python scripts/cost_report.py monthly 2026 6
    python scripts/cost_report.py all
"""

import sys
from datetime import datetime, timezone

from src.services.cost_tracker import get_cost_tracker


def format_cost(cost_usd: float) -> str:
    """Format cost with appropriate precision."""
    if cost_usd == 0:
        return "$0.00"
    elif cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    else:
        return f"${cost_usd:.2f}"


def print_daily_report(date: str | None = None):
    """Print cost report for a specific date."""
    tracker = get_cost_tracker()
    summary = tracker.get_daily_summary(date)
    
    print("=" * 70)
    print(f"BEDROCK COST REPORT — {summary['date']}")
    print("=" * 70)
    print(f"Total Calls:         {summary['total_calls']}")
    print(f"Total Cost:          {format_cost(summary['total_cost_usd'])}")
    print(f"Input Tokens:        {summary['total_input_tokens']:,}")
    print(f"Output Tokens:       {summary['total_output_tokens']:,}")
    print()
    
    if summary['breakdown']:
        print("Breakdown by Component:")
        print("-" * 70)
        print(f"{'Component':<30} {'Calls':>10} {'Cost':>15} {'Tokens':>15}")
        print("-" * 70)
        for item in summary['breakdown']:
            total_tokens = item['input_tokens'] + item['output_tokens']
            print(
                f"{item['component']:<30} "
                f"{item['calls']:>10} "
                f"{format_cost(item['cost_usd']):>15} "
                f"{total_tokens:>15,}"
            )
        print()
    
    if summary.get('by_service'):
        print("Breakdown by AWS Service:")
        print("-" * 70)
        print(f"{'Service':<30} {'Calls':>10} {'Cost':>15}")
        print("-" * 70)
        for item in summary['by_service']:
            print(
                f"{item['service']:<30} "
                f"{item['calls']:>10} "
                f"{format_cost(item['cost_usd']):>15}"
            )
        print("=" * 70)
    else:
        print("=" * 70)


def print_monthly_report(year: int, month: int):
    """Print cost report for a specific month."""
    tracker = get_cost_tracker()
    summary = tracker.get_monthly_summary(year, month)
    
    print("=" * 70)
    print(f"BEDROCK COST REPORT — {year}-{month:02d}")
    print("=" * 70)
    print(f"Total Calls:         {summary['total_calls']}")
    print(f"Total Cost:          {format_cost(summary['total_cost_usd'])}")
    print(f"Input Tokens:        {summary['total_input_tokens']:,}")
    print(f"Output Tokens:       {summary['total_output_tokens']:,}")
    print()
    
    if summary['daily']:
        print("Daily Breakdown:")
        print("-" * 70)
        print(f"{'Date':<15} {'Calls':>10} {'Cost':>15}")
        print("-" * 70)
        for item in summary['daily']:
            print(
                f"{item['date']:<15} "
                f"{item['calls']:>10} "
                f"{format_cost(item['cost_usd']):>15}"
            )
        print("=" * 70)
    else:
        print("No data for this month.")
        print("=" * 70)


def print_all_time_report():
    """Print all-time cost report."""
    tracker = get_cost_tracker()
    summary = tracker.get_all_time_summary()
    
    print("=" * 70)
    print("BEDROCK COST REPORT — ALL TIME")
    print("=" * 70)
    print(f"Total Calls:         {summary['total_calls']}")
    print(f"Total Cost:          {format_cost(summary['total_cost_usd'])}")
    print(f"Input Tokens:        {summary['total_input_tokens']:,}")
    print(f"Output Tokens:       {summary['total_output_tokens']:,}")
    print()
    
    if summary['breakdown']:
        print("Breakdown by Component:")
        print("-" * 70)
        print(f"{'Component':<30} {'Calls':>10} {'Cost':>15}")
        print("-" * 70)
        for item in summary['by_service']:
            print(
                f"{item['service']:<30} "
                f"{item['calls']:>10} "
                f"{format_cost(item['cost_usd']):>15}"
            )
        print()
    
    if summary['by_model']:
        print("Breakdown by Model:")
        print("-" * 70)
        print(f"{'Model':<50} {'Calls':>10} {'Cost':>10}")
        print("-" * 70)
        for item in summary['by_model']:
            model_short = item['model_id'].split('.')[-1][:50]
            print(
                f"{model_short:<50} "
                f"{item['calls']:>10} "
                f"{format_cost(item['cost_usd']):>10}"
            )
        print("=" * 70)


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/cost_report.py today")
        print("  python scripts/cost_report.py daily YYYY-MM-DD")
        print("  python scripts/cost_report.py monthly YYYY MM")
        print("  python scripts/cost_report.py all")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "today":
        print_daily_report()
    elif command == "daily":
        if len(sys.argv) < 3:
            print("Error: Missing date argument (YYYY-MM-DD)")
            sys.exit(1)
        print_daily_report(sys.argv[2])
    elif command == "monthly":
        if len(sys.argv) < 4:
            print("Error: Missing year and month arguments")
            sys.exit(1)
        year = int(sys.argv[2])
        month = int(sys.argv[3])
        print_monthly_report(year, month)
    elif command == "all":
        print_all_time_report()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
