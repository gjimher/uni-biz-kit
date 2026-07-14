def runtime_source() -> str:
    return r'''"""Apply model-owned deployed data transactionally."""
import json
from pathlib import Path

from psycopg2 import sql
from psycopg2.extras import Json


def load_data(path):
    path = Path(path)
    if path.suffix == ".jsonc":
        try:
            from jsoncomment import JsonComment
        except ImportError as exc:
            raise RuntimeError("Applying JSONC requires the jsoncomment package") from exc
        with path.open(encoding="utf-8") as handle:
            return JsonComment().load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def apply_deployed_data(conn, concepts_path, data_path):
    concepts_data = load_data(concepts_path)
    config = load_data(data_path)
    concept_map = {concept["name"]: concept for concept in concepts_data["concepts"]}
    entries = config.get("concepts")
    if not isinstance(entries, list):
        raise ValueError("deployed_data must contain a concepts array")
    names = [entry.get("concept") for entry in entries]
    if None in names or len(names) != len(set(names)):
        raise ValueError("deployed_data concept names must be present and unique")

    old_autocommit = conn.autocommit
    conn.autocommit = False
    stats = {}
    try:
        with conn.cursor() as cur:
            for entry in entries:
                concept_name = entry["concept"]
                concept = concept_map.get(concept_name)
                if not concept:
                    raise ValueError(f"Unknown deployed_data concept '{concept_name}'")
                records = entry.get("records")
                if not isinstance(records, list):
                    raise ValueError(f"deployed_data records for '{concept_name}' must be an array")
                on_removed = entry.get("on_removed", "ignore")
                field_map = {field["name"]: field for field in concept["fields"]}
                key_fields = [name for name in concept["id_presentation"]["fields"] if "." not in name]
                _validate_entry(concept_name, records, on_removed, field_map, key_fields)
                declared_keys = set()
                inserted = updated = 0

                for record in records:
                    key = _key_token(record[name] for name in key_fields)
                    if key in declared_keys:
                        raise ValueError(f"Duplicate deployed_data key for '{concept_name}': {key}")
                    declared_keys.add(key)
                    condition = sql.SQL(" AND ").join(
                        sql.SQL("{} IS NOT DISTINCT FROM %s").format(sql.Identifier(name))
                        for name in key_fields
                    )
                    key_values = [_value(record[name], field_map[name]) for name in key_fields]
                    cur.execute(
                        sql.SQL("SELECT count(*) FROM {} WHERE ").format(sql.Identifier(concept_name)) + condition,
                        key_values,
                    )
                    matched = cur.fetchone()[0]
                    if matched > 1:
                        raise ValueError(f"deployed_data matched multiple '{concept_name}' rows for key {key}")
                    columns = list(record)
                    values = [_value(record[name], field_map[name]) for name in columns]
                    if matched == 1:
                        assignments = sql.SQL(", ").join(
                            sql.SQL("{} = %s").format(sql.Identifier(name)) for name in columns
                        )
                        cur.execute(
                            sql.SQL("UPDATE {} SET ").format(sql.Identifier(concept_name))
                            + assignments + sql.SQL(" WHERE ") + condition,
                            values + key_values,
                        )
                        updated += 1
                    else:
                        cur.execute(
                            sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                                sql.Identifier(concept_name),
                                sql.SQL(", ").join(map(sql.Identifier, columns)),
                                sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                            ),
                            values,
                        )
                        inserted += 1

                affected_removed = 0
                if on_removed != "ignore":
                    cur.execute(
                        sql.SQL("SELECT {}, {} FROM {}").format(
                            sql.Identifier("id"),
                            sql.SQL(", ").join(map(sql.Identifier, key_fields)),
                            sql.Identifier(concept_name),
                        )
                    )
                    missing_ids = [
                        row[0] for row in cur.fetchall()
                        if _key_token(row[1:]) not in declared_keys
                    ]
                    if missing_ids:
                        cur.execute(
                            sql.SQL("DELETE FROM {} WHERE id = ANY(%s)").format(sql.Identifier(concept_name)),
                            (missing_ids,),
                        )
                        affected_removed = len(missing_ids)
                stats[concept_name] = {
                    "inserted": inserted,
                    "updated": updated,
                    "removed_affected": affected_removed,
                }
        conn.commit()
        return stats
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = old_autocommit


def _validate_entry(concept_name, records, on_removed, field_map, key_fields):
    if not key_fields or "id" in key_fields:
        raise ValueError(f"Concept '{concept_name}' has no valid local id_presentation key")
    if on_removed not in ("ignore", "delete"):
        raise ValueError(f"Invalid on_removed for '{concept_name}'")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"deployed_data record for '{concept_name}' must be an object")
        missing = [name for name in key_fields if name not in record]
        if missing:
            raise ValueError(f"deployed_data record for '{concept_name}' misses keys: {', '.join(missing)}")
        for name in record:
            field = field_map.get(name)
            if not field:
                raise ValueError(f"Unknown deployed_data field '{concept_name}.{name}'")
            if field.get("calculated") or field.get("_be_sql_type") == "SERIAL" or field["type"] == "relation_to_many":
                raise ValueError(f"deployed_data cannot set generated field '{concept_name}.{name}'")


def _key_token(values):
    return json.dumps(list(values), sort_keys=True, separators=(",", ":"), default=str)


def _value(value, field=None):
    return Json(value) if (field and field["type"] == "json") or isinstance(value, (dict, list)) else value
'''
