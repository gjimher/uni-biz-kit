import pytest
from unibizkit.schema_processor import SchemaProcessor

def test_security_rules_merging():
    schema = {
        "concepts": [
            {"name": "product", "plural_name": "products", "fields": [], "id_presentation": {"fields": []}},
            {"name": "order", "plural_name": "orders", "fields": [], "id_presentation": {"fields": []}}
        ]
    }
    
    security_config = {
        "authentication_required": True,
        "rules_level_1": [
            {"role": "user", "concept": "*", "access": "read"},
            {"role": "admin", "concept": "*", "access": "write"}
        ],
        "rules_level_2": [
            {"role": "user", "concept": "product", "access": "write"}
        ],
        "rules_level_3": [
            {"role": "user", "concept": "product", "access": "read"}
        ]
    }
    
    processor = SchemaProcessor(schema, security_config=security_config)
    processed = processor.process()
    
    rules = processor.security_extended["rules"]
    
    # Helper to find a rule
    def find_rule(role, concept):
        for r in rules:
            if r["role"] == role and r["concept"] == concept:
                return r["access"]
        return None

    # User rules:
    # Level 1: user product read, user order read
    # Level 2: user product write (overrides L1)
    # Level 3: user product read (overrides L2)
    assert find_rule("user", "product") == "read"
    assert find_rule("user", "order") == "read"
    
    # Admin rules:
    # Level 1: admin product write, admin order write
    assert find_rule("admin", "product") == "write"
    assert find_rule("admin", "order") == "write"

    # Final cleanup check
    for level in ["rules_level_1", "rules_level_2", "rules_level_3"]:
        assert level not in processor.security_extended, f"{level} should be removed from processed security"

def test_security_rules_default_level_1():
    schema = {
        "concepts": [
            {"name": "product", "plural_name": "products", "fields": [], "id_presentation": {"fields": []}}
        ]
    }
    
    # No rules_level_1 provided
    security_config = {
        "authentication_required": True
    }
    
    processor = SchemaProcessor(schema, security_config=security_config)
    processor.process()
    
    rules = processor.security_extended["rules"]
    
    def find_rule(role, concept):
        for r in rules:
            if r["role"] == role and r["concept"] == concept:
                return r["access"]
        return None

    # Should use default: admin write, user read
    assert find_rule("admin", "product") == "write"
    assert find_rule("user", "product") == "read"

    # Final cleanup check
    for level in ["rules_level_1", "rules_level_2", "rules_level_3"]:
        assert level not in processor.security_extended, f"{level} should be removed from processed security"

def test_security_rules_complex_override():
    schema = {
        "concepts": [
            {"name": "product", "plural_name": "products", "fields": [], "id_presentation": {"fields": []}},
            {"name": "order", "plural_name": "orders", "fields": [], "id_presentation": {"fields": []}}
        ]
    }
    
    security_config = {
        "authentication_required": True,
        "rules_level_1": [
            {"role": "user", "concept": "*", "access": "read"}
        ],
        "rules_level_2": [
            {"role": "user", "concept": "*", "access": "write"} # Global override
        ],
        "rules_level_3": [
            {"role": "user", "concept": "order", "access": "read"} # Specific exception
        ]
    }
    
    processor = SchemaProcessor(schema, security_config=security_config)
    processor.process()
    
    rules = processor.security_extended["rules"]
    
    def find_rule(role, concept):
        for r in rules:
            if r["role"] == role and r["concept"] == concept:
                return r["access"]
        return None

    assert find_rule("user", "product") == "write"
    assert find_rule("user", "order") == "read"

    # Final cleanup check
    for level in ["rules_level_1", "rules_level_2", "rules_level_3"]:
        assert level not in processor.security_extended, f"{level} should be removed from processed security"
