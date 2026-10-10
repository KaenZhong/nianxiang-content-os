#!/usr/bin/env python3
"""Validate the private expression-baseline snapshot metadata and body."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import re
import sys
from runtime.paths import add_profile_args, default_private_file
from runtime.models import NianxiangError


EXPECTED = {
    "source_title": '"04｜个人表达风格"',
    "knowledge_id": "expression.baseline",
    "snapshot_status": "current",
    "private": "true",
    "include_in_public_release": "false",
}


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise ValueError("missing YAML-style frontmatter")
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "snapshot",
        nargs="?",
        type=Path,
        default=None,
    )
    add_profile_args(parser)
    args = parser.parse_args()
    if args.snapshot is None:
        try: args.snapshot = default_private_file(Path(__file__).resolve().parents[1], "expression-baseline-snapshot.md", args)
        except NianxiangError as exc:
            print(f"FAIL: {exc.code}", file=sys.stderr)
            return 2
    try:
        text = args.snapshot.read_text(encoding="utf-8")
        metadata = parse_frontmatter(text)
        for key, expected in EXPECTED.items():
            if metadata.get(key) != expected:
                raise ValueError(f"{key} must be {expected}")
        revision = int(metadata.get("source_revision", ""))
        if revision < 1:
            raise ValueError("source_revision must be at least 1")
        count = int(metadata.get("confirmed_rule_count", ""))
        if count < 0:
            raise ValueError("confirmed_rule_count must not be negative")
        date.fromisoformat(metadata.get("synced_on", ""))
        if count == 0 and "暂无已确认的跨渠道个人表达规则" not in text:
            raise ValueError("zero-rule snapshot must explicitly say no confirmed rules")
        if "飞书原文是唯一权威" not in text:
            raise ValueError("snapshot must preserve Feishu authority boundary")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: expression baseline snapshot is valid at revision {revision} with {count} confirmed rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
