---
name: databento-research
description: >
  Research-first workflow for any Databento API work. MUST research docs, subscription tier,
  and symbology before making any API calls. Standard $179 tier only. Invoke with
  /databento-research before any Databento work.
---

# Databento Research-First Workflow

CRITICAL: Research BEFORE any API calls. Getting this wrong costs money.

## Step 1: Research the docs and tier limits

Before writing ANY Databento API code:
- Check what schemas are available on Standard $179/mo tier
- Free schemas: ohlcv-1s, ohlcv-1m, ohlcv-1h, ohlcv-1d, definition, statistics
- Paid schemas (DO NOT USE without approval): trades, mbp-1, mbp-10, mbo

## Step 2: Lock symbology (non-negotiable)

- Use `.c.0` continuous front-month contracts for all futures symbols.
- Set `stype_in=continuous` on Databento calls.
- Do NOT implement manual contract-roll logic, roll dates, expiry switching, or custom roll handlers.
- Keep symbology aligned with authority docs (`AGENTS.md`, `CLAUDE.md`).

## Step 3: Check current usage

- Review existing Databento code in the repo
- Check which schemas are currently being pulled
- Verify you are not duplicating an existing data pipeline

## Step 4: Symbol safety

- ONLY query symbols where `is_active=true AND data_source='DATABENTO'`
- NEVER hardcode symbol names — always query the active symbols table

## Step 5: Cost awareness

- Space data pulls evenly across available windows — never stack pulls
- Minimize API calls — batch where possible
- Check if the data already exists in Supabase before pulling

## Step 6: Implementation

Only AFTER steps 1-5 are complete, write the code.
- Follow cron route creation workflow if this is a scheduled pull
- Use Supabase admin client for writes
- Log to job_log
