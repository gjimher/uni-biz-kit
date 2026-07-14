import logging
from pathlib import Path
from .context import Context
from . import backend_functions, deployed_data, integrations, payments, rules, supabase_config_dev, supabase_schema, supabase_seed_data_dev

logger = logging.getLogger(__name__)


class SupabaseGenerator:
    def __init__(self, schema_loader):
        self.schema_loader = schema_loader
        concepts = schema_loader.get_all_concepts()
        integration_targets = {
            item["target_concept"]
            for item in (getattr(schema_loader, "integrations_config", None) or {"integrations": []})["integrations"]
        }
        for concept in concepts:
            concept["_integration_target"] = concept["name"] in integration_targets
        self._ctx = Context(
            concepts=concepts,
            concept_map={c["name"]: c for c in concepts},
            security_config=schema_loader.security_config,
            business_schema=schema_loader.business_schema,
            workflow_config=schema_loader.workflow_config,
            system_config=getattr(schema_loader, 'system_config', None) or {},
            deployment_config=getattr(schema_loader, 'deployment_config', None) or {},
            seed_data_config=getattr(schema_loader, 'seed_data_config', None) or {"include_test_data": True, "records": {}},
            rules_config=getattr(schema_loader, 'rules_config', None) or {"rules": []},
            integrations_config=getattr(schema_loader, 'integrations_config', None) or {"roles": ["admin"], "integrations": []},
            validations_config=getattr(schema_loader, 'validations_config', None) or {"validations": []},
            deployed_data_config=getattr(schema_loader, 'deployed_data_config', None) or {"concepts": []},
            model_dir=Path(schema_loader.schema_path).parent,
        )

    def generate_supabase_config(self) -> str:
        return supabase_config_dev.generate(self._ctx)

    def generate_sql_schema(self) -> str:
        return supabase_schema.generate(self._ctx)

    def generate_seed_data_dev_sql(self) -> str:
        return supabase_seed_data_dev.generate(self._ctx)

    def generate_deployed_data_runtime(self) -> str:
        return deployed_data.runtime_source()

    def generate_supabase_rules(self) -> dict[str, dict[str, str]]:
        return rules.generate_supabase_rules(self._ctx)

    def generate_supabase_payments(self) -> dict[str, dict[str, str]]:
        return payments.generate_payment_function(self._ctx)

    def generate_supabase_integrations(self) -> dict[str, dict[str, str]]:
        return integrations.generate_integration_function(self._ctx)

    def generate_backend_actions(self) -> dict[str, dict[str, str]]:
        return backend_functions.generate_backend_actions(self._ctx)
