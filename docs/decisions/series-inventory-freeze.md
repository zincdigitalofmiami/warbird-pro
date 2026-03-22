# Series Inventory Freeze — v1

**Date:** 2026-03-22
**Status:** PENDING VERIFICATION

## request.security() Series (7 calls)

| Symbol | TV Ticker | Verified | 15m Data | Notes |
|--------|-----------|----------|----------|-------|
| NQ | `CME_MINI:NQ1!` | [ ] | [ ] | |
| BANK | `NASDAQ:BANK` | [ ] | [ ] | |
| VIX | `CBOE:VIX` | [ ] | [ ] | |
| DXY | `TVC:DXY` | [ ] | [ ] | |
| US10Y | `TVC:US10Y` | [ ] | [ ] | |
| HYG | `AMEX:HYG` | [ ] | [ ] | |
| LQD | `AMEX:LQD` | [ ] | [ ] | |

## request.economic() Series (4 calls — pending Pine verification)

| Series | TV Code | Purpose | Verified |
|--------|---------|---------|----------|
| Fed Funds | `request.economic("US", "IRSTCB01")` | Interest rates | [ ] |
| CPI YoY | `request.economic("US", "CPALTT01")` | Inflation | [ ] |
| Unemployment | `request.economic("US", "LRHUTTTTUSM156S")` | Labor | [ ] |
| PMI Mfg | `request.economic("US", "BSCICP02")` | Activity | [ ] |

## Pine Test Indicator

Use this to verify `request.economic()` codes resolve with real data:

```pinescript
//@version=6
indicator("Series Verification Test", overlay=false)

fed = request.economic("US", "IRSTCB01")
cpi = request.economic("US", "CPALTT01")
unemp = request.economic("US", "LRHUTTTTUSM156S")
pmi = request.economic("US", "BSCICP02")

plot(fed, "Fed Funds")
plot(cpi, "CPI YoY")
plot(unemp, "Unemployment")
plot(pmi, "PMI Mfg")
```

Load on any chart in TradingView. Verify all 4 plots render with real data.

## Budget

- Planned: 11 unique request.*() calls (7 security + 4 economic)
- TV limit: 40 (64 on Ultimate)
- Reserve: 29 calls for future expansion

## Excluded from v1 (unless reopened by decision)

- RTY1!, YM1!, crude, gold, VVIX, JNK, GDP growth
