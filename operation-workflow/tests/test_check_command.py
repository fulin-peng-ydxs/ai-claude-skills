"""Exercise real policy decisions without a server or command execution."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("command_gate", ROOT / "scripts/check_command.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "assets/command-policy.json").read_text())
        self.policy["targets"] = [{"server_id": "test-01", "user": "ops"}]
        self.policy["approval_ref"] = "fixture:approved-v1"

    def decision(self, command, **kwargs):
        return GATE.classify(self.policy, kwargs.get("server_id", "test-01"), kwargs.get("user", "ops"), command)

    def test_default_candidates_and_changes(self):
        for command, expected in [
            ("id", "allow"), ("systemctl is-active nginx.service", "allow"),
            ("docker --host unix:///var/run/docker.sock service ls", "allow"),
            ("systemctl restart nginx.service", "ask"), ("mkfs.ext4 /dev/example", "deny"),
            ("dd if=/dev/example of=/dev/example2", "deny"), ("rm -rf /", "deny"),
            ("docker inspect example", "ask"),
        ]:
            with self.subTest(command=command):
                self.assertEqual(expected, self.decision(command)["decision"])

    def test_single_argument_glob_does_not_swallow_options(self):
        self.assertEqual("ask", self.decision("systemctl is-active nginx.service --unexpected")["decision"])
        self.policy["allow"] = ["probe svc-?.[ab] --format '*'"]
        self.assertEqual("allow", self.decision("probe svc-1.a --format 'value with spaces'")["decision"])
        self.assertEqual("ask", self.decision("probe svc-11.a --format value")["decision"])

    def test_double_star_spans_zero_or_more_arguments(self):
        self.policy["allow"] = ["probe ** --ready"]
        for command in ["probe --ready", "probe a b --ready"]:
            self.assertEqual("allow", self.decision(command)["decision"])
        self.assertEqual("ask", self.decision("probe a --ready extra")["decision"])

    def test_deny_and_ask_override_allow(self):
        self.policy["allow"] = ["**"]
        self.assertEqual("deny", self.decision("rm -rf /")["decision"])
        self.assertEqual("ask", self.decision("systemctl restart nginx.service")["decision"])

    def test_target_and_identity_are_exact(self):
        for kwargs in [{"server_id": "other"}, {"user": "root"}]:
            self.assertEqual("ask", self.decision("id", **kwargs)["decision"])

    def test_draft_never_enables_allow(self):
        self.policy["approval_ref"] = None
        self.assertEqual("unapproved-policy", self.decision("id")["reason"])
        self.assertEqual("deny", self.decision("rm -rf /")["decision"])

    def test_shell_composition_cannot_use_broad_allow(self):
        self.policy["allow"] = ["**"]
        for command in [
            "id; rm -rf /", "id && reboot", "id | sh", "id > /tmp/example",
            "id 2>&1", "id\nhostname", "echo $(id)", "echo `id`", "echo $HOME",
            "cat <(id)", "id &", "(id)", "id\0", "echo 'unterminated",
        ]:
            with self.subTest(command=command):
                self.assertEqual("ask", self.decision(command)["decision"])

    def test_wrappers_and_scripts_require_review(self):
        self.policy["allow"] = ["**"]
        for command in [
            "ssh host id", "sudo id", "/bin/bash -c id", "python3.12 -c pass",
            "env id", "PATH=/tmp id", "timeout 5 id", "./task.sh", "find /tmp -delete",
        ]:
            with self.subTest(command=command):
                self.assertEqual("ask", self.decision(command)["decision"])

    def test_shell_globs_do_not_change_approved_argument_count(self):
        self.policy["allow"] = ["**"]
        for command in [
            "systemctl is-active *.service", "probe file?.conf", "probe [ab]",
            "probe ~/config", "probe {a,b}", "rm -rf / # comment",
        ]:
            with self.subTest(command=command):
                self.assertEqual("shell-expansion", self.decision(command)["reason"])

    def test_quoted_formats_are_literal_arguments(self):
        self.policy["allow"] = ["probe --format *"]
        for command in ["probe --format '{{json .State}}'", "probe --format '*'", r"probe --format \*"]:
            self.assertEqual("allow", self.decision(command)["decision"])

    def test_deny_still_applies_to_a_wrapper(self):
        self.policy["deny"].append("bash **")
        self.assertEqual("deny", self.decision("bash -c id")["decision"])

    def test_invalid_policies_do_not_allow(self):
        for field, value in [
            ("version", True), ("version", 0), ("targets", ["test-01"]),
            ("default", "allow"), ("allow", "id"), ("deny", [None]),
            ("ask", ["id; reboot"]), ("approval_ref", ""),
        ]:
            policy = deepcopy(self.policy)
            policy[field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual("invalid-policy", GATE.classify(policy, "test-01", "ops", "id")["reason"])
        policy = dict(self.policy, alow=["**"])
        self.assertEqual("ask", GATE.classify(policy, "test-01", "ops", "id")["decision"])

    def test_cli_exit_codes_and_no_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            marker = Path(directory) / "must-not-exist"
            path.write_text(json.dumps(self.policy))
            for command, expected in [("id", 0), ("unknown", 2), ("rm -rf /", 3), (f"touch {marker}", 2)]:
                result = subprocess.run([
                    sys.executable, str(ROOT / "scripts/check_command.py"), "--policy", str(path),
                    "--server-id", "test-01", "--user", "ops", "--command", command,
                ], capture_output=True, text=True)
                self.assertEqual(expected, result.returncode, result.stderr)
                self.assertIn("decision", json.loads(result.stdout))
            self.assertFalse(marker.exists())
            path.write_text("not JSON")
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/check_command.py"), "--policy", str(path),
                "--server-id", "test-01", "--user", "ops", "--command", "id",
            ], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)


if __name__ == "__main__":
    unittest.main()
