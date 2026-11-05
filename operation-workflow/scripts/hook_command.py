#!/usr/bin/env python3
"""Adapt native pre-tool events to the one command policy; never run commands.

Human confirmation belongs to the host. Unsupported native ask is handed back
to the AI's native question tool; Codex receipts are checked read-only on retry.
There is no approval window, plan manifest, grant database or approval issuer.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import stat
import subprocess
import sys
import time

import check_command as gate


HOSTS = {"codex": False, "claude": True, "kimi": False}
ORDINARY_ASK = {"ask-pattern", "unmatched", "scenario-default", "scenario-exception", "scenario-not-covered"}
MAX_INPUT = 2_000_000
CONFIRM = "执行本次命令"
DEFAULT_OPERATIONS_ROOT = "agent-works/operations"
# Supported SSH grammar, not a duplicate command permission table.
SSH_OPTIONS = {
    "batchmode": {"yes"}, "identitiesonly": {"yes"}, "identityagent": {"none"},
    "stricthostkeychecking": {"yes"}, "hostkeyalgorithms": {"ssh-ed25519"},
    "globalknownhostsfile": {"/dev/null"}, "updatehostkeys": {"no"},
    "forwardagent": {"no"}, "clearallforwardings": {"yes"},
    "controlmaster": {"no"}, "controlpath": {"none"},
}


def result(decision, reason):
    return {"decision": decision, "reason": reason}


def read_document(path, root):
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.stat().st_size > MAX_INPUT:
        raise ValueError("invalid context path")
    return resolved.read_text(encoding="utf-8")


def belongs_to_project(path, project_root):
    """Use the same canonical project boundary for tool and native-session cwd."""
    candidate = Path(path)
    return candidate.is_absolute() and candidate.resolve().is_relative_to(Path(project_root).resolve())


def operations_path(project_root, value):
    """Bind a configured operations directory inside the initialized project."""
    relative = Path(value)
    root = Path(project_root).resolve()
    target = (root/relative).resolve()
    if (relative.is_absolute() or not relative.parts or ".." in relative.parts
            or not target.is_relative_to(root) or (target.exists() and not target.is_dir())):
        raise ValueError("invalid operations root")
    return relative.as_posix()


def native_items(thread_id, project_root):
    """Read native Codex receipts, without starting/resuming a model turn.

    Only native user messages and structured questions are authorization sources.
    No local plan, tool argument, pending file or approval label is trusted.
    """
    process = subprocess.Popen(["codex", "--no-daemon", "app-server", "--listen", "stdio://"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    deadline, buffered, sequence = time.monotonic()+6, b"", 0

    def rpc(method, params):
        nonlocal buffered, sequence
        sequence += 1
        process.stdin.write((json.dumps({"id": sequence, "method": method, "params": params})+"\n").encode())
        process.stdin.flush()
        while time.monotonic() < deadline:
            if b"\n" not in buffered:
                ready, _, _ = select.select([process.stdout], [], [], max(0, deadline-time.monotonic()))
                if not ready:
                    break
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                buffered += chunk
                if len(buffered) > 8_000_000:
                    raise ValueError("oversized native response")
                continue
            line, buffered = buffered.split(b"\n", 1)
            response = json.loads(line)
            if response.get("id") == sequence:
                if "error" in response:
                    raise ValueError("native history unavailable")
                return response["result"]
        raise ValueError("native history timeout")

    try:
        rpc("initialize", {"clientInfo": {"name": "operation-workflow", "version": "1"},
                           "capabilities": {"experimentalApi": True}})
        process.stdin.write(b'{"method":"initialized"}\n')
        process.stdin.flush()
        thread = rpc("thread/read", {"threadId": thread_id})["thread"]
        if thread["id"] != thread_id or not belongs_to_project(thread["cwd"], project_root):
            raise ValueError("native thread target mismatch")
        # The current answer and its question must be in this bounded recent
        # window. Older unrelated approvals must never authorize a new command.
        return rpc("thread/items/list", {"threadId": thread_id, "limit": 200,
                                          "sortDirection": "desc"})["data"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()


def confirmation_title(command, report):
    """Runtime question binding; this is never a precomputed plan manifest."""
    return ("是否执行本次命令？\n目标："+report["server_id"]+" / "+report["user"]+
            "\n策略版本："+str(report["policy_version"])+"\n```sh\n"+command+"\n```")


def conversation_question(title):
    """Exact fallback only when the host question tool is unavailable."""
    return title+"\n\n请回复“执行本次命令”或“取消”。"


def confirmed_command(rows, payload, title):
    """Return a bound native receipt id, False for a decline, or None otherwise."""
    for index, row in enumerate(rows):
        item = row.get("item", {})
        if item.get("type") != "userMessage":
            continue
        if row.get("turnId") != payload.get("turn_id") or not item.get("clientId"):
            return None
        contents = item.get("content", [])
        if len(contents) != 1 or contents[0].get("type") != "text":
            return None
        text = contents[0].get("text", "")
        plain_answer = text.strip() in {CONFIRM, "取消"}
        accepted = text.strip() == CONFIRM
        match = re.fullmatch(r"\s*<send_user_message_question_reply>\s*(.*?)\s*</send_user_message_question_reply>\s*",
                             text, re.DOTALL)
        if not match and not plain_answer:
            return None
        question_id = None
        if match:
            answers = json.loads(match[1])
            if not isinstance(answers, list) or len(answers) != 1:
                return None
            answer = answers[0]
            if answer.get("question") != title:
                return None
            accepted = answer.get("answer") == CONFIRM
            question_id = json.loads(answer["questionItemId"])
            if (not isinstance(question_id, list) or len(question_id) != 3
                    or question_id[0] != "request_user_input_async" or question_id[2] != 0):
                return None
        # A typed quote or fabricated question reply is insufficient: it must
        # point to a real native structured question stored before the answer.
        for earlier in rows[index+1:]:
            question = earlier.get("item", {})
            if question.get("type") == "userMessage":
                break
            if (plain_answer and question.get("type") == "agentMessage"
                    and question.get("phase") == "final_answer"
                    and question.get("text") == conversation_question(title)):
                return item["id"] if accepted else False
            if (question_id and question.get("type") == "agentMessage" and question.get("id") == question_id[1]
                    and question.get("questions") == [{"title": title, "options": [CONFIRM, "取消"]}]):
                return item["id"] if accepted else False
        return None
    return None


def consume_confirmation(project_root, thread_id, receipt):
    """Append consumed receipt ids under one lock; never overwrite older ids.

    Keeping A after B prevents a worker holding an older A snapshot from using
    it again. Legacy single-id markers are read as a one-entry log. This bounded
    local log cannot create approval and is never automatically rotated/reset.
    """
    if (not isinstance(receipt, str) or not receipt or receipt.splitlines() != [receipt]
            or len(receipt.encode("utf-8")) > 256):
        raise ValueError("invalid receipt id")
    folder = Path(project_root)/".local/operation-hook-used"
    if not folder.resolve().is_relative_to(Path(project_root).resolve()):
        raise ValueError("consumption path escapes project")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = hashlib.sha256(thread_id.encode()).hexdigest()
    path = folder/name
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, "r+") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("invalid consumption marker")
        fcntl.flock(stream, fcntl.LOCK_EX)
        size = os.fstat(stream.fileno()).st_size
        if size > MAX_INPUT:
            raise ValueError("consumption log full")
        used = stream.read(MAX_INPUT+1)
        if receipt in used.splitlines():
            return False
        # Preserve a pre-upgrade marker without a terminating newline. Append
        # only after the locked read, including the size check, has completed.
        entry = ("\n" if used and not used.endswith("\n") else "")+receipt+"\n"
        if size+len(entry.encode("utf-8")) > MAX_INPUT:
            raise ValueError("consumption log full")
        stream.seek(0, os.SEEK_END)
        stream.write(entry)
        stream.flush()
        os.fsync(stream.fileno())
        return True


def ssh_target(argv):
    """Accept the explicit noninteractive transport documented by the skill.

    No SSH config, proxy, multiplexing, shell program or forwarding can hide a
    different endpoint. Unsupported forms stop instead of guessing their target.
    """
    i, options, port, login, config = 1, {}, 22, None, None
    seen = set()
    while i < len(argv) and argv[i].startswith("-"):
        flag = argv[i]
        if flag == "--":
            i += 1
            break
        if flag in {"-T", "-n"}:
            i += 1
            continue
        if flag not in {"-F", "-i", "-p", "-l", "-o"} or i + 1 >= len(argv):
            raise ValueError("unsupported SSH option")
        value = argv[i + 1]
        i += 2
        if flag != "-o":
            if flag in seen:
                raise ValueError("duplicate SSH option")
            seen.add(flag)
        if flag == "-F":
            config = value
        elif flag == "-p":
            if not value.isdecimal() or not 0 < int(value) < 65536:
                raise ValueError("invalid SSH port")
            port = int(value)
        elif flag == "-l":
            login = value
        elif flag == "-o":
            pair = value.split("=", 1) if "=" in value else value.split(None, 1)
            if len(pair) != 2:
                raise ValueError("invalid SSH option")
            key, val = pair[0].lower(), pair[1]
            if key in options:
                raise ValueError("duplicate SSH option")
            if key == "userknownhostsfile":
                if Path(val).expanduser().resolve() != (Path.home()/".ssh/known_hosts").resolve():
                    raise ValueError("unsupported known-hosts source")
            elif key == "connecttimeout":
                if not val.isdecimal() or not 0 < int(val) <= 60:
                    raise ValueError("invalid connection timeout")
            elif key not in SSH_OPTIONS or val not in SSH_OPTIONS[key]:
                raise ValueError("unsupported SSH option")
            options[key] = val
    if config != "/dev/null" or options.get("stricthostkeychecking") != "yes":
        raise ValueError("explicit strict SSH required")
    if options.get("controlmaster") != "no" or options.get("controlpath") != "none":
        raise ValueError("connection reuse unsupported")
    if len(argv[i:]) != 2:
        raise ValueError("one noninteractive remote command required")
    destination, command = argv[i:]
    if "@" in destination:
        user, address = destination.rsplit("@", 1)
        if login is not None and login != user:
            raise ValueError("conflicting SSH user")
    else:
        user, address = login, destination
    if not user or not address or address.startswith("-") or not command.strip():
        raise ValueError("explicit SSH destination required")
    return address, port, user, command


def evaluate(payload, project_root, operations_root=DEFAULT_OPERATIONS_ROOT, host=None, history_reader=None):
    """Classify one concrete command and check a current native user receipt.

    This adapter never creates approval requests, stores grants or runs the
    candidate command. Unsupported remote transports stop rather than guessing.
    """
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "PreToolUse":
        return result("stop", "unsupported-event")
    root = Path(project_root).resolve(strict=True)
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return result("stop", "invalid-cwd")
    if not belongs_to_project(cwd, root):
        return result("pass", "outside-project")
    if payload.get("tool_name") not in {"Bash", "Shell", "exec_command"}:
        return result("stop", "unsupported-tool")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return result("stop", "invalid-tool-input")
    command = tool_input.get("command", tool_input.get("cmd"))
    if "command" in tool_input and "cmd" in tool_input and tool_input["command"] != tool_input["cmd"]:
        return result("stop", "conflicting-command-fields")
    try:
        argv = gate.tokens(command)
        if gate.has_shell_expansion(command):
            raise ValueError("shell expansion")
    except ValueError:
        return result("stop", "unsupported-shell")
    executable = Path(argv[0]).name
    if executable != "ssh":
        if (executable in gate.WRAPPERS or executable == "docker" or "=" in argv[0]
                or re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
                or executable.endswith((".sh", ".py", ".pl", ".rb", ".js"))):
            return result("stop", "unbound-or-wrapped-command")
        return result("pass", "local-host-permissions")
    try:
        address, port, user, remote_command = ssh_target(argv)
    except ValueError:
        return result("stop", "unsupported-ssh-transport")
    try:
        ops = root / operations_path(root, operations_root)
        policy_text = read_document(ops/"command-policy.json", root)
        policy = json.loads(policy_text)
        gate.validate(policy)
    except (OSError, ValueError, TypeError, RecursionError):
        return result("stop", "invalid-policy")
    try:
        import yaml
        inventory_text = read_document(ops/"servers.yaml", root)
        inventory = yaml.safe_load(inventory_text)
        rows = inventory["servers"]
        if not isinstance(rows, list):
            raise ValueError("invalid inventory")
        matches = [row for row in rows if isinstance(row, dict)
                   and row.get("address") == address and row.get("port") == port
                   and row.get("username") == user and row.get("connection_method") == "ssh"]
        if len(matches) != 1 or not isinstance(matches[0].get("server_id"), str):
            raise ValueError("ambiguous target")
    except Exception:
        return result("stop", "invalid-or-uncovered-target")
    server_id = matches[0]["server_id"]
    report = gate.classify(policy, server_id, user, remote_command)
    if report["decision"] == "ask" and report["reason"] not in ORDINARY_ASK:
        return result("stop", report["reason"])
    if report["decision"] == "ask" and host == "codex":
        title = confirmation_title(command, dict(report, server_id=server_id, user=user))
        report["confirmation_question"] = {"title": title, "options": [CONFIRM, "取消"]}
        thread_id = payload.get("session_id")
        if (isinstance(thread_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", thread_id)
                and isinstance(payload.get("turn_id"), str)):
            try:
                rows = (history_reader or native_items)(thread_id, root)
                receipt = confirmed_command(rows, payload, title)
                if receipt is False:
                    return result("stop", "command-confirmation-declined")
                if receipt:
                    try:
                        consumed = consume_confirmation(root, thread_id, receipt)
                    except (OSError, ValueError):
                        return dict(report, confirmation_error="confirmation-consumption-unavailable")
                    if consumed:
                        return dict(report, decision="allow", reason="human-command-confirmation")
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                report["confirmation_error"] = "native-history-unavailable"
        else:
            report["confirmation_error"] = "native-session-context-required"
    return report


def host_response(report, host):
    """Translate decisions, never forward classifier exit codes to a host."""
    decision, reason = report["decision"], report["reason"]
    if decision in {"allow", "pass"}:
        return "", "", 0  # Preserve the host's own permission checks.
    message = "operation-workflow: " + reason
    if decision == "ask" and HOSTS[host]:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                  "permissionDecision": "ask", "permissionDecisionReason": message}}
        return json.dumps(output, ensure_ascii=False), "", 0
    if decision == "ask":
        if report.get("confirmation_error"):
            message += "; "+report["confirmation_error"]+"; stop and restore confirmation context/storage; do not repeatedly ask the user"
        elif "confirmation_question" in report:
            message += ("; ask the user with request_user_input_async using exactly this single question, "
                        "wait for their answer, then retry the unchanged command once. This is task "
                        "authorization; keep all host execution permission checks unchanged. If the "
                        "question tool is unavailable or disallowed, explain why and ask the same title "
                        "in your final message followed by: 请回复“执行本次命令”或“取消”。\n"+
                        json.dumps(report["confirmation_question"], ensure_ascii=False))
        else:
            message += "; command confirmation required; no verified host receipt adapter is available"
    return "", message, 2  # Exit 3 would fail open on some hosts.


def registration(host, project_root, operations_root=DEFAULT_OPERATIONS_ROOT):
    """Render the command hook only; never change or bypass host permissions."""
    operations_root = operations_path(project_root, operations_root)
    arguments = [sys.executable, str(Path(__file__).resolve()), "--host", host,
                 "--project-root", str(Path(project_root).resolve())]
    # Keep existing default registrations identical, including their host trust
    # identity. Only a genuinely custom layout needs the extra argument.
    if operations_root != DEFAULT_OPERATIONS_ROOT:
        arguments += ["--operations-root", operations_root]
    command = shlex.join(arguments)
    if host == "kimi":
        return '\n'.join(['[[hooks]]', 'event = "PreToolUse"', 'matcher = "^(Bash|Shell)$"',
                          'command = '+json.dumps(command), 'timeout = 10'])
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "^Bash$", "hooks": [
        {"type": "command", "command": command, "timeout": 10}]}]}}, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=HOSTS, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--operations-root", default=DEFAULT_OPERATIONS_ROOT)
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()
    try:
        if args.print_config:
            print(registration(args.host, args.project_root, args.operations_root))
            return 0
        raw = sys.stdin.read(MAX_INPUT+1)
        if len(raw) > MAX_INPUT:
            raise ValueError("oversized input")
        report = evaluate(json.loads(raw), args.project_root, args.operations_root, host=args.host)
    except Exception:
        report = result("stop", "invalid-hook-context")
    output, error, code = host_response(report, args.host)
    if output:
        print(output)
    if error:
        print(error, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
