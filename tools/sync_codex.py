#!/usr/bin/env python3
"""Check or install the committed public package into the local Codex Skill slot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "nianxiang-content-os"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE / "scripts"))

from runtime.models import NianxiangError, read_json  # noqa: E402
from runtime.releases import (  # noqa: E402
    apply_release,
    installation_status,
    verify_release,
    verify_tree,
)


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def selected_profile(data_root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().absolute()
    profiles = data_root / "profiles"
    candidates = sorted(path for path in profiles.iterdir() if path.is_dir())
    if len(candidates) != 1:
        raise ValueError("select one private profile with --profile-dir")
    return candidates[0]


def make_archive(path: Path, manifest: dict) -> None:
    names = sorted(manifest["files"]) + ["release-manifest.json"]
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(SOURCE / name, arcname=f"nianxiang-content-os/{name}")


def committed_source() -> str:
    changed = subprocess.run(
        ["git", "status", "--porcelain", "--", "nianxiang-content-os"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    if changed.stdout.strip():
        raise ValueError("commit public source changes before syncing Codex")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return head.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform a managed local update")
    parser.add_argument("--consent", help="the user's actual instruction authorizing this update")
    parser.add_argument(
        "--skill-root",
        type=Path,
        default=Path.home() / ".codex/skills/nianxiang-content-os",
    )
    parser.add_argument("--data-root", type=Path, default=Path.home() / ".nianxiang")
    parser.add_argument("--profile-dir", type=Path)
    args = parser.parse_args()

    try:
        manifest = read_json(SOURCE / "release-manifest.json")
        verify_tree(SOURCE, manifest)
        source_commit = committed_source()
        requested_root = args.skill_root.expanduser().absolute()
        resolved_root = requested_root.resolve(strict=True)
        before = installation_status(resolved_root)
        result = {
            "source_version": manifest["version"],
            "source_verified": True,
            "source_commit": source_commit,
            "requested_skill_root": str(requested_root),
            "codex_skill_root": str(resolved_root),
            "current_chat_reloaded": False,
            "cross_session_verified": False,
            "codex_before": before,
        }
        if not args.apply:
            result["next_action"] = "run with --apply and --consent after reviewing the versions"
            emit(result)
            return 0
        if not (args.consent or "").strip():
            raise ValueError("--apply requires --consent with the user's actual instruction")
        if before["status"] not in {"unmanaged", "active", "rolled_back", "aborted"}:
            raise ValueError(f"Codex installation needs inspection: {before['status']}")
        profile = selected_profile(args.data_root.expanduser().absolute(), args.profile_dir)
        with TemporaryDirectory(prefix="nianxiang-codex-sync-") as temp:
            archive = Path(temp) / "nianxiang-content-os.zip"
            make_archive(archive, manifest)
            checked = verify_release(archive, manifest)
            if checked["status"] != "verified":
                raise ValueError(f"package verification failed: {checked}")
            result["archive_sha256"] = checked["archive_sha256"]
            if requested_root.resolve(strict=True) != resolved_root:
                raise ValueError("installation path changed during preflight")
            applied = apply_release(archive, resolved_root, profile, args.consent)
        result["apply_result"] = applied
        result["codex_after"] = installation_status(resolved_root)
        if applied["status"] not in {"updated", "up_to_date"}:
            emit(result)
            return 1
        verify_tree(resolved_root, manifest)
        result["installed_matches_source"] = True
        emit(result)
        return 0
    except (NianxiangError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        emit({"status": "blocked", "reason": getattr(exc, "code", str(exc))})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
