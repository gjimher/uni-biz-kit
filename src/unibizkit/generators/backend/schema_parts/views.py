from typing import Any, Dict, List

from .internal_columns import API_ROLES


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def generate_views(concepts: List[Dict[str, Any]]) -> List[str]:
    """CREATE VIEW for every concept declaring a 'view' query.

    The model query is wrapped in an explicit projection instead of a `SELECT *`
    for three reasons: the view exposes exactly the declared columns (a join in
    the query cannot leak anything else), a query that forgets a declared column
    fails when the schema is applied rather than at runtime, and 'id' — which
    React-Admin requires on every record — is derived here instead of being one
    more thing the model has to get right: a row standing for a record is
    identified by it, an aggregate row by its own presentation label.

    security_invoker makes the view run under the caller's row-level security,
    so a reader can never see through it more than they already could. Views are
    created after every table, in model order, so a view over another view only
    needs to be declared after it.
    """
    statements = []
    for concept in concepts:
        if concept["_be_storage"] != "view":
            continue
        name = concept["name"]
        presentation = concept["_be_presentation_expr"]
        columns = [
            f'''coalesce("concept" || '-' || "concept_id"::text, {presentation}) AS "id"''',
            f'{presentation} AS "id_presentation"',
        ]
        columns.extend(_quote_ident(field["name"]) for field in concept["fields"])
        projection = ",\n    ".join(columns)
        statements.append(f'''CREATE VIEW {_quote_ident(name)} WITH (security_invoker = true) AS
  SELECT
    {projection}
  FROM (
   {concept["view"]["query"]}
  ) AS "v";

-- A view is read-only: a single-table view would otherwise be updatable
-- through the API, since PostgreSQL makes simple views auto-updatable.
REVOKE INSERT, UPDATE, DELETE ON {_quote_ident(name)} FROM {API_ROLES};''')
    return statements
