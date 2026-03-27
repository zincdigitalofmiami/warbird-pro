// job_log writer for Edge Functions.

import { createAdminClient } from "./admin.ts";

type JobLogStatus = "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";

export async function writeJobLog(params: {
  job_name: string;
  status: JobLogStatus;
  rows_affected: number;
  duration_ms: number;
  error_message?: string | null;
}): Promise<void> {
  const supabase = createAdminClient();
  const { error } = await supabase.from("job_log").insert({
    ...params,
    error_message: params.error_message ?? null,
  });

  if (error) {
    throw new Error(`job_log insert failed: ${error.message}`);
  }
}
