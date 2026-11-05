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
SCENARIO_FIELDS = {"version", "targets", "approval_ref", "deny", "scenarios"}
OPERATORS = set(";&|<>()")
WRAPPERS = {
    "ssh", "scp", "sftp", "sudo", "doas", "su", "env", "sh", "bash", "dash",
    "zsh", "fish", "busybox", "perl", "ruby", "node", "awk", "gawk", "mawk",
    "sed", "xargs", "find", "timeout", "nice", "nohup", "watch", "eval", "exec",
    "command", "builtin", "source", ".",
}
DOCKER_BOOLEAN_FLAGS = {"--debug", "--tls", "--tlsverify", "--help", "--version"}
DOCKER_VALUE_FLAGS = {
    "--config", "--context", "--host", "--log-level", "--tlscacert", "--tlscert", "--tlskey",
}
DOCKER_SHORT_FLAGS = {
    "D": "--debug", "c": "--context", "H": "--host", "l": "--log-level",
    "h": "--help", "v": "--version",
}
DOCKER_GROUPS = {
    "builder", "buildx", "checkpoint", "compose", "config", "container", "context",
    "desktop", "image", "manifest", "network", "node", "plugin", "secret", "service",
    "stack", "swarm", "system", "trust", "volume",
}


def docker_arguments(argv, *, pattern=False):
    """Locate Docker verbs without moving or interpreting command operands.

    Only global flags before the root verb or a management verb are parsed.
    Cosmetic flags are omitted from matching; endpoint/security flags stay
    visible to policy rules. Never scan exec payloads or inspect object names.
    """
    if not argv or Path(argv[0]).name != "docker":
        return argv

    def globals_at(index):
        kept = []
        while index < len(argv) and argv[index].startswith("-"):
            argument = argv[index]
            index += 1
            if argument.startswith("--"):
                option, separator, value = argument.partition("=")
                parts = [(option, value if separator else None)]
            else:
                parts, short = [], argument[1:]
                if not short:
                    raise ValueError("invalid Docker global option")
                while short:
                    option = DOCKER_SHORT_FLAGS.get(short[0])
                    if option is None:
                        raise ValueError("unknown Docker global option")
                    short = short[1:]
                    if option in DOCKER_VALUE_FLAGS or short.startswith("="):
                        parts.append((option, short.removeprefix("=") if short else None))
                        break
                    parts.append((option, None))
            for option, value in parts:
                if option in DOCKER_VALUE_FLAGS:
                    if value is None:
                        if index == len(argv) or argv[index].startswith("-"):
                            raise ValueError("missing Docker global option value")
                        value = argv[index]
                        index += 1
                    if not value:
                        raise ValueError("empty Docker global option value")
                    if option == "--log-level":
                        if not pattern and value not in {"debug", "info", "warn", "error", "fatal"}:
                            raise ValueError("invalid Docker log level")
                    else:
                        kept.extend([option, value])
                elif option in DOCKER_BOOLEAN_FLAGS:
                    if not pattern and value is not None and value not in {"1", "0", "t", "T", "f", "F", "true", "True", "TRUE", "false", "False", "FALSE"}:
                        raise ValueError("invalid Docker boolean option")
                    if option not in {"--debug", "--help", "--version"}:
                        if value is None or value in {"1", "t", "T", "true", "True", "TRUE"}:
                            value = "true"
                        elif value in {"0", "f", "F", "false", "False", "FALSE"}:
                            value = "false"
                        kept.append(option + "=" + value)
                else:
                    raise ValueError("unknown Docker global option")
        return index, kept

    index, kept = globals_at(1)
    normalized = [argv[0]] + kept
    if index < len(argv):
        command = argv[index]
        if pattern and any(c in command for c in "*?["):
            if command != "**" or index != len(argv) - 1:
                raise ValueError("ambiguous Docker deny command path")
        normalized.append(command)
        index += 1
        if command in DOCKER_GROUPS:
            index, kept = globals_at(index)
            normalized.extend(kept)
            if pattern and index < len(argv) and any(c in argv[index] for c in "*?["):
                if argv[index] != "**" or index != len(argv) - 1:
                    raise ValueError("ambiguous Docker deny management command")
    return normalized + argv[index:]


def docker_deny_arguments(argv):
    """Compile the same canonical view for deny patterns, retaining their source.

    Alternatives are expanded before parsing flag arity. Ambiguous prefixes or
    excessive combinations reject the policy instead of weakening its denies.
    """
    if not argv:
        return [argv]
    programs = choices(argv[0])
    if any(fnmatchcase("docker", Path(program).name) and Path(program).name != "docker" for program in programs):
        if argv not in (["**"], ["*", "**"]):
            raise ValueError("Docker deny requires an unambiguous executable")
    if not any(Path(program).name == "docker" for program in programs):
        return [argv]
    variants = [[]]
    for part in argv:
        options = choices(part)
        if len(variants) * len(options) > 256:
            raise ValueError("too many Docker deny alternatives")
        variants = [prefix + [option] for prefix in variants for option in options]
    return [docker_arguments(variant, pattern=True) for variant in variants]


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


def choices(part):
    """New-format alternatives occupy one complete argv slot, never shell code."""
    if part.startswith("{") and not part.startswith("{{") and "," in part:
        if not part.endswith("}") or any(c in part[1:-1] for c in "{}"):
            raise ValueError("invalid alternatives")
        result = part[1:-1].split(",")
        if any(not item or item == "**" for item in result):
            raise ValueError("invalid alternatives")
        return result
    return [part]


def matches(pattern, argv, alternatives=False):
    """A glob stays inside one argument; a standalone ** spans arguments."""
    row = [True] + [False] * len(argv)
    for part in pattern:
        if part == "**":
            current = [row[0]]
            for index in range(1, len(row)):
                current.append(row[index] or current[index - 1])
        else:
            options = choices(part) if alternatives else [part]
            current = [False] + [
                row[index - 1] and any(fnmatchcase(argument, option) for option in options)
                for index, argument in enumerate(argv, 1)
            ]
        row = current
    return row[-1]


def restriction_matches(pattern, argv, alternatives=False):
    """Pathless restrictions cover that executable name at any path.

    Only argv[0] is adapted, and only for deny/ask rules. An explicitly pathed
    rule keeps its path constraint; allow rules never inherit basename trust.
    """
    if matches(pattern, argv, alternatives):
        return True
    if not argv or not pattern or "/" not in argv[0]:
        return False
    options = choices(pattern[0]) if alternatives else [pattern[0]]
    return any(
        "/" not in option and matches([option] + pattern[1:], [Path(argv[0]).name] + argv[1:], alternatives)
        for option in options
    )


def docker_wraps_command(argv):
    """Inspect the canonical verb position, never object names or exec payloads."""
    if Path(argv[0]).name != "docker":
        return False
    def verb_at(index):
        while index < len(argv) and argv[index].startswith("-"):
            option = argv[index].split("=", 1)[0]
            index += 2 if option in DOCKER_VALUE_FLAGS else 1
        return index

    index = verb_at(1)
    if index < len(argv) and argv[index] == "container":
        index = verb_at(index + 1)
    return index < len(argv) and argv[index] in {"exec", "run"}


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
    if not isinstance(policy, dict) or set(policy) not in (FIELDS, SCENARIO_FIELDS):
        raise ValueError("invalid policy fields")
    if type(policy["version"]) is not int or policy["version"] < 1:
        raise ValueError("invalid version")
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
    def parse_rules(value, alternatives=False):
        if not isinstance(value, list):
            raise ValueError("rules must be lists")
        parsed = [(pattern, tokens(pattern)) for pattern in value]
        if alternatives:
            for _, parts in parsed:
                for part in parts:
                    choices(part)
        return parsed

    if "scenarios" in policy:
        rules = {"deny": parse_rules(policy["deny"], True), "scenarios": []}
        rules["normalized_deny"] = [
            (pattern, normalized)
            for pattern, parsed in rules["deny"]
            for normalized in docker_deny_arguments(parsed)
        ]
        if not isinstance(policy["scenarios"], list) or not policy["scenarios"]:
            raise ValueError("invalid scenarios")
        names, prefixes = set(), set()
        for scenario in policy["scenarios"]:
            if not isinstance(scenario, dict) or scenario.get("default") not in ("ask", "allow"):
                raise ValueError("invalid scenario mode")
            exception = "ask" if scenario["default"] == "allow" else "allow"
            if set(scenario) != {"name", "prefix", "default", exception}:
                raise ValueError("a scenario has exactly one exception list")
            name, prefix = scenario["name"], scenario["prefix"]
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError("invalid scenario name")
            if not isinstance(prefix, str):
                raise ValueError("invalid scenario prefix")
            argv = tokens(prefix) if prefix else []
            if any(any(c in part for c in "*?[]{}") for part in argv) or tuple(argv) in prefixes:
                raise ValueError("scenario prefixes must be unique literal argv")
            argv = docker_arguments(argv)
            if tuple(argv) in prefixes:
                raise ValueError("scenario prefixes must be unique after normalization")
            names.add(name)
            prefixes.add(tuple(argv))
            rules["scenarios"].append({
                "name": name, "prefix": argv, "default": scenario["default"],
                "exception": exception, "rules": parse_rules(scenario[exception], True),
            })
        return rules

    # Existing project policies keep their original default-ask semantics.
    if policy["default"] != "ask":
        raise ValueError("legacy default must be ask")
    rules = {}
    for category in ("deny", "ask", "allow"):
        rules[category] = parse_rules(policy[category])
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
    scoped = "scenarios" in rules
    for pattern, parsed in rules["deny"]:
        if restriction_matches(parsed, argv, alternatives=scoped):
            return dict(report, decision="deny", reason="deny-pattern", pattern=pattern)
    # Static argv matching cannot resolve shell pathname expansion safely.
    if has_shell_expansion(command):
        return dict(report, reason="shell-expansion")
    try:
        normalized = docker_arguments(argv)
    except ValueError:
        return dict(report, reason="unsupported-docker-options")
    if scoped:
        for pattern, parsed in rules["normalized_deny"]:
            if restriction_matches(parsed, normalized, alternatives=True):
                return dict(report, decision="deny", reason="deny-pattern", pattern=pattern)
    executable = Path(argv[0]).name
    if (
        executable in WRAPPERS or "=" in argv[0]
        or re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
        or executable.endswith((".sh", ".py", ".pl", ".rb", ".js"))
        or docker_wraps_command(normalized)
    ):
        return dict(report, reason="wrapped-command")
    if scoped:
        argv = normalized
        candidates = [scenario for scenario in rules["scenarios"]
                      if argv[:len(scenario["prefix"])] == scenario["prefix"]]
        if not candidates:
            return dict(report, reason="scenario-not-covered")
        scenario = max(candidates, key=lambda item: len(item["prefix"]))
        report.update(scenario=scenario["name"], mode=scenario["default"])
        suffix = argv[len(scenario["prefix"]):]
        decision, reason, pattern = scenario["default"], "scenario-default", None
        for candidate, parsed in scenario["rules"]:
            match = restriction_matches if scenario["exception"] == "ask" and not scenario["prefix"] else matches
            if match(parsed, suffix, alternatives=True):
                decision, reason, pattern = scenario["exception"], "scenario-exception", candidate
                break
        if decision == "allow" and not policy["approval_ref"]:
            return dict(report, reason="unapproved-policy", pattern=pattern)
        return dict(report, decision=decision, reason=reason, pattern=pattern)
    for pattern, parsed in rules["ask"]:
        if restriction_matches(parsed, argv):
            return dict(report, reason="ask-pattern", pattern=pattern)
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
