#!/usr/bin/env python3
"""Verify private Nianxiang mappings against live Feishu wiki nodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from runtime.paths import add_profile_args, default_private_file
from runtime.models import NianxiangError


def run_json(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ValueError("live lookup failed")
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("live response is not valid JSON") from exc
    if response.get("ok") is not True or response.get("identity") != "user":
        raise ValueError("live lookup did not return ok user identity")
    return response.get("data", {})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=None,
    )
    add_profile_args(parser)
    args = parser.parse_args()
    if args.config is None:
        try: args.config = default_private_file(Path(__file__).resolve().parents[1], "local-config.json", args)
        except NianxiangError as exc:
            print(f"FAIL: {exc.code}", file=sys.stderr)
            return 2

    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read private config: {exc}", file=sys.stderr)
        return 1

    expected_space = str(config.get("space_id", ""))
    mapping = config.get("knowledge_map", {})
    errors: list[str] = []
    checked = 0

    for knowledge_id, expected in mapping.items():
        command = [
            "lark-cli",
            "wiki",
            "+node-get",
            "--node-token",
            f"https://feishu.cn/wiki/{expected['node_token']}",
            "--as",
            "user",
            "--format",
            "json",
        ]
        try:
            actual = run_json(command)
        except ValueError as exc:
            errors.append(f"{knowledge_id}: {exc}")
            continue
        comparisons = {
            "space_id": expected_space,
            "node_token": expected.get("node_token"),
            "obj_token": expected.get("obj_token"),
            "obj_type": expected.get("obj_type"),
            "title": expected.get("expected_title"),
            "parent_node_token": expected.get("parent_node_token"),
        }
        mismatches = [
            field for field, wanted in comparisons.items() if str(actual.get(field, "")) != str(wanted)
        ]
        if mismatches:
            errors.append(f"{knowledge_id}: mismatch in {', '.join(mismatches)}")
            continue
        checked += 1

    base_item = mapping.get("operations.base", {})
    base_token = base_item.get("obj_token", "")
    tables = config.get("base_tables", {})
    if not errors and base_token:
        try:
            data = run_json([
                "lark-cli", "base", "+table-list", "--base-token", base_token,
                "--as", "user", "--format", "json",
            ])
            actual_tables = data.get("tables", [])
            for table_key, expected in tables.items():
                matches = [table for table in actual_tables if table.get("id") == expected.get("table_id")]
                if len(matches) != 1 or matches[0].get("name") != expected.get("expected_title"):
                    errors.append(f"base_tables.{table_key}: live table mismatch")
        except ValueError as exc:
            errors.append(f"base_tables: {exc}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"OK: {checked} live knowledge mappings and {len(tables)} Base tables match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
