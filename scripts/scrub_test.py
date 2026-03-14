#!/usr/bin/env python3
"""Quick tool to feed any log file through the BundleScrubber and see what it catches.

Usage:
    python scripts/scrub_test.py <file_or_directory> [--layer llm|storage] [--strict]

Examples:
    # Scrub a single file
    python scripts/scrub_test.py cloudwatch-logs.txt

    # Scrub all files in a directory
    python scripts/scrub_test.py ./aws-logs/

    # Use strict mode (redacts everything aggressively)
    python scripts/scrub_test.py eks-logs.json --strict

    # Test Layer 2 (LLM mode — includes prompt injection detection)
    python scripts/scrub_test.py logs.txt --layer llm

    # Read from stdin (pipe AWS CLI output directly)
    aws logs filter-log-events --log-group-name /my/group --output text | python scripts/scrub_test.py -
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bundle_analyzer.security.models import SecurityPolicy
from bundle_analyzer.security.scrubber import BundleScrubber


def scrub_file(
    scrubber: BundleScrubber,
    content: str,
    filename: str,
    layer: str,
) -> dict:
    """Scrub a single file's content and return results."""
    if layer == "llm":
        result, report = scrubber.scrub_for_llm(content)
    else:
        result, report = scrubber.scrub_for_storage(content, source_type="container_log", source_path=filename)

    return {
        "file": filename,
        "original_length": len(content),
        "scrubbed_length": len(result),
        "total_redactions": report.total_redactions,
        "prompt_injection_detected": report.prompt_injection_detected,
        "categories": dict(report.redactions_by_category),
        "summary": report.summary_line(),
        "scrubbed_preview": result[:2000] + ("..." if len(result) > 2000 else ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Feed logs through BundleScrubber to test secret detection"
    )
    parser.add_argument(
        "input",
        help="File path, directory, or '-' for stdin",
    )
    parser.add_argument(
        "--layer",
        choices=["storage", "llm"],
        default="storage",
        help="Scrubbing layer: 'storage' (Layer 1) or 'llm' (Layer 2 with prompt guard)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict security policy (redacts everything aggressively)",
    )
    parser.add_argument(
        "--show-full",
        action="store_true",
        help="Show full scrubbed output instead of 2000-char preview",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Build scrubber
    policy = SecurityPolicy(mode="strict") if args.strict else SecurityPolicy()
    scrubber = BundleScrubber(policy=policy)

    results: list[dict] = []

    if args.input == "-":
        # Read from stdin
        content = sys.stdin.read()
        results.append(scrub_file(scrubber, content, "<stdin>", args.layer))
    elif Path(args.input).is_dir():
        # Process all files in directory
        for p in sorted(Path(args.input).rglob("*")):
            if p.is_file() and p.stat().st_size < 50_000_000:  # skip >50MB
                try:
                    content = p.read_text(errors="replace")
                    results.append(scrub_file(scrubber, content, str(p), args.layer))
                except Exception as e:
                    print(f"SKIP {p}: {e}", file=sys.stderr)
    else:
        content = Path(args.input).read_text(errors="replace")
        results.append(scrub_file(scrubber, content, args.input, args.layer))

    # Output
    if args.json_output:
        print(json.dumps(results, indent=2))
        return

    total_redactions = 0
    for r in results:
        total_redactions += r["total_redactions"]
        print(f"\n{'='*60}")
        print(f"File: {r['file']}")
        print(f"Size: {r['original_length']:,} → {r['scrubbed_length']:,} chars")
        print(f"Redactions: {r['total_redactions']}")
        if r["categories"]:
            print(f"Categories: {r['categories']}")
        if r["prompt_injection_detected"]:
            print("⚠ PROMPT INJECTION DETECTED")
        print(f"Summary: {r['summary']}")
        if args.show_full:
            print(f"\n--- Scrubbed output ---\n{r['scrubbed_preview']}")
        print(f"{'='*60}")

    print(f"\nTotal: {len(results)} file(s), {total_redactions} redaction(s)")


if __name__ == "__main__":
    main()
