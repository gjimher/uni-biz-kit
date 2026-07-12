from unibizkit.release import (
    Version,
    incompatible_migration_changes,
    migration_hash,
    next_version,
    tagged_versions,
    version_tag,
)


def test_versions_are_scoped_to_the_model_and_start_at_v1():
    tags = ["prod-shop-v1.2", "prod-other-v9.9", "v3.0", "prod-shop-v2.0"]
    assert tagged_versions("shop", tags) == [
        (Version(1, 2), "prod-shop-v1.2"),
        (Version(2, 0), "prod-shop-v2.0"),
    ]
    assert next_version("new-app", tags) == Version(1, 0)
    assert next_version("shop", tags) == Version(2, 1)
    assert next_version("shop", tags, major=True) == Version(3, 0)
    assert version_tag("shop", Version(2, 1)) == "prod-shop-v2.1"


def test_migration_hash_ignores_only_line_endings_and_trailing_space():
    left = "\r\nALTER TABLE item ADD COLUMN note text;   \r\n"
    right = "ALTER TABLE item ADD COLUMN note text;\n"
    assert migration_hash(left) == migration_hash(right)
    assert migration_hash(right) != migration_hash("ALTER TABLE item ADD COLUMN note bigint;\n")


def test_minor_compatibility_rejects_old_client_write_breaks():
    sql = """
    ALTER TABLE invoice DROP COLUMN legacy_code;
    ALTER TABLE invoice ADD COLUMN tenant_id uuid NOT NULL;
    ALTER TABLE invoice ADD CONSTRAINT positive_total CHECK (total > 0);
    CREATE UNIQUE INDEX invoice_code_key ON invoice (code);
    DROP FUNCTION public.old_invoice_hook();
    """
    reasons = incompatible_migration_changes(sql)
    assert "drops a column" in reasons
    assert "adds a mandatory column without a default" in reasons
    assert "adds a write-restricting constraint" in reasons
    assert "adds a write-restricting unique index" in reasons
    assert "removes a function or procedure" in reasons


def test_minor_compatibility_accepts_nullable_and_defaulted_columns():
    sql = """
    ALTER TABLE invoice ADD COLUMN note text;
    ALTER TABLE invoice ADD COLUMN created_by uuid NOT NULL DEFAULT auth.uid();
    """
    assert incompatible_migration_changes(sql) == []
