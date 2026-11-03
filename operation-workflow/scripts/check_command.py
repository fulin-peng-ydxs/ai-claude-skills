#!/usr/bin/env python3
"""Classify command text against JSON globs; never execute or authorize it."""

import argparse
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
import shlex


EXIT_CODES = {"allow": 0, "ask": 2, "deny": 3}
FIELDS = {"version", "targets", "approval_ref", "default", "deny", "ask", "allow"}
OPERATORS = set(";&|<>()")
WRAPPERS = {
    "ssh", "scp", "sftp", "sudo", "doas", "su", "env", "sh", "bash", "dash",
    "zsh", "fish", "busybox", "perl", "ruby", "node", "awk", "gawk", "mawk",
    "sed", "xargs", "find", "timeout", "nice", "nohup", "watch", "eval", "exec",
    "command", "source", ".",
}


def tokens(text):
    """Parse only literal argv; shell evaluation must receive separate review."""
    if not isinstance(text, str) or any(c in text for c in "\n\r\0$`"):
        raise ValueError("unsupported shell syntax")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    result = list(lexer)
    if not result or any(token and set(token) <= OPERATORS for token in result):
        raise ValueError("unsupported shell syntax")
    return result


def matches(pattern, argv):
    """A glob stays inside one argument; a standalone ** spans arguments."""
    row = [True] + [False] * len(argv)
    for part in pattern:
        if part == "**":
            current = [row[0]]
            for index in range(1, len(row)):
                current.append(row[index] or current[index - 1])
        else:
            current = [False] + [
                row[index - 1] and fnmatchcase(argument, part)
                for index, argument in enumerate(argv, 1)
            ]
        row = current
    return row[-1]


def has_shell_expansion(command):
    """Keep quoted literal formats usable; do not guess unquoted expansions."""
    quote = None
    escaped = False
    for character in command:
        if escaped:
            escaped = False
        elif character == "\\" and quote != "'":
            escaped = True
        elif character in "\"'":
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
        elif quote is None and character in "*?[{}~#":
            return True
    return False


def validate(policy):
    """Reject incomplete/unknown fields instead of silently ignoring a rule."""
    if not isinstance(policy, dict) or set(policy) != FIELDS:
        raise ValueError("invalid policy fields")
    if type(policy["version"]) is not int or policy["version"] < 1:
        raise ValueError("invalid version")
    if policy["default"] != "ask":
        raise ValueError("default must be ask")
    approval = policy["approval_ref"]
    if approval is not None and (not isinstance(approval, str) or not approval.strip()):
        raise ValueError("invalid approval reference")
    if not isinstance(policy["targets"], list):
        raise ValueError("invalid targets")
    for target in policy["targets"]:
        if not isinstance(target, dict) or set(target) != {"server_id", "user"}:
            raise ValueError("invalid target fields")
        if any(not isinstance(v, str) or not v.strip() for v in target.values()):
            raise ValueError("invalid target value")
    rules = {}
    for category in ("deny", "ask", "allow"):
        if not isinstance(policy[category], list):
            raise ValueError("rules must be lists")
        rules[category] = [(pattern, tokens(pattern)) for pattern in policy[category]]
    return rules


def classify(policy, server_id, user, command):
    """Return a decision, not a claim about trusted approval or server state."""
    report = {"decision": "ask", "reason": "invalid-policy", "pattern": None, "policy_version": None}
    try:
        rules = validate(policy)
    except ValueError:
        return report
    report["policy_version"] = policy["version"]
    if {"server_id": server_id, "user": user} not in policy["targets"]:
        return dict(report, reason="target-not-covered")
    try:
        argv = tokens(command)
    except ValueError:
        return dict(report, reason="unsupported-shell")
    for category in ("deny", "ask"):
        for pattern, parsed in rules[category]:
            if matches(parsed, argv):
                return dict(report, decision=category, reason=category + "-pattern", pattern=pattern)
    # Static argv matching cannot resolve shell pathname expansion safely.
    if has_shell_expansion(command):
        return dict(report, reason="shell-expansion")
    executable = Path(argv[0]).name
    if (
        executable in WRAPPERS or "=" in argv[0]
        or re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
        or executable.endswith((".sh", ".py", ".pl", ".rb", ".js"))
    ):
        return dict(report, reason="wrapped-command")
    for pattern, parsed in rules["allow"]:
        if matches(parsed, argv):
            reason = "allow-pattern" if policy["approval_ref"] else "unapproved-policy"
            return dict(report, decision="allow" if policy["approval_ref"] else "ask", reason=reason, pattern=pattern)
    return dict(report, reason="unmatched")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        policy = None
    report = classify(policy, args.server_id, args.user, args.command)
    print(json.dumps(report, ensure_ascii=False))
    return EXIT_CODES[report["decision"]]


if __name__ == "__main__":
    raise SystemExit(main())
