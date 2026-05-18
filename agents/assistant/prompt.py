# SPDX-License-Identifier: Apache-2.0

"""System prompt assembly for the Studio assistant.

Loads prompt.md, skills, and few-shot examples into a single string
injected as the system message in the LangGraph agent node.
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROMPT_PATH = Path("/app/prompt.md")
SKILLS_DIR = Path("/app/skills")
FEW_SHOT_DIR = Path("/app/prompts/few-shot")


def load_system_prompt() -> str:
    """Assemble the full system prompt from prompt.md + skills + few-shot."""
    base = _load_base_prompt()
    skills = _load_skills()
    if skills:
        base = f"{base}\n\n## Loaded Skills\n\n{skills}"
    few_shot = _load_few_shot_examples()
    if few_shot:
        base = f"{base}\n\n{few_shot}"
    return base


def _load_base_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text()
    local = Path(__file__).parent / "prompt.md"
    if local.exists():
        return local.read_text()
    logger.warning("prompt.md not found — using empty system prompt")
    return ""


def _load_skills() -> str:
    if not SKILLS_DIR.exists():
        local = Path(__file__).parent / "skills"
        if not local.exists():
            return ""
        skills_dir = local
    else:
        skills_dir = SKILLS_DIR

    parts = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        parts.append(skill_file.read_text())
    return "\n\n---\n\n".join(parts)


def _load_few_shot_examples() -> str:
    if not FEW_SHOT_DIR.exists():
        local = Path(__file__).parent / "prompts" / "few-shot"
        if not local.exists():
            return ""
        few_shot_dir = local
    else:
        few_shot_dir = FEW_SHOT_DIR

    parts: list[str] = []
    for f in sorted(few_shot_dir.glob("*.yaml")):
        try:
            examples = yaml.safe_load(f.read_text())
        except yaml.YAMLError:
            logger.warning("Skipping malformed few-shot file: %s", f.name)
            continue
        if not isinstance(examples, list):
            continue
        for ex in examples:
            if not isinstance(ex, dict) or "scenario" not in ex:
                continue
            lines = [f"**Scenario:** {ex['scenario']}"]
            if ex.get("evidence"):
                lines.append(f"**Evidence:** {ex['evidence']}")
            elif ex.get("audit_result_type"):
                lines.append(f"**AuditResult type:** {ex['audit_result_type']}")
                if ex.get("mapping"):
                    lines.append(f"**Mapping:** {ex['mapping']}")
            for key in ("classification", "determination", "coverage"):
                if key in ex:
                    lines.append(f"**{key.title()}:** {ex[key]}")
            if ex.get("reasoning"):
                lines.append(f"**Reasoning:** {ex['reasoning'].strip()}")
            parts.append("\n".join(lines))

    if not parts:
        return ""
    return "## Classification Examples\n\n" + "\n\n---\n\n".join(parts)
