// Edge Function cron auth — validates x-cron-secret header.
// Ported from lib/cron-auth.ts — NextResponse → Response, process.env → Deno.env.

export function validateCronRequest(req: Request): Response | null {
  const secret = Deno.env.get("EDGE_CRON_SECRET");

  if (!secret) {
    return new Response(
      JSON.stringify({ error: "EDGE_CRON_SECRET is not configured" }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }

  const header = req.headers.get("x-cron-secret");
  if (header !== secret) {
    return new Response(
      JSON.stringify({ error: "Unauthorized" }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    );
  }

  return null;
}
