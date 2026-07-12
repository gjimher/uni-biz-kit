import copy

import pytest

from unibizkit.schema_processor import SchemaProcessor
from unibizkit.generators.backend.schema_parts.joins import generate_foreign_key_constraints


def _schema(required=False):
    return {
        "concepts": [
            {
                "name": "target",
                "plural_name": "targets",
                "fields": [
                    {
                        "name": "name",
                        "type": "string",
                        "size": "s",
                        "required": False,
                        "unique": False,
                        "description": "",
                    }
                ],
                "id_presentation": {"fields": ["name"], "separator": " ", "show": False},
            },
            {
                "name": "source",
                "plural_name": "sources",
                "fields": [
                    {
                        "name": "target",
                        "type": "relation_to_one",
                        "subtype": "related_to",
                        "target": "target",
                        "on_delete": "snapshot_data",
                        "size": "s",
                        "required": required,
                        "unique": False,
                        "description": "",
                    }
                ],
                "id_presentation": {"fields": ["target"], "separator": " ", "show": False},
            },
        ]
    }


def test_snapshot_relation_adds_internal_jsonb_field():
    processor = SchemaProcessor(
        copy.deepcopy(_schema()), security_config={"authentication_required": False}
    )
    processor.process()

    fields = {field["name"]: field for field in processor.concept_map["source"]["fields"]}
    snapshot = fields["_target_deleted_snapshot"]
    assert snapshot["_be_sql_type"] == "JSONB"
    assert snapshot["_fe_visibility"] == "internal"
    assert snapshot["_be_not_null"] is False


def test_snapshot_relation_must_be_optional():
    processor = SchemaProcessor(
        copy.deepcopy(_schema(required=True)),
        security_config={"authentication_required": False},
    )

    with pytest.raises(ValueError, match="must be optional"):
        processor.process()


def test_optional_relation_can_explicitly_cascade():
    schema = _schema()
    relation = schema["concepts"][1]["fields"][0]
    relation["on_delete"] = "cascade"
    processor = SchemaProcessor(
        copy.deepcopy(schema), security_config={"authentication_required": False}
    )
    processor.process()

    sql = "\n".join(
        generate_foreign_key_constraints(
            processor.concepts, processor.security_extended
        )
    )
    assert 'FOREIGN KEY ("target") REFERENCES "target"("id") ON DELETE CASCADE' in sql
    assert "_target_deleted_snapshot" not in {
        field["name"] for field in processor.concept_map["source"]["fields"]
    }


def test_required_relation_cannot_explicitly_set_null():
    schema = _schema(required=True)
    schema["concepts"][1]["fields"][0]["on_delete"] = "set_null"
    processor = SchemaProcessor(
        copy.deepcopy(schema), security_config={"authentication_required": False}
    )

    with pytest.raises(ValueError, match="must be optional"):
        processor.process()
