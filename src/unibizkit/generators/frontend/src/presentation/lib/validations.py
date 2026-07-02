import json

from ....context import Context


def generate(ctx: Context) -> str:
    """CSV-driven related-field validation helpers.

    The data (rows from validations/*.csv) and the pure logic live here so they can
    be shared by both the generated React-Admin resources (via react-hook-form) and
    any custom presentation page (plain controlled forms). These functions are
    framework-agnostic: they operate on a plain `values` object keyed by the
    validation's column names.
    """
    validations = ctx.validations_config.get("validations", [])
    by_concept: dict = {}
    for validation in validations:
        by_concept.setdefault(validation["concept"], []).append({
            "name": validation["name"],
            "concept": validation["concept"],
            "columns": validation["columns"],
            "rows": validation["rows"],
        })
    data_json = json.dumps(by_concept, indent=2, ensure_ascii=False)

    return f"""// All CSV validations, indexed by concept name. Each entry is
// {{ name, concept, columns: [...], rows: [[...], ...] }} where a cell of '*'
// matches any value (free entry).
export const VALIDATIONS = {data_json};

// Marker option shown in autocompletes for columns that allow free entry ('*').
export const FREE_ENTRY_OPTION = '(type any value)';

// All validations defined for a concept (empty array when none).
export function getValidations(concept) {{
  return VALIDATIONS[concept] ?? [];
}}

// The first validation for `concept` whose columns include `source`.
export function firstValidationForSource(concept, source) {{
  return getValidations(concept).find((validation) => validation.columns.includes(source));
}}

// Rows still compatible with the currently filled-in values. `ignoredColumn` lets
// callers compute the options for one column without constraining on it.
export function compatibleRows(validation, values, ignoredColumn = null) {{
  let rows = validation.rows;
  for (const [index, column] of validation.columns.entries()) {{
    if (column === ignoredColumn) continue;
    const value = values[column];
    if (value === undefined || value === null || value === '') continue;
    if (rows.some((row) => row[index] === value)) {{
      rows = rows.filter((row) => row[index] === value);
    }} else {{
      rows = rows.filter((row) => row[index] === '*');
    }}
  }}
  return rows;
}}

// Does the values object match at least one allowed row of the validation?
export function matchesValidationRow(validation, values) {{
  return compatibleRows(validation, values).some((row) =>
    validation.columns.every((column, index) => row[index] === '*' || values[column] === row[index])
  );
}}

// Suggested options for `source` given the other filled-in values. When the column
// allows free entry, FREE_ENTRY_OPTION is appended.
export function optionsFor(validation, source, values) {{
  const sourceIndex = validation.columns.indexOf(source);
  const rows = compatibleRows(validation, values, source);
  const concrete = Array.from(new Set(rows.map((row) => row[sourceIndex]).filter((value) => value !== '*'))).sort();
  const options = rows.some((row) => row[sourceIndex] === '*') ? [...concrete, FREE_ENTRY_OPTION] : concrete;
  return {{ options }};
}}

// Validate a record for a concept. Returns an errors object keyed by field name.
// Flags missing `requiredFields` and any complete-but-invalid validation group.
export function validateRecord(concept, values, requiredFields = []) {{
  const errors = {{}};
  for (const field of requiredFields) {{
    if (values[field] === undefined || values[field] === null || values[field] === '') {{
      errors[field] = 'Required';
    }}
  }}
  for (const validation of getValidations(concept)) {{
    const complete = validation.columns.every(
      (column) => values[column] !== undefined && values[column] !== null && values[column] !== ''
    );
    if (!complete) continue;
    if (!matchesValidationRow(validation, values)) {{
      for (const column of validation.columns) errors[column] = 'Invalid combination';
    }}
  }}
  return errors;
}}

// Normalize a react-hook-form / plain error into a display string.
export function validationErrorText(error) {{
  if (!error) return '';
  if (typeof error === 'string') return error;
  if (typeof error.message === 'string') return error.message;
  if (error.message) return validationErrorText(error.message);
  return '';
}}
"""
