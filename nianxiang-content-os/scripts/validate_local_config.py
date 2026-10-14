#!/usr/bin/env python3
"""Validate the private Nianxiang knowledge-backend configuration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from runtime.paths import add_profile_args, default_private_file
from runtime.models import NianxiangError


REQUIRED_IDS = {
    "content.strategy", "audience.needs", "ip.profile", "expression.baseline", "cocreation.index",
    "content.assets", "operations.index", "operations.base", "content.archives",
    "content.campaigns", "content.reviews", "methodology.current", "content.methods",
}

EXPECTED_ACCESS = {
    "content.strategy": "read_write", "audience.needs": "read_write",
    "ip.profile": "read_write", "expression.baseline": "read_write",
    "cocreation.index": "create_child",
    "content.assets": "read_write", "operations.index": "read_write",
    "operations.base": "read_write", "content.archives": "create_child",
    "content.campaigns": "create_child", "content.reviews": "create_child",
    "methodology.current": "read_write", "content.methods": "read_write",
}

SYNC_IDS = {
    "content.strategy", "audience.needs", "ip.profile", "expression.baseline",
    "content.assets", "methodology.current", "content.methods",
}

BASE_TABLES = {
    "topic_pool": "选题池",
    "moments_works": "朋友圈文案",
    "video_works": "短视频口播",
    "article_works": "公众号长文",
}
OPTIONAL_BASE_TABLES = {"works_index": "旧作品索引（迁移备份）"}


def fail(message: str) -> None:
    raise ValueError(message)


def require_same_parent(mapping: dict, ids: tuple[str, ...], label: str) -> None:
    parents = {str(mapping[item].get("parent_node_token", "")) for item in ids}
    if "" in parents or len(parents) != 1:
        fail(f"{label} parent hierarchy is invalid")


def validate(data: dict, schema_version: int = 5) -> None:
    if schema_version not in (4, 5) or data.get("schema_version") != schema_version:
        fail(f"schema_version must be {schema_version}; schema 4 requires explicit upgrade")
    if data.get("knowledge_backend") != "feishu":
        fail("knowledge_backend must be feishu")
    if data.get("identity") != "user":
        fail("identity must be user")
    if data.get("fail_closed") is not True:
        fail("fail_closed must be true")
    if not str(data.get("space_id", "")).strip():
        fail("space_id is required")
    if "REPLACE_WITH" in json.dumps(data, ensure_ascii=False):
        fail("private config still contains placeholders")

    mapping = data.get("knowledge_map")
    if not isinstance(mapping, dict):
        fail("knowledge_map must be an object")
    required_ids = REQUIRED_IDS if schema_version == 5 else REQUIRED_IDS - {"content.methods"}
    missing = required_ids - set(mapping)
    extra = set(mapping) - required_ids
    if missing or extra:
        fail(f"knowledge_map mismatch; missing={sorted(missing)}, extra={sorted(extra)}")

    node_tokens: set[str] = set()
    obj_tokens: set[str] = set()
    for knowledge_id, item in mapping.items():
        if not isinstance(item, dict):
            fail(f"{knowledge_id} must be an object")
        for key in ("expected_title", "node_token", "obj_token", "obj_type", "access"):
            if not str(item.get(key, "")).strip():
                fail(f"{knowledge_id}.{key} is required")
        expected_type = "bitable" if knowledge_id == "operations.base" else "docx"
        if item["obj_type"] != expected_type:
            fail(f"{knowledge_id}.obj_type must be {expected_type}")
        expected_access = EXPECTED_ACCESS[knowledge_id]
        if item["access"] != expected_access:
            fail(f"{knowledge_id}.access must be {expected_access}")
        if item["node_token"] in node_tokens:
            fail(f"duplicate node_token at {knowledge_id}")
        if item["obj_token"] in obj_tokens:
            fail(f"duplicate obj_token at {knowledge_id}")
        node_tokens.add(item["node_token"])
        obj_tokens.add(item["obj_token"])

    require_same_parent(
        mapping,
        ("content.strategy", "audience.needs", "ip.profile", "expression.baseline"),
        "positioning",
    )
    require_same_parent(mapping, ("cocreation.index", "content.assets"), "assets")
    require_same_parent(
        mapping,
        ("operations.index", "content.archives", "content.campaigns", "content.reviews"),
        "operations",
    )
    if mapping["operations.base"].get("parent_node_token") != mapping["operations.index"].get("node_token"):
        fail("operations.base.parent_node_token must point to operations.index.node_token")

    if schema_version == 5:
        methods = mapping["content.methods"]
        if methods.get("parent_node_token") != mapping["methodology.current"]["node_token"]:
            fail("content.methods must be a direct child of methodology.current")
        if methods["expected_title"] != "01｜创作方法与规则":
            fail("content.methods title must be 01｜创作方法与规则")

    tables = data.get("base_tables")
    if (not isinstance(tables, dict) or not set(BASE_TABLES).issubset(tables)
            or set(tables) - set(BASE_TABLES) - set(OPTIONAL_BASE_TABLES)):
        fail("base_tables must contain topic_pool and the three channel tables")
    table_ids: set[str] = set()
    expected_tables = {**BASE_TABLES, **{key: title for key, title in OPTIONAL_BASE_TABLES.items() if key in tables}}
    for table_key, expected_title in expected_tables.items():
        table = tables[table_key]
        if not isinstance(table, dict):
            fail(f"base_tables.{table_key} must be an object")
        if table.get("expected_title") != expected_title:
            fail(f"base_tables.{table_key}.expected_title must be {expected_title}")
        table_id = str(table.get("table_id", "")).strip()
        if not table_id:
            fail(f"base_tables.{table_key}.table_id is required")
        if table_id in table_ids:
            fail(f"duplicate base table_id at {table_key}")
        table_ids.add(table_id)

    targets = data.get("write_targets", {})
    expected_targets = {
        "cocreation_parent_knowledge_id": "cocreation.index",
        "archive_parent_knowledge_id": "content.archives",
        "campaign_parent_knowledge_id": "content.campaigns",
        "review_parent_knowledge_id": "content.reviews",
        "content_base_knowledge_id": "operations.base",
    }
    for key, value in expected_targets.items():
        if targets.get(key) != value:
            fail(f"write_targets.{key} must be {value}")
    sync_ids = targets.get("sync_candidate_knowledge_ids")
    if not isinstance(sync_ids, list) or set(sync_ids) != (SYNC_IDS if schema_version == 5 else SYNC_IDS - {"content.methods"}) or len(sync_ids) != (len(SYNC_IDS) if schema_version == 5 else len(SYNC_IDS) - 1):
        fail("sync_candidate_knowledge_ids must contain the configured long-term pages")
    if data.get("private") is not True or data.get("include_in_public_release") is not False:
        fail("private/public-release flags are invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config", nargs="?", type=Path,
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
        data = json.loads(args.config.read_text(encoding="utf-8"))
        validate(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("OK: private local configuration is structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
