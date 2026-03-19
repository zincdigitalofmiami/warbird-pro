import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { isMarketOpen } from "@/lib/market-hours";

export const maxDuration = 60;

type JobLogPayload = {
  job_name: string;
  status: "SUCCESS" | "PARTIAL" | "FAILED" | "SKIPPED";
  rows_affected?: number;
  duration_ms: number;
  error_message?: string;
};

type WriterInvocation = {
  invoked: boolean;
  url: string | null;
  status_code: number | null;
  duration_ms: number | null;
  response_preview: unknown;
};

async function writeJobLog(
  supabase: ReturnType<typeof createAdminClient>,
  payload: JobLogPayload,
) {
  const { error } = await supabase.from("job_log").insert(payload);
  if (error) {
    throw new Error(`job_log insert failed: ${error.message}`);
  }
}

function parseEnvNumber(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return parsed;
}

function maybeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text.slice(0, 500);
  }
}

async function invokeWriter(request: Request): Promise<WriterInvocation> {
  const writerUrl = process.env.WARBIRD_FORECAST_WRITER_URL ?? null;
  if (!writerUrl) {
    return {
      invoked: false,
      url: null,
      status_code: null,
      duration_ms: null,
      response_preview: "missing_writer_url",
    };
  }

  const writerToken = process.env.WARBIRD_FORECAST_WRITER_TOKEN;
  const writerTimeoutMs = parseEnvNumber("WARBIRD_FORECAST_WRITER_TIMEOUT_MS", 45_000);
  const started = Date.now();

  const payload = {
    source: "vercel-cron-forecast",
    invoked_at: new Date().toISOString(),
    force: new URL(request.url).searchParams.get("force") === "1",
  };

  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-warbird-cron": "1",
  };
  if (writerToken) {
    headers.authorization = `Bearer ${writerToken}`;
  }

  const response = await fetch(writerUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    cache: "no-store",
    signal: AbortSignal.timeout(writerTimeoutMs),
  });

  const rawBody = await response.text();
  const preview = maybeJson(rawBody);

  if (!response.ok) {
    const previewText = typeof preview === "string" ? preview : JSON.stringify(preview);
    throw new Error(`writer_http_${response.status}: ${previewText.slice(0, 300)}`);
  }

  return {
    invoked: true,
    url: writerUrl,
    status_code: response.status,
    duration_ms: Date.now() - started,
    response_preview: preview,
  };
}

export async function GET(request: Request) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${cronSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const startTime = Date.now();
  const supabase = createAdminClient();

  // Skip outside market hours unless forced.
  const force = new URL(request.url).searchParams.get("force") === "1";
  if (!force && !isMarketOpen()) {
    try {
      await writeJobLog(supabase, {
        job_name: "forecast-check",
        status: "SKIPPED",
        rows_affected: 0,
        duration_ms: Date.now() - startTime,
        error_message: "market_closed",
      });
    } catch {
      // Ignore logging failure to preserve skip response.
    }
    return NextResponse.json({ skipped: true, reason: "market_closed" });
  }

  let writer: WriterInvocation = {
    invoked: false,
    url: null,
    status_code: null,
    duration_ms: null,
    response_preview: null,
  };

  try {
    writer = await invokeWriter(request);
    if (!writer.invoked) {
      const duration = Date.now() - startTime;
      const failure = "forecast_writer_not_configured";
      await writeJobLog(supabase, {
        job_name: "forecast-check",
        status: "FAILED",
        rows_affected: 0,
        duration_ms: duration,
        error_message: failure,
      });
      return NextResponse.json(
        {
          error: failure,
          writer,
          duration_ms: duration,
        },
        { status: 503 },
      );
    }

    const cutoff = new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString();
    const { data: forecasts, error } = await supabase
      .from("warbird_forecasts_1h")
      .select("*")
      .gte("ts", cutoff)
      .order("ts", { ascending: false });

    if (error) throw error;

    const { data: latestBar } = await supabase
      .from("mes_15m")
      .select("ts, close")
      .order("ts", { ascending: false })
      .limit(1)
      .single();

    const currentPrice = latestBar ? Number(latestBar.close) : null;

    const hasForecast = Boolean(forecasts && forecasts.length > 0);
    const newestForecastTs = hasForecast ? String(forecasts?.[0]?.ts) : null;
    const newestForecastMs = newestForecastTs ? new Date(newestForecastTs).getTime() : null;
    const forecastAgeMs = newestForecastMs != null ? Date.now() - newestForecastMs : null;
    const maxForecastAgeMs = parseEnvNumber("WARBIRD_MAX_FORECAST_AGE_MS", 90 * 60 * 1000);
    const stale = forecastAgeMs != null && forecastAgeMs > maxForecastAgeMs;
    const healthy = hasForecast && !stale;
    const failureReason = !hasForecast
      ? `no_forecast_since_cutoff:${cutoff}`
      : `stale_forecast age_ms=${forecastAgeMs}`;

    const duration = Date.now() - startTime;

    await writeJobLog(supabase, {
      job_name: "forecast-check",
      status: healthy ? "SUCCESS" : "FAILED",
      rows_affected: forecasts?.length ?? 0,
      duration_ms: duration,
      error_message: healthy
        ? undefined
        : `${failureReason}, writer_status=${writer.status_code}, current_price=${currentPrice ?? "n/a"}`,
    });

    if (!healthy) {
      return NextResponse.json(
        {
          error: failureReason,
          stale,
          forecasts: forecasts ?? [],
          forecast_ts: newestForecastTs,
          forecast_age_ms: forecastAgeMs,
          current_price: currentPrice,
          writer,
          duration_ms: duration,
        },
        { status: 503 },
      );
    }

    return NextResponse.json(
      {
        success: true,
        forecasts: forecasts ?? [],
        forecast_ts: newestForecastTs,
        forecast_age_ms: forecastAgeMs,
        current_price: currentPrice,
        stale: false,
        writer,
        duration_ms: duration,
      },
      { status: 200 },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const duration = Date.now() - startTime;

    await writeJobLog(supabase, {
      job_name: "forecast-check",
      status: "FAILED",
      rows_affected: 0,
      duration_ms: duration,
      error_message: message,
    });

    return NextResponse.json(
      {
        error: message,
        writer,
        duration_ms: duration,
      },
      { status: 500 },
    );
  }
}
