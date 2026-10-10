#!/usr/bin/env python3
"""Return only local writing rules matching the current creative task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from runtime.paths import add_profile_args, default_private_file
from runtime.rules import select_confirmed_rules
from runtime.models import NianxiangError,read_json
from runtime.paths import resolve_profile
from runtime.personal import read_personal_context
from runtime.feishu_cli import FeishuAdapter
STATUSES = {"active", "trial", "paused", "retired"}
BASES = {"user_explicit", "user_confirmed", "cross_work", "agent_inference"}


def validate(data: object) -> list[dict]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("rule memory schema_version must be 1")
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("each rule must be an object")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id or rule_id in seen:
            raise ValueError("rule IDs must be nonempty and unique")
        seen.add(rule_id)
        if not isinstance(rule.get("instruction"), str) or not rule["instruction"].strip():
            raise ValueError(f"{rule_id}: instruction is required")
        for key in ("channels", "surfaces", "materials"):
            values = rule.get(key)
            if not isinstance(values, list) or not values or not all(isinstance(value, str) and value for value in values):
                raise ValueError(f"{rule_id}: {key} must be a nonempty string list")
        if rule.get("status") not in STATUSES or rule.get("basis") not in BASES:
            raise ValueError(f"{rule_id}: invalid status or basis")
    return rules


def matches(values: list[str], actual: str) -> bool:
    return "*" in values or actual in values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", help="moments, wechat_image, short_video, article, etc.")
    parser.add_argument("--surface", help="body, caption_title, cover_title, etc.")
    parser.add_argument("--material", default="general", help="event_recording, general, etc.")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--include-trial", action="store_true")
    parser.add_argument("--check", action="store_true", help="validate the private rule file")
    parser.add_argument("--rules-file", type=Path, help="explicit private file for isolated validation")
    add_profile_args(parser)
    args = parser.parse_args()
    if not args.check and (not args.channel or not args.surface):
        parser.error("--channel and --surface are required unless --check is used")
    if not 1 <= args.limit <= 8:parser.error("--limit must be from 1 to 8")
    try:
        if args.rules_file:
            if not args.check:raise NianxiangError('legacy_source_not_active','explicit files may only be checked; migrate to Feishu before applying rules')
            rules=validate(read_json(args.rules_file))
        else:
            profile=resolve_profile(Path(__file__).resolve().parents[1],args.data_dir,args.profile)
            ctx=read_personal_context(profile,FeishuAdapter(read_json(profile/'local-config.json')))
            if ctx['status'] not in ('ready','empty'):raise NianxiangError(ctx.get('code',ctx['status']),'personal source is not current')
            rules=ctx['rules']['rules']
    except (NianxiangError,ValueError) as exc:
        print('FAIL: '+getattr(exc,'code','invalid_rules'),file=sys.stderr);return 2
    if args.check:
        print(f"OK: {len(rules)} private rules are structurally valid")
        return 0
    try:
        selected = select_confirmed_rules({"schema_version": 1, "rules": rules}, {"channel": args.channel, "surface": args.surface, "material": args.material, "include_trial": args.include_trial, "limit": args.limit})
    except NianxiangError as exc:
        print(f"FAIL: {exc.code}", file=sys.stderr)
        return 1
    for rule in selected[:args.limit]:
        tag = " [试行]" if rule["status"] == "trial" else ""
        print(f"- {rule['id']}{tag}: {rule['instruction']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
