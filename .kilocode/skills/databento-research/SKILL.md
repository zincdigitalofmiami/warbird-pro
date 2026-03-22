---
name: databento-research
description: >
  Research-first workflow for any Databento API work. MUST research docs, subscription tier,
  and symbology before making any API calls. Standard $179 tier only. Invoke with
  /databento-research before any Databento work.
---

# Databento Research-First Workflow

CRITICAL: Research BEFORE any API calls. Getting this wrong costs money.

## Step 1: Research the Docs

Before writing ANY Databento API code:
- Check what schemas are available on Standard $179/mo tier
- Free schemas: ohlcv-1s, ohlcv-1m, ohlcv-1h, ohlcv-1d, definition, statistics
- Paid schemas (DO NOT USE without approval): trades, mbp-1, mbp-10, mbo
- Check symbology: use `.v.0` for volume roll conventions

## Step 2: Check Current Usage

- Review existing Databento code in the repo
- Check which schemas are currently being pulled
- Verify you are not duplicating an existing data pipeline

## Step 3: Symbol Safety

- ONLY query symbols where `is_active=true AND data_source='DATABENTO'`
- NEVER hardcode symbol names — always query the active symbols table
- Use the correct contract roll methodology (TradingView MES1! rolls 8 cal days before 3rd Friday)

## Step 4: Cost Awareness

- Space data pulls evenly across available windows — never stack pulls
- Minimize API calls — batch where possible
- Check if the data already exists in Supabase before pulling

## Step 5: Implementation

Only AFTER steps 1-4 are complete, write the code.
- Follow cron route creation workflow if this is a scheduled pull
- Use Supabase admin client for writes
- Log to job_log
