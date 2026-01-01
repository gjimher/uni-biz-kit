"""
Command Line Interface Module

Provides the main CLI entry point for UniBizKit.
"""

import argparse
import logging
import sys
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
  unibizkit generate path/to/schema.json
  unibizkit generate path/to/schema.json --output-dir my-app
            """
        )
        
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Generate command
        generate_parser = subparsers.add_parser('generate', help='Generate a complete business application')
        generate_parser.add_argument(
            'schema_path',
            type=str,
            help='Path to the business schema JSON file'
        )
        generate_parser.add_argument(
            '--output-dir',
            type=str,
            default='generated-app',
            help='Output directory for generated files (default: generated-app)'
        )
        generate_parser.add_argument(
            '--skip-frontend',
            action='store_true',
            help='Skip React-Admin frontend generation'
        )
        generate_parser.add_argument(
            '--skip-backend',
            action='store_true',
            help='Skip Supabase backend generation'
        )
        
        # Validate command
        validate_parser = subparsers.add_parser('validate', help='Validate a business schema')
        validate_parser.add_argument(
            'schema_path',
            type=str,
            help='Path to the business schema JSON file'
        )
        
        return parser
    
    def run(self):
        """Run the CLI."""
        args = self.parser.parse_args()
        
        if not args.command:
            self.parser.print_help()
            sys.exit(1)
        
        try:
            if args.command == 'generate':
                self._handle_generate_command(args)
            elif args.command == 'validate':
                self._handle_validate_command(args)
            else:
                logger.error(f"Unknown command: {args.command}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Error: {e}")
            sys.exit(1)
    
    def _handle_generate_command(self, args):
        """Handle the generate command."""
        logger.info(f"Generating application from schema: {args.schema_path}")
        
        # Validate schema path
        schema_path = Path(args.schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {args.schema_path}")
        
        # Load and validate schema
        schema_loader = SchemaLoader(str(schema_path))
        business_schema = schema_loader.load_and_validate()
        
        logger.info(f"Schema validated successfully: {business_schema['name']}")
        
        # Create output directory
        output_dir = Path(args.output_dir)
        output_dir.mkdir(exist_ok=True)
        
        # Generate Supabase schema
        if not args.skip_backend:
            logger.info("Generating Supabase database schema...")
            supabase_generator = SupabaseGenerator(schema_loader)
            
            # Write SQL schema
            sql_schema = supabase_generator.generate_sql_schema()
            sql_file = output_dir / "supabase_schema.sql"
            with open(sql_file, 'w', encoding='utf-8') as f:
                f.write(sql_schema)
            
            # Write sample data
            sample_data = supabase_generator.generate_sample_data_sql()
            sample_data_file = output_dir / "supabase_sample_data.sql"
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
        logger.info(f"Validating schema: {args.schema_path}")
        
        # Validate schema path
        schema_path = Path(args.schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {args.schema_path}")
        
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