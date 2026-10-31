#!/usr/bin/env python3
"""Read-only size/type gate for local files and the actual Git index.

This is not a secret scanner, approval verifier, or server policy enforcer.
"""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess


MAX_BYTES = 15_000_000  # Decimal MB; exactly this size is allowed.


def git(repo, *args):
    """Read real Git objects, ignoring replacement refs and optional index writes."""
    result = subprocess.run(
        ["git", "--no-replace-objects", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        # Do not echo arbitrary repository/config output into audit reports.
        raise ValueError(f"git {args[0]} failed (exit {result.returncode})")
    return result.stdout


def check_file(path):
    """Inspect metadata only; never follow a final symlink or read file content."""
    info = Path(path).lstat()
    errors = []
    if not stat.S_ISREG(info.st_mode):
        errors.append("not a regular file; record metadata only")
    elif info.st_size > MAX_BYTES:
        errors.append(f"size {info.st_size} exceeds {MAX_BYTES} bytes")
    return {"path": str(path), "size_bytes": info.st_size, "errors": errors}


def validate_root(value):
    """Require a canonical repo-relative directory, never a Git pathspec."""
    parts = value.split("/")
    if not value or any(part in ("", ".", "..", ".git") for part in parts):
        raise ValueError("operations-root must be a canonical repo-relative directory")
    if PurePosixPath(value).is_absolute() or "\\" in value or "\0" in value:
        raise ValueError("operations-root must be a canonical repo-relative directory")
    return value


def check_index(repo, operations_root):
    """Check every staged/tracked object in the resulting operations snapshot.

    Reading object IDs instead of worktree files catches partial staging, files
    changed after `git add`, and gitlinks; NUL records preserve unusual filenames.
    """
    root = validate_root(operations_root)
    repo = Path(repo).resolve(strict=True)
    actual = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel")).rstrip("\n")).resolve()
    if actual != repo:
        raise ValueError("repo must be the repository root, not a subdirectory")
    index = git(repo, "ls-files", "--stage", "-z")
    prefix = os.fsencode(root + "/")
    entries = []
    errors = []
    sizes = {}
    for record in index.split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        if not raw_path.startswith(prefix):
            # A symlink/gitlink at the root is also invalid, not an empty archive.
            if raw_path == os.fsencode(root):
                errors.append({"path": os.fsdecode(raw_path), "error": "operations-root is an index file, not a directory"})
            continue
        mode, oid, stage = header.split()
        path = os.fsdecode(raw_path)
        entry = {"path": path, "mode": mode.decode("ascii"), "errors": []}
        if stage != b"0":
            entry["errors"].append("unresolved index conflict")
        if mode not in (b"100644", b"100755"):
            entry["errors"].append("not a regular Git file; symlinks/gitlinks are metadata-only")
        # Missing/promised blobs are failures; unknown size must not pass.
        if not entry["errors"]:
            if oid not in sizes:
                sizes[oid] = int(git(repo, "cat-file", "-s", oid.decode("ascii")))
            entry["size_bytes"] = sizes[oid]
            if sizes[oid] > MAX_BYTES:
                entry["errors"].append(f"size {sizes[oid]} exceeds {MAX_BYTES} bytes")
        entries.append(entry)
    if not entries and not errors:
        errors.append({"path": root, "error": "no indexed operations files; check root and staging"})
    errors.extend({"path": entry["path"], "error": error} for entry in entries for error in entry["errors"])
    return {"repo": str(repo), "operations_root": root, "checked": len(entries), "files": entries, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    file_parser = commands.add_parser("file", help="check local metadata before staging")
    file_parser.add_argument("path", type=Path)
    index_parser = commands.add_parser("index", help="check the actual Git index before commit")
    index_parser.add_argument("--repo", required=True, type=Path)
    index_parser.add_argument("--operations-root", default="agent-works/operations")
    args = parser.parse_args()
    try:
        report = check_file(args.path) if args.command == "file" else check_index(args.repo, args.operations_root)
    except (OSError, ValueError) as error:
        report = {"errors": [str(error)]}
    report["limit_bytes"] = MAX_BYTES
    report["passed"] = not report["errors"]
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
