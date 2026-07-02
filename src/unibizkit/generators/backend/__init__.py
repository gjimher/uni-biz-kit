import logging
from pathlib import Path
from .context import Context
from . import payments, rules, supabase_config_dev, supabase_schema, supabase_seed_data_dev

logger = logging.getLogger(__name__)


class SupabaseGenerator:
    def __init__(self, schema_loader):
        self.schema_loader = schema_loader
        concepts = schema_loader.get_all_concepts()
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
            validations_config=getattr(schema_loader, 'validations_config', None) or {"validations": []},
            model_dir=Path(schema_loader.schema_path).parent,
        )

    def generate_supabase_config(self) -> str:
        return supabase_config_dev.generate(self._ctx)

    def generate_sql_schema(self) -> str:
        return supabase_schema.generate(self._ctx)

    def generate_seed_data_dev_sql(self) -> str:
        return supabase_seed_data_dev.generate(self._ctx)

    def generate_supabase_rules(self) -> dict[str, dict[str, str]]:
        return rules.generate_supabase_rules(self._ctx)

    def generate_supabase_payments(self) -> dict[str, dict[str, str]]:
        return payments.generate_payment_function(self._ctx)
