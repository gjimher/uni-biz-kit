from typing import Any, Dict, List, Tuple

from .joins import _join_table_pairs


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _part_of_field(concept: Dict[str, Any]) -> Dict[str, Any] | None:
    return next((
        field for field in concept["fields"]
        if field["type"] == "relation_to_one" and field.get("subtype") == "part_of"
    ), None)


def aggregate_root(
    concept_name: str,
    concept_map: Dict[str, Dict[str, Any]],
) -> Tuple[str, List[Tuple[str, str, str]]]:
    """Return (root concept, child/fk/parent hops) for a part_of aggregate."""
    hops = []
    seen = set()
    current = concept_name
    while True:
        if current in seen:
            # A self part_of concept is its own aggregate root; runtime SQL walks
            # the record tree to find the top row.
            return current, hops
        seen.add(current)
        field = _part_of_field(concept_map[current])
        if field is None or field["target"] == current:
            return current, hops
        hops.append((current, field["name"], field["target"]))
        current = field["target"]


def _resolver_sql(
    concept: Dict[str, Any],
    concept_map: Dict[str, Dict[str, Any]],
    history_table: str,
) -> str:
    name = concept["name"]
    resolver = f"{history_table}_resolve_{name}_root"
    _, hops = aggregate_root(name, concept_map)
    own_part_of = _part_of_field(concept)
    if own_part_of and own_part_of["target"] == name:
        parent = own_part_of["name"]
        body = f"""
  WITH RECURSIVE ancestors(id, parent_id, depth) AS (
    SELECT p_id, COALESCE(
      NULLIF(p_row ->> {_quote(parent)}, '')::integer,
      (SELECT {_quote_ident(parent)} FROM {_quote_ident(name)} WHERE id = p_id)
    ), 0
    UNION ALL
    SELECT item.id, item.{_quote_ident(parent)}, child.depth + 1
    FROM {_quote_ident(name)} item
    JOIN ancestors child ON item.id = child.parent_id
  )
  SELECT id, parent_id INTO resolved, unresolved_parent
  FROM ancestors
  ORDER BY depth DESC
  LIMIT 1;
  IF unresolved_parent IS NOT NULL THEN
    SELECT root_concept_id INTO version_root FROM {_quote_ident(history_table)}
    WHERE concept = {_quote(name)} AND concept_id = unresolved_parent
      AND transaction_id = txid_current()::text
    ORDER BY id DESC LIMIT 1;
  END IF;
  RETURN COALESCE(version_root, resolved, p_id);"""
    elif not hops:
        body = "\n  RETURN p_id;"
    else:
        lines = ["  current_id := p_id;"]
        for index, (child, fk, _parent) in enumerate(hops):
            if index == 0:
                lines.extend([
                    f"  parent_id := NULLIF(p_row ->> {_quote(fk)}, '')::integer;",
                    "  IF parent_id IS NULL THEN",
                    f"    SELECT {_quote_ident(fk)} INTO parent_id FROM {_quote_ident(child)} WHERE id = current_id;",
                    "  END IF;",
                ])
            else:
                lines.append(
                    f"  SELECT {_quote_ident(fk)} INTO parent_id FROM {_quote_ident(child)} WHERE id = current_id;"
                )
            lines.extend([
                "  IF parent_id IS NULL THEN",
                f"    SELECT root_concept_id INTO parent_id FROM {_quote_ident(history_table)}",
                f"    WHERE concept = {_quote(child)} AND concept_id = current_id",
                "      AND transaction_id = txid_current()::text",
                "    ORDER BY id DESC LIMIT 1;",
                "  END IF;",
                "  IF parent_id IS NULL THEN RETURN current_id; END IF;",
                "  current_id := parent_id;",
            ])
        lines.append("  RETURN current_id;")
        body = "\n" + "\n".join(lines)

    declarations = "  resolved integer;\n  unresolved_parent integer;\n  version_root integer;" if own_part_of and own_part_of["target"] == name else "  current_id integer;\n  parent_id integer;"
    return f"""
CREATE OR REPLACE FUNCTION {_quote_ident(resolver)}(p_id integer, p_row jsonb DEFAULT NULL)
RETURNS integer AS $$
DECLARE
{declarations}
BEGIN{body}
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

REVOKE ALL ON FUNCTION {_quote_ident(resolver)}(integer, jsonb) FROM PUBLIC;
"""


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _audit_function_sql(history_table: str) -> str:
    presentation_function = f"{history_table}_id_presentation"
    capture_function = f"{history_table}_capture"
    immutable_function = f"00_{history_table.lstrip('_')}_immutable"
    template = r'''
CREATE OR REPLACE FUNCTION __PRESENTATION_FUNCTION__(p_concept text, p_id integer, p_fallback text DEFAULT NULL)
RETURNS text AS $$
DECLARE
  result text;
BEGIN
  IF p_id IS NOT NULL THEN
    BEGIN
      EXECUTE format('SELECT id_presentation FROM %I WHERE id = $1', p_concept)
        INTO result USING p_id;
    EXCEPTION WHEN undefined_table OR undefined_column THEN
      result := NULL;
    END;
    IF result IS NULL THEN
      SELECT concept_id_presentation INTO result
      FROM __HISTORY_TABLE__
      WHERE concept = p_concept AND concept_id = p_id
      ORDER BY id DESC
      LIMIT 1;
    END IF;
  END IF;
  RETURN COALESCE(NULLIF(p_fallback, ''), NULLIF(result, ''), '#' || COALESCE(p_id::text, '?'));
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

REVOKE ALL ON FUNCTION __PRESENTATION_FUNCTION__(text, integer, text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION __CAPTURE_FUNCTION__()
RETURNS TRIGGER AS $$
DECLARE
  row_before jsonb;
  row_after jsonb;
  changed_values jsonb := '{}'::jsonb;
  row_value jsonb;
  record_id integer;
  aggregate_source_id integer;
  aggregate_id integer;
  record_presentation text;
  aggregate_presentation text;
  aggregate_concept text := TG_ARGV[0];
  event_type text := TG_ARGV[1];
  resolver text := TG_ARGV[2];
BEGIN
  IF TG_OP = 'INSERT' THEN
    row_after := to_jsonb(NEW);
    row_value := row_after;
    changed_values := row_after - 'id' - '_created_at' - '_updated_at' - 'id_presentation';
    record_id := NEW.id;
  ELSIF TG_OP = 'DELETE' THEN
    row_before := to_jsonb(OLD);
    row_value := row_before;
    record_id := OLD.id;
  ELSE
    row_before := to_jsonb(OLD);
    row_after := to_jsonb(NEW);
    row_value := row_after;
    SELECT coalesce(jsonb_object_agg(after_value.key, after_value.value), '{}'::jsonb)
      INTO changed_values
    FROM jsonb_each(row_after) after_value
    WHERE after_value.key NOT IN ('_created_at', '_updated_at', 'id_presentation')
      AND after_value.value IS DISTINCT FROM row_before -> after_value.key;
    IF changed_values = '{}'::jsonb THEN
      RETURN NEW;
    END IF;
    record_id := NEW.id;
  END IF;

  aggregate_source_id := CASE
    WHEN TG_NARGS > 3 THEN NULLIF(row_value ->> TG_ARGV[3], '')::integer
    ELSE record_id
  END;
  EXECUTE format('SELECT %I($1, $2)', resolver) INTO aggregate_id USING aggregate_source_id, row_value;
  record_presentation := CASE
    WHEN event_type = 'documents' THEN concat_ws(' · ', row_value ->> 'tag', row_value ->> 'storage_path')
    ELSE row_value ->> 'id_presentation'
  END;
  record_presentation := __PRESENTATION_FUNCTION__(TG_TABLE_NAME, record_id, record_presentation);
  aggregate_presentation := __PRESENTATION_FUNCTION__(
    aggregate_concept,
    aggregate_id,
    CASE WHEN aggregate_concept = TG_TABLE_NAME AND aggregate_id = record_id THEN record_presentation END
  );
  INSERT INTO __HISTORY_TABLE__ (
    concept, concept_id, concept_id_presentation,
    root_concept, root_concept_id, root_concept_id_presentation,
    change_type, operation, changed_by, transaction_id, before, changed
  ) VALUES (
    TG_TABLE_NAME, record_id, record_presentation,
    aggregate_concept, aggregate_id, aggregate_presentation,
    event_type, lower(TG_OP), auth.jwt() ->> 'email',
    txid_current()::text, row_before, changed_values
  );
  IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

CREATE OR REPLACE FUNCTION __IMMUTABLE_FUNCTION__()
RETURNS TRIGGER AS $$
BEGIN
  IF pg_trigger_depth() <= 1 THEN
    RAISE EXCEPTION '__HISTORY_NAME__ is immutable' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS __IMMUTABLE_FUNCTION__ ON __HISTORY_TABLE__;
CREATE TRIGGER __IMMUTABLE_FUNCTION__
BEFORE INSERT OR UPDATE OR DELETE ON __HISTORY_TABLE__
FOR EACH ROW EXECUTE FUNCTION __IMMUTABLE_FUNCTION__();
'''
    return (
        template
        .replace("__HISTORY_TABLE__", _quote_ident(history_table))
        .replace("__PRESENTATION_FUNCTION__", _quote_ident(presentation_function))
        .replace("__CAPTURE_FUNCTION__", _quote_ident(capture_function))
        .replace("__IMMUTABLE_FUNCTION__", _quote_ident(immutable_function))
        .replace("__HISTORY_NAME__", history_table.replace("'", "''"))
    )


def _row_trigger_sql(
    table: str,
    root: str,
    change_type: str,
    resolver_concept: str,
    history_table: str,
    owner_column: str | None = None,
) -> str:
    feature = history_table.lstrip("_")
    trigger = f"99_{feature}_{table}"
    delete_trigger = f"99_{feature}_{table}_delete"
    resolver = f"{history_table}_resolve_{resolver_concept}_root"
    capture_function = f"{history_table}_capture"
    owner_argument = f", {_quote(owner_column)}" if owner_column else ""
    return f'''
DROP TRIGGER IF EXISTS {_quote_ident(trigger)} ON {_quote_ident(table)};
CREATE TRIGGER {_quote_ident(trigger)}
AFTER INSERT OR UPDATE ON {_quote_ident(table)}
FOR EACH ROW EXECUTE FUNCTION {_quote_ident(capture_function)}({_quote(root)}, {_quote(change_type)}, {_quote(resolver)}{owner_argument});

DROP TRIGGER IF EXISTS {_quote_ident(delete_trigger)} ON {_quote_ident(table)};
CREATE TRIGGER {_quote_ident(delete_trigger)}
BEFORE DELETE ON {_quote_ident(table)}
FOR EACH ROW EXECUTE FUNCTION {_quote_ident(capture_function)}({_quote(root)}, {_quote(change_type)}, {_quote(resolver)}{owner_argument});
'''


def _join_trigger_sql(
    table: str,
    table1: str,
    table2: str,
    endpoint: str,
    root: str,
    history_table: str,
) -> str:
    feature = history_table.lstrip("_")
    function = f"{history_table}_capture_{table}_{endpoint}"
    trigger = f"99_{feature}_{table}_{endpoint}"
    endpoint_col = f"{endpoint}_id"
    resolver = f"{history_table}_resolve_{endpoint}_root"
    presentation_function = f"{history_table}_id_presentation"
    return f'''
CREATE OR REPLACE FUNCTION {_quote_ident(function)}()
RETURNS TRIGGER AS $$
DECLARE
  row_before jsonb;
  row_after jsonb;
  row_value jsonb;
  endpoint_id integer;
  aggregate_id integer;
  relation_id integer;
  relation_presentation text;
  aggregate_presentation text;
BEGIN
  IF TG_OP = 'INSERT' THEN
    row_after := to_jsonb(NEW);
    row_value := row_after;
    endpoint_id := NEW.{_quote_ident(endpoint_col)};
    relation_id := NEW.id;
  ELSIF TG_OP = 'DELETE' THEN
    row_before := to_jsonb(OLD);
    row_value := row_before;
    endpoint_id := OLD.{_quote_ident(endpoint_col)};
    relation_id := OLD.id;
  ELSE
    row_before := to_jsonb(OLD);
    row_after := to_jsonb(NEW);
    row_value := row_after;
    endpoint_id := NEW.{_quote_ident(endpoint_col)};
    relation_id := NEW.id;
  END IF;
  aggregate_id := {_quote_ident(resolver)}(endpoint_id, NULL);
  relation_presentation := concat_ws(
    ' · ',
    {_quote_ident(presentation_function)}({_quote(table1)}, NULLIF(row_value ->> {_quote(f'{table1}_id')}, '')::integer),
    {_quote_ident(presentation_function)}({_quote(table2)}, NULLIF(row_value ->> {_quote(f'{table2}_id')}, '')::integer)
  );
  aggregate_presentation := {_quote_ident(presentation_function)}({_quote(root)}, aggregate_id);
  INSERT INTO {_quote_ident(history_table)} (
    concept, concept_id, concept_id_presentation,
    root_concept, root_concept_id, root_concept_id_presentation,
    change_type, operation, changed_by, transaction_id, before, changed
  ) VALUES (
    {_quote(table)}, relation_id, relation_presentation,
    {_quote(root)}, aggregate_id, aggregate_presentation,
    'relations', lower(TG_OP), auth.jwt() ->> 'email',
    txid_current()::text, row_before,
    CASE WHEN TG_OP = 'DELETE' THEN '{{}}'::jsonb ELSE row_after - 'id' - '_created_at' - '_updated_at' END
  );
  IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

DROP TRIGGER IF EXISTS {_quote_ident(trigger)} ON {_quote_ident(table)};
CREATE TRIGGER {_quote_ident(trigger)}
AFTER INSERT OR UPDATE OR DELETE ON {_quote_ident(table)}
FOR EACH ROW EXECUTE FUNCTION {_quote_ident(function)}();
'''


def generate_versioning_sql(
    concepts: List[Dict[str, Any]],
    concept_map: Dict[str, Dict[str, Any]],
) -> List[str]:
    versioned = [concept for concept in concepts if concept.get("versioned")]
    if not versioned:
        return []
    history_concept = next(
        (concept for concept in concepts if concept.get("_be_version_history")),
        None,
    )
    if history_concept is None:
        raise ValueError("Versioned concepts require a version-history capability")
    history_table = history_concept["name"]
    sql = [_audit_function_sql(history_table)]
    for concept in versioned:
        sql.append(_resolver_sql(concept, concept_map, history_table))
    for concept in versioned:
        root, _ = aggregate_root(concept["name"], concept_map)
        sql.append(_row_trigger_sql(
            concept["name"], root, "fields", concept["name"], history_table,
        ))
        if concept["documents"]["enabled"] and concept["documents"]["versioned"]:
            sql.append(_row_trigger_sql(
                f"{concept['name']}_document", root, "documents", concept["name"],
                history_table,
                f"{concept['name']}_id",
            ))

    for join_table, table1, table2 in _join_table_pairs(concepts, concept_map):
        for endpoint in (table1, table2):
            endpoint_concept = concept_map[endpoint]
            if endpoint_concept.get("versioned"):
                root, _ = aggregate_root(endpoint, concept_map)
                sql.append(_join_trigger_sql(
                    join_table, table1, table2, endpoint, root, history_table,
                ))
    return sql


def generate_versioning_access_sql(
    concepts: List[Dict[str, Any]],
    concept_map: Dict[str, Dict[str, Any]],
) -> List[str]:
    history_concept = next(
        (concept for concept in concepts if concept.get("_be_version_history")),
        None,
    )
    roots = sorted({
        aggregate_root(concept["name"], concept_map)[0]
        for concept in concepts if concept.get("versioned")
    })
    if history_concept is None or not roots:
        return []
    history_table = _quote_ident(history_concept["name"])
    visible = "\n    OR ".join(
        f'(root_concept = {_quote(root)} AND EXISTS '
        f'(SELECT 1 FROM {_quote_ident(root)} visible_root WHERE visible_root.id = root_concept_id))'
        for root in roots
    )
    return [f'''
ALTER TABLE {history_table} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "read_visible_record_versions" ON {history_table};
CREATE POLICY "read_visible_record_versions" ON {history_table}
FOR SELECT TO authenticated
USING (
    {visible}
);
''']
