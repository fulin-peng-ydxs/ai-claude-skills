"""Boundary and Git-index checks use isolated repositories, never a server."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_archive.py"
SPEC = importlib.util.spec_from_file_location("archive_gate", SCRIPT)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
ROOT = "agent-works/operations"


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        self.git("init", "-q")

    def git(self, *args, input=None):
        result = subprocess.run(["git", "-C", str(self.repo), *args], input=input, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout

    def file(self, relative, size):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            stream.truncate(size)
        return path

    def stage(self, relative):
        self.git("add", "--", relative)

    def test_exact_decimal_limit_and_one_byte_over(self):
        for size, allowed in [(0, True), (14_999_999, True), (15_000_000, True), (15_000_001, False), (15 * 1024 * 1024, False)]:
            with self.subTest(size=size):
                path = self.file(f"{ROOT}/servers/prod-a/rootfs/etc/config", size)
                self.assertEqual(allowed, not GATE.check_file(path)["errors"])
                self.stage(ROOT)
                self.assertEqual(allowed, not GATE.check_index(self.repo, ROOT)["errors"])

    def test_index_wins_over_smaller_worktree(self):
        relative = f"{ROOT}/servers/prod-a/rootfs/etc/config"
        self.file(relative, 15_000_001)
        self.stage(ROOT)
        self.file(relative, 1)
        self.assertTrue(GATE.check_index(self.repo, ROOT)["errors"])

    def test_unstaged_large_file_is_not_claimed_as_staged(self):
        relative = f"{ROOT}/servers/prod-a/rootfs/etc/config"
        self.file(relative, 1)
        self.stage(ROOT)
        self.file(relative, 15_000_001)
        self.assertFalse(GATE.check_index(self.repo, ROOT)["errors"])
        self.assertTrue(GATE.check_file(self.repo / relative)["errors"])

    def test_records_cannot_hide_large_server_payload(self):
        relative = f"{ROOT}/records/202609102256/baseline/prod-a/rootfs/opt/data"
        self.file(relative, 15_000_001)
        self.stage(ROOT)
        self.assertTrue(GATE.check_index(self.repo, ROOT)["errors"])

    def test_replacement_refs_do_not_change_indexed_blob_size(self):
        relative = f"{ROOT}/servers/prod-a/rootfs/etc/config"
        for original_size, replacement_size in [(15_000_001, 1), (1, 15_000_001)]:
            with self.subTest(original_size=original_size):
                self.file(relative, original_size)
                self.stage(ROOT)
                original = self.git("ls-files", "--stage", "--", relative).split()[1].decode()
                replacement_file = self.file("replacement", replacement_size)
                replacement = self.git("hash-object", "-w", str(replacement_file)).strip().decode()
                self.git("replace", original, replacement)
                try:
                    report = GATE.check_index(self.repo, ROOT)
                    self.assertEqual(original_size, report["files"][0]["size_bytes"])
                    self.assertEqual(original_size > GATE.MAX_BYTES, bool(report["errors"]))
                finally:
                    self.git("replace", "-d", original)

    def test_symlink_and_fifo_are_not_opened(self):
        relative = f"{ROOT}/servers/prod-a/rootfs/etc/link"
        path = self.repo / relative
        path.parent.mkdir(parents=True)
        path.symlink_to("/not/a/real/secret")
        self.assertTrue(GATE.check_file(path)["errors"])
        self.stage(ROOT)
        self.assertTrue(GATE.check_index(self.repo, ROOT)["errors"])
        fifo = self.repo / "fifo"
        os.mkfifo(fifo)
        self.assertTrue(GATE.check_file(fifo)["errors"])

    def test_odd_filenames_and_similar_prefix(self):
        self.file(f"{ROOT}/records/space\tand\nnewline", 5)
        self.file(f"{ROOT}-other/large", 15_000_001)
        self.stage("agent-works")
        report = GATE.check_index(self.repo, ROOT)
        self.assertEqual(1, report["checked"])
        self.assertFalse(report["errors"])

    def test_bad_root_empty_index_and_subdirectory_fail(self):
        for root in ["", ".", "../other", "/tmp", "a//b", "a/../b", ".git", "a/", "a\\b"]:
            with self.subTest(root=root), self.assertRaises(ValueError):
                GATE.check_index(self.repo, root)
        self.assertTrue(GATE.check_index(self.repo, ROOT)["errors"])
        (self.repo / "subdir").mkdir()
        with self.assertRaises(ValueError):
            GATE.check_index(self.repo / "subdir", ROOT)

    def test_index_conflict_is_rejected(self):
        relative = f"{ROOT}/records/conflicted"
        oid = self.git("hash-object", "-w", "--stdin", input=b"base").strip()
        data = b"100644 " + oid + b" 1\t" + relative.encode() + b"\0"
        self.git("update-index", "-z", "--index-info", input=data)
        self.assertTrue(GATE.check_index(self.repo, ROOT)["errors"])

    def test_gitlink_and_root_symlink_are_rejected(self):
        # A gitlink points at a commit, not a file; never accept its tiny metadata.
        tree = self.git("mktree", input=b"").strip()
        commit = self.git("-c", "user.name=Archive Test", "-c", "user.email=test@example.invalid", "commit-tree", tree.decode(), input=b"fixture\n").strip()
        relative = f"{ROOT}/servers/prod-a/rootfs/nested"
        self.git("update-index", "--add", "--cacheinfo", f"160000,{commit.decode()},{relative}")
        self.assertTrue(GATE.check_index(self.repo, ROOT)["errors"])
        self.git("update-index", "--force-remove", relative)
        root_path = self.repo / ROOT
        root_path.parent.mkdir(parents=True, exist_ok=True)
        root_path.symlink_to("/missing/archive")
        self.stage(ROOT)
        self.assertTrue(GATE.check_index(self.repo, ROOT)["errors"])

    def test_deleted_large_file_not_in_resulting_snapshot(self):
        relative = f"{ROOT}/records/large"
        self.file(relative, 15_000_001)
        self.file(f"{ROOT}/records/manifest.json", 2)
        self.stage(ROOT)
        self.git("rm", "--cached", "--", relative)
        self.assertFalse(GATE.check_index(self.repo, ROOT)["errors"])

    def test_cli_fails_closed_for_missing_file(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "file", str(self.repo / "missing")], capture_output=True, text=True)
        self.assertEqual(1, result.returncode)
        self.assertIn('"passed": false', result.stdout)


if __name__ == "__main__":
    unittest.main()
