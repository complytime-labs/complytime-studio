# SPDX-License-Identifier: Apache-2.0

"""Custom ADK-to-A2A event converter that adds artifact metadata.

Wraps the default converter and enriches TaskArtifactUpdateEvent parts with
MIME type and provenance metadata when the originating ADK event carries
artifact_delta.
"""

import logging
from typing import Dict, List, Optional, Union

from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent

from google.adk.a2a.converters.from_adk_event import (
    convert_event_to_a2a_events as default_converter,
)
from google.adk.a2a.converters.part_converter import (
    GenAIPartToA2APartConverter,
    convert_genai_part_to_a2a_part,
)
from google.adk.events.event import Event

logger = logging.getLogger(__name__)

A2AUpdateEvent = Union[TaskStatusUpdateEvent, TaskArtifactUpdateEvent]


def convert_event_with_yaml_metadata(
    event: Event,
    agents_artifacts: Optional[Dict[str, str]] = None,
    task_id: Optional[str] = None,
    context_id: Optional[str] = None,
    part_converter: GenAIPartToA2APartConverter = convert_genai_part_to_a2a_part,
) -> List[A2AUpdateEvent]:
    """Convert ADK events to A2A events, adding YAML metadata on artifact deltas."""
    if agents_artifacts is None:
        agents_artifacts = {}

    a2a_events = default_converter(
        event, agents_artifacts, task_id, context_id, part_converter
    )

    has_artifact_delta = (
        hasattr(event, "actions")
        and event.actions
        and hasattr(event.actions, "artifact_delta")
        and event.actions.artifact_delta
    )

    if has_artifact_delta:
        for a2a_event in a2a_events:
            if isinstance(a2a_event, TaskArtifactUpdateEvent):
                _enrich_artifact_metadata(a2a_event, event)

    return a2a_events


def _enrich_artifact_metadata(
    a2a_event: TaskArtifactUpdateEvent, adk_event: Event
) -> None:
    """Add MIME type and provenance metadata to artifact parts."""
    if not a2a_event.artifact or not a2a_event.artifact.parts:
        return

    filenames = list(adk_event.actions.artifact_delta.keys())

    from main import MODEL_NAME, PROMPT_VERSION

    for part in a2a_event.artifact.parts:
        root = getattr(part, "root", part)
        if not hasattr(root, "metadata"):
            continue
        if root.metadata is None:
            root.metadata = {}
        root.metadata["mimeType"] = "application/yaml"
        root.metadata["model"] = MODEL_NAME
        root.metadata["promptVersion"] = PROMPT_VERSION
        if filenames:
            root.metadata["name"] = filenames[0]
            logger.info(
                "Enriched artifact part with metadata: %s (model=%s, prompt=%s)",
                filenames[0],
                MODEL_NAME,
                PROMPT_VERSION,
            )
