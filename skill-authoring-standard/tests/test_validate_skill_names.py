"""Exercise naming contracts with valid and invalid user skill fixtures."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/validate_skill_names.py"
SPEC = importlib.util.spec_from_file_location("skill_names", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def skill(self, folder="code-sample-analysis", name=None, title="样本分析", ui=None):
        path = self.root / folder
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(f"---\nname: {name or folder}\ndescription: 分析样本。\n---\n\n# {title}\n", encoding="utf-8")
        if ui is not None:
            (path / "agents").mkdir()
            (path / "agents/openai.yaml").write_text(yaml.safe_dump({"interface": ui}, allow_unicode=True), encoding="utf-8")
        return path

    def test_valid_capabilities_and_command_exception(self):
        for name in ["code-sample-" + capability for capability in MODULE.CAPABILITIES] + ["git-push"]:
            with self.subTest(name=name):
                self.assertEqual([], MODULE.validate_skill(self.skill(name)))

    def test_directory_mismatch(self):
        errors = MODULE.validate_skill(self.skill(name="code-other-analysis"))
        self.assertTrue(any("目录名" in error for error in errors))

    def test_registered_domain_is_required_before_subdomain(self):
        for name in ["design-spec-authoring", "frontend-prototype-design", "frontend-ux-audit", "config-codex-sync", "system-disk-usage-analysis", "operation-workflow"]:
            with self.subTest(name=name):
                self.assertEqual([], MODULE.validate_skill(self.skill(name)))
        for name in ["page-ux-audit", "disk-usage-analysis", "codex-config-sync", "module-architecture-doc-authoring", "operations-workflow", "server-operation-workflow"]:
            with self.subTest(name=name):
                errors = MODULE.validate_skill(self.skill(name))
                self.assertTrue(any("一级领域" in error for error in errors))

    def test_invalid_identifiers_and_unsupported_suffixes(self):
        for name in ["Code-sample-analysis", "code-sample--analysis", "-code-sample-analysis", "code-sample-analysis-", "code-sample_analysis", "x" * 60 + "-analysis", "code-sample-reviewer", "code-sample-report", "analysis", "auto-code-sample-analysis", "code-sample-msg-authoring", "code-sample-v2-analysis"]:
            with self.subTest(name=name):
                self.assertTrue(MODULE.validate_skill(self.skill(name)))

    def test_acronyms_and_recommended_word_count_are_not_banned(self):
        self.assertEqual([], MODULE.validate_skill(self.skill("ai-code-sample-mcp-ux-data-risk-analysis")))

    def test_chinese_title_contract(self):
        for i, title in enumerate(["Sample analysis", "样本分析器", "样本分析助手"]):
            self.assertTrue(MODULE.validate_skill(self.skill(f"code-sample-{i}-analysis", title=title)))

    def test_ui_and_prompt_match_current_identity(self):
        valid = {"display_name": "样本分析", "default_prompt": "使用 $code-sample-analysis 分析样本。"}
        self.assertEqual([], MODULE.validate_skill(self.skill(ui=valid)))
        for name, ui in [("code-other-analysis", {"display_name": "别的名称"}), ("code-third-analysis", {"default_prompt": "使用 $code-third-analysis-extra。"}), ("code-fourth-analysis", {"default_prompt": 123})]:
            self.assertTrue(MODULE.validate_skill(self.skill(name, ui=ui)))

    def test_malformed_yaml_and_wrong_metadata_type(self):
        path = self.skill()
        for content in ["---\nname: [\n---\n# 样本分析\n", "---\n- code-sample\n---\n# 样本分析\n", "# 样本分析\n"]:
            (path / "SKILL.md").write_text(content, encoding="utf-8")
            self.assertTrue(MODULE.validate_skill(path))

    def test_root_skips_hidden_system_skills_and_cli_fails_for_invalid_skill(self):
        self.skill()
        self.skill(".system/provider")
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("检查 1 个技能", result.stdout)
        self.skill("code-sample-helper")
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        self.assertEqual(1, result.returncode)
        self.assertIn("1 个失败", result.stdout)

    def test_empty_root_is_an_error(self):
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
