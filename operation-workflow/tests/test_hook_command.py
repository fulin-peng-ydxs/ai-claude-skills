"""Native hook protocol/transport regressions; no remote commands execute."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import hook_command as hook


class HookTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT.parent/".local/tmp/ai-agent/hook-verification"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="hook-fixture-", dir=temporary_root)
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.ops = self.project / "agent-works/operations"
        self.ops.mkdir(parents=True)
        self.policy = json.loads((ROOT/"assets/command-policy.json").read_text())
        self.policy["targets"] = [{"server_id": "fixture", "user": "operator"}]
        self.policy["approval_ref"] = "fixture:adopted"
        self.servers = {"servers": [{"server_id": "fixture", "address": "192.0.2.10",
                         "port": 22, "username": "operator", "connection_method": "ssh"}]}
        self.save()
        self.prefix = ["ssh", "-F", "/dev/null", "-o", "StrictHostKeyChecking=yes",
                       "-o", "ControlMaster=no", "-o", "ControlPath=none", "operator@192.0.2.10"]
        self.docker = "docker --host unix:///var/run/docker.sock "


    def save(self):
        (self.ops/"command-policy.json").write_text(json.dumps(self.policy))
        (self.ops/"servers.yaml").write_text(json.dumps(self.servers))


    def event(self, remote="id", prefix=None):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.project),
                "tool_input": {"command": shlex.join((prefix or self.prefix)+[remote])}}


    def test_classification_reuses_the_shared_policy(self):
        for remote, decision in [("id", "allow"), (self.docker+"service ls", "allow"),
                                 (self.docker+'service inspect redis --format "{{json .Endpoint.Spec.Ports}}"', "allow"),
                                 (self.docker+"container inspect redis --format '{{json .Mounts}}'", "allow"),
                                 (self.docker+"container inspect redis --format '{{json .Config.Env}}'", "ask"),
                                 (self.docker+"service update --force redis", "ask"),
                                 ("rm -rf /", "deny")]:
            with self.subTest(command=remote):
                self.assertEqual(decision, hook.evaluate(self.event(remote), self.project)["decision"])


    def test_no_product_adapter_forwards_deny_exit_three(self):
        for host in hook.HOSTS:
            with self.subTest(host=host):
                self.assertEqual(("", "", 0), hook.host_response(hook.result("allow", "fixture"), host))
                out, err, code = hook.host_response(hook.result("deny", "deny-pattern"), host)
                self.assertEqual(2, code)
                self.assertEqual("", out)
                self.assertIn("deny-pattern", err)


    def test_native_ask_is_a_capability_not_an_approval(self):
        for host in hook.HOSTS:
            with self.subTest(host=host):
                output, error, code = hook.host_response(hook.result("ask", "scenario-exception"), host)
                if host == "claude":
                    self.assertEqual("ask", json.loads(output)["hookSpecificOutput"]["permissionDecision"])
                    self.assertEqual(("", 0), (error, code))
                else:
                    self.assertEqual(("", 2), (output, code))
                    self.assertIn("command confirmation required", error)


    def test_tool_input_cannot_forge_approval(self):
        event = self.event(self.docker+"service update --force redis")
        event["approved"] = True
        event["approval_ref"] = "record.md#approved"
        event["tool_input"]["approved"] = True
        self.assertEqual("ask", hook.evaluate(event, self.project)["decision"])


    def test_global_option_alias_deny_cannot_be_bypassed(self):
        self.policy["deny"] = ["docker -Hunix:///var/run/docker.sock service inspect **"]
        self.save()
        report = hook.evaluate(self.event(self.docker+"--debug service inspect redis"), self.project)
        self.assertEqual("deny", report["decision"])

    def test_executable_paths_and_wrappers_cannot_enter_ordinary_confirmation(self):
        for command in ["/bin/rm -rf /", "./rm -rf /"]:
            self.assertEqual("deny", hook.evaluate(self.event(command), self.project)["decision"])
        self.policy["scenarios"] = [{"name": "all", "prefix": "", "default": "allow", "ask": []}]
        self.save()
        for command in ["builtin eval id", self.docker+"exec example sh -c id",
                        self.docker+"container --debug exec example /bin/rm -rf /"]:
            report = hook.evaluate(self.event(command), self.project)
            self.assertEqual("stop", report["decision"])
            self.assertEqual("wrapped-command", report["reason"])
            self.assertEqual(2, hook.host_response(report, "codex")[2])


    def test_ssh_address_user_and_port_are_bound_to_inventory(self):
        for prefix in [self.prefix[:-1]+["operator@192.0.2.11"], self.prefix[:-1]+["root@192.0.2.10"],
                       self.prefix[:-1]+["-p", "2222", self.prefix[-1]]]:
            with self.subTest(prefix=prefix):
                self.assertEqual("stop", hook.evaluate(self.event(prefix=prefix), self.project)["decision"])
        self.policy["targets"] = []
        self.save()
        self.assertEqual("target-not-covered", hook.evaluate(self.event(), self.project)["reason"])


    def test_transport_cannot_redirect_or_hide_a_different_target(self):
        for extra in [["-o", "ProxyCommand=touch /tmp/hook-must-not-execute"], ["-o", "HostName=elsewhere"],
                      ["-J", "jump"], ["-L", "6380:localhost:6379"], ["-t"], ["-F", "/tmp/config"]]:
            with self.subTest(extra=extra):
                prefix=self.prefix[:-1]+extra+[self.prefix[-1]]
                self.assertEqual("stop", hook.evaluate(self.event(prefix=prefix), self.project)["decision"])
        event=self.event()
        event["tool_input"]["command"]=shlex.join(self.prefix)
        self.assertEqual("stop", hook.evaluate(event,self.project)["decision"])


    def test_shell_wrappers_and_dynamic_payloads_are_not_silently_allowed(self):
        for command in ["ssh host id && echo done", "bash -c 'ssh host id'", "python3 script.py",
                        "docker service ls", "echo $TOKEN", "id\nssh host id"]:
            with self.subTest(command=command):
                event=self.event(); event["tool_input"]["command"]=command
                self.assertEqual("stop",hook.evaluate(event,self.project)["decision"])
        self.assertEqual("stop",hook.evaluate(self.event("bash -s"),self.project)["decision"])


    def test_local_commands_do_not_inherit_remote_permissions(self):
        event=self.event(); event["tool_input"]["command"]="git status --short"
        self.assertEqual({"decision":"pass","reason":"local-host-permissions"},hook.evaluate(event,self.project))
        event["cwd"]=str(self.project.parent)
        self.assertEqual("outside-project",hook.evaluate(event,self.project)["reason"])


    def test_ambiguous_inventory_and_escaping_policy_stop(self):
        self.servers["servers"] *= 2
        self.save()
        self.assertEqual("stop",hook.evaluate(self.event(),self.project)["decision"])
        with tempfile.TemporaryDirectory() as other:
            outside=Path(other)/"command-policy.json"; outside.write_text(json.dumps(self.policy))
            target=self.ops/"command-policy.json"; target.unlink(); target.symlink_to(outside)
            self.assertEqual("invalid-policy",hook.evaluate(self.event(),self.project)["reason"])


    def test_three_registration_formats_are_parseable_and_read_only(self):
        for host in hook.HOSTS:
            config=hook.registration(host,self.project)
            parsed=tomllib.loads(config) if host=="kimi" else json.loads(config)
            self.assertIn("hooks",parsed)
            self.assertIn("--project-root",config)
        self.assertFalse((self.project/".codex").exists())

    def test_custom_operations_root_is_used_by_generated_registrations(self):
        custom = self.project/"custom operations"
        self.ops.rename(custom)
        self.ops.mkdir(parents=True)
        decoy = json.loads(json.dumps(self.policy)); decoy["deny"] = ["id **"]
        (self.ops/"command-policy.json").write_text(json.dumps(decoy))
        (self.ops/"servers.yaml").write_text(json.dumps(self.servers))
        self.assertEqual("deny", hook.evaluate(self.event(), self.project)["decision"])
        for host in hook.HOSTS:
            with self.subTest(host=host):
                generated = self.cli(host, extra=("--operations-root", "custom operations", "--print-config"))
                self.assertEqual(0, generated.returncode, generated.stderr)
                parsed = tomllib.loads(generated.stdout) if host == "kimi" else json.loads(generated.stdout)
                command = (parsed["hooks"][0]["command"] if host == "kimi" else
                           parsed["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
                argv = shlex.split(command)
                self.assertEqual("custom operations", argv[argv.index("--operations-root")+1])
                checked = subprocess.run(argv, input=json.dumps(self.event()), text=True,
                                         capture_output=True, timeout=10)
                self.assertEqual(0, checked.returncode, checked.stderr)
                self.assertNotIn("--operations-root", hook.registration(host, self.project))

    def test_custom_operations_root_cannot_escape_the_project(self):
        for value in ["../other", str(self.project), "nested/../../other", "."]:
            with self.subTest(value=value):
                for host in hook.HOSTS:
                    proc = self.cli(host, extra=("--operations-root", value, "--print-config"))
                    self.assertEqual(2, proc.returncode)
                    self.assertEqual("", proc.stdout)
                self.assertEqual("invalid-policy", hook.evaluate(self.event(), self.project, value)["reason"])
        with tempfile.TemporaryDirectory(dir=self.project.parent) as other:
            (self.project/"escaped-ops").symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                hook.registration("codex", self.project, "escaped-ops")


    def test_cli_handles_malformed_events_and_does_not_execute_commands(self):
        marker=self.project/"must-not-exist"
        for host in hook.HOSTS:
            for event in ["invalid JSON",json.dumps(self.event("touch "+str(marker)))]:
                with self.subTest(host=host,event=event[:30]):
                    proc=subprocess.run([sys.executable,str(ROOT/"scripts/hook_command.py"),"--host",host,
                                         "--project-root",str(self.project)],input=event,text=True,capture_output=True)
                    self.assertIn(proc.returncode,(0,2))
                    self.assertNotIn("Traceback",proc.stderr)
                    self.assertFalse(marker.exists())


    def cli(self, host, payload=None, extra=()):
        """Run the actual registered executable across independent processes."""
        return subprocess.run([sys.executable, str(ROOT/"scripts/hook_command.py"), "--host", host,
                               "--project-root", str(self.project), *extra],
                              input=json.dumps(payload) if payload is not None else "",
                              text=True, capture_output=True, timeout=10)

    def test_invalid_policy_stops_instead_of_becoming_an_approval_request(self):
        (self.ops/"command-policy.json").write_text("broken")
        for host in hook.HOSTS:
            proc = self.cli(host, self.event())
            self.assertEqual(2, proc.returncode)
            self.assertIn("invalid-policy", proc.stderr)
            self.assertEqual("", proc.stdout)

    def test_real_command_field_aliases_cannot_conflict(self):
        event = self.event(self.docker+"service update --force redis")
        event["tool_name"] = "exec_command"
        event["tool_input"]["cmd"] = event["tool_input"].pop("command")
        self.assertEqual("ask", hook.evaluate(event, self.project)["decision"])
        event["tool_input"]["command"] = "id"
        self.assertEqual("conflicting-command-fields", hook.evaluate(event, self.project)["reason"])

    def test_approval_system_entrypoints_have_been_removed(self):
        for option in ["--request-approval", "--prepare-plan", "--show-plan", "--sync-native-approval"]:
            with self.subTest(option=option):
                proc = self.cli("codex", extra=[option, "OP-fixture"])
                self.assertEqual(2, proc.returncode)
                self.assertIn("unrecognized arguments", proc.stderr)
        for name in ["ApprovalStore", "CodexHistory", "desktop_review", "sync_codex_approval"]:
            self.assertFalse(hasattr(hook, name))
        self.assertFalse((self.project/".local/operation-hook.sqlite3").exists())

    def test_legacy_approval_labels_and_databases_do_not_grant_permission(self):
        local = self.project/".local"; local.mkdir(exist_ok=True)
        (local/"operation-hook.sqlite3").write_text("legacy approved data must be ignored")
        event = self.event(self.docker+"service update --force redis")
        event["approved"] = True
        event["approval_ref"] = "record.md#approved"
        for _ in range(2):
            self.assertEqual("ask", hook.evaluate(event, self.project)["decision"])

    def command_confirmation(self, event, answer=None):
        """Native-shaped question/answer fixtures; never issued as real grants."""
        event.update(session_id="fixture-thread", turn_id="fixture-answer-turn")
        report = hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: [])
        question = report["confirmation_question"]
        question_id = ["request_user_input_async", "call_runtime_question", 0]
        reply = [{"questionItemId": json.dumps(question_id, separators=(",", ":")),
                  "question": question["title"], "answer": hook.CONFIRM if answer is None else answer}]
        rows = [
            {"turnId": event["turn_id"], "item": {"type": "userMessage", "id": "native-answer-1",
                "clientId": "native-human-message", "content": [{"type": "text", "text":
                "<send_user_message_question_reply>\n"+json.dumps(reply)+"\n</send_user_message_question_reply>"}]}},
            {"turnId": "question-turn", "item": {"type": "agentMessage", "id": question_id[1],
                "questions": [question], "text": question["title"]}},
        ]
        return question, rows

    def test_runtime_ask_waits_for_actual_native_answer_and_consumes_once(self):
        event = self.event(self.docker+"service update --publish-add published=6380,target=6379 redis")
        question, rows = self.command_confirmation(event)
        before = hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: [])
        self.assertEqual("ask", before["decision"])
        self.assertIn(event["tool_input"]["command"], question["title"])
        self.assertFalse((self.project/".local/operation-hook-used").exists())
        allowed = hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: rows)
        self.assertEqual("allow", allowed["decision"])
        self.assertEqual("human-command-confirmation", allowed["reason"])
        repeated = hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: rows)
        self.assertEqual("ask", repeated["decision"])
        self.assertFalse((self.project/".local/operation-hook.sqlite3").exists())

    def test_rejection_cancel_silence_and_forged_receipts_never_allow(self):
        for answer in ["取消", "拒绝", "", "确认", "执行本次命令，但换成其他目标"]:
            with self.subTest(answer=answer):
                event = self.event(self.docker+"service update --force redis")
                _, rows = self.command_confirmation(event, answer=answer)
                report = hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: rows)
                self.assertEqual("stop", report["decision"])
                self.assertEqual("command-confirmation-declined", report["reason"])
        event = self.event(self.docker+"service update --force redis")
        _, rows = self.command_confirmation(event)
        for mutate in [lambda r: r[0]["item"].update(clientId=None),
                       lambda r: r[0].update(turnId="older-answer-turn"),
                       lambda r: r[1]["item"].update(questions=None),
                       lambda r: r[1]["item"].update(id="another-question"),
                       lambda r: r.pop()]:
            copy = json.loads(json.dumps(rows)); mutate(copy)
            self.assertEqual("ask", hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: copy)["decision"])

    def test_confirmation_does_not_cover_changed_command_target_or_policy(self):
        event = self.event(self.docker+"service update --force redis")
        _, rows = self.command_confirmation(event)
        changed = self.event(self.docker+"service update --force redis-other")
        changed.update(session_id=event["session_id"], turn_id=event["turn_id"])
        self.assertEqual("ask", hook.evaluate(changed, self.project, host="codex", history_reader=lambda *_: rows)["decision"])
        self.policy["version"] += 1; self.save()
        self.assertEqual("ask", hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: rows)["decision"])
        self.policy["deny"] = ["docker **"]; self.save()
        with patch.object(hook, "native_items", side_effect=AssertionError("deny must not read approvals")):
            self.assertEqual("deny", hook.evaluate(event, self.project, host="codex")["decision"])

    def test_confirmation_reader_failure_and_atomic_replay_protection(self):
        event = self.event(self.docker+"service update --force redis")
        self.command_confirmation(event)
        def unavailable(*_): raise ValueError("native unavailable")
        report = hook.evaluate(event, self.project, host="codex", history_reader=unavailable)
        out, error, code = hook.host_response(report, "codex")
        self.assertEqual(("", 2), (out, code))
        self.assertIn("native-history-unavailable", error)
        self.assertNotIn("request_user_input_async", error)
        self.assertIn(event["tool_input"]["command"], report["confirmation_question"]["title"])
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as workers:
            consumed = list(workers.map(lambda _: hook.consume_confirmation(self.project, "thread", "receipt"), range(4)))
        self.assertEqual(1, consumed.count(True))

    def test_delayed_a_cannot_be_consumed_again_after_b(self):
        event_a = self.event(self.docker+"service update --force redis")
        _, rows_a = self.command_confirmation(event_a)
        event_b = json.loads(json.dumps(event_a))
        event_b["turn_id"] = "answer-turn-B"
        rows_b = json.loads(json.dumps(rows_a).replace("native-answer-1", "native-answer-B")
                            .replace("fixture-answer-turn", "answer-turn-B")
                            .replace("call_runtime_question", "call_runtime_question_B")
                            .replace("question-turn", "question-turn-B"))
        self.assertEqual("allow", hook.evaluate(event_a, self.project, host="codex", history_reader=lambda *_: rows_a)["decision"])
        reached, release = threading.Event(), threading.Event()
        consume = hook.consume_confirmation
        def delayed_consume(root, thread_id, receipt):
            if receipt == "native-answer-1":
                reached.set()
                if not release.wait(5):
                    raise RuntimeError("fixture scheduling timed out")
            return consume(root, thread_id, receipt)
        from concurrent.futures import ThreadPoolExecutor
        with patch.object(hook, "consume_confirmation", delayed_consume):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(hook.evaluate, event_a, self.project, host="codex", history_reader=lambda *_: rows_a)
                try:
                    self.assertTrue(reached.wait(5))
                    result_b = hook.evaluate(event_b, self.project, host="codex", history_reader=lambda *_: rows_b)
                    self.assertEqual("allow", result_b["decision"])
                finally:
                    release.set()
                self.assertEqual("ask", future.result(timeout=5)["decision"])

    def test_consumption_preserves_legacy_and_earlier_receipts(self):
        import hashlib
        folder = self.project/".local/operation-hook-used"
        folder.mkdir(parents=True)
        path = folder/hashlib.sha256(b"thread").hexdigest()
        path.write_text("legacy-A")
        self.assertTrue(hook.consume_confirmation(self.project, "thread", "new-B"))
        self.assertFalse(hook.consume_confirmation(self.project, "thread", "legacy-A"))
        self.assertFalse(hook.consume_confirmation(self.project, "thread", "new-B"))
        self.assertEqual(["legacy-A", "new-B"], path.read_text().splitlines())

    def test_consumption_storage_failure_never_discards_or_grants(self):
        with patch.object(hook, "MAX_INPUT", 4):
            self.assertTrue(hook.consume_confirmation(self.project, "bounded", "A"))
            self.assertTrue(hook.consume_confirmation(self.project, "bounded", "B"))
            self.assertFalse(hook.consume_confirmation(self.project, "bounded", "A"))
            with self.assertRaises(ValueError):
                hook.consume_confirmation(self.project, "bounded", "C")
        self.assertFalse(hook.consume_confirmation(self.project, "bounded", "A"))
        self.assertFalse(hook.consume_confirmation(self.project, "bounded", "B"))
        for receipt in ["", "A\nB", "A\u2028B"]:
            with self.subTest(receipt=repr(receipt)), self.assertRaises(ValueError):
                hook.consume_confirmation(self.project, "bounded", receipt)
        event = self.event(self.docker+"service update --force redis")
        _, rows = self.command_confirmation(event)
        with patch.object(hook, "consume_confirmation", side_effect=OSError("fixture storage unavailable")):
            report = hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: rows)
        self.assertEqual("confirmation-consumption-unavailable", report["confirmation_error"])
        self.assertEqual(2, hook.host_response(report, "codex")[2])

    def test_native_history_accepts_subdirectories_but_rejects_cross_project_paths(self):
        event = self.event(self.docker+"service update --force redis")
        _, rows = self.command_confirmation(event)
        child = self.project/"subdir"; child.mkdir()
        internal = self.project/"internal-link"; internal.symlink_to(child, target_is_directory=True)
        outside = self.project/"outside-link"; outside.symlink_to(self.project.parent, target_is_directory=True)
        fixture = self.project/"native-history.json"
        bindir = self.project/"native-bin"; bindir.mkdir()
        fake = bindir/"codex"
        fake.write_text("#!"+sys.executable+"\nimport json,sys\nfrom pathlib import Path\n"
                        "fixture=json.loads(Path("+repr(str(fixture))+").read_text())\n"
                        "for line in sys.stdin:\n request=json.loads(line)\n"
                        " if 'id' not in request: continue\n method=request['method']\n"
                        " value={} if method=='initialize' else ({'thread':{'id':'fixture-thread','cwd':fixture['cwd']}} "
                        "if method=='thread/read' else {'data':fixture['rows']})\n"
                        " print(json.dumps({'id':request['id'],'result':value}),flush=True)\n")
        fake.chmod(0o700)
        with patch.dict(os.environ, {"PATH": str(bindir)+os.pathsep+os.environ.get("PATH", "")}):
            for cwd in [self.project, child, internal]:
                with self.subTest(accepted=cwd.name):
                    fixture.write_text(json.dumps({"cwd": str(cwd), "rows": rows}))
                    self.assertEqual(rows, hook.native_items("fixture-thread", self.project))
            for cwd in [self.project.parent, self.project.parent/(self.project.name+"-other"), outside]:
                with self.subTest(rejected=cwd.name):
                    fixture.write_text(json.dumps({"cwd": str(cwd), "rows": rows}))
                    with self.assertRaises(ValueError):
                        hook.native_items("fixture-thread", self.project)
            fixture.write_text(json.dumps({"cwd": str(child), "rows": rows}))
            event["cwd"] = str(child)
            self.assertEqual("allow", hook.evaluate(event, self.project, host="codex")["decision"])

    def test_pre_enable_self_check_and_post_enable_probe_use_distinct_entries(self):
        configuration = self.cli("codex", extra=("--print-config",))
        self.assertEqual(0, configuration.returncode, configuration.stderr)
        registered = json.loads(configuration.stdout)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        event = self.event()
        event["tool_input"]["command"] = shlex.join([sys.executable, str(ROOT/"scripts/hook_command.py"),
            "--host", "codex", "--project-root", str(self.project), "--print-config"])
        active = subprocess.run(shlex.split(registered), input=json.dumps(event), text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(2, active.returncode)
        self.assertIn("unbound-or-wrapped-command", active.stderr)
        marker = self.project/"probe-count"
        fake = self.project/"ssh"
        fake.write_text("#!"+sys.executable+"\nwith open("+repr(str(marker))+", 'a') as f: f.write('probe\\n')\n")
        fake.chmod(0o700)
        probe = self.event("id", [str(fake), *self.prefix[1:]])
        accepted = subprocess.run(shlex.split(registered), input=json.dumps(probe), text=True,
                                  capture_output=True, timeout=10)
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        subprocess.run(shlex.split(probe["tool_input"]["command"]), check=True, timeout=5)
        self.assertEqual(["probe"], marker.read_text().splitlines())

    def test_conversation_fallback_still_requires_a_real_specific_question(self):
        event = self.event(self.docker+"service update --force redis")
        question, rows = self.command_confirmation(event)
        rows[0]["item"]["content"][0]["text"] = hook.CONFIRM
        rows[1]["item"].update(questions=None, phase="final_answer",
                               text=hook.conversation_question(question["title"]))
        self.assertEqual("native-answer-1", hook.confirmed_command(rows, event, question["title"]))
        rows[1]["item"]["text"] = "是否执行方案？"
        self.assertIsNone(hook.confirmed_command(rows, event, question["title"]))

    def test_runtime_question_is_returned_without_executing_the_command(self):
        event = self.event(self.docker+"service update --force redis")
        event.update(session_id="fixture-thread", turn_id="question-turn")
        report = hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: [])
        output, error, code = hook.host_response(report, "codex")
        self.assertEqual(("", 2), (output, code))
        self.assertIn("request_user_input_async", error)
        self.assertIn(event["tool_input"]["command"], json.loads(error.split("\n", 1)[1])["title"])

    def test_confirmed_runtime_command_executes_once_with_fake_ssh(self):
        marker = self.project/"runtime-executed"
        fake = self.project/"ssh"
        fake.write_text("#!"+sys.executable+"\nwith open("+repr(str(marker))+", 'a') as f: f.write('executed\\n')\n")
        fake.chmod(0o700)
        event = self.event(self.docker+"service update --force redis", [str(fake), *self.prefix[1:]])
        _, rows = self.command_confirmation(event)
        for _ in range(2):
            report = hook.evaluate(event, self.project, host="codex", history_reader=lambda *_: rows)
            if hook.host_response(report, "codex")[2] == 0:
                subprocess.run(shlex.split(event["tool_input"]["command"]), check=True, timeout=5)
        self.assertEqual(["executed"], marker.read_text().splitlines())

    def test_registered_processes_never_execute_unapproved_or_denied_commands(self):
        # An actual executor is used only after a hook allows a query. Its
        # executable named SSH writes a marker and cannot access the network.
        bindir = self.project/"bin"; bindir.mkdir()
        marker = self.project/"executed.txt"
        fake = bindir/"ssh"
        fake.write_text("#!"+sys.executable+"\nwith open("+repr(str(marker))+", 'a') as f: f.write('query\\n')\n")
        fake.chmod(0o700)
        prefix = [str(fake), *self.prefix[1:]]
        for host in hook.HOSTS:
            config = hook.registration(host, self.project)
            parsed = tomllib.loads(config) if host == "kimi" else json.loads(config)
            command = (parsed["hooks"][0]["command"] if host == "kimi" else
                       parsed["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
            for remote, expected in [("id", "allow"), (self.docker+"service update --force redis", "ask"),
                                     (self.docker+"service update --force redis", "ask"), ("rm -rf /", "deny")]:
                event = self.event(remote, prefix)
                proc = subprocess.run(shlex.split(command), input=json.dumps(event), text=True,
                                      capture_output=True, timeout=10)
                if expected == "allow":
                    self.assertEqual(0, proc.returncode, proc.stderr)
                    subprocess.run(shlex.split(event["tool_input"]["command"]), check=True, timeout=5)
                elif expected == "ask" and host == "claude":
                    self.assertEqual(0, proc.returncode)
                    self.assertEqual("ask", json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"])
                    # The host still needs an actual user answer. No fake
                    # approval is synthesized and no execution occurs here.
                else:
                    self.assertEqual(2, proc.returncode)
                    self.assertEqual("", proc.stdout)
        self.assertEqual(3, len(marker.read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
