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
    def test_excludes_all_mcp_skill_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            skills_root = Path(temporary_directory)
            included_names = ("database-client", "regular-skill")
            excluded_names = (
                "dm-mcp-creator",
                "mcp-audit",
                "mcp-generator",
                "mcp-monitor",
                "mcp-security",
                "ordinary-mcp-client",
                "sync-project-mcp",
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


if __name__ == "__main__":
    unittest.main()
