# Pine Script Compilation Rule

**Real Compilation Validation**
You have the ability to run real Pine Script compilation checks using TradingView's `pine-facade` API. This uses the exact same compiler as the web editor and will return errors with line/column numbers. 

**No MCP or authentication is needed.**

Every Pine change MUST go through the real compiler before you claim the work is done. 

## How to test a Pine script:

```bash
pine_code=$(cat "indicators/your-file-name.pine")
curl -s -X POST "https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=admin&v=3" \
  -H 'Referer: https://www.tradingview.com/' \
  -F "source=$pine_code"
```

## What you DO NOT have:
You cannot load the indicator onto a live chart, see visual output, or run strategy backtests. The user must do this manually in the TradingView web editor.

Always report compiler output to the user clearly so they know the script compiles correctly before they manually paste it into TradingView.
