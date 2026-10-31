"""Exercise shared parsing through installed validator entrypoints."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILLS = Path(__file__).resolve().parents[2]
VALIDATORS = {
    'ai-constraint-doc-authoring': 'validate_ai_constraint_docs.py',
    'project-readme-authoring': 'validate_readme_structure.py',
    'project-module-architecture-doc-authoring': 'validate_architecture_doc_structure.py',
}


class DocumentValidatorsTest(unittest.TestCase):
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
