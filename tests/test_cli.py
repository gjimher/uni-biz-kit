"""
Test CLI Functionality

Tests for the command line interface.
"""

import pytest
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from unibizkit.cli import CLI
from unibizkit.schema_loader import SchemaValidationError
import shutil

class TestCLI:
    """Test cases for CLI functionality."""
    
    def test_cli_help(self):
        """Test that CLI help is displayed correctly."""
        cli = CLI()
        
        with patch('sys.argv', ['unibizkit', '--help']):
            with pytest.raises(SystemExit) as exit_info:
                cli.run()
            assert exit_info.value.code == 0
    
    def test_cli_no_command(self):
        """Test that CLI exits with error when no command is provided."""
        cli = CLI()
        
        with patch('sys.argv', ['unibizkit']):
            with pytest.raises(SystemExit) as exit_info:
                cli.run()
            assert exit_info.value.code == 1
    
    def test_cli_validate_command_valid_schema(self):
        """Test validate command with valid schema."""
        cli = CLI()
        
        # Create a valid schema
        valid_schema = {
            "version": "1.0.0",
            "name": "Test App",
            "concepts": [
                {
                    "name": "TestConcept",
                    "fields": [
                        {
                            "name": "testField",
                            "type": "string",
                            "required": True
                        }
                    ]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_schema, f)
            temp_path = f.name
        
        try:
            with patch('sys.argv', ['unibizkit', 'validate', temp_path]):
                # Should not raise an exception
                cli.run()
        finally:
            os.unlink(temp_path)
    
    def test_cli_validate_command_invalid_schema(self):
        """Test validate command with invalid schema."""
        cli = CLI()
        
        # Create an invalid schema
        invalid_schema = {
            "name": "Test App",  # Missing version
            "concepts": []
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_schema, f)
            temp_path = f.name
        
        try:
            with patch('sys.argv', ['unibizkit', 'validate', temp_path]):
                with pytest.raises(SystemExit) as exit_info:
                    cli.run()
                assert exit_info.value.code == 1
        finally:
            os.unlink(temp_path)
    
    def test_cli_validate_command_nonexistent_file(self):
        """Test validate command with non-existent file."""
        cli = CLI()
        
        with patch('sys.argv', ['unibizkit', 'validate', 'nonexistent.json']):
            with pytest.raises(SystemExit) as exit_info:
                cli.run()
            assert exit_info.value.code == 1
    
    def test_cli_generate_command_valid_schema(self):
        """Test generate command with valid schema."""
        output_dir = Path('generated-app')
        shutil.rmtree(output_dir, ignore_errors=True)
        cli = CLI()
        
        # Create a valid schema
        valid_schema = {
            "version": "1.0.0",
            "name": "Test App",
            "concepts": [
                {
                    "name": "TestConcept",
                    "fields": [
                        {
                            "name": "testField",
                            "type": "string",
                            "required": True
                        }
                    ]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_schema, f)
            temp_path = f.name
        
        try:
            with patch('sys.argv', ['unibizkit', 'generate', temp_path]):
                # Should not raise an exception
                cli.run()
                
            # Check that output directory was created
            assert output_dir.exists()
            
            # Check that SQL files were generated
            assert (output_dir / 'backend' / 'supabase_schema.sql').exists()
            assert (output_dir / 'backend' / 'supabase_sample_data.sql').exists()
            
            # Check that frontend was generated
            assert (output_dir / 'frontend').exists()
            
            # Clean up
            shutil.rmtree(output_dir)
            
        finally:
            os.unlink(temp_path)
    
    def test_cli_generate_command_skip_options(self):
        """Test generate command with skip options."""
        output_dir = Path('generated-app')
        shutil.rmtree(output_dir, ignore_errors=True)
        cli = CLI()
        
        # Create a valid schema
        valid_schema = {
            "version": "1.0.0",
            "name": "Test App",
            "concepts": [
                {
                    "name": "TestConcept",
                    "fields": [
                        {
                            "name": "testField",
                            "type": "string",
                            "required": True
                        }
                    ]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_schema, f)
            temp_path = f.name
        
        try:
            # Test skip frontend
            with patch('sys.argv', ['unibizkit', 'generate', temp_path, '--skip-frontend']):
                cli.run()
                
            assert output_dir.exists()
            assert (output_dir / 'backend' / 'supabase_schema.sql').exists()
            assert not (output_dir / 'frontend').exists()
            
            # Clean up
            shutil.rmtree(output_dir)
            
            # Test skip backend
            with patch('sys.argv', ['unibizkit', 'generate', temp_path, '--skip-backend']):
                cli.run()
                
            assert output_dir.exists()
            assert not (output_dir / 'supabase_schema.sql').exists()
            assert (output_dir / 'frontend').exists()
                        
        finally:
            # Clean up
            os.unlink(temp_path)
    
    def test_cli_generate_command_custom_output_dir(self):
        """Test generate command with custom output directory."""
        cli = CLI()
        
        # Create a valid schema
        valid_schema = {
            "version": "1.0.0",
            "name": "Test App",
            "concepts": [
                {
                    "name": "TestConcept",
                    "fields": [
                        {
                            "name": "testField",
                            "type": "string",
                            "required": True
                        }
                    ]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_schema, f)
            temp_path = f.name
        
        try:
            custom_dir = 'my-custom-app'
            with patch('sys.argv', ['unibizkit', 'generate', temp_path, '--output-dir', custom_dir]):
                cli.run()
                
            output_dir = Path(custom_dir)
            assert output_dir.exists()
            assert (output_dir / 'backend' / 'supabase_schema.sql').exists()
            assert (output_dir / 'frontend').exists()
            
            # Clean up
            shutil.rmtree(output_dir)
            
        finally:
            os.unlink(temp_path)
    
    def test_cli_generate_command_invalid_schema(self):
        """Test generate command with invalid schema."""
        cli = CLI()
        
        # Create an invalid schema
        invalid_schema = {
            "name": "Test App",  # Missing version
            "concepts": []
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_schema, f)
            temp_path = f.name
        
        try:
            with patch('sys.argv', ['unibizkit', 'generate', temp_path]):
                with pytest.raises(SystemExit) as exit_info:
                    cli.run()
                assert exit_info.value.code == 1
        finally:
            os.unlink(temp_path)
    
    def test_cli_generate_command_nonexistent_file(self):
        """Test generate command with non-existent file."""
        cli = CLI()
        
        with patch('sys.argv', ['unibizkit', 'generate', 'nonexistent.json']):
            with pytest.raises(SystemExit) as exit_info:
                cli.run()
            assert exit_info.value.code == 1