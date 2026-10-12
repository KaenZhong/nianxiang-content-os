#!/usr/bin/env python3
"""Discover a Nianxiang Feishu wiki and safely initialize local-config.json."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Pattern
from runtime.paths import add_profile_args, default_private_file
from runtime.models import NianxiangError, read_json, write_json
from runtime.feishu_cli import FeishuAdapter
from runtime.knowledge import verify_account, profile_state


ROOT_TITLES = {
    "home": re.compile(r"^首页｜念响AI · 内容(?:OS|工坊)$"),
    "positioning": re.compile(r"^01｜定位与策略$"),
    "assets": re.compile(r"^02｜共创与资产$"),
    "creation": re.compile(r"^03｜创作与运营$"),
    "methodology.current": re.compile(r"^04｜内容方法论$"),
}

CHILDREN = {
    "positioning": [
        ("content.strategy", re.compile(r"^01｜内容经营策略$"), "read_write"),
        ("audience.needs", re.compile(r"^02｜受众与需求$"), "read_write"),
        ("ip.profile", re.compile(r"^03｜个人IP档案$"), "read_write"),
        ("expression.baseline", re.compile(r"^04｜个人表达风格$"), "read_write"),
    ],
    "assets": [
        ("cocreation.index", re.compile(r"^01｜念响共创记录$"), "create_child"),
        ("content.assets", re.compile(r"^02｜内容资产库$"), "read_write"),
    ],
    "creation": [
        ("operations.index", re.compile(r"^01｜内容操盘$"), "read_write"),
        ("content.archives", re.compile(r"^02｜内容档案$"), "create_child"),
        ("content.campaigns", re.compile(r"^03｜内容战役$"), "create_child"),
        ("content.reviews", re.compile(r"^04｜阶段复盘$"), "create_child"),
    ],
}

BASE_TABLE_TITLES = {
    "topic_pool": "选题池",
    "moments_works": "朋友圈文案",
    "video_works": "短视频口播",
    "article_works": "公众号长文",
}


class InitError(RuntimeError):
    pass


class UnsupportedAuthCommand(InitError):
    pass


def run_json(command: list[str], *, require_ok: bool = True) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        if command[1:3] == ["auth", "status"] and 'unknown command "auth" for "lark-cli"' in result.stderr:
            raise UnsupportedAuthCommand("this CLI has no auth status command")
        action = " ".join(command[1:3])
        raise InitError(f"Feishu {action} read failed (exit {result.returncode}); check login, permission, entry URL, and network")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InitError("Feishu CLI returned an unreadable response") from exc
    if require_ok and payload.get("ok") is not True:
        raise InitError("Feishu CLI returned ok=false")
    return payload


def verify_user_identity() -> None:
    try:
        payload = run_json(
            ["lark-cli", "auth", "status", "--json", "--verify"],
            require_ok=False,
        )
    except UnsupportedAuthCommand:
        payload = run_json(["lark-cli", "contact", "+get-user", "--as", "user", "--format", "json"])
        data = payload.get("data")
        user = data.get("user") if isinstance(data, dict) else None
        account_id = (user.get("open_id") or user.get("openId")) if isinstance(user, dict) else None
        if payload.get("identity") != "user" or not isinstance(account_id, str) or not account_id.strip():
            raise InitError("verified Feishu user identity is required")
    else:
        identities = payload.get("identities")
        user = identities.get("user") if isinstance(identities, dict) else None
        if payload.get("verified") is not True or not isinstance(user, dict) or user.get("verified") is not True or not user.get("openId"):
            raise InitError("verified Feishu user identity is required")


def normalize_entry(entry: str) -> str:
    entry = entry.strip()
    if not entry:
        raise InitError("entry URL or wiki node token is required")
    if "://" not in entry:
        return f"https://feishu.cn/wiki/{entry}"
    if "/wiki/" not in entry:
        raise InitError("entry must be a Feishu wiki URL, not a docx or drive URL")
    return entry


def list_nodes(space_id: str, parent_token: str | None = None) -> list[dict[str, Any]]:
    command = [
        "lark-cli",
        "wiki",
        "+node-list",
        "--space-id",
        space_id,
        "--page-all",
        "--as",
        "user",
        "--format",
        "json",
    ]
    if parent_token:
        command.extend(["--parent-node-token", parent_token])
    payload = run_json(command)
    if payload.get("data", {}).get("has_more") is True:
        raise InitError("wiki listing is incomplete; refusing partial discovery")
    nodes = payload.get("data", {}).get("nodes")
    if not isinstance(nodes, list):
        raise InitError("node listing did not contain a node list")
    return nodes


def select_unique(
    nodes: list[dict[str, Any]],
    pattern: Pattern[str],
    label: str,
    space_id: str,
    parent_token: str,
    expected_type: str = "docx",
) -> dict[str, Any]:
    matches = [node for node in nodes if pattern.fullmatch(str(node.get("title", "")))]
    if not matches:
        raise InitError(f"missing expected node: {label}")
    if len(matches) > 1:
        raise InitError(f"duplicate expected node: {label}")
    node = matches[0]
    if str(node.get("space_id", "")) != space_id:
        raise InitError(f"space mismatch at {label}")
    if str(node.get("parent_node_token", "")) != parent_token:
        raise InitError(f"hierarchy mismatch at {label}")
    if node.get("obj_type") != expected_type:
        raise InitError(f"expected {expected_type} node at {label}")
    if not node.get("node_token") or not node.get("obj_token"):
        raise InitError(f"missing token pair at {label}")
    return node


def mapping_item(node: dict[str, Any], access: str) -> dict[str, Any]:
    return {
        "expected_title": node["title"],
        "node_token": node["node_token"],
        "obj_token": node["obj_token"],
        "obj_type": node["obj_type"],
        "parent_node_token": node.get("parent_node_token", ""),
        "access": access,
    }


def discover_base_tables(base_token: str) -> dict[str, dict[str, str]]:
    payload = run_json([
        "lark-cli", "base", "+table-list", "--base-token", base_token,
        "--as", "user", "--format", "json",
    ])
    if payload.get("data", {}).get("has_more") is True:
        raise InitError("Base listing is incomplete; refusing partial discovery")
    tables = payload.get("data", {}).get("tables")
    if not isinstance(tables, list):
        raise InitError("Base table listing did not contain a table list")
    result: dict[str, dict[str, str]] = {}
    for table_key, expected_title in BASE_TABLE_TITLES.items():
        matches = [table for table in tables if table.get("name") == expected_title]
        if not matches:
            raise InitError(f"missing expected Base table: {expected_title}")
        if len(matches) > 1:
            raise InitError(f"duplicate expected Base table: {expected_title}")
        table_id = str(matches[0].get("id", ""))
        if not table_id:
            raise InitError(f"missing table ID at {expected_title}")
        result[table_key] = {"expected_title": expected_title, "table_id": table_id}
    return result


def discover(entry: str) -> tuple[dict[str, Any], dict[str, str]]:
    verify_user_identity()
    entry_payload = run_json([
        "lark-cli",
        "wiki",
        "+node-get",
        "--node-token",
        normalize_entry(entry),
        "--as",
        "user",
        "--format",
        "json",
    ])
    entry_node = entry_payload.get("data", {})
    space_id = str(entry_node.get("space_id", ""))
    if not space_id:
        raise InitError("entry did not resolve to a wiki space")

    root_nodes = list_nodes(space_id)
    roots: dict[str, dict[str, Any]] = {}
    for root_id, pattern in ROOT_TITLES.items():
        roots[root_id] = select_unique(root_nodes, pattern, root_id, space_id, "")

    knowledge_map: dict[str, dict[str, Any]] = {
        "methodology.current": mapping_item(roots["methodology.current"], "read_write")
    }
    display_paths: dict[str, str] = {
        "methodology.current": roots["methodology.current"]["title"]
    }
    for root_id, specifications in CHILDREN.items():
        parent = roots[root_id]
        child_nodes = list_nodes(space_id, parent["node_token"])
        for knowledge_id, pattern, access in specifications:
            node = select_unique(
                child_nodes,
                pattern,
                knowledge_id,
                space_id,
                parent["node_token"],
            )
            knowledge_map[knowledge_id] = mapping_item(node, access)
            display_paths[knowledge_id] = f"{parent['title']} / {node['title']}"

    operations_parent = knowledge_map["operations.index"]
    operation_children = list_nodes(space_id, operations_parent["node_token"])
    base_node = select_unique(
        operation_children,
        re.compile(r"^念响AI · 内容中台$"),
        "operations.base",
        space_id,
        operations_parent["node_token"],
        "bitable",
    )
    knowledge_map["operations.base"] = mapping_item(base_node, "read_write")
    display_paths["operations.base"] = (
        f"{roots['creation']['title']} / {operations_parent['expected_title']} / {base_node['title']}"
    )
    base_tables = discover_base_tables(base_node["obj_token"])

    ordered_ids = [
        "content.strategy",
        "audience.needs",
        "ip.profile",
        "expression.baseline",
        "cocreation.index",
        "content.assets",
        "operations.index",
        "operations.base",
        "content.archives",
        "content.campaigns",
        "content.reviews",
        "methodology.current",
    ]
    config = {
        "schema_version": 4,
        "knowledge_backend": "feishu",
        "identity": "user",
        "fail_closed": True,
        "space_id": space_id,
        "last_verified_date": datetime.now().astimezone().date().isoformat(),
        "knowledge_map": {knowledge_id: knowledge_map[knowledge_id] for knowledge_id in ordered_ids},
        "base_tables": base_tables,
        "write_targets": {
            "cocreation_parent_knowledge_id": "cocreation.index",
            "archive_parent_knowledge_id": "content.archives",
            "campaign_parent_knowledge_id": "content.campaigns",
            "review_parent_knowledge_id": "content.reviews",
            "content_base_knowledge_id": "operations.base",
            "sync_candidate_knowledge_ids": [
                "content.strategy",
                "audience.needs",
                "ip.profile",
                "expression.baseline",
                "content.assets",
                "methodology.current",
            ],
        },
        "private": True,
        "include_in_public_release": False,
    }
    return config, display_paths


def show_preview(
    config: dict[str, Any], display_paths: dict[str, str], *, write_requested: bool
) -> None:
    print("Configuration preview")
    print(f"Space verified; {len(config['knowledge_map'])} knowledge mappings discovered")
    for knowledge_id, item in config["knowledge_map"].items():
        print(f"- {knowledge_id}: {display_paths[knowledge_id]} [{item['access']}]")
    if not write_requested:
        print("Preview only: no file has been written")


def write_config(output: Path, config: dict[str, Any], overwrite: bool) -> None:
    output = output.expanduser().resolve()
    if output.exists() and not overwrite:
        raise InitError("target local-config.json already exists; refusing to overwrite without --overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output.parent,
            prefix=".local-config.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, output)
    finally:
        if temp_name and Path(temp_name).exists():
            Path(temp_name).unlink()
    print(f"Created private configuration: {output}")


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry-url", required=True, help="Feishu wiki URL or raw wiki node token")
    parser.add_argument("--write", action="store_true", help="write the discovered configuration")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output path; defaults to the Skill private local-config.json",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output; use only after explicit user confirmation",
    )
    add_profile_args(parser)
    args = parser.parse_args()
    if args.output is None:
        try: args.output = default_private_file(Path(__file__).resolve().parents[1], "local-config.json", args)
        except NianxiangError as exc:
            print(f"FAIL: {exc.code}", file=sys.stderr)
            return 2

    if Path(__file__).resolve().parents[1] in args.output.expanduser().resolve().parents:
        print("FAIL: private output must be outside the Skill", file=sys.stderr)
        return 2
    if args.overwrite and not args.write:
        print("FAIL: --overwrite requires --write", file=sys.stderr)
        return 2
    if args.write and args.output.expanduser().exists() and not args.overwrite:
        print(
            "FAIL: target local-config.json already exists; refusing to overwrite without --overwrite",
            file=sys.stderr,
        )
        return 2

    try:
        config, display_paths = discover(args.entry_url)
        show_preview(config, display_paths, write_requested=args.write)
        if args.write:
            selected = default_private_file(skill_root, "local-config.json", args) if args.profile else None
            if selected and args.output.expanduser().resolve() == selected:
                state = profile_state(selected.parent, require_active=False)
                if state["space_id"] != config["space_id"]:
                    raise NianxiangError("space_mismatch", "discovered space differs from selected profile")
                verify_account(state, FeishuAdapter(config))
                state["active"] = False
                write_json(selected.parent / "state.json", state)
            write_config(args.output, config, args.overwrite)
    except (InitError, OSError, KeyError, NianxiangError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
