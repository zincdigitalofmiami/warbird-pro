# Warbird Status MCP

Read-only local MCP server for high-signal Warbird status checks. It exposes
repo-native status without creating training artifacts, touching Pine, or
contacting TradingView live automation.

Tools:

- `warbird_git_status`
- `warbird_validator_summary`
- `warbird_dataset_manifest_summary`
- `warbird_tv_doctor_status`

Run through Hermes with:

```bash
hermes mcp add warbird-status --command /Volumes/Satechi\ Hub/warbird-pro/.hermes/mcp/warbird-status/run.sh
hermes mcp test warbird-status
```
