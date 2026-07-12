import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from py_mini_racer import MiniRacer

from .. import dev_ports
from .context import Context


@dataclass
class FeelRule:
    concept: str | None
    name: str
    expression: str
    action: str
    context_source: str
    context_concept: str
    db_paths: List[str]
    child_collections: Dict[str, str]
    when: List[str]
    when_async: List[str]


def discover_rules(
    rules_config: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    security_config: Dict[str, Any] | None = None,
) -> List[FeelRule]:
    concept_names = {concept["name"] for concept in concepts}
    profile_concepts = {
        profile["concept"]
        for profile in (security_config or {}).get("_profile_concepts", [])
    }
    rules = []
    for rule_config in rules_config["rules"]:
        expression = rule_config["feel_expr"].strip()
        context_paths = _context_paths(expression)
        db_paths = [path for path in context_paths if path.startswith("db.")]
        configured_concept = rule_config.get("concept")
        if configured_concept is not None:
            if configured_concept not in concept_names:
                raise ValueError(
                    f"Rule '{rule_config['name']}' references unknown concept '{configured_concept}'"
                )
            contexts = [("db", configured_concept)]
        else:
            contexts = sorted({
                (parts[0], parts[1])
                for context_path in context_paths
                for parts in [context_path.split(".")]
                if len(parts) >= 2 and parts[1] in concept_names
            })
        if len(contexts) != 1:
            raise ValueError(
                f"Rule '{rule_config['name']}' must resolve exactly one context concept; "
                f"found {contexts or 'none'}"
            )
        context_source, context_concept = contexts[0]
        when = rule_config["when"]
        when_async = rule_config["when_async"]
        if (when or when_async) and configured_concept is None:
            raise ValueError(f"Rule '{rule_config['name']}' with when/when_async must define concept")
        if rule_config["action"] == "check":
            if when_async:
                raise ValueError(f"Rule '{rule_config['name']}' action check cannot use when_async")
            if not when:
                raise ValueError(f"Rule '{rule_config['name']}' action check requires when")
        if rule_config["action"] == "return" and (when or when_async):
            raise ValueError(f"Rule '{rule_config['name']}' action return cannot use when/when_async")
        if context_source == "auth" and context_concept not in profile_concepts:
            raise ValueError(
                f"Rule '{rule_config['name']}' references auth.{context_concept}, "
                "but it is not a profile concept"
            )
        rules.append(FeelRule(
            concept=configured_concept,
            name=rule_config["name"],
            expression=expression,
            action=rule_config["action"],
            context_source=context_source,
            context_concept=context_concept,
            db_paths=db_paths,
            child_collections=_child_collections(context_concept, db_paths, concepts)
            if context_source == "db" else {},
            when=when,
            when_async=when_async,
        ))
    return rules


def generate_supabase_rules(ctx: Context) -> Dict[str, Dict[str, str]]:
    rules = discover_rules(ctx.rules_config, ctx.concepts, ctx.security_config)
    generated = {
        rule.name: {
            "index.ts": _generate_index_ts(rule),
            "deno.json": _generate_deno_json(),
        }
        for rule in rules
    }
    if ctx.workflow_config["_concept_workflow"]:
        generated["workflow-transition"] = {
            "index.ts": _generate_workflow_transition_ts(ctx, rules),
            "deno.json": _generate_deno_json(),
        }
        if ctx.security_config["authentication_required"]:
            generated["task-assigned-email"] = {
                "index.ts": _generate_task_assigned_email_ts(ctx),
                "deno.json": _generate_deno_json(),
            }
    return generated


def _context_paths(expression: str) -> List[str]:
    paths = _db_paths_with_py_mini_racer(expression)
    return sorted(path for path in paths if path.startswith(("db.", "auth.")))


def _db_paths_with_py_mini_racer(expression: str) -> List[str]:
    ctx = MiniRacer()
    ctx.eval(_bundle_text())
    ctx.eval(_VARIABLE_EXTRACTOR_JS)
    return ctx.call("get_variable_names", expression)


def _bundle_text() -> str:
    return (Path(__file__).parent / "gen-feelin-umd.js").read_text(encoding="utf-8")


_VARIABLE_EXTRACTOR_JS = r"""
function get_variable_names(expr) {
  var tree = feelin.parseExpression(expr);
  var out = [];
  var c = tree.cursor();
  (function walk() {
    do {
      var t = c.type && c.type.name;
      if (t === "PathExpression" || t === "VariableName") {
        out.push(expr.slice(c.from, c.to));
        continue;
      }
      if (c.firstChild()) { walk(); c.parent(); }
    } while (c.nextSibling());
  })();
  return Array.from(new Set(out));
}
"""


def _child_collections(
    context_concept: str,
    db_paths: List[str],
    concepts: List[Dict[str, Any]],
) -> Dict[str, str]:
    child_by_plural = {}
    for concept in concepts:
        for field in concept["fields"]:
            if (
                field["type"] == "relation_to_one"
                and field.get("subtype") == "part_of"
                and field["target"] == context_concept
            ):
                child_by_plural[concept["plural_name"]] = concept["name"]

    requested = {}
    prefix = f"db.{context_concept}."
    for db_path in db_paths:
        if not db_path.startswith(prefix):
            continue
        tail = db_path[len(prefix):].split(".")[0]
        if tail in child_by_plural:
            requested[tail] = child_by_plural[tail]
    return requested


def _generate_deno_json() -> str:
    return json.dumps({
        "imports": {
            "@supabase/supabase-js": "npm:@supabase/supabase-js@2.89.0",
            "feelin": "npm:feelin@6.2.0",
        }
    }, indent=2) + "\n"


def _generate_index_ts(rule: FeelRule) -> str:
    child_loaders = "\n".join(
        _child_loader_ts(collection_name, child_table, rule.context_concept)
        for collection_name, child_table in rule.child_collections.items()
    )
    expression_json = json.dumps(rule.expression)
    context_concept_json = json.dumps(rule.context_concept)
    context_source_json = json.dumps(rule.context_source)
    action_json = json.dumps(rule.action)
    return f"""import {{ createClient }} from "@supabase/supabase-js";
import {{ evaluate }} from "feelin";

const RULE_EXPRESSION = {expression_json};
const CONTEXT_SOURCE = {context_source_json};
const CONTEXT_CONCEPT = {context_concept_json};
const RULE_ACTION = {action_json};

Deno.serve(async (req) => {{
  if (req.method !== "POST") {{
    return jsonResponse({{ error: "Method not allowed" }}, 405);
  }}

  const authorization = req.headers.get("Authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) {{
    return jsonResponse({{ error: "Missing bearer token" }}, 401);
  }}

  const supabaseUrl = requiredEnv("SUPABASE_URL");
  const anonKey = requiredEnv("SUPABASE_ANON_KEY");

  const userClient = createClient(supabaseUrl, anonKey, {{
    global: {{ headers: {{ Authorization: authorization }} }},
  }});

  const db: Record<string, any> = {{}};
  const auth: Record<string, any> = {{}};
  let id: unknown = null;

  if (CONTEXT_SOURCE === "db") {{
    const body = await req.json().catch(() => ({{}}));
    id = body.id;
    if (id === undefined || id === null || id === "") {{
      return jsonResponse({{ error: "Missing id" }}, 400);
    }}

    const {{ data: rows, error: selectError }} = await userClient
      .from(CONTEXT_CONCEPT)
      .select("*")
      .eq("id", id)
      .limit(2);

    if (selectError) {{
      return jsonResponse({{ error: selectError.message }}, 400);
    }}
    if (!rows || rows.length !== 1) {{
      return jsonResponse({{ error: "Expected exactly one accessible record", count: rows?.length ?? 0 }}, 403);
    }}
    db[CONTEXT_CONCEPT] = rows[0];
  }} else if (CONTEXT_SOURCE === "auth") {{
    const {{ data: authData, error: authError }} = await userClient.auth.getUser();
    if (authError || !authData.user) {{
      return jsonResponse({{ error: authError?.message ?? "Missing authenticated user" }}, 401);
    }}

    const {{ data: rows, error: selectError }} = await userClient
      .from(CONTEXT_CONCEPT)
      .select("*")
      .eq("_user", authData.user.id)
      .limit(2);

    if (selectError) {{
      return jsonResponse({{ error: selectError.message }}, 400);
    }}
    if (!rows || rows.length !== 1) {{
      return jsonResponse({{ error: "Expected exactly one authenticated profile", count: rows?.length ?? 0 }}, 403);
    }}
    auth[CONTEXT_CONCEPT] = rows[0];
  }} else {{
    return jsonResponse({{ error: `Unsupported context source ${{CONTEXT_SOURCE}}` }}, 500);
  }}

{child_loaders}
  let evaluated;
  try {{
    evaluated = evaluate(RULE_EXPRESSION, {{ db, auth }});
  }} catch (error) {{
    return jsonResponse({{ error: error instanceof Error ? error.message : String(error) }}, 400);
  }}
  const updates = evaluated && typeof evaluated === "object" && "value" in evaluated
    ? evaluated.value
    : evaluated;

  if (RULE_ACTION === "return") {{
    return jsonResponse({{ data: updates }});
  }}

  if (RULE_ACTION === "check") {{
    if (updates === true) {{
      return jsonResponse({{ data: true }});
    }}
    if (updates && typeof updates === "object" && !Array.isArray(updates) && "error" in updates) {{
      return jsonResponse(updates, 422);
    }}
    if (updates === false) {{
      return jsonResponse({{ error: "Rule check failed" }}, 422);
    }}
    return jsonResponse({{ error: "Check rule must return true, false, or an object with error" }}, 400);
  }}

  if (!updates || typeof updates !== "object" || Array.isArray(updates)) {{
    return jsonResponse({{ error: "Rule must return an object" }}, 400);
  }}

  const serviceRoleKey = requiredEnv("SUPABASE_SERVICE_ROLE_KEY");
  const serviceClient = createClient(supabaseUrl, serviceRoleKey);
  const {{ data: updatedRows, error: updateError }} = await serviceClient
    .from(CONTEXT_CONCEPT)
    .update(updates)
    .eq("id", id)
    .select("*")
    .limit(2);

  if (updateError) {{
    return jsonResponse({{ error: updateError.message }}, 400);
  }}
  if (!updatedRows || updatedRows.length !== 1) {{
    return jsonResponse({{ error: "Expected exactly one updated record", count: updatedRows?.length ?? 0 }}, 500);
  }}

  return jsonResponse({{ data: updatedRows[0], updates }});
}});

function requiredEnv(name: string): string {{
  const value = Deno.env.get(name);
  if (!value) {{
    throw new Error(`Missing environment variable ${{name}}`);
  }}
  return value;
}}

function jsonResponse(body: unknown, status = 200): Response {{
  return new Response(JSON.stringify(body), {{
    status,
    headers: {{ "Content-Type": "application/json" }},
  }});
}}
"""


def _child_loader_ts(collection_name: str, child_table: str, fk_field: str) -> str:
    safe_collection = re.sub(r"[^a-zA-Z0-9_]", "_", collection_name)
    return f"""
  const {{ data: {safe_collection}Rows, error: {safe_collection}Error }} = await userClient
    .from({json.dumps(child_table)})
    .select("*")
    .eq({json.dumps(fk_field)}, id);
  if ({safe_collection}Error) {{
    return jsonResponse({{ error: {safe_collection}Error.message }}, 400);
  }}
  db[CONTEXT_CONCEPT][{json.dumps(collection_name)}] = {safe_collection}Rows ?? [];
"""


def generate_async_rule_execution_sql(ctx: Context) -> List[str]:
    rules = discover_rules(ctx.rules_config, ctx.concepts, ctx.security_config)
    statements = []
    for rule in rules:
        for expression in rule.when_async:
            if rule.context_source != "db":
                raise ValueError(
                    f"Rule '{rule.name}' when_async is only supported for db contexts"
                )
            state_name = _parse_async_when(expression)
            statements.append(_generate_on_db_change_sql(rule, rule.context_concept, state_name))
    if not statements:
        return []
    return ["CREATE EXTENSION IF NOT EXISTS pg_net;"] + statements


def _parse_async_when(expression: str) -> str | None:
    if expression == "on_change":
        return None
    match = re.fullmatch(r"on_change_in_state_([a-zA-Z_][a-zA-Z0-9_]*)", expression)
    if not match:
        raise ValueError(f"Unsupported when_async expression: {expression}")
    return match.group(1)


def _generate_on_db_change_sql(rule: FeelRule, concept_name: str, state_name: str | None) -> str:
    # One trigger per when_async expression: the state must be part of the name,
    # otherwise a rule with several on_change_in_state_* entries would generate
    # same-named triggers and the last DROP+CREATE would silently win.
    state_suffix = f"_{_safe_sql_name(state_name)}" if state_name else ""
    function_name = f"02_enqueue_rule_{_safe_sql_name(rule.name)}{state_suffix}_trigger_function"
    trigger_name = f"02_enqueue_rule_{_safe_sql_name(rule.name)}{state_suffix}_trigger"
    function_url_path = f"/functions/v1/{rule.name}"
    state_guard = ""
    if state_name is not None:
        state_guard = f"""
    IF NEW."state" IS DISTINCT FROM {_sql_literal(state_name)} THEN
        RETURN NEW;
    END IF;
"""
    return f"""
CREATE OR REPLACE FUNCTION {_quote_ident(function_name)}()
RETURNS TRIGGER AS $$
DECLARE
    claims JSONB := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
    headers JSONB := nullif(current_setting('request.headers', true), '')::jsonb;
    auth_header TEXT;
    api_key TEXT;
    request_headers JSONB;
    supabase_url TEXT := coalesce(
        nullif(current_setting('app.settings.supabase_url', true), ''),
        nullif(current_setting('app.settings.api_url', true), ''),
        'http://kong:8000'
    );
BEGIN
    IF current_role <> 'authenticated'
       OR claims IS NULL
       OR claims ->> 'role' <> 'authenticated'
    THEN
        RETURN NEW;
    END IF;
{state_guard}

    auth_header := headers ->> 'authorization';
    IF auth_header IS NULL OR auth_header = '' THEN
        RETURN NEW;
    END IF;
    request_headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', auth_header
    );
    api_key := headers ->> 'apikey';
    IF api_key IS NOT NULL AND api_key <> '' THEN
        request_headers := request_headers || jsonb_build_object('apikey', api_key);
    END IF;

    PERFORM net.http_post(
        url := supabase_url || {_sql_literal(function_url_path)},
        headers := request_headers,
        body := jsonb_build_object('id', NEW."id"),
        timeout_milliseconds := 10000
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS {_quote_ident(trigger_name)} ON {_quote_ident(concept_name)};
CREATE TRIGGER {_quote_ident(trigger_name)}
AFTER INSERT OR UPDATE ON {_quote_ident(concept_name)}
FOR EACH ROW
EXECUTE FUNCTION {_quote_ident(function_name)}();
"""


def _generate_workflow_transition_ts(ctx: Context, rules: List[FeelRule]) -> str:
    workflows_json = json.dumps(ctx.workflow_config["_concept_workflow"], indent=2)
    validations_json = json.dumps(ctx.validations_config.get("validations", []), indent=2)
    rules_json = json.dumps([
        {
            "name": rule.name,
            "concept": rule.concept,
            "action": rule.action,
            "when": rule.when,
        }
        for rule in rules
        if rule.when
    ], indent=2)
    return f"""import {{ createClient }} from "@supabase/supabase-js";

const WORKFLOWS = {workflows_json};
const VALIDATIONS = {validations_json};
const RULES = {rules_json};

Deno.serve(async (req) => {{
  if (req.method !== "POST") {{
    return jsonResponse({{ error: "Method not allowed" }}, 405);
  }}

  const authorization = req.headers.get("Authorization") ?? "";
  const apiKey = req.headers.get("apikey") ?? "";
  if (!authorization.startsWith("Bearer ")) {{
    return jsonResponse({{ error: "Missing bearer token" }}, 401);
  }}

  const {{ concept, id, to_state: toState, comment = null }} = await req.json().catch(() => ({{}}));
  if (!concept || id === undefined || id === null || !toState) {{
    return jsonResponse({{ error: "Missing concept, id, or to_state" }}, 400);
  }}
  if (!WORKFLOWS[concept]) {{
    return jsonResponse({{ error: `Concept ${{concept}} has no workflow` }}, 400);
  }}
  if (!WORKFLOWS[concept].states?.some((state: {{ name: string }}) => state.name === toState)) {{
    return jsonResponse({{ error: `Unknown workflow state ${{toState}} for ${{concept}}` }}, 400);
  }}

  const supabaseUrl = requiredEnv("SUPABASE_URL");
  const anonKey = requiredEnv("SUPABASE_ANON_KEY");
  const serviceRoleKey = requiredEnv("SUPABASE_SERVICE_ROLE_KEY");
  const userClient = createClient(supabaseUrl, anonKey, {{
    global: {{ headers: {{ Authorization: authorization }} }},
  }});
  const serviceClient = createClient(supabaseUrl, serviceRoleKey);

  const {{ data: authData, error: authError }} = await userClient.auth.getUser();
  if (authError || !authData.user) {{
    return jsonResponse({{ error: authError?.message ?? "Missing authenticated user" }}, 401);
  }}

  const {{ data: rows, error: selectError }} = await userClient
    .from(concept)
    .select("*")
    .eq("id", id)
    .limit(2);
  if (selectError) {{
    return jsonResponse({{ error: selectError.message }}, 400);
  }}
  if (!rows || rows.length !== 1) {{
    return jsonResponse({{ error: "Expected exactly one accessible record", count: rows?.length ?? 0 }}, 403);
  }}
  const record = rows[0];
  const validationError = validateRecord(concept, record);
  if (validationError) {{
    return jsonResponse({{ ok: false, ...validationError }});
  }}
  const currentStateName = record.state ?? WORKFLOWS[concept].states[0]?.name;
  const currentState = WORKFLOWS[concept].states.find((state: {{ name: string }}) => state.name === currentStateName);
  const userRoles = Array.isArray(authData.user.app_metadata?.roles) ? authData.user.app_metadata.roles : [];
  if (!currentState?.owners?.some((role: string) => userRoles.includes(role))) {{
    return jsonResponse({{ error: `Insufficient privilege for state ${{currentStateName}}` }}, 403);
  }}

  const transitionRules = RULES.filter((rule) =>
    rule.concept === concept && rule.when.includes(`on_state_changed_to_${{toState}}`)
  );
  for (const rule of transitionRules) {{
    const {{ status, body }} = await callRule(supabaseUrl, apiKey, authorization, rule.name, id);
    if (status >= 400) {{
      if (rule.action === "check") {{
        return jsonResponse({{
          ok: false,
          error: body?.error ?? `Rule ${{rule.name}} failed`,
          rule: rule.name,
        }});
      }}
      return jsonResponse({{
        error: body?.error ?? `Rule ${{rule.name}} failed`,
        rule: rule.name,
      }}, status);
    }}
    if (rule.action === "check" && body?.data !== true) {{
      return jsonResponse({{
        ok: false,
        error: body?.error ?? `Rule ${{rule.name}} failed`,
        rule: rule.name,
      }});
    }}
  }}

  const stateInfo = {{
    last_transition: {{
      to_state: toState,
      comment,
      changed_at: new Date().toISOString(),
    }},
  }};
  // Task assignment belongs to the state: entering a state clears the task
  // owner back to the assignable pool unless the state retains it.
  const toStateConfig = WORKFLOWS[concept].states.find((state: {{ name: string }}) => state.name === toState);
  const update: Record<string, unknown> = {{ state: toState, state_info: stateInfo }};
  if (!toStateConfig?.retain_task_owner) {{
    update.state_task_owner = null;
  }}
  const {{ data: updatedRows, error: updateError }} = await serviceClient
    .from(concept)
    .update(update)
    .eq("id", id)
    .select("*")
    .limit(2);

  if (updateError) {{
    return jsonResponse({{ error: updateError.message }}, 400);
  }}
  if (!updatedRows || updatedRows.length !== 1) {{
    return jsonResponse({{ error: "Expected exactly one updated record", count: updatedRows?.length ?? 0 }}, 500);
  }}

  return jsonResponse({{ ok: true, data: updatedRows[0], rules: transitionRules.map((rule) => rule.name) }});
}});

async function callRule(supabaseUrl: string, apiKey: string, authorization: string, ruleName: string, id: unknown) {{
  const response = await fetch(`${{supabaseUrl}}/functions/v1/${{ruleName}}`, {{
    method: "POST",
    headers: {{
      "Content-Type": "application/json",
      "Authorization": authorization,
      ...(apiKey ? {{ "apikey": apiKey }} : {{}}),
    }},
    body: JSON.stringify({{ id }}),
  }});
  const text = await response.text();
  let body: any = null;
  try {{
    body = text ? JSON.parse(text) : null;
  }} catch {{
    body = text;
  }}
  return {{ status: response.status, body }};
}}

function validateRecord(concept: string, record: Record<string, any>) {{
  const validations = VALIDATIONS.filter((validation: any) => validation.concept === concept);
  for (const validation of validations) {{
    const complete = validation.columns.every((column: string) =>
      record[column] !== undefined && record[column] !== null && record[column] !== ""
    );
    if (!complete) {{
      continue;
    }}
    const matches = compatibleRows(validation, record).some((row: string[]) =>
      validation.columns.every((column: string, index: number) =>
        row[index] === "*" || record[column] === row[index]
      )
    );
    if (!matches) {{
      const labels = validation.columns.map((column: string) => column.replaceAll("_", " ")).join(", ");
      return {{
        error: `Validation failed for ${{validation.name}}: ${{labels}}`,
        validation: validation.name,
        concept,
        fields: validation.columns,
      }};
    }}
  }}
  return null;
}}

function compatibleRows(validation: any, values: Record<string, any>) {{
  let rows = validation.rows;
  validation.columns.forEach((column: string, index: number) => {{
    const value = values[column];
    if (value === undefined || value === null || value === "") return;
    if (rows.some((row: string[]) => row[index] === value)) {{
      rows = rows.filter((row: string[]) => row[index] === value);
    }} else {{
      rows = rows.filter((row: string[]) => row[index] === "*");
    }}
  }});
  return rows;
}}

function requiredEnv(name: string): string {{
  const value = Deno.env.get(name);
  if (!value) {{
    throw new Error(`Missing environment variable ${{name}}`);
  }}
  return value;
}}

function jsonResponse(body: unknown, status = 200): Response {{
  return new Response(JSON.stringify(body), {{
    status,
    headers: {{ "Content-Type": "application/json" }},
  }});
}}
"""


def _generate_task_assigned_email_ts(ctx: Context) -> str:
    """Edge function that emails the new task owner of a workflow record.

    Invoked by the 02_notify_task_assignment DB trigger (pg_net) with the
    assigner's Authorization header. SMTP and app URL come from environment
    variables when set (production docker-compose) and fall back to the
    generated development values (SMTP mock, dev frontend URL).
    """
    smtp = ctx.system_config.get("smtp", {})
    smtp_host = smtp.get("host", "127.0.0.1")
    if smtp_host in ("127.0.0.1", "localhost"):
        # Reach the host's dev SMTP mock from the edge runtime container.
        smtp_host = "172.17.0.1"
        smtp_port = dev_ports.SMTP
    else:
        smtp_port = smtp.get("port", 25)
    smtp_from = smtp.get("from_email", "noreply@localhost")
    smtp_user = smtp.get("user") or ""
    smtp_pass = smtp.get("password") or ""
    base_uri = ctx.deployment_config.get("base_uri", "/")
    dev_app_base_url = f"http://localhost:{dev_ports.FRONTEND}{base_uri}"

    workflow_concepts_json = json.dumps(sorted(ctx.workflow_config["_concept_workflow"].keys()))
    return f"""import {{ createClient }} from "@supabase/supabase-js";

const WORKFLOW_CONCEPTS = new Set({workflow_concepts_json});
const SMTP_HOST = Deno.env.get("SMTP_HOST") || {json.dumps(smtp_host)};
const SMTP_PORT = Number(Deno.env.get("SMTP_PORT") || {json.dumps(str(smtp_port))});
const SMTP_USER = Deno.env.get("SMTP_USER") ?? {json.dumps(smtp_user)};
const SMTP_PASS = Deno.env.get("SMTP_PASS") ?? {json.dumps(smtp_pass)};
const SMTP_FROM = Deno.env.get("SMTP_FROM") || {json.dumps(smtp_from)};
const SMTP_TLS = (Deno.env.get("SMTP_TLS") || "false") === "true";
const APP_BASE_URL = Deno.env.get("APP_BASE_URL") || {json.dumps(dev_app_base_url)};

Deno.serve(async (req) => {{
  if (req.method !== "POST") {{
    return jsonResponse({{ error: "Method not allowed" }}, 405);
  }}

  const authorization = req.headers.get("Authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) {{
    return jsonResponse({{ error: "Missing bearer token" }}, 401);
  }}

  const {{ concept, id }} = await req.json().catch(() => ({{}}));
  if (!concept || id === undefined || id === null) {{
    return jsonResponse({{ error: "Missing concept or id" }}, 400);
  }}
  if (!WORKFLOW_CONCEPTS.has(concept)) {{
    return jsonResponse({{ error: `Concept ${{concept}} has no workflow` }}, 400);
  }}

  const supabaseUrl = requiredEnv("SUPABASE_URL");
  const anonKey = requiredEnv("SUPABASE_ANON_KEY");
  const serviceRoleKey = requiredEnv("SUPABASE_SERVICE_ROLE_KEY");

  const userClient = createClient(supabaseUrl, anonKey, {{
    global: {{ headers: {{ Authorization: authorization }} }},
  }});
  const {{ data: authData, error: authError }} = await userClient.auth.getUser();
  if (authError || !authData.user) {{
    return jsonResponse({{ error: authError?.message ?? "Missing authenticated user" }}, 401);
  }}
  const actorEmail = (authData.user.email ?? "").toLowerCase();

  // Re-read the record: the notification always goes to the *current* task
  // owner, so a forged body cannot direct mail to arbitrary addresses.
  const serviceClient = createClient(supabaseUrl, serviceRoleKey);
  const {{ data: record, error: selectError }} = await serviceClient
    .from(concept)
    .select("id, state, state_task_owner")
    .eq("id", id)
    .maybeSingle();
  if (selectError) {{
    return jsonResponse({{ error: selectError.message }}, 400);
  }}
  const ownerEmail = (record?.state_task_owner ?? "").toLowerCase();
  if (!ownerEmail || ownerEmail === actorEmail) {{
    return jsonResponse({{ ok: true, skipped: true }});
  }}

  const editUrl = `${{APP_BASE_URL}}#/admin/${{concept}}/${{id}}`;
  await sendSmtpMail({{
    to: ownerEmail,
    subject: `Task assigned to you: ${{concept}} #${{id}}`,
    body: [
      `${{actorEmail}} assigned you a workflow task.`,
      ``,
      `Record: ${{concept}} #${{id}} (state: ${{record.state}})`,
      `Edit it at: ${{editUrl}}`,
    ].join("\\r\\n"),
  }});

  return jsonResponse({{ ok: true, to: ownerEmail }});
}});

// Minimal SMTP client (EHLO / AUTH LOGIN / MAIL / RCPT / DATA) over a raw
// socket: the edge runtime cannot load remote deno.land modules and the needs
// here (plain text mail to one recipient) do not justify a dependency.
// TLS is connection-level (SMTP_TLS); STARTTLS is not supported.
async function sendSmtpMail({{ to, subject, body }}: {{ to: string; subject: string; body: string }}) {{
  const conn = SMTP_TLS
    ? await Deno.connectTls({{ hostname: SMTP_HOST, port: SMTP_PORT }})
    : await Deno.connect({{ hostname: SMTP_HOST, port: SMTP_PORT }});
  const reader = conn.readable.getReader();
  const writer = conn.writable.getWriter();
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  // Reads one SMTP reply (multiline replies end with "NNN " on the last line).
  async function readReply(): Promise<string> {{
    let data = "";
    while (true) {{
      const {{ value, done }} = await reader.read();
      if (done) return data;
      data += decoder.decode(value);
      const lines = data.split("\\r\\n").filter((line) => line.length > 0);
      if (lines.length && /^\\d{{3}} /.test(lines[lines.length - 1])) return data;
    }}
  }}

  async function command(line: string | null, expectedCode: string): Promise<void> {{
    if (line !== null) await writer.write(encoder.encode(line + "\\r\\n"));
    const reply = await readReply();
    if (!reply.startsWith(expectedCode)) {{
      throw new Error(`SMTP error (expected ${{expectedCode}}): ${{reply.trim()}}`);
    }}
  }}

  try {{
    await command(null, "220");
    await command("EHLO localhost", "250");
    if (SMTP_USER) {{
      await command("AUTH LOGIN", "334");
      await command(btoa(SMTP_USER), "334");
      await command(btoa(SMTP_PASS), "235");
    }}
    await command(`MAIL FROM:<${{SMTP_FROM}}>`, "250");
    await command(`RCPT TO:<${{to}}>`, "250");
    await command("DATA", "354");
    const message = [
      `From: ${{SMTP_FROM}}`,
      `To: ${{to}}`,
      `Subject: ${{subject}}`,
      `Date: ${{new Date().toUTCString()}}`,
      `MIME-Version: 1.0`,
      `Content-Type: text/plain; charset=utf-8`,
      ``,
      body,
    ].join("\\r\\n").replace(/\\r\\n\\./g, "\\r\\n.."); // dot-stuffing
    await command(message + "\\r\\n.", "250");
    await writer.write(encoder.encode("QUIT\\r\\n"));
  }} finally {{
    try {{ conn.close(); }} catch {{ /* already closed */ }}
  }}
}}

function requiredEnv(name: string): string {{
  const value = Deno.env.get(name);
  if (!value) {{
    throw new Error(`Missing environment variable ${{name}}`);
  }}
  return value;
}}

function jsonResponse(body: unknown, status = 200): Response {{
  return new Response(JSON.stringify(body), {{
    status,
    headers: {{ "Content-Type": "application/json" }},
  }});
}}
"""


def _safe_sql_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", value)


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
