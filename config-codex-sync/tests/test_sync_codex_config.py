import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "sync_codex_config.py"
)
SPEC = importlib.util.spec_from_file_location("sync_codex_config", SCRIPT_PATH)
assert SPEC and SPEC.loader
SYNC_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SYNC_MODULE
SPEC.loader.exec_module(SYNC_MODULE)


class DiscoverSkillsTest(unittest.TestCase):
    def test_codex_automation_excluded_from_sync_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source", root / "target"
            for base in [source, target]:
                base.mkdir()
                for name in ["automation-management", "portable", "alias"]:
                    folder = base / name
                    folder.mkdir()
                    identity = "automation-management" if name == "alias" else name
                    (folder / "SKILL.md").write_text(f"---\nname: '{identity}'\ndescription: Codex workflow\n---\n")
                (base / "automation-management.md").write_text("---\nname: automation-management\ndescription: test\n---\n")
            (target / "automation-management" / "old.txt").write_text("keep")
            included, excluded = SYNC_MODULE.discover_skills(source)
            self.assertEqual(["portable"], [p.name for p in included])
            self.assertEqual({"automation-management", "automation-management.md", "alias"}, {p.name for p in excluded})
            self.assertEqual([], SYNC_MODULE.plan_deletions(source, target))

    def test_excludes_all_mcp_skill_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            skills_root = Path(temporary_directory)
            included_names = ("database-client", "regular-skill")
            excluded_names = (
                "config-project-mcp-sync",
                "dm-mcp-creator",
                "mcp-audit",
                "mcp-generator",
                "mcp-monitor",
                "mcp-security",
                "ordinary-mcp-client",
                "synchronize_mcp_profile",
            )

            for name in included_names + excluded_names:
                skill_directory = skills_root / name
                skill_directory.mkdir()
                (skill_directory / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: test\n---\n",
                    encoding="utf-8",
                )

            skills, excluded_skills = SYNC_MODULE.discover_skills(skills_root)

            self.assertEqual([skill.name for skill in skills], list(included_names))
            self.assertEqual(
                [skill.name for skill in excluded_skills],
                list(excluded_names),
            )

    def test_excludes_skill_identified_as_mcp_in_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            skills_root = Path(temporary_directory)
            skill_directory = skills_root / "protocol-tool"
            skill_directory.mkdir()
            (skill_directory / "SKILL.md").write_text(
                "---\n"
                "name: protocol-tool\n"
                "description: Audit and monitor MCP servers\n"
                "---\n",
                encoding="utf-8",
            )

            skills, excluded_skills = SYNC_MODULE.discover_skills(skills_root)

            self.assertEqual(skills, [])
            self.assertEqual(excluded_skills, [skill_directory])

    def test_excludes_single_file_mcp_sync_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            skills_root = Path(temporary_directory)
            skill_file = skills_root / "mcp-sync.md"
            skill_file.write_text(
                "---\nname: mcp-sync\ndescription: test\n---\n",
                encoding="utf-8",
            )

            skills, excluded_skills = SYNC_MODULE.discover_skills(skills_root)

            self.assertEqual(skills, [])
            self.assertEqual(excluded_skills, [skill_file])



class DeleteSyncTest(unittest.TestCase):
    def test_preview_default_delete_and_protected_entries(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / 'source', root / 'target'
            def skill(base, name):
                path = base / 'skills' / name
                path.mkdir(parents=True)
                (path / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test\n---\n')
                return path
            keep = skill(source, 'keep')
            (source / 'AGENTS.md').write_text('rules')
            target_keep = skill(target, 'keep')
            (target_keep / 'obsolete.txt').write_text('old')
            old = skill(target, 'retired')
            protected = skill(target, 'protected')
            (protected / '.git').mkdir()
            (protected / '.git' / 'config').write_text('preserve')
            mcp = skill(target, 'setup-mcp')
            (target / 'skills' / 'README.md').write_text('index')
            outside = root / 'outside'; outside.mkdir()
            (outside / 'data').write_text('preserve')
            (target_keep / 'link').symlink_to(outside, target_is_directory=True)
            command = [sys.executable, str(SCRIPT_PATH), '--target', 'claude', '--codex-root', str(source), '--claude-root', str(target)]
            def run(*args):
                result = subprocess.run(command + list(args), capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                return result.stdout
            preview = run('--delete', '--dry-run')
            self.assertNotIn(str(old / 'SKILL.md'), preview)
            self.assertIn(str(target_keep / 'obsolete.txt'), preview)
            self.assertTrue(old.exists())
            self.assertFalse((target / 'CLAUDE.md').exists())
            run()
            self.assertTrue(old.exists())
            run('--delete')
            self.assertTrue((old / 'SKILL.md').exists())
            self.assertTrue((protected / 'SKILL.md').exists())
            self.assertFalse((target_keep / 'obsolete.txt').exists())
            self.assertTrue((mcp / 'SKILL.md').exists())
            self.assertTrue((protected / '.git' / 'config').exists())
            self.assertTrue((outside / 'data').exists())
            self.assertTrue((target_keep / 'link').is_symlink())
            self.assertTrue((target / 'skills' / 'README.md').exists())
            self.assertEqual([], SYNC_MODULE.plan_deletions(source / 'skills', target / 'skills'))

    def test_empty_source_and_conflict_do_not_delete(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; target = root / 'target'
            (source / 'skills').mkdir(parents=True)
            (source / 'AGENTS.md').write_text('rules')
            old = target / 'skills' / 'old'; old.mkdir(parents=True)
            (old / 'SKILL.md').write_text('---\nname: old\ndescription: test\n---\n')
            command = [sys.executable, str(SCRIPT_PATH), '--target', 'claude', '--codex-root', str(source), '--claude-root', str(target), '--delete']
            self.assertNotEqual(0, subprocess.run(command, capture_output=True).returncode)
            keep = source / 'skills' / 'keep'; keep.mkdir()
            (keep / 'SKILL.md').write_text('---\nname: keep\ndescription: test\n---\n')
            (target / 'skills' / 'keep').write_text('conflict')
            self.assertNotEqual(0, subprocess.run(command, capture_output=True).returncode)
            self.assertTrue((old / 'SKILL.md').exists())
            self.assertFalse((target / 'CLAUDE.md').exists())

    def test_single_file_and_source_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; target = root / 'target'
            source.mkdir(); target.mkdir()
            def entry(base, name, description='test'):
                path = base / name
                path.write_text(f'---\nname: sample\ndescription: {description}\n---\n')
                return path
            stale = entry(target, 'old.md')
            entry(target, 'mcp.md', 'MCP tool')
            entry(target, 'excluded.md')
            entry(source, 'excluded.md', 'MCP tool')
            entry(target, 'kept.md'); entry(source, 'kept.md')
            (target / 'notes.txt').write_text('unmanaged')
            self.assertEqual([], SYNC_MODULE.plan_deletions(source, target))
            self.assertTrue(stale.exists())

    def test_reject_nested_and_symlink_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'
            (source / 'skills').mkdir(parents=True)
            (source / 'AGENTS.md').write_text('rules')
            for target in [root, source / 'child', source]:
                with self.assertRaises(SYNC_MODULE.SyncError):
                    SYNC_MODULE.validate_paths(source, [('Claude', target)])
            target = root / 'target'; target.mkdir()
            (target / 'skills').symlink_to(source / 'skills', target_is_directory=True)
            with self.assertRaises(SYNC_MODULE.SyncError):
                SYNC_MODULE.validate_paths(source, [('Claude', target)])

if __name__ == "__main__":
    unittest.main()
