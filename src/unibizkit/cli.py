"""
Command Line Interface Module

Provides the main CLI entry point for UniBizKit.
"""

import argparse
import logging
import sys
import os
from pathlib import Path
from .schema_loader import SchemaLoader, SchemaValidationError
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
            if args.task == 'generate':
                self._handle_generate_command(args)
            elif args.task == 'validate':
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
        
        logger.info(f"Schema validated successfully: {business_schema['name']}")
        
        # Create output directory
        output_dir.mkdir(exist_ok=True)
        
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
        
        # For validate, we don't strictly need output_dir, so we ignore the second return value
        # But we reuse the logic to find the schema file
        schema_path, _ = self._resolve_paths(args.input_path)
        
        logger.info(f"Validating schema: {schema_path}")
        
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        
        # Load and validate schema
        schema_loader = SchemaLoader(str(schema_path))
        business_schema = schema_loader.load_and_validate()
        
        logger.info(f"Schema is valid: {business_schema['name']}")
        logger.info(f"Version: {business_schema['version']}")
        logger.info(f"Number of concepts: {len(business_schema['concepts'])}")
        
        # List concepts
        for concept in business_schema['concepts']:
            logger.info(f"  - {concept['name']}: {len(concept['fields'])} fields")
            if 'relationships' in concept:
                logger.info(f"    Relationships: {len(concept['relationships'])}")

def main():
    """Main entry point."""
    cli = CLI()
    cli.run()

if __name__ == '__main__':
    main()