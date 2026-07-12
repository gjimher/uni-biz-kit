import json

from ..context import Context


def generate(ctx: Context) -> str:
    """Concept-to-workflow map shared by the workflow task pages."""
    workflows_json = json.dumps(ctx.workflow_config["_concept_workflow"], indent=2)
    return f"""// Workflow configuration per concept (generated from workflow.jsonc).
export const CONCEPT_WORKFLOWS = {workflows_json};
"""
