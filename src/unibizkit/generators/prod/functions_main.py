def generate() -> str:
    """Main-service router for the self-hosted edge runtime: dispatches
    /<function-name>/... (Kong already stripped /functions/v1) to a user
    worker running that function, forwarding the process env (SUPABASE_URL,
    keys, ...) to the worker."""
    return """\
// UniBizKit edge functions main router (self-hosted edge-runtime entrypoint).
Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  const serviceName = url.pathname.split("/")[1];
  if (!serviceName) {
    return new Response(
      JSON.stringify({ error: "missing function name in path" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }
  const servicePath = `/home/deno/functions/${serviceName}`;
  try {
    const worker = await EdgeRuntime.userWorkers.create({
      servicePath,
      memoryLimitMb: 256,
      workerTimeoutMs: 120 * 1000,
      cpuTimeSoftLimitMs: 10 * 1000,
      cpuTimeHardLimitMs: 20 * 1000,
      envVars: Object.entries(Deno.env.toObject()),
    });
    return await worker.fetch(req);
  } catch (e) {
    console.error(`error serving ${serviceName}:`, e);
    return new Response(
      JSON.stringify({ error: String(e) }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
});
"""
