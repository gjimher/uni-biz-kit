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
from typing import Dict, Any
from pathlib import Path
from .schema_loader import SchemaLoader, SchemaValidationError
from .schema_processor import SchemaProcessor
from .supabase_generator import SupabaseGenerator
from .react_admin_generator import ReactAdminGenerator

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
            
            # Auto-generate required from keys
            if "required" not in base_field_items:
                base_field_items["required"] = []
            
            # Add all keys from extra properties to required
            base_field_items["required"].extend(extra_field_items["properties"].keys())
            base_field_items["required"] = list(set(base_field_items["required"]))

        # 1b. Merge Direct Concept Properties
        for key, value in extra_concept_props.items():
            if key == "fields":
                continue
            base_concept_props[key] = value

        # 2. Merge Concept Required (Auto-generate)
        if "required" not in base_concept_items:
             base_concept_items["required"] = []
        
        # Add all keys from extra properties (excluding fields as it is nested container) to required
        keys_to_require = [k for k in extra_concept_props.keys() if k != "fields"]
        base_concept_items["required"].extend(keys_to_require)
        base_concept_items["required"] = list(set(base_concept_items["required"]))
             
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
            schema_loader.presentation_config
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

        # Save Presentation Extended Schema (copy of the original)
        pres_schema_dump_path = output_dir / "presentation_extended_schema.json"
        with open(pres_schema_dump_path, 'w', encoding='utf-8') as f:
            json.dump(schema_loader.presentation_validation_schema, f, indent=2)
        logger.info(f"Presentation extended schema saved to: {pres_schema_dump_path}")

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

        # Pass the EXTENDED schema to generators
        schema_loader.business_schema = extended_schema
        schema_loader.concepts = extended_schema["concepts"]
        schema_loader.security_config = processor.security_extended
        
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
            
            # Write sample data
            sample_data = supabase_generator.generate_sample_data_sql()
            sample_data_file = backend_dir / "supabase_sample_data.sql"
            with open(sample_data_file, 'w', encoding='utf-8') as f:
                f.write(sample_data)

            logger.info(f"Supabase schema generated: {sql_file}")
            logger.info(f"Sample data generated: {sample_data_file}")
        
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
            schema_loader.presentation_config
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

        # Save Presentation Extended Schema (copy of the original)
        pres_schema_dump_path = output_dir / "presentation_extended_schema.json"
        with open(pres_schema_dump_path, 'w', encoding='utf-8') as f:
            json.dump(schema_loader.presentation_validation_schema, f, indent=2)
        logger.info(f"Presentation extended schema saved to: {pres_schema_dump_path}")

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