# UniBizKit - Business Application Generator

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PoC](https://img.shields.io/badge/status-Proof%20of%20Concept-orange)](#)

**UniBizKit** is a proof of concept that demonstrates how complete business applications can be generated from a single JSON definition. It generates both **Supabase (PostgreSQL) database schemas** and **React-Admin frontend applications** from a declarative JSON schema.

## 🚀 Quick Start

```bash
# Install UniBizKit
pip install -e .

# Generate a complete e-commerce application
uni-biz-kit models/test-app --output-dir test-app

# Start the React-Admin frontend
cd test-app/frontend
npm install
npm start
```

## ✨ Features

### JSON Schema Definition
- **Named concepts** with descriptions
- **Field definitions** with types and constraints
- **Relationship definitions** (1:N, M:N, belongs-to)
- **Field types**: string, integer, decimal, boolean, date, datetime, enum
- **Field constraints**: required, unique, min/max, length, precision
- **Relationship support**: ownership, required relationships

### Database Generation (Supabase/PostgreSQL)
- ✅ Table creation for each concept
- ✅ Primary keys and auto-incrementing IDs
- ✅ Field type mapping to PostgreSQL types
- ✅ Unique constraints
- ✅ Enum value validation with CHECK constraints
- ✅ Foreign key relationships
- ✅ Join tables for many-to-many relationships
- ✅ Timestamps (_created_at, _updated_at)
- ✅ Sample data generation

### Frontend Generation (React-Admin)
- ✅ Complete CRUD interface for each concept
- ✅ List, Create, Edit, and Show views
- ✅ Automatic field component selection
- ✅ Relationship handling in UI
- ✅ Form validation for required fields
- ✅ Supabase data provider configuration
- ✅ Ready-to-run React application

## 📁 Example: ECommerce Platform

The repository includes a complete e-commerce example (`models/test-app`) that demonstrates:

- **Products** with various field types (string, decimal, enum, boolean)
- **Categories** with hierarchical relationships
- **Customers** with contact information
- **Orders** with status tracking
- **OrderItems** with product relationships
- **Many-to-many relationships** between products and categories

```bash
# Generate the e-commerce application
uni-biz-kit models/test-app --output-dir test-app

# Explore the generated files
ls -la test-app/
```

## 🔧 Installation

### Prerequisites
- Python 3.8+
- Node.js (for React-Admin frontend)
- PostgreSQL (for database)

### Install UniBizKit

```bash
# Clone the repository
git clone https://github.com/unibizkit/unibizkit.git
cd unibizkit

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .
```

## 📖 Documentation

Complete documentation is available in the [docs/USAGE.md](docs/USAGE.md) file, including:

- Detailed JSON schema format specification
- CLI usage and options
- Examples and tutorials
- Architecture overview
- Testing guide
- Running generated applications

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/unibizkit --cov-report=term-missing
```

### Test Coverage
- ✅ Schema validation (valid and invalid schemas)
- ✅ Relationship handling (1:N and M:N)
- ✅ Database schema generation
- ✅ Sample data generation
- ✅ React-Admin code generation
- ✅ CLI command execution

## 🏗️ Architecture

UniBizKit follows a modular design:

```
src/unibizkit/
├── schema_loader.py      # Schema validation
├── supabase_generator.py # Database generation
├── react_admin_generator.py # Frontend generation
├── cli.py               # Command line interface
└── main.py              # Entry point
```

## 🎯 Use Cases

UniBizKit is ideal for:

- **Rapid prototyping** of business applications
- **Proof of concept** development
- **Learning** about code generation
- **Standardizing** application structure
- **Reducing boilerplate** code

## ⚠️ Limitations

This is a **proof of concept** with known limitations:

- Basic relationship handling only
- Simple field type mapping
- Limited customization options
- No authentication/authorization
- Not production-ready

## 🔮 Future Enhancements

Potential areas for future development:

- More field types (arrays, JSON, etc.)
- Advanced relationship configurations
- Custom validation rules
- Theming and branding options
- Authentication integration
- API generation
- Mobile app generation

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please open issues and pull requests to help improve UniBizKit.

## 🙏 Acknowledgments

- Built with Python, React-Admin, and Supabase
- Inspired by low-code platforms and code generation tools
- Designed for clarity, extensibility, and testability