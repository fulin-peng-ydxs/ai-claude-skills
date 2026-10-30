from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "scan_project_handover.py"
)
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "project-handover-report-template.md"
)


def load_scanner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scan_project_handover", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load scanner: {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCANNER = load_scanner()


class ProjectHandoverScannerTests(unittest.TestCase):
    def test_report_template_keeps_full_handover_structure(self) -> None:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        expected_headings = [
            "一页结论",
            "代码包全景地图",
            "总体功能说明",
            "总体技术架构",
            "部署架构",
            "模块职责与依赖关系",
            "依赖关系详细说明",
            "前端应用结构",
            "模块完整性评估",
            "典型调用链",
            "接手路线图",
            "接手时最该问交付方的问题",
            "关键证据入口",
            "最后建议",
        ]

        for number, heading in enumerate(expected_headings, start=1):
            self.assertIn(f"## {number}. {heading}", template)

    def test_detects_nested_repositories_and_declared_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").mkdir()
            (root / "nested" / ".git").mkdir(parents=True)
            (root / "core").mkdir()
            (root / "core" / "pom.xml").write_text(
                "<project><artifactId>core</artifactId></project>", encoding="utf-8"
            )
            (root / "pom.xml").write_text(
                """
                <project>
                  <artifactId>root</artifactId>
                  <modules><module>core</module><module>missing-service</module></modules>
                </project>
                """,
                encoding="utf-8",
            )
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "name": "fixture",
                        "dependencies": {"missing-ui": "file:packages/missing-ui"},
                    }
                ),
                encoding="utf-8",
            )

            report = SCANNER.build_inventory(root, 10, 80)

            self.assertEqual(
                report["candidate_delivery_shape"],
                "repository containing nested repositories or worktrees",
            )
            references = {
                item["reference"] for item in report["declared_local_reference_gaps"]
            }
            self.assertEqual(references, {"missing-service", "missing-ui"})

    def test_reports_manifest_parse_errors_without_absolute_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "package.json").write_text("{invalid", encoding="utf-8")
            (root / "pom.xml").write_text("<project>", encoding="utf-8")

            report = SCANNER.build_inventory(root, 10, 80)

            self.assertEqual(report["root"], ".")
            self.assertNotIn("absolute_root", report)
            self.assertEqual(len(report["manifest_parse_errors"]), 2)
            self.assertEqual(
                {item["manifest"] for item in report["manifest_parse_errors"]},
                {"package.json", "pom.xml"},
            )

    def test_scans_external_directory_unless_explicitly_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            external = root / "external"
            external.mkdir()
            (external / "package.json").write_text(
                json.dumps({"name": "external-adapter"}), encoding="utf-8"
            )

            included = SCANNER.build_inventory(root, 10, 80)
            excluded = SCANNER.build_inventory(
                root, 10, 80, extra_excludes=["external"]
            )

            self.assertIn("external/package.json", included["build_manifests"]["items"])
            self.assertNotIn(
                "external/package.json", excluded["build_manifests"]["items"]
            )

    def test_output_lists_sensitive_path_without_reading_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            secret_value = "SYNTHETIC_SECRET_VALUE"
            (root / ".env").write_text(f"TOKEN={secret_value}\n", encoding="utf-8")

            report = SCANNER.build_inventory(root, 10, 80)
            markdown = SCANNER.format_markdown(report)
            json_output = json.dumps(report)

            self.assertIn(".env", markdown)
            self.assertNotIn(secret_value, markdown)
            self.assertNotIn(secret_value, json_output)


if __name__ == "__main__":
    unittest.main()
