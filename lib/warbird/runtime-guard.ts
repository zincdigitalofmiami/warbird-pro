import type { PostgrestError } from "@supabase/supabase-js";
import { createAdminClient } from "@/lib/supabase/admin";
import type { WarbirdRuntimeState } from "@/lib/warbird/types";

const LEGACY_READER_OBJECTS = [
  "warbird_daily_bias",
  "warbird_structure_4h",
  "warbird_triggers_15m",
  "warbird_conviction",
  "warbird_risk",
  "warbird_setups",
  "warbird_setup_events",
] as const;

function buildRuntimeState(
  overrides: Partial<WarbirdRuntimeState>,
): WarbirdRuntimeState {
  return {
    active: false,
    mode: "OK",
    reason: null,
    missingObjects: [],
    checkedObjects: [...LEGACY_READER_OBJECTS],
    checkedAt: new Date().toISOString(),
    ...overrides,
  };
}

function isMissingSchemaObjectError(error: PostgrestError | null): boolean {
  return error?.code === "PGRST205";
}

function formatProbeFailure(table: string, error: PostgrestError): string {
  const code = error.code ?? "UNKNOWN";
  const message = error.message ?? "unknown probe failure";
  return `${table}: ${code} ${message}`;
}

export async function checkWarbirdLegacyReaderRuntime(): Promise<WarbirdRuntimeState> {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
    return buildRuntimeState({
      active: true,
      mode: "RUNTIME_GUARD_FAILED",
      reason: "Service-role Supabase configuration is missing, so legacy reader health cannot be proven.",
    });
  }

  try {
    const supabase = createAdminClient();
    const results = await Promise.all(
      LEGACY_READER_OBJECTS.map(async (table) => {
        const result = await supabase.from(table).select("*").limit(1);
        return { table, error: result.error };
      }),
    );

    const missingObjects = results
      .filter((result) => isMissingSchemaObjectError(result.error))
      .map((result) => result.table);

    if (missingObjects.length > 0) {
      return buildRuntimeState({
        active: true,
        mode: "LEGACY_READER_MISSING_OBJECTS",
        reason:
          "Legacy Warbird reader tables are absent on the live database; runtime is in degraded mode until the canonical writer/reader cutover is complete.",
        missingObjects,
      });
    }

    const probeFailures = results
      .filter((result) => result.error != null)
      .map((result) => formatProbeFailure(result.table, result.error!));

    if (probeFailures.length > 0) {
      return buildRuntimeState({
        active: true,
        mode: "RUNTIME_GUARD_FAILED",
        reason: `Runtime guard probe failed: ${probeFailures.join("; ")}`,
      });
    }

    return buildRuntimeState({});
  } catch (error) {
    return buildRuntimeState({
      active: true,
      mode: "RUNTIME_GUARD_FAILED",
      reason:
        error instanceof Error
          ? `Runtime guard threw before legacy-reader health could be proven: ${error.message}`
          : "Runtime guard threw before legacy-reader health could be proven.",
    });
  }
}
