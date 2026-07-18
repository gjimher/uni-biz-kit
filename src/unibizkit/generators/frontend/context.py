from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Context:
    concepts: List[Dict[str, Any]]
    concept_map: Dict[str, Any]
    presentation_config: Dict[str, Any]
    system_config: Dict[str, Any]
    security_config: Dict[str, Any]
    deployment_config: Dict[str, Any]
    business_schema: Dict[str, Any]
    workflow_config: Dict[str, Any]
    validations_config: Dict[str, Any]
    integrations_config: Dict[str, Any]
    presentation_custom_config: Dict[str, Any]
    output_dir: Path

    @property
    def customization(self) -> bool:
        """Whether the presentation customization system is generated at all.

        designer 'off' removes it entirely: the emitted app matches the
        pre-customization output (no runtime merge engine, no design tools).
        """
        return self.presentation_config["designer"] != "off"
