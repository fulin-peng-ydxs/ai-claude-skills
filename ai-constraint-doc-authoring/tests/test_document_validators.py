"""Exercise shared parsing through installed validator entrypoints."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS / 'ai-constraint-doc-authoring/scripts'))
import document_markdown as markdown
VALIDATORS = {
    'ai-constraint-doc-authoring': 'validate_ai_constraint_docs.py',
    'project-readme-authoring': 'validate_readme_structure.py',
    'project-module-architecture-doc-authoring': 'validate_architecture_doc_structure.py',
}


class DocumentValidatorsTest(unittest.TestCase):
    def test_field_aware_fences_keep_original_lines_and_detect_unclosed_blocks(self):
        for indent in [2, 3, 4, 5]:
            for marker in ['```', '~~~~']:
                with self.subTest(indent=indent, marker=marker):
                    pad = ' ' * indent
                    opening = '- 步骤：\n\n' + pad + marker + 'bash\n'
                    content = pad + 'printf example\n'
                    closing = pad + marker + '\n'
                    text = opening + content + closing + '- 验证：未执行。\n'
                    classified = list(markdown.fenced_lines(text, field_continuations=True))
                    self.assertEqual(text.splitlines(), [line for line, _ in classified])
                    self.assertEqual(2, sum(kind == 'marker' for _, kind in classified))
                    self.assertTrue(markdown.fences_closed(text, field_continuations=True))
                    self.assertFalse(markdown.fences_closed(opening + content, field_continuations=True))
                    self.assertFalse(markdown.fences_closed(opening + content + pad + '``\n', field_continuations=True))
        # Opt-in field parsing does not reinterpret every four-space literal as a fence.
        literal = '# 示例\n\n    ```bash\n    printf example\n'
        self.assertFalse(any(kind == 'marker' for _, kind in markdown.fenced_lines(literal, field_continuations=True)))
        self.assertEqual(list(markdown.fenced_lines(literal)), list(markdown.fenced_lines(literal, field_continuations=True)))
        raw = '``````text\n- 步骤：原文中的字段示例。\n    ```bash\n    未闭合的示例原文\n``````\n'
        classified = list(markdown.fenced_lines(raw, field_continuations=True))
        self.assertEqual(2, sum(kind == 'marker' for _, kind in classified))
        self.assertTrue(markdown.fences_closed(raw, field_continuations=True))

    def test_relocated_installations_keep_contracts(self):
        # Entry points must work outside the checkout and from an unrelated cwd.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for skill, script in VALIDATORS.items():
                destination = root / 'skills' / skill / 'scripts'
                destination.mkdir(parents=True)
                shutil.copy2(SKILLS / skill / 'scripts' / script, destination / script)
            shutil.copy2(
                SKILLS / 'ai-constraint-doc-authoring/scripts/document_markdown.py',
                root / 'skills/ai-constraint-doc-authoring/scripts/document_markdown.py',
            )
            engine = root / 'skills/skill-authoring-standard/scripts'
            engine.mkdir(parents=True)
            shutil.copy2(SKILLS / 'skill-authoring-standard/scripts/validate_document_template.py', engine / 'validate_document_template.py')
            for skill in VALIDATORS:
                references = root / 'skills' / skill / 'references'
                references.mkdir()
                shutil.copy2(SKILLS / skill / 'references/output-contract.md', references / 'output-contract.md')
            sys.path.insert(0, str(SKILLS / 'skill-authoring-standard/scripts'))
            import validate_document_template as templates
            for skill in VALIDATORS:
                contract = (SKILLS / skill / 'references/output-contract.md').read_text()
                self.assertEqual([], templates.check_template(contract))
            for skill, script in VALIDATORS.items():
                with self.subTest(skill=skill):
                    result = subprocess.run(
                        [sys.executable, str(root / 'skills' / skill / 'scripts' / script), '--self-test'],
                        cwd=root, capture_output=True, text=True,
                    )
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_missing_dependency_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for skill, script in VALIDATORS.items():
                with self.subTest(skill=skill):
                    destination = root / 'skills' / skill / 'scripts'
                    destination.mkdir(parents=True)
                    shutil.copy2(SKILLS / skill / 'scripts' / script, destination / script)
                    result = subprocess.run(
                        [sys.executable, str(destination / script), '--self-test'],
                        cwd=root, capture_output=True, text=True,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn('Missing dependency:', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
