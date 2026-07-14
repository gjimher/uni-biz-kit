import json
from pathlib import Path

from .context import Context


def function_name(source: str) -> str:
    return Path(source).stem.lstrip("_")


def generate_backend_actions(ctx: Context) -> dict[str, dict[str, str]]:
    generated = {}
    sources = {
        action["source"]
        for concept in ctx.concepts
        for action in concept.get("actions", [])
        if not Path(action["source"]).name.startswith("_")
    }
    for source in sorted(sources):
        name = function_name(source)
        if name in generated:
            raise ValueError(f"Backend action function name collision: {name}")
        generated[name] = generate_action_function(
            (ctx.model_dir / "backend" / "actions" / source).read_text(encoding="utf-8")
        )
    return generated


def generate_action_function(function_js: str) -> dict[str, str]:
    """Wrap a model or generated action in the shared authenticated contract."""
    return {
        "index.ts": _index_ts(),
        "function.js": function_js,
        "deno.json": json.dumps({
            "imports": {
                "@supabase/supabase-js": "npm:@supabase/supabase-js@2.89.0",
            },
        }, indent=2) + "\n",
    }


def _index_ts() -> str:
    return '''import { createClient } from "@supabase/supabase-js";
import { run } from "./function.js";

Deno.serve(async (req) => {
  if (req.method !== "POST") return jsonResponse({ status: "ko", message: "Method not allowed" }, 405);
  const authorization = req.headers.get("Authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) return jsonResponse({ status: "ko", message: "Missing bearer token" }, 401);
  const url = required("SUPABASE_URL");
  const userClient = createClient(url, required("SUPABASE_ANON_KEY"), { global: { headers: { Authorization: authorization } } });
  const { data, error } = await userClient.auth.getUser();
  if (error || !data.user) return jsonResponse({ status: "ko", message: error?.message ?? "Missing authenticated user" }, 401);
  const body = await req.json().catch(() => ({}));
  const ids = Array.isArray(body.ids) ? body.ids : body.id !== undefined && body.id !== null ? [body.id] : [];
  if (!ids.length) return jsonResponse({ status: "ko", message: "At least one record id is required" }, 400);
  try {
    const result = await run({
      id: ids.length === 1 ? ids[0] : null,
      ids,
      supabase: userClient,
      serviceClient: createClient(url, required("SUPABASE_SERVICE_ROLE_KEY")),
      user: data.user,
    });
    if (!result || !["ok", "ko"].includes(result.status) || (result.message !== undefined && typeof result.message !== "string")) {
      return jsonResponse({ status: "ko", message: "Backend function must return { status: 'ok'|'ko', message?: string }" }, 500);
    }
    return jsonResponse(result);
  } catch (error) {
    return jsonResponse({ status: "ko", message: error instanceof Error ? error.message : String(error) }, 500);
  }
});

function required(name: string): string { const value = Deno.env.get(name); if (!value) throw new Error(`Missing environment variable ${name}`); return value; }
function jsonResponse(body: unknown, status = 200): Response { return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }); }
'''
