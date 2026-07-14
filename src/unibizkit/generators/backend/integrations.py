import json
from pathlib import Path

from .context import Context
from .backend_functions import generate_action_function


def generate_integration_sql(ctx: Context) -> list[str]:
    config = ctx.integrations_config
    if not config["integrations"]:
        return []
    return ["""
CREATE EXTENSION IF NOT EXISTS pg_net;
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE INDEX "integration_runs_integration_requested_idx"
  ON "_integration_run" ("integration", "requested_at" DESC);

CREATE TABLE "_integration_scheduler_secret" (
  "id" BOOLEAN PRIMARY KEY DEFAULT true CHECK (id),
  "token" TEXT NOT NULL
);
REVOKE ALL ON "_integration_scheduler_secret" FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public._reconcile_integration_cron()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
  job record;
  integration record;
  command text;
BEGIN
  FOR job IN
    SELECT jobid
      FROM cron.job
     WHERE jobname LIKE '\\_integration\\_%' ESCAPE '\\'
        OR jobname LIKE 'ubk\\_integration\\_%' ESCAPE '\\'
  LOOP
    PERFORM cron.unschedule(job.jobid);
  END LOOP;

  FOR integration IN
    SELECT name, schedule
      FROM public._integration
     WHERE NULLIF(schedule, '') IS NOT NULL
     ORDER BY name
  LOOP
    command := format(
      $command$SELECT net.http_post(
        url := 'http://kong:8000/functions/v1/integration-run',
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'X-UBK-Scheduler-Token',
          (SELECT token FROM public._integration_scheduler_secret WHERE id = true)
        ),
        body := %L::jsonb,
        timeout_milliseconds := 30000
      );$command$,
      jsonb_build_object('integration', integration.name, 'trigger', 'scheduled')::text
    );
    PERFORM cron.schedule('_integration_' || integration.name, integration.schedule, command);
  END LOOP;
END;
$function$;
REVOKE ALL ON FUNCTION public._reconcile_integration_cron() FROM PUBLIC;
"""]


def generate_integration_function(ctx: Context) -> dict[str, dict[str, str]]:
    items = ctx.integrations_config["integrations"]
    if not items:
        return {}
    imports = []
    dispatch = []
    files: dict[str, str] = {}
    definitions = {}
    for index, item in enumerate(items):
        alias = f"fetchPage{index}"
        filename = f"sources/{Path(item['source']).name}"
        imports.append(f'import {{ fetchPage as {alias} }} from "./{filename}";')
        dispatch.append(f"  {json.dumps(item['name'])}: {alias},")
        definitions[item["name"]] = {
            "target": item["target_concept"],
            "expression": item["transform"],
            "onRemovedField": item["on_removed"].get("set_false") if isinstance(item["on_removed"], dict) else None,
        }
        files[filename] = (ctx.model_dir / "backend" / "integrations" / item["source"]).read_text(encoding="utf-8")
    roles = json.dumps(ctx.integrations_config["roles"])
    files["deno.json"] = json.dumps({
        "imports": {
            "@supabase/supabase-js": "npm:@supabase/supabase-js@2.89.0",
            "feelin": "npm:feelin@6.2.0",
            "croner": "npm:croner@9.1.0",
        },
    }, indent=2) + "\n"
    files["index.ts"] = f'''import {{ createClient }} from "@supabase/supabase-js";
import {{ evaluate }} from "feelin";
import {{ Cron }} from "croner";
{chr(10).join(imports)}

const FETCHERS: Record<string, Function> = {{
{chr(10).join(dispatch)}
}};
const DEFINITIONS: Record<string, {{ target: string; expression: string; onRemovedField: string | null }}> = {json.dumps(definitions)};
const OPERATION_ROLES = new Set({roles});

Deno.serve(async (req) => {{
  if (req.method !== "POST") return response({{ status: "ko", message: "Method not allowed" }}, 405);
  const body = await req.json().catch(() => ({{}}));
  let name = typeof body.integration === "string" ? body.integration : null;
  const requestedId = body.id;
  const scheduled = body.trigger === "scheduled";
  const schedulerToken = Deno.env.get("INTEGRATION_SCHEDULER_TOKEN") ?? "";
  const authorization = req.headers.get("Authorization") ?? "";
  const url = required("SUPABASE_URL");
  const service = createClient(url, required("SUPABASE_SERVICE_ROLE_KEY"));
  let requestedBy: string | null = null;
  if (scheduled) {{
    if (!schedulerToken || req.headers.get("X-UBK-Scheduler-Token") !== schedulerToken) return response({{ status: "ko", message: "Forbidden" }}, 403);
  }} else {{
    if (!authorization.startsWith("Bearer ")) return response({{ status: "ko", message: "Missing bearer token" }}, 401);
    const userClient = createClient(url, required("SUPABASE_ANON_KEY"), {{ global: {{ headers: {{ Authorization: authorization }} }} }});
    const {{ data, error }} = await userClient.auth.getUser();
    const roles = data.user?.app_metadata?.roles ?? [];
    if (error || !data.user || !roles.some((role: string) => OPERATION_ROLES.has(role))) return response({{ status: "ko", message: "Forbidden" }}, 403);
    requestedBy = data.user.email ?? data.user.id;
  }}
  if (!name && requestedId !== undefined && requestedId !== null) {{
    const {{ data: selected }} = await service.from("_integration").select("name").eq("id", requestedId).single();
    name = selected?.name ?? null;
  }}
  if (!name || !FETCHERS[name]) return response({{ status: "ko", message: "Unknown integration" }}, 404);
  const definition = DEFINITIONS[name];
  const {{ data: integration, error: loadError }} = await service.from("_integration").select("*").eq("name", name).single();
  if (loadError || !integration) return response({{ status: "ko", message: loadError?.message ?? "Missing integration" }}, 500);
  if (integration.operational_status === "paused") {{
    const reason = "paused";
    const completed = new Date().toISOString();
    const {{ data: skippedRun, error: skippedError }} = await service.from("_integration_run").insert({{
      integration: integration.id, trigger: scheduled ? "scheduled" : "manual", requested_by: requestedBy,
      requested_at: completed, status: "skipped", started_at: completed, completed_at: completed,
      checkpoint_before: integration.checkpoint, checkpoint_after: integration.checkpoint, error: reason,
    }}).select("id").single();
    if (skippedError) return response({{ status: "ko", message: skippedError.message }}, 500);
    await service.from("_integration").update({{ last_started_at: completed, last_completed_at: completed, last_status: "skipped", last_error: reason }}).eq("id", integration.id);
    return response({{ status: "ko", message: `Integration ${{reason}}`, run_id: skippedRun.id }});
  }}
  const nextExecution = integration.schedule ? new Cron(integration.schedule, {{ timezone: "UTC" }}).nextRun()?.toISOString() ?? null : null;
  const leaseOwner = crypto.randomUUID();
  const now = new Date();
  const leaseUntil = new Date(now.getTime() + 30 * 60_000).toISOString();
  const {{ data: claimed }} = await service.from("_integration").update({{ lease_owner: leaseOwner, lease_expires_at: leaseUntil, last_started_at: now.toISOString(), last_status: "running", next_execution_at: nextExecution }})
    .eq("id", integration.id).or(`lease_expires_at.is.null,lease_expires_at.lt.${{now.toISOString()}}`).select("id");
  if (!claimed?.length) return response({{ status: "ko", message: "Integration is already running" }});
  const {{ data: run, error: runError }} = await service.from("_integration_run").insert({{
    integration: integration.id, trigger: scheduled ? "scheduled" : "manual", requested_by: requestedBy,
    requested_at: now.toISOString(), status: "running", started_at: now.toISOString(), checkpoint_before: integration.checkpoint,
  }}).select("id").single();
  if (runError) return response({{ status: "ko", message: runError.message }}, 500);
  let cursor: unknown = null;
  let checkpoint = integration.checkpoint;
  let pages = 0, received = 0, upserted = 0, removed = 0;
  try {{
    while (true) {{
      const page = await FETCHERS[name]({{ cursor, checkpoint, pageSize: 100, config: {{}}, secrets: Deno.env.toObject() }});
      if (!page || !Array.isArray(page.items)) throw new Error("fetchPage must return an items array");
      pages += 1;
      for (const input of page.items) {{
        const wrapped = evaluate(definition.expression, {{ input }});
        const mapped = wrapped && typeof wrapped === "object" && "value" in wrapped ? wrapped.value : wrapped;
        if (!mapped || typeof mapped !== "object" || Array.isArray(mapped)) throw new Error("FEEL transform must return an object");
        if (typeof mapped._external_id !== "string" || !mapped._external_id) throw new Error("FEEL transform must return a non-empty string _external_id");
        const {{ error }} = await service.from(definition.target).upsert(mapped, {{ onConflict: "_external_id" }});
        if (error) throw new Error(error.message);
        received += 1; upserted += 1;
      }}
      const removedExternalIds = page.removedExternalIds ?? [];
      if (!Array.isArray(removedExternalIds) || removedExternalIds.some((id: unknown) => typeof id !== "string" || !id)) {{
        throw new Error("fetchPage removedExternalIds must be an array of non-empty strings");
      }}
      if (definition.onRemovedField && removedExternalIds.length) {{
        const ids = [...new Set<string>(removedExternalIds)];
        const {{ data, error }} = await service.from(definition.target)
          .update({{ [definition.onRemovedField]: false }})
          .in("_external_id", ids)
          .select("_external_id");
        if (error) throw new Error(error.message);
        removed += data?.length ?? 0;
      }}
      if (page.checkpoint !== undefined) checkpoint = page.checkpoint;
      if (page.complete || page.nextCursor == null) break;
      cursor = page.nextCursor;
    }}
    const completed = new Date().toISOString();
    await service.from("_integration_run").update({{ status: "completed", completed_at: completed, checkpoint_after: checkpoint, pages_count: pages, received_count: received, upserted_count: upserted, removed_count: removed }}).eq("id", run.id);
    await service.from("_integration").update({{ checkpoint, lease_owner: null, lease_expires_at: null, last_completed_at: completed, last_status: "completed", last_error: null, last_received_count: received, last_upserted_count: upserted, last_removed_count: removed }}).eq("id", integration.id).eq("lease_owner", leaseOwner);
    return response({{ status: "ok", message: `Received ${{received}} record(s), upserted ${{upserted}}, handled ${{removed}} removal(s)`, data: {{ run_id: run.id, pages, received, upserted, removed, checkpoint }} }});
  }} catch (error) {{
    const message = error instanceof Error ? error.message : String(error);
    const completed = new Date().toISOString();
    await service.from("_integration_run").update({{ status: "failed", completed_at: completed, pages_count: pages, received_count: received, upserted_count: upserted, error: message }}).eq("id", run.id);
    await service.from("_integration").update({{ lease_owner: null, lease_expires_at: null, last_completed_at: completed, last_status: "failed", last_error: message }}).eq("id", integration.id).eq("lease_owner", leaseOwner);
    return response({{ status: "ko", message, data: {{ run_id: run.id }} }}, 500);
  }}
}});

function required(name: string): string {{ const value = Deno.env.get(name); if (!value) throw new Error(`Missing environment variable ${{name}}`); return value; }}
function response(body: unknown, status = 200): Response {{ return new Response(JSON.stringify(body), {{ status, headers: {{ "Content-Type": "application/json" }} }}); }}
'''
    reset_checkpoint_js = f'''const OPERATION_ROLES = new Set({roles});

export async function run({{ ids, serviceClient, user }}) {{
  const roles = user.app_metadata?.roles ?? [];
  if (!roles.some((role) => OPERATION_ROLES.has(role))) {{
    return {{ status: "ko", message: "Forbidden" }};
  }}

  const uniqueIds = [...new Set(ids)];
  const leaseOwner = crypto.randomUUID();
  const now = new Date();
  const leaseUntil = new Date(now.getTime() + 60_000).toISOString();
  const {{ data: claimed, error: claimError }} = await serviceClient
    .from("_integration")
    .update({{ lease_owner: leaseOwner, lease_expires_at: leaseUntil }})
    .in("id", uniqueIds)
    .or(`lease_expires_at.is.null,lease_expires_at.lt.${{now.toISOString()}}`)
    .select("id,name");
  if (claimError) return {{ status: "ko", message: claimError.message }};

  if (claimed?.length !== uniqueIds.length) {{
    await serviceClient.from("_integration")
      .update({{ lease_owner: null, lease_expires_at: null }})
      .eq("lease_owner", leaseOwner);
    return {{ status: "ko", message: "One or more integrations are running or do not exist" }};
  }}

  const {{ error: resetError }} = await serviceClient
    .from("_integration")
    .update({{ checkpoint: null, lease_owner: null, lease_expires_at: null }})
    .eq("lease_owner", leaseOwner);
  if (resetError) {{
    await serviceClient.from("_integration")
      .update({{ lease_owner: null, lease_expires_at: null }})
      .eq("lease_owner", leaseOwner);
    return {{ status: "ko", message: resetError.message }};
  }}

  const names = claimed.map((integration) => integration.name).join(", ");
  return {{ status: "ok", message: `Checkpoint reset for ${{names}}` }};
}}
'''
    return {
        "integration-run": files,
        "integration-reset-checkpoint": generate_action_function(reset_checkpoint_js),
    }
