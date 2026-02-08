"""
Command Line Interface Module

Provides the main CLI entry point for UniBizKit.
"""

import argparse
import logging
import sys
import os
import json
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
        processor = SchemaProcessor(business_schema)
        extended_schema = processor.process()
        
        # Save Extended Schema (for debugging/verification)
        output_dir.mkdir(exist_ok=True)
        dump_path = output_dir / "concepts_extended.json"
        with open(dump_path, 'w', encoding='utf-8') as f:
            json.dump(extended_schema, f, indent=2)
        logger.info(f"Extended schema saved to: {dump_path}")

        # Pass the EXTENDED schema to generators
        schema_loader.business_schema = extended_schema
        schema_loader.concepts = extended_schema["concepts"]
        
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
        processor = SchemaProcessor(business_schema)
        extended_schema = processor.process()
        
        # Validate against Extended Schema Definition
        try:
            extended_schema_def_path = Path(__file__).parent.parent.parent / "schemas" / "concepts_extended_schema.json"
            if extended_schema_def_path.exists():
                import jsonschema
                from jsonschema.validators import validator_for
                from referencing import Registry, Resource
                
                # Load base schema for reference resolution
                base_schema_path = extended_schema_def_path.parent / "concepts_schema.json"
                with open(base_schema_path, 'r', encoding='utf-8') as f:
                    base_schema = json.load(f)
                
                # Load extended schema definition
                with open(extended_schema_def_path, 'r', encoding='utf-8') as f:
                    extended_schema_def = json.load(f)
                
                # Create Registry with base schema
                # referencing allows us to map the filename used in $ref to the schema content
                base_resource = Resource.from_contents(base_schema)
                registry = Registry().with_resource(uri="concepts_schema.json", resource=base_resource)
                
                # Validate
                ValidatorClass = validator_for(extended_schema_def)
                validator = ValidatorClass(extended_schema_def, registry=registry)
                validator.validate(extended_schema)
                
                logger.info("Enriched schema validation successful (compliant with concepts_extended_schema.json)")
            else:
                logger.warning(f"Extended schema definition not found at {extended_schema_def_path}, skipping validation.")
        except jsonschema.ValidationError as e:
            logger.error(f"Enriched schema validation failed: {e.message}")
            # We don't exit here to allow dumping for inspection
        except Exception as e:
            logger.error(f"Error during extended schema validation: {e}")

        # Dump extended schema to Output Directory
        # Ensure output directory exists (it might not if we are just validating)
        output_dir.mkdir(exist_ok=True)
        dump_path = output_dir / "concepts_extended.json"
        
        with open(dump_path, 'w', encoding='utf-8') as f:
            json.dump(extended_schema, f, indent=2)
            
        logger.info(f"Extended schema dumped to: {dump_path}")
        
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