---
name: cron-route-creation
description: >
  Step-by-step workflow for creating new Vercel cron routes in Warbird-Pro. Ensures
  CRON_SECRET validation, job_log logging, maxDuration, and vercel.json registration.
  Invoke with /cron-route-creation.
---

# Cron Route Creation Workflow

Follow these steps exactly when creating a new Vercel cron route.

## Step 1: Confirm Requirements

- What data does this cron fetch/process?
- What table(s) does it write to?
- What schedule does it need? (Check existing schedules in `vercel.json` for conflicts)
- Will this increase Vercel function invocations significantly? (Cost concern)

## Step 2: Create the Route File

Location: `app/api/cron/<route-name>/route.ts`

Required boilerplate:
```typescript
export const maxDuration = 60

export async function GET(request: Request) {
  // 1. Validate CRON_SECRET
  const authHeader = request.headers.get('authorization')
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const startTime = Date.now()

  try {
    // 2. Do the work here

    // 3. Log success to job_log
    await supabaseAdmin.from('job_log').insert({
      job_name: '<route-name>',
      status: 'success',
      duration_ms: Date.now() - startTime,
      details: { /* relevant metrics */ }
    })

    return Response.json({ success: true })
  } catch (error) {
    // 4. Log failure to job_log
    await supabaseAdmin.from('job_log').insert({
      job_name: '<route-name>',
      status: 'error',
      duration_ms: Date.now() - startTime,
      details: { error: error.message }
    })

    return Response.json({ error: error.message }, { status: 500 })
  }
}
```

## Step 3: Register in vercel.json

Add the schedule to `vercel.json` under `crons`:
```json
{
  "path": "/api/cron/<route-name>",
  "schedule": "<cron-expression>"
}
```

## Step 4: Verify

- Run `npm run build`
- Confirm the route compiles
- Confirm no duplicate schedules in `vercel.json`
- Remove any dead schedules found during review
