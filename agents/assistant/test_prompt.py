# SPDX-License-Identifier: Apache-2.0

"""Tests for prompt.py — system prompt assembly from files."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import prompt as prompt_module
from prompt import _load_few_shot_examples, _load_skills, load_system_prompt


class TestLoadSystemPrompt:
    def test_assembles_base_plus_skills(self, tmp_path):
        skills_dir = tmp_path / "skills" / "audit"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# Audit Skill")

        with patch.object(prompt_module, "_load_base_prompt", return_value="You are a compliance assistant."):
            with patch.object(prompt_module, "SKILLS_DIR", tmp_path / "skills"):
                with patch.object(prompt_module, "FEW_SHOT_DIR", Path("/nonexistent")):
                    result = load_system_prompt()
                    assert "compliance assistant" in result
                    assert "Audit Skill" in result
                    assert "Loaded Skills" in result

    def test_empty_when_no_files(self, tmp_path):
        with patch.object(prompt_module, "_load_base_prompt", return_value=""):
            with patch.object(prompt_module, "_load_skills", return_value=""):
                with patch.object(prompt_module, "_load_few_shot_examples", return_value=""):
                    result = load_system_prompt()
                    assert result == ""

    def test_base_prompt_only(self):
        with patch.object(prompt_module, "_load_base_prompt", return_value="Base prompt here."):
            with patch.object(prompt_module, "_load_skills", return_value=""):
                with patch.object(prompt_module, "_load_few_shot_examples", return_value=""):
                    result = load_system_prompt()
                    assert result == "Base prompt here."


class TestLoadSkills:
    def test_loads_skills_from_directory(self, tmp_path):
        skill_dir = tmp_path / "skills" / "audit"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Audit Skill\nClassification logic here.")

        with patch.object(prompt_module, "SKILLS_DIR", tmp_path / "skills"):
            result = _load_skills()
            assert "Audit Skill" in result
            assert "Classification logic" in result

    def test_empty_when_skills_dir_has_no_skill_files(self, tmp_path, monkeypatch):
        empty_skills = tmp_path / "skills"
        empty_skills.mkdir()
        (empty_skills / "empty-dir").mkdir()
        monkeypatch.setattr(prompt_module, "SKILLS_DIR", empty_skills)
        result = _load_skills()
        assert result == ""

    def test_multiple_skills_joined(self, tmp_path):
        skills_root = tmp_path / "skills"
        for name in ("alpha", "beta"):
            d = skills_root / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"# {name.title()} Skill")

        with patch.object(prompt_module, "SKILLS_DIR", skills_root):
            result = _load_skills()
            assert "Alpha Skill" in result
            assert "Beta Skill" in result
            assert "---" in result


class TestLoadFewShotExamples:
    def test_valid_examples(self, tmp_path):
        few_shot_dir = tmp_path / "few-shot"
        few_shot_dir.mkdir()
        examples = [
            {"scenario": "Pass with evidence", "classification": "Observation", "reasoning": "All checks pass"},
            {"scenario": "Missing attestation", "classification": "Finding", "reasoning": "No proof"},
        ]
        (few_shot_dir / "audit.yaml").write_text(yaml.dump(examples))

        with patch.object(prompt_module, "FEW_SHOT_DIR", few_shot_dir):
            result = _load_few_shot_examples()
            assert "Classification Examples" in result
            assert "Pass with evidence" in result
            assert "Missing attestation" in result
            assert "Observation" in result
            assert "Finding" in result

    def test_malformed_yaml_skipped(self, tmp_path):
        few_shot_dir = tmp_path / "few-shot"
        few_shot_dir.mkdir()
        (few_shot_dir / "bad.yaml").write_text("{{invalid: yaml: [")
        (few_shot_dir / "good.yaml").write_text(
            yaml.dump([{"scenario": "Valid one", "classification": "Observation", "reasoning": "OK"}])
        )

        with patch.object(prompt_module, "FEW_SHOT_DIR", few_shot_dir):
            result = _load_few_shot_examples()
            assert "Valid one" in result

    def test_non_list_yaml_skipped(self, tmp_path):
        few_shot_dir = tmp_path / "few-shot"
        few_shot_dir.mkdir()
        (few_shot_dir / "scalar.yaml").write_text("just a string")

        with patch.object(prompt_module, "FEW_SHOT_DIR", few_shot_dir):
            result = _load_few_shot_examples()
            assert result == ""

    def test_empty_directory(self, tmp_path):
        few_shot_dir = tmp_path / "few-shot"
        few_shot_dir.mkdir()

        with patch.object(prompt_module, "FEW_SHOT_DIR", few_shot_dir):
            result = _load_few_shot_examples()
            assert result == ""
