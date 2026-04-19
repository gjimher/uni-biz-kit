from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Context:
    concepts: List[Dict[str, Any]]
    concept_map: Dict[str, Any]
    security_config: Dict[str, Any]
    business_schema: Dict[str, Any]
    system_config: Dict[str, Any]
