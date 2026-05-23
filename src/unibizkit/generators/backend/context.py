from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Context:
    concepts: List[Dict[str, Any]]
    concept_map: Dict[str, Any]
    security_config: Dict[str, Any]
    business_schema: Dict[str, Any]
    workflow_config: Dict[str, Any]
    system_config: Dict[str, Any]
    deployment_config: Dict[str, Any]
    seed_data_config: Dict[str, Any]
    rules_config: Dict[str, Any]
    validations_config: Dict[str, Any]
    model_dir: Path = field(default_factory=lambda: Path("."))
