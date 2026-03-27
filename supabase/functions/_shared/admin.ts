// Supabase service-role client for Edge Functions.
// Ported from lib/supabase/admin.ts — process.env → Deno.env, npm: import.

import { createClient } from "npm:@supabase/supabase-js@2";

export function createAdminClient() {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    {
      auth: { persistSession: false },
    },
  );
}
