# Stock Briefing Hermes Workspace

This folder contains the GitHub-facing source/config layer for the Hermes `Daily Market Intelligence Briefing` scheduled Discord briefing.

## Split of responsibilities

### Kept in AppData / Hermes internal storage

- Active cron job definition: `C:/Users/enson/AppData/Local/hermes/cron/jobs.json`
- Cron outputs/logs/state/locks: `C:/Users/enson/AppData/Local/hermes/cron/output/`
- Hermes profile config, `.env`, sessions, memory, and gateway files
- Tiny cron wrapper scripts required by Hermes cron script resolution/security policy

### Kept here for GitHub / user editing

- Prompt source copy: `briefing_prompt.md`
- Editable briefing/watchlist configuration: `watchlist.json`
- Lightweight briefing state: `state.json`
- Real pre-run source script: `scripts/select_daily_focus.py`
- This README and `.gitignore`

Hermes cron resolves relative script names from the active Hermes profile's internal `scripts/` directory. Therefore the AppData script is wrapper-only; the real logic lives here.

## Scheduled job

### Daily Market Intelligence Briefing

- Cron job ID: `dd71669ea059`
- Schedule: `0 9 * * *`
- Delivery: `discord:1519512531771592885` (`#daily-briefing` channel)
- Skill: `daily-market-intelligence-briefing`
- Enabled toolsets: `web`
- Workdir: `C:/Users/enson/.hermes`
- AppData wrapper: `C:/Users/enson/AppData/Local/hermes/scripts/stock_briefing_select_daily_focus.py`
- Source script: `scripts/select_daily_focus.py`
- Prompt source: `briefing_prompt.md`

The source script emits JSON with date, timezone, watchlist, focus categories, effective Google News RSS lookback, actual query strings, prior summary, collection errors, and current-news seed results. These seed results are discovery inputs only, not evidence; the briefing agent should verify or down-rank secondary/aggregator items.

## Runtime state

`state.json` stores lightweight local run state and the previous briefing summary. It is part of the editable workspace because the daily briefing prompt uses it for continuity, but do not treat it as an audit log or source of market truth.

Python cache files under `scripts/__pycache__/` are ignored.

## Customize watchlist

Edit `watchlist.json`:

```json
"always_watch": ["NVDA", "TSLA", "AMD"],
"priority_watch": ["NVDA"]
```

- `always_watch` means Hermes should check those tickers every briefing.
- `priority_watch` means Hermes should pay extra attention to those tickers.

## Briefing policy

The briefing should **not** have a stock-of-the-day section or a rotating theme/focus section. Keep the structure consistent across days.

Prioritize:

- M&A, divestitures, IPO/SPAC activity, activist stakes, strategic investments, joint ventures, and major partnerships.
- New technological innovations, product launches, commercialization milestones, and AI/semiconductor/space/defense/energy/cyber/biotech/fintech breakthroughs.
- Government contracts, grants, procurement awards, defense/aerospace awards, infrastructure/chips/energy funding, and agency budget allocations.
- Regulatory and legal catalysts with clear company exposure.
- Supply-chain and operating developments affecting public suppliers, customers, competitors, and sectors.
- Watchlist-specific company news.

Deprioritize routine Fed/rates commentary, generic index tone, and broad "market was neutral/mixed" summaries unless they directly create a company or sector catalyst.

## Wrapper policy

Keep the AppData wrapper tiny and logic-free. It should only:

1. Locate `C:/Users/enson/.hermes/stock-briefing/scripts/select_daily_focus.py`.
2. Add Hermes venv site-packages to `sys.path` if needed.
3. Execute the source script with `runpy.run_path(..., run_name="__main__")`.

Do not duplicate briefing logic in `C:/Users/enson/AppData/Local/hermes/scripts/`.

## Cron creation/update sketch

If this job ever needs to be recreated, use settings equivalent to:

- schedule: `0 9 * * *`
- skill: `daily-market-intelligence-briefing`
- script: `stock_briefing_select_daily_focus.py` in the AppData scripts directory; that file must remain a thin wrapper delegating to `scripts/select_daily_focus.py` in this folder
- prompt: contents of `briefing_prompt.md`
- enabled toolsets: `web` only; avoid terminal/file tools during cron runs because the pre-run script already injects config and Windows shell resolution can fail in scheduler context
- delivery: explicit Discord destination `discord:1519512531771592885`; do not use default/origin from the TUI

Because TUI cron jobs are local-only by default, use an explicit gateway-connected delivery target when scheduling notifications.
