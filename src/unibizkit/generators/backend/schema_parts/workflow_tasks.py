from typing import Any, Dict, List


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def generate_workflow_tasks_view(workflow_config: Dict[str, Any], security_config: Dict[str, Any]) -> List[str]:
    """UNION view of all workflow concepts, backing the admin task list pages.

    security_invoker makes each branch run under the caller's RLS, so users
    only see the records they can already read. The 'assigners' column bakes
    the current state's assigner roles as text[], letting the assignable-tasks
    page filter server-side with a PostgREST array overlap (assigners=ov.{...}).
    """
    if not workflow_config["_concept_workflow"]:
        return []
    if not security_config["authentication_required"]:
        return []

    selects = []
    for concept_name, workflow in sorted(workflow_config["_concept_workflow"].items()):
        whens = "\n".join(
            f"      WHEN {_sql_literal(state['name'])} THEN "
            f"ARRAY[{', '.join(_sql_literal(role) for role in state['assigners'])}]::text[]"
            for state in workflow["states"]
        )
        selects.append(f"""SELECT
    {_sql_literal(concept_name)} || '-' || t."id"::text AS "id",
    {_sql_literal(concept_name)}::text AS "concept",
    t."id" AS "record_id",
    t."id_presentation",
    t."state",
    t."state_task_owner",
    CASE t."state"
{whens}
      ELSE ARRAY[]::text[]
    END AS "assigners",
    t."_updated_at"
  FROM {_quote_ident(concept_name)} t""")

    view_sql = (
        'CREATE VIEW "workflow_tasks" WITH (security_invoker = true) AS\n  '
        + "\nUNION ALL\n  ".join(selects)
        + ";"
    )
    return [view_sql]


def generate_user_directory(workflow_config: Dict[str, Any], security_config: Dict[str, Any]) -> List[str]:
    """Discovery cache of application users for workflow task assignment.

    Not a source of truth and never used for security decisions (the security
    triggers check the JWT roles): it only feeds the assignment autocomplete.
    It is populated by seeds ('seed'), by the access token hook on every login
    ('login'), and in the future by external directory synchronization.
    """
    if not workflow_config["_concept_workflow"]:
        return []
    if not security_config["authentication_required"]:
        return []

    return ["""
CREATE TABLE "user_directory" (
    "email"        TEXT PRIMARY KEY,
    "_user"        UUID,
    "roles"        JSONB NOT NULL DEFAULT '[]'::jsonb,
    "source"       TEXT NOT NULL,
    "last_seen_at" TIMESTAMP WITH TIME ZONE
);

-- Supports roles ?| array[...] and roles @> ... (PostgREST cs.) lookups.
CREATE INDEX "user_directory_roles_idx" ON "user_directory" USING GIN ("roles");

ALTER TABLE "user_directory" ENABLE ROW LEVEL SECURITY;

-- Read-only for the app: writes happen through the access token hook
-- (SECURITY DEFINER) and seed/service-role scripts only.
CREATE POLICY "authenticated_read_user_directory" ON "user_directory"
FOR SELECT
TO authenticated
USING (true);
"""]


def generate_task_assignment_email_triggers(
    workflow_config: Dict[str, Any],
    security_config: Dict[str, Any],
) -> List[str]:
    """Notify the new task owner by email when someone else assigns them a task.

    An AFTER UPDATE trigger on every workflow table posts to the
    task-assigned-email edge function (same pg_net pattern as async rules,
    forwarding the assigner's Authorization header). The edge function
    re-reads the record and sends the email over SMTP.
    """
    if not workflow_config["_concept_workflow"]:
        return []
    if not security_config["authentication_required"]:
        return []

    statements = ["CREATE EXTENSION IF NOT EXISTS pg_net;", """
CREATE OR REPLACE FUNCTION "02_notify_task_assignment_trigger_function"()
RETURNS TRIGGER AS $$
DECLARE
    claims JSONB := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
    headers JSONB := nullif(current_setting('request.headers', true), '')::jsonb;
    actor_email TEXT;
    auth_header TEXT;
    api_key TEXT;
    request_headers JSONB;
    supabase_url TEXT := coalesce(
        nullif(current_setting('app.settings.supabase_url', true), ''),
        nullif(current_setting('app.settings.api_url', true), ''),
        'http://kong:8000'
    );
BEGIN
    IF NEW."state_task_owner" IS NULL
       OR NEW."state_task_owner" IS NOT DISTINCT FROM OLD."state_task_owner"
    THEN
        RETURN NEW;
    END IF;

    -- Only notify on changes made by an authenticated user who is not the
    -- new owner (self-assignment needs no notification).
    IF claims IS NULL OR claims ->> 'role' <> 'authenticated' THEN
        RETURN NEW;
    END IF;
    actor_email := lower(claims ->> 'email');
    IF actor_email IS NULL OR actor_email = lower(NEW."state_task_owner") THEN
        RETURN NEW;
    END IF;

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
        url := supabase_url || '/functions/v1/task-assigned-email',
        headers := request_headers,
        body := jsonb_build_object('concept', TG_TABLE_NAME, 'id', NEW."id"),
        timeout_milliseconds := 10000
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""]

    for concept_name in workflow_config["_concept_workflow"]:
        statements.append(f"""
DROP TRIGGER IF EXISTS "02_notify_task_assignment_trigger" ON {_quote_ident(concept_name)};
CREATE TRIGGER "02_notify_task_assignment_trigger"
AFTER UPDATE ON {_quote_ident(concept_name)}
FOR EACH ROW
EXECUTE FUNCTION "02_notify_task_assignment_trigger_function"();
""")

    return statements
