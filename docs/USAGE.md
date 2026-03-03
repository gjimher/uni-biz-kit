# UniBizKit - Business Application Generator

UniBizKit is a proof of concept for generating complete business applications from JSON definitions. It generates both Supabase (PostgreSQL) database schemas and React-Admin frontend applications.

## Table of Contents

- [Installation](#installation)
- [JSON Schema Format](#json-schema-format)
- [CLI Usage](#cli-usage)
- [Examples](#examples)
- [Generated Output](#generated-output)
- [Running the Generated Application](#running-the-generated-application)
  - [Option 1: Using Docker with Supabase (Recommended)](#option-1-using-docker-with-supabase-recommended)
  - [Option 2: Using PostgreSQL Directly](#option-2-using-postgresql-directly)
- [Testing](#testing)
- [Architecture](#architecture)

## Installation

### Prerequisites

- Python 3.8+
- Node.js (for running the generated React-Admin application)
- PostgreSQL (for running the generated Supabase schema)

### Install UniBizKit

```bash
# Clone the repository
git clone https://github.com/unibizkit/unibizkit.git
cd unibizkit

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Linux/Mac
# venv\Scripts\activate  # On Windows

# Install dependencies
pip install -e .
```

## JSON Schema Format

UniBizKit uses a JSON schema to define business concepts, their fields, and relationships.

### Basic Structure

```json
{
  "version": "1.0.0",
  "name": "My Business Application",
  "description": "Description of the application",
  "concepts": [
    {
      "name": "ConceptName",
      "pluralName": "ConceptNames",
      "description": "Description of the concept",
      "fields": [],
      "relationships": []
    }
  ]
}
```

### Field Types

Supported field types:

- `string`: Text fields
- `integer`: Whole numbers
- `decimal`: Decimal numbers (with precision and scale)
- `boolean`: True/false values
- `date`: Date values
- `datetime`: Date and time values
- `enum`: Enumerated values with explicit allowed values

### Field Properties

```json
{
  "name": "fieldName",
  "type": "string",
  "required": true,
  "unique": true,
  "default": "default value",
  "minLength": 2,
  "maxLength": 100,
  "min": 0,
  "max": 100,
  "precision": 10,
  "scale": 2,
  "enumValues": ["value1", "value2"],
  "description": "Field description"
}
```

### Relationship Types

- `belongs-to`: One-to-one or many-to-one relationship (foreign key)
- `one-to-many`: One-to-many relationship (inverse of belongs-to)
- `many-to-many`: Many-to-many relationship (creates join table)

### Relationship Properties

```json
{
  "type": "belongs-to",
  "target": "TargetConcept",
  "fieldName": "targetField",
  "targetFieldName": "inverseField",
  "ownership": true,
  "required": true
}
```

## CLI Usage

### Validate a Schema

```bash
uni-biz-kit --task validate path/to/model_dir
```

### Generate a Complete Application

```bash
uni-biz-kit path/to/model_dir
```

### Generate with Custom Output Directory

```bash
uni-biz-kit path/to/model_dir --output-dir my-app
```

### Skip Frontend Generation

```bash
uni-biz-kit path/to/model_dir --skip-frontend
```

### Skip Backend Generation

```bash
uni-biz-kit path/to/model_dir --skip-backend
```

## Examples

### ECommerce Schema

The repository includes a complete e-commerce example in `models/test-app` that demonstrates:

- Products with various field types
- Categories with hierarchical relationships
- Customers with contact information
- Orders with status tracking
- Order items with product relationships
- Many-to-many relationships between products and categories

### Simple CRM Schema

Here's a simple CRM example:

```json
{
  "version": "1.0.0",
  "name": "Simple CRM",
  "concepts": [
    {
      "name": "Contact",
      "fields": [
        {"name": "firstName", "type": "string", "required": true},
        {"name": "lastName", "type": "string", "required": true},
        {"name": "email", "type": "string", "required": true, "unique": true},
        {"name": "phone", "type": "string"},
        {"name": "company", "type": "string"},
        {"name": "status", "type": "enum", "enumValues": ["lead", "customer", "inactive"], "default": "lead"}
      ]
    },
    {
      "name": "Deal",
      "fields": [
        {"name": "name", "type": "string", "required": true},
        {"name": "amount", "type": "decimal", "precision": 10, "scale": 2},
        {"name": "stage", "type": "enum", "enumValues": ["proposal", "negotiation", "closed-won", "closed-lost"], "default": "proposal"},
        {"name": "closeDate", "type": "date"}
      ],
      "relationships": [
        {
          "type": "belongs-to",
          "target": "Contact",
          "fieldName": "contact",
          "required": true
        }
      ]
    }
  ]
}
```

## Generated Output

When you run the generate command, UniBizKit creates:

```
my-app/
├── backend/
│   ├── supabase_schema.sql          # PostgreSQL database schema
│   └── supabase_sample_data.sql    # Sample data for testing
└── frontend/                   # React-Admin frontend application
    ├── package.json
    ├── public/
    ├── src/
    │   ├── App.js
    │   ├── dataProvider.js
    │   ├── index.js
    │   ├── resources/           # One directory per concept
    │   │   └── product/
    │   │       └── product.js
    │   ├── components/
    │   ├── utils/
    │   └── layout/
    └── ...
```

### Database Schema Features

- Tables for each concept with proper field types
- Primary keys and auto-incrementing IDs
- Unique constraints for unique fields
- Enum constraints for enum fields
- Foreign key constraints for relationships
- Join tables for many-to-many relationships
- Timestamps (_created_at, _updated_at)
- Sample data for testing

### React-Admin Frontend Features

- Complete Create-Read-Update-Delete (CRUD) interface
- List, Create, Edit, and Show views for each concept
- Proper field components based on field types
- Relationship handling in the UI
- Form validation for required fields
- Supabase data provider configuration
- Ready-to-run React application

## Running the Generated Application

### Install Docker

Install Docker and Docker Compose.
For example, on Ubuntu 22.04, run the following commands to install Docker, add your user to the Docker group, and reboot the system:
```bash
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
sudo init 6
docker --version # example output: 28.2.2
```

### Install Nvm, Npm and Supabase

```bash
# nvm https://github.com/nvm-sh/nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm --version # 0.40.3
nvm install --lts --default 24.11.0 
npm --version # 11.6.1

# supabase https://supabase.com/docs/guides/local-development/cli/getting-started
nvm use node
# npx checks for latest version in every execution
npx -y supabase --version # example output: 2.70.5
```

### Generate the e-commerce application

```bash
uni-biz-kit models/test-app --output-dir test-app
```

### configure supabase instance

Create a supabase instance for the application:
```bash
cd test-app/backend

# clean previous instance: npx supabase stop --no-backup
npx supabase init
# set project_id to parent directory name (replace "backend" with parent dir name)
sed -i "s/project_id = \"backend\"/project_id = \"$(basename $(dirname $(pwd)))\"/" supabase/config.toml
npx supabase start
npx supabase status -o json # view urls and keys
# view containter logs: docker ps --format '{{.Names}}' | grep '^supabase_' | xargs -I {} docker logs -f {} 

# save api key
cat > ../frontend/.env << EOF
REACT_APP_SUPABASE_URL=$(npx supabase status -o json | jq -r '.API_URL')
REACT_APP_SUPABASE_KEY=$(npx supabase status -o json | jq -r '.ANON_KEY')
EOF

cat > .env << EOF
DB_URL=$(npx supabase status -o json | jq -r '.DB_URL')
SUPABASE_URL=$(npx supabase status -o json | jq -r '.API_URL')
SUPABASE_SERVICE_ROLE_KEY=$(npx supabase status -o json | jq -r '.SERVICE_ROLE_KEY')
EOF
```

### Load the Generated Schema and Data

```bash
rm -rf supabase/migrations/*
npx supabase migration new init_schema
cp supabase_schema.sql supabase/migrations/*_init_schema.sql
cp supabase_sample_data.sql supabase/seed.sql
npx supabase db reset
# check data
source frontend/.env
curl -X GET -H "apikey: $REACT_APP_SUPABASE_KEY" "$REACT_APP_SUPABASE_URL/rest/v1/customer?select=*" | jq '.' # ok, 3 customers
```

### Create Auth Users

Since Supabase Auth users cannot be easily created via SQL in some environments, UniBizKit generates a `security_extended.json` file in the output directory. You can create these users using the Supabase Admin API:

```bash
# Load environment variables
source .env

# Create users using curl from security_extended.json (located in the parent directory)
jq -c '.users[]' ../security_extended.json | while read user; do
  email=$(echo $user | jq -r '.email')
  password=$(echo $user | jq -r '.password')
  role=$(echo $user | jq -r '.roles[0]')
  
  echo "Creating user: $email"
  curl -X POST "$SUPABASE_URL/auth/v1/admin/users" \
    -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
    -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "email": "'$email'",
      "password": "'$password'",
      "email_confirm": true,
      "app_metadata": { "roles": ["'$role'"] }
    }'
done
```

### Start the React-Admin Application

```bash
# Navigate to the frontend directory
cd frontend
# Install dependencies
npm install
# Run
npm start
```

The application will be available at `http://localhost:3000` (or another port if 3000 is occupied)

## Testing

Run the test suite:

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run tests with coverage
pytest --cov=src/unibizkit --cov-report=term-missing
```

### Test Categories

- **Schema Validation**: Tests for JSON schema validation
- **Supabase Generation**: Tests for database schema generation
- **React-Admin Generation**: Tests for frontend code generation
- **CLI Functionality**: Tests for command line interface

## Architecture

UniBizKit follows a modular architecture:

```
src/unibizkit/
├── __init__.py           # Package initialization
├── schema_loader.py     # Schema loading and validation
├── supabase_generator.py # Supabase database schema generation
├── react_admin_generator.py # React-Admin frontend generation
├── cli.py               # Command line interface
└── main.py              # Main entry point
```

### Key Components

1. **Schema Loader**: Validates business schemas against the JSON schema definition
2. **Supabase Generator**: Generates PostgreSQL database schemas with tables, constraints, and relationships
3. **React-Admin Generator**: Generates complete React-Admin applications with CRUD interfaces
4. **CLI**: Provides a user-friendly command line interface

### Design Principles

- **Explicitness**: Clear, well-documented JSON schema format
- **Extensibility**: Easy to add new field types and features
- **Testability**: Comprehensive test coverage
- **Modularity**: Clear separation of concerns between components

## Limitations

This is a proof of concept with the following limitations:

- Basic relationship handling (no complex join conditions)
- Simple field type mapping
- Basic React-Admin configuration
- No authentication/authorization generation
- Limited customization options

## Future Enhancements

Potential areas for future development:

- More field types (arrays, JSON, etc.)
- Advanced relationship configurations
- Custom validation rules
- Theming and branding options
- Authentication integration
- API generation
- Mobile app generation
- More database backends
- More frontend frameworks
