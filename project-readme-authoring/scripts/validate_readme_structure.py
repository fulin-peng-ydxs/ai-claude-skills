#!/usr/bin/env python3
"""Validate the artifact using its authoritative template, without a second schema."""
from pathlib import Path
import sys

_engine = Path(__file__).resolve().parents[2] / 'skill-authoring-standard/scripts'
if not (_engine / 'validate_document_template.py').is_file():
    raise SystemExit('Missing dependency: install skill-authoring-standard and ai-constraint-doc-authoring beside this skill.')
sys.path.insert(0, str(_engine))
from validate_document_template import artifact_cli, validate as validate_template, validate_existing

TEMPLATE = Path(__file__).resolve().parents[1] / 'references/output-contract.md'


def validate(text: str, *, custom_structure: bool = False) -> list[str]:
    return validate_existing(text) if custom_structure else validate_template(text, TEMPLATE.read_text(encoding='utf-8'))


if __name__ == '__main__':
    raise SystemExit(artifact_cli(TEMPLATE))
