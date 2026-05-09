"""
Command Line Interface Module

Provides the main CLI entry point for UniBizKit.
"""

import argparse
import logging
import sys
import os
import json
import copy
import shutil
from typing import Dict, Any
from pathlib import Path
from .schema_loader import SchemaLoader, SchemaValidationError
from .schema_processor import SchemaProcessor
from .supabase_generator import SupabaseGenerator
from .react_admin_generator import ReactAdminGenerator
from .generators.bin import generate as generate_bin_scripts

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CLI:
    def __init__(self):
        """Initialize the CLI."""
        self.parser = self._create_parser()
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser."""
        parser = argparse.ArgumentParser(
            description='UniBizKit - Business Application Generator',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  uni-biz-kit models/my-app
  uni-biz-kit --task validate models/my-app
            """
        )
        
        parser.add_argument(
            'input_path',
            type=str,
            nargs='?',
            help='Path to the model directory (containing concepts.json). Defaults to the single folder in models/ if not provided.'
        )

        parser.add_argument(
            '--task',
            type=str,
            default='generate',
            choices=['generate', 'validate'],
            help='Task to perform (default: generate)'
        )

        parser.add_argument(
            '--output-dir',
            type=str,
            help='Output directory for generated files (default: current directory + input directory name)'
        )
        parser.add_argument(
            '--skip-frontend',
            action='store_true',
            help='Skip React-Admin frontend generation'
        )
        parser.add_argument(
            '--skip-backend',
            action='store_true',
            help='Skip Supabase backend generation'
        )
        
        return parser
    
    def run(self):
        """Run the CLI."""
        args = self.parser.parse_args()
        
        try:
            if args.task == "generate":
                self._handle_generate_command(args)
            elif args.task == "validate":
                self._handle_validate_command(args)
            else:
                logger.error(f"Unknown task: {args.task}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Error: {e}")
            sys.exit(1)
    
    def _resolve_paths(self, input_path_arg: str, output_dir_arg: str = None):
        """
        Resolve input and output paths based on arguments and defaults.
        
        Returns:
            Tuple of (schema_file_path, output_dir_path)
        """
        # Determine Input Directory
        if input_path_arg:
            input_dir = Path(input_path_arg)
        else:
            # Try to auto-discover in 'models/'
            models_dir = Path('models')
            if not models_dir.exists():
                 raise FileNotFoundError(f"No input path provided and 'models' directory not found.")
            
            subdirs = [d for d in models_dir.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                input_dir = subdirs[0]
                logger.info(f"Auto-detected model directory: {input_dir}")
            else:
                raise ValueError(
                    f"Ambiguous input. 'models/' contains {len(subdirs)} directories. "
                    "Please specify the input directory explicitly."
                )

        if not input_dir.exists():
             raise FileNotFoundError(f"Input directory not found: {input_dir}")

        # Determine Schema File Path
        schema_path = input_dir / "concepts.json"
        
        # Determine Output Directory
        if output_dir_arg:
            output_dir = Path(output_dir_arg)
        else:
            # Default to current working directory + input directory name
            output_dir = Path.cwd() / input_dir.name
            
        return schema_path, output_dir

    def _generate_concepts_extended_schema_def(self, output_dir: Path) -> Dict[str, Any]:
        """
        Dynamically generate the full extended schema definition by merging
        concepts_schema.json and concepts_extended_required_additions.json.
        """
        schemas_dir = Path(__file__).parent.parent.parent / "schemas"
        base_schema_path = schemas_dir / "concepts_schema.json"
        additions_path = schemas_dir / "concepts_extended_required_additions.json"
        
        with open(base_schema_path, 'r', encoding='utf-8') as f:
            base_schema = json.load(f)
            
        with open(additions_path, 'r', encoding='utf-8') as f:
            additions = json.load(f)
            
        # Explicit merge of known structure
        
        # 1. Merge Concept Properties
        base_concept_items = base_schema["properties"]["concepts"]["items"]
        extra_concept_items = additions["properties"]["concepts"]["items"]
        
        base_concept_props = base_concept_items["properties"]
        extra_concept_props = extra_concept_items["properties"]
        
        # 1a. Merge Field Properties (Nested)
        if "fields" in extra_concept_props:
            base_field_items = base_concept_props["fields"]["items"]
            extra_field_items = extra_concept_props["fields"]["items"]

            # Merge properties
            base_field_items["properties"].update(extra_field_items["properties"])

            # Auto-generate required from keys, respecting optional_properties
            if "required" not in base_field_items:
                base_field_items["required"] = []

            optional_field_keys = set(extra_field_items.get("optional_properties", []))
            required_field_keys = [k for k in extra_field_items["properties"].keys() if k not in optional_field_keys]
            base_field_items["required"].extend(required_field_keys)
            base_field_items["required"] = list(set(base_field_items["required"]))

        # 1b. Merge Direct Concept Properties
        for key, value in extra_concept_props.items():
            if key in ("fields", "optional_properties"):
                continue
            base_concept_props[key] = value

        # Add _concept_workflow to root
        base_schema["properties"]["_concept_workflow"] = {
            "type": "object",
            "description": "Mapping of concept names to their workflow configurations"
        }

        # 2. Merge Concept Required (Auto-generate)
        if "required" not in base_concept_items:
             base_concept_items["required"] = []

        # Add all keys from extra properties (excluding fields as it is nested container) to required
        # _workflow is optional; keys in optional_properties are also excluded from required
        optional_concept_keys = set(extra_concept_items.get("optional_properties", []))
        keys_to_require = [k for k in extra_concept_props.keys() if k not in ("fields", "_workflow", "optional_properties") and k not in optional_concept_keys]
        base_concept_items["required"].extend(keys_to_require)
        base_concept_items["required"] = list(set(base_concept_items["required"]))
             
        # In the extended schema, documents.tags is not required: the enrichment process
        # injects documents with enabled/versioned defaults on all concepts, even those
        # that didn't originally configure documents (so tags may be absent for disabled docs).
        docs_def = base_concept_props.get("documents")
        if docs_def and "required" in docs_def:
            docs_def["required"] = [r for r in docs_def["required"] if r != "tags"]
            if not docs_def["required"]:
                del docs_def["required"]

        # Update metadata
        base_schema["title"] = "Extended Business Application Schema"
        base_schema["description"] = "Dynamically generated extended schema."
        
        # Allow $schema property in the extended schema
        base_schema["properties"]["$schema"] = { "type": "string", "description": "Schema definition reference" }
        
        # Save to output dir for reference/debug
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "concepts_extended_schema.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(base_schema, f, indent=2)
            
        return base_schema

    def _validate_extended_schema(self, data: Dict[str, Any], schema_def: Dict[str, Any], label: str):
        """Validate enriched data against a dynamically generated extended schema."""
        import jsonschema
        from jsonschema.validators import validator_for
        
        try:
            # Validate
            ValidatorClass = validator_for(schema_def)
            validator = ValidatorClass(schema_def)
            validator.validate(data)
            
            logger.info(f"Enriched {label} validation successful")
        except jsonschema.ValidationError as e:
            error_msg = f"Enriched {label} validation failed: {e.message}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)
        except Exception as e:
            error_msg = f"Error during extended {label} validation: {e}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)

    def _generate_security_extended_schema_def(self, output_dir: Path) -> Dict[str, Any]:
        """
        Dynamically generate the full extended security schema definition by merging
        security_schema.json and security_extended_required_additions.json.
        """
        schemas_dir = Path(__file__).parent.parent.parent / "schemas"
        base_schema_path = schemas_dir / "security_schema.json"
        additions_path = schemas_dir / "security_extended_required_additions.json"
        
        with open(base_schema_path, 'r', encoding='utf-8') as f:
            base_schema = json.load(f)
            
        with open(additions_path, 'r', encoding='utf-8') as f:
            additions = json.load(f)
            
        # Merge Properties
        if "properties" in additions:
            base_schema["properties"].update(additions["properties"])
            
        # Merge Required
        if "required" in additions:
            if "required" not in base_schema:
                base_schema["required"] = []
            base_schema["required"].extend(additions["required"])
            base_schema["required"] = list(set(base_schema["required"]))

        # Update metadata
        base_schema["title"] = "Extended Security Schema"
        base_schema["description"] = "Dynamically generated extended security schema."
        
        # Save to output dir for reference/debug
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "security_extended_schema.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(base_schema, f, indent=2)
            
        return base_schema

    def _generate_presentation_extended_schema_def(self, output_dir: Path) -> Dict[str, Any]:
        """
        Dynamically generate the full extended presentation schema definition by merging
        presentation_schema.json and presentation_extended_required_additions.json.
        """
        schemas_dir = Path(__file__).parent.parent.parent / "schemas"
        base_schema_path = schemas_dir / "presentation_schema.json"
        additions_path = schemas_dir / "presentation_extended_required_additions.json"

        with open(base_schema_path, 'r', encoding='utf-8') as f:
            base_schema = json.load(f)

        if additions_path.exists():
            with open(additions_path, 'r', encoding='utf-8') as f:
                additions = json.load(f)

            # Merge Properties
            if "properties" in additions:
                base_schema["properties"].update(additions["properties"])

            # Merge Required
            if "required" in additions:
                if "required" not in base_schema:
                    base_schema["required"] = []
                base_schema["required"].extend(additions["required"])
                base_schema["required"] = list(set(base_schema["required"]))

        # Update metadata
        base_schema["title"] = "Extended Presentation Schema"
        base_schema["description"] = "Dynamically generated extended presentation schema."

        # Save to output dir for reference/debug
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "presentation_extended_schema.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(base_schema, f, indent=2)

        return base_schema

    def _generate_workflow_extended_schema_def(self, output_dir: Path) -> Dict[str, Any]:
        """
        Dynamically generate the full extended workflow schema definition.
        """
        schemas_dir = Path(__file__).parent.parent.parent / "schemas"
        base_schema_path = schemas_dir / "workflow_schema.json"
        
        with open(base_schema_path, 'r', encoding='utf-8') as f:
            base_schema = json.load(f)
            
        # Update metadata
        base_schema["title"] = "Extended Workflow Schema"
        base_schema["description"] = "Dynamically generated extended workflow schema."
        
        # Save to output dir for reference/debug
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "workflow_extended_schema.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(base_schema, f, indent=2)
            
        return base_schema

    def _generate_system_extended_schema_def(self, output_dir: Path) -> Dict[str, Any]:
        """
        Dynamically generate the full extended system schema definition by merging
        system_schema.json and system_extended_required_additions.json.
        """
        schemas_dir = Path(__file__).parent.parent.parent / "schemas"
        base_schema_path = schemas_dir / "system_schema.json"
        additions_path = schemas_dir / "system_extended_required_additions.json"

        with open(base_schema_path, 'r', encoding='utf-8') as f:
            base_schema = json.load(f)

        if additions_path.exists():
            with open(additions_path, 'r', encoding='utf-8') as f:
                additions = json.load(f)

            if "properties" in additions:
                base_schema["properties"].update(additions["properties"])

            if "required" in additions:
                if "required" not in base_schema:
                    base_schema["required"] = []
                base_schema["required"].extend(additions["required"])
                base_schema["required"] = list(set(base_schema["required"]))

        base_schema["title"] = "Extended System Schema"
        base_schema["description"] = "Dynamically generated extended system schema."

        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "system_extended_schema.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(base_schema, f, indent=2)

        return base_schema

    def _handle_generate_command(self, args):
        """Handle the generate command."""
        
        schema_path, output_dir = self._resolve_paths(args.input_path, args.output_dir)
        
        logger.info(f"Generating application from schema: {schema_path}")
        
        # Validate schema path existence
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        
        # Load and validate schema
        schema_loader = SchemaLoader(str(schema_path))
        business_schema = schema_loader.load_and_validate()
        
        # Enrich Schema (Intermediate Representation)
        logger.info("Enriching schema with internal metadata...")
        processor = SchemaProcessor(
            business_schema,
            schema_loader.security_config,
            schema_loader.presentation_config,
            schema_loader.workflow_config,
            schema_loader.system_config
        )
        extended_schema = processor.process()

        # Validate Extended Schema
        extended_concepts_schema_def = self._generate_concepts_extended_schema_def(output_dir)
        self._validate_extended_schema(extended_schema, extended_concepts_schema_def, "concepts")
        
        # Save Extended Schema (for debugging/verification)
        output_dir.mkdir(exist_ok=True)
        dump_path = output_dir / "concepts_extended.json"
        
        # Inject $schema for VSCode intellisense (at the top)
        new_schema = {"$schema": "./concepts_extended_schema.json"}
        # Remove original $schema if present to avoid overwriting our new link
        if "$schema" in extended_schema:
            del extended_schema["$schema"]
        new_schema.update(extended_schema)
        
        with open(dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_schema, f, indent=2)
        logger.info(f"Extended schema saved to: {dump_path}")

        # Save Workflow Extended
        wf_dump_path = output_dir / "workflow_extended.json"
        # Inject $schema for VSCode
        new_wf_config = {"$schema": "./workflow_extended_schema.json"}
        # Remove original $schema if present to avoid overwriting our new link
        wf_config_copy = processor.workflow_extended.copy()
        if "$schema" in wf_config_copy:
            del wf_config_copy["$schema"]
        # Maintain renamed 'workflow_rules'
        new_wf_config.update(wf_config_copy)

        with open(wf_dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_wf_config, f, indent=2)
        logger.info(f"Workflow extended saved to: {wf_dump_path}")

        # Validate Workflow Extended (generates the extended schema file)
        extended_workflow_schema_def = self._generate_workflow_extended_schema_def(output_dir)
        self._validate_extended_schema(new_wf_config, extended_workflow_schema_def, "workflow")

        # Save Presentation Extended
        pres_dump_path = output_dir / "presentation_extended.json"
        # Inject $schema for VSCode
        new_pres_config = {"$schema": "./presentation_extended_schema.json"}
        # Remove original $schema if present to avoid overwriting our new link
        pres_config_copy = processor.presentation_extended.copy()
        if "$schema" in pres_config_copy:
            del pres_config_copy["$schema"]
        new_pres_config.update(pres_config_copy)

        with open(pres_dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_pres_config, f, indent=2)
        logger.info(f"Presentation extended saved to: {pres_dump_path}")

        # Validate Presentation Extended (this also generates the extended schema file)
        extended_presentation_schema_def = self._generate_presentation_extended_schema_def(output_dir)
        self._validate_extended_schema(new_pres_config, extended_presentation_schema_def, "presentation")

        # Update loader with enriched configs for generators
        schema_loader.presentation_config = processor.presentation_extended

        # Save Security Extended
        sec_dump_path = output_dir / "security_extended.json"
        # Inject $schema for VSCode
        new_sec_config = {"$schema": "./security_extended_schema.json"}
        # Remove original $schema if present to avoid overwriting our new link
        sec_config_copy = processor.security_extended.copy()
        if "$schema" in sec_config_copy:
            del sec_config_copy["$schema"]
        new_sec_config.update(sec_config_copy)

        # Validate Security Extended (this also generates the extended schema file)
        extended_security_schema_def = self._generate_security_extended_schema_def(output_dir)
        self._validate_extended_schema(new_sec_config, extended_security_schema_def, "security")

        with open(sec_dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_sec_config, f, indent=2)
        logger.info(f"Security extended saved to: {sec_dump_path}")

        # Save System Extended
        sys_dump_path = output_dir / "system_extended.json"
        new_sys_config = {"$schema": "./system_extended_schema.json"}
        sys_config_copy = processor.system_extended.copy()
        if "$schema" in sys_config_copy:
            del sys_config_copy["$schema"]
        new_sys_config.update(sys_config_copy)

        # Validate System Extended (this also generates the extended schema file)
        extended_system_schema_def = self._generate_system_extended_schema_def(output_dir)
        self._validate_extended_schema(new_sys_config, extended_system_schema_def, "system")

        with open(sys_dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_sys_config, f, indent=2)
        logger.info(f"System extended saved to: {sys_dump_path}")

        # Pass the EXTENDED schema to generators
        schema_loader.business_schema = extended_schema
        schema_loader.concepts = extended_schema["concepts"]
        schema_loader.security_config = processor.security_extended
        schema_loader.system_config = processor.system_extended

        seed_dump_path = output_dir / "seed_data_extended.json"
        with open(seed_dump_path, 'w', encoding='utf-8') as f:
            json.dump(schema_loader.seed_data_config, f, indent=2)
        logger.info(f"Seed data saved to: {seed_dump_path}")
        legacy_initial_dump_path = output_dir / "initial_data_extended.json"
        if legacy_initial_dump_path.exists():
            legacy_initial_dump_path.unlink()

        # Generate Supabase schema
        if not args.skip_backend:
            logger.info("Generating Supabase database schema...")
            supabase_generator = SupabaseGenerator(schema_loader)

            backend_dir = output_dir / "backend"
            backend_dir.mkdir(exist_ok=True)
            
            # Write SQL schema
            sql_schema = supabase_generator.generate_sql_schema()
            sql_file =  backend_dir / "supabase_schema.sql"
            with open(sql_file, 'w', encoding='utf-8') as f:
                f.write(sql_schema)
            
            # Write development seed data
            seed_data_dev = supabase_generator.generate_seed_data_dev_sql()
            seed_data_dev_file = backend_dir / "supabase_seed_data_dev.sql"
            with open(seed_data_dev_file, 'w', encoding='utf-8') as f:
                f.write(seed_data_dev)
            legacy_sample_data_file = backend_dir / "supabase_sample_data.sql"
            if legacy_sample_data_file.exists():
                legacy_sample_data_file.unlink()

            # Write dev Supabase config (complete config.toml for local dev)
            supabase_config = supabase_generator.generate_supabase_config()
            supabase_config_file = backend_dir / "supabase_config_dev.toml"
            with open(supabase_config_file, 'w', encoding='utf-8') as f:
                f.write(supabase_config)

            # Write Supabase Edge Functions for FEEL business rules.
            supabase_rules = supabase_generator.generate_supabase_rules()
            rules_dir = backend_dir / "supabase" / "functions"
            if rules_dir.exists():
                for item in rules_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            else:
                rules_dir.mkdir(parents=True, exist_ok=True)
            if supabase_rules:
                for function_name, files in supabase_rules.items():
                    function_dir = rules_dir / function_name
                    function_dir.mkdir(parents=True, exist_ok=True)
                    for filename, content in files.items():
                        with open(function_dir / filename, 'w', encoding='utf-8') as f:
                            f.write(content)

            logger.info(f"Supabase schema generated: {sql_file}")
            logger.info(f"Development seed data generated: {seed_data_dev_file}")
            logger.info(f"Supabase dev config generated: {supabase_config_file}")

            # Generate bin/ scripts
            bin_dir = output_dir / "bin"
            bin_dir.mkdir(exist_ok=True)
            generate_bin_scripts(bin_dir, schema_loader.security_config)
        
        # Generate React-Admin frontend
        if not args.skip_frontend:
            logger.info("Generating React-Admin frontend...")
            react_admin_generator = ReactAdminGenerator(schema_loader, str(output_dir / "frontend"))
            react_admin_generator.generate_frontend()
            logger.info("React-Admin frontend generated")
        
        logger.info(f"Application generation completed. Output directory: {output_dir}")
    
    def _handle_validate_command(self, args):
        """Handle the validate command."""
        
        schema_path, output_dir = self._resolve_paths(args.input_path, args.output_dir)
        
        logger.info(f"Validating schema: {schema_path}")
        
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        
        # Load and validate schema
        schema_loader = SchemaLoader(str(schema_path))
        business_schema = schema_loader.load_and_validate()
        
        logger.info(f"Schema is valid: {business_schema["name"]}")
        
        # Enrich Schema to test processor
        logger.info("Enriching schema to verify processor logic...")
        processor = SchemaProcessor(
            business_schema,
            schema_loader.security_config,
            schema_loader.presentation_config,
            schema_loader.workflow_config,
            schema_loader.system_config
        )
        extended_schema = processor.process()
        
        # Validate against Extended Schema Definition
        extended_concepts_schema_def = self._generate_concepts_extended_schema_def(output_dir)
        self._validate_extended_schema(extended_schema, extended_concepts_schema_def, "concepts")

        # Dump extended schema to Output Directory
        # Ensure output directory exists (it might not if we are just validating)
        output_dir.mkdir(exist_ok=True)
        dump_path = output_dir / "concepts_extended.json"
        
        # Inject $schema for VSCode intellisense (at the top)
        new_schema = {"$schema": "./concepts_extended_schema.json"}
        # Remove original $schema if present to avoid overwriting our new link
        if "$schema" in extended_schema:
            del extended_schema["$schema"]
        new_schema.update(extended_schema)
        
        with open(dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_schema, f, indent=2)
            
        logger.info(f"Extended schema dumped to: {dump_path}")

        # Save Workflow Extended
        wf_dump_path = output_dir / "workflow_extended.json"
        # Inject $schema for VSCode
        new_wf_config = {"$schema": "./workflow_extended_schema.json"}
        # Remove original $schema if present to avoid overwriting our new link
        wf_config_copy = processor.workflow_extended.copy()
        if "$schema" in wf_config_copy:
            del wf_config_copy["$schema"]
        # Maintain renamed 'workflow_rules'
        new_wf_config.update(wf_config_copy)

        with open(wf_dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_wf_config, f, indent=2)
        logger.info(f"Workflow extended saved to: {wf_dump_path}")

        # Validate Workflow Extended (generates the extended schema file)
        extended_workflow_schema_def = self._generate_workflow_extended_schema_def(output_dir)
        self._validate_extended_schema(new_wf_config, extended_workflow_schema_def, "workflow")

        # Save Presentation Extended
        pres_dump_path = output_dir / "presentation_extended.json"
        # Inject $schema for VSCode
        new_pres_config = {"$schema": "./presentation_extended_schema.json"}
        # Remove original $schema if present to avoid overwriting our new link
        pres_config_copy = processor.presentation_extended.copy()
        if "$schema" in pres_config_copy:
            del pres_config_copy["$schema"]
        new_pres_config.update(pres_config_copy)

        with open(pres_dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_pres_config, f, indent=2)
        logger.info(f"Presentation extended saved to: {pres_dump_path}")

        # Validate Presentation Extended (this also generates the extended schema file)
        extended_presentation_schema_def = self._generate_presentation_extended_schema_def(output_dir)
        self._validate_extended_schema(new_pres_config, extended_presentation_schema_def, "presentation")

        # Update loader with enriched configs for generators
        schema_loader.presentation_config = processor.presentation_extended

        # Save Security Extended
        sec_dump_path = output_dir / "security_extended.json"
        # Inject $schema for VSCode
        new_sec_config = {"$schema": "./security_extended_schema.json"}
        # Remove original $schema if present to avoid overwriting our new link
        sec_config_copy = processor.security_extended.copy()
        if "$schema" in sec_config_copy:
            del sec_config_copy["$schema"]
        new_sec_config.update(sec_config_copy)

        # Validate Security Extended (this also generates the extended schema file)
        extended_security_schema_def = self._generate_security_extended_schema_def(output_dir)
        self._validate_extended_schema(new_sec_config, extended_security_schema_def, "security")

        with open(sec_dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_sec_config, f, indent=2)
        logger.info(f"Security extended saved to: {sec_dump_path}")

        # Save System Extended
        sys_dump_path = output_dir / "system_extended.json"
        new_sys_config = {"$schema": "./system_extended_schema.json"}
        sys_config_copy = processor.system_extended.copy()
        if "$schema" in sys_config_copy:
            del sys_config_copy["$schema"]
        new_sys_config.update(sys_config_copy)

        extended_system_schema_def = self._generate_system_extended_schema_def(output_dir)
        self._validate_extended_schema(new_sys_config, extended_system_schema_def, "system")

        with open(sys_dump_path, 'w', encoding='utf-8') as f:
            json.dump(new_sys_config, f, indent=2)
        logger.info(f"System extended saved to: {sys_dump_path}")

        logger.info(f"Version: {business_schema["version"]}")
        logger.info(f"Number of concepts: {len(business_schema["concepts"])}")
        
        # List concepts with enriched type
        for concept in extended_schema["concepts"]:
            c_type = concept["_type"]
            logger.info(f"  - {concept["name"]} [{c_type}]: {len(concept["fields"])} fields")
        
        logger.info(f"Version: {business_schema["version"]}")
        logger.info(f"Number of concepts: {len(business_schema["concepts"])}")
        
        # List concepts with enriched type
        for concept in extended_schema["concepts"]:
            c_type = concept["_type"]
            logger.info(f"  - {concept["name"]} [{c_type}]: {len(concept["fields"])} fields")

def main():
    """Main entry point."""
    cli = CLI()
    cli.run()

if __name__ == "__main__":
    main()
