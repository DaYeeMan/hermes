# AI Supply Chain Research Hermes Workspace

This folder contains the GitHub/user-editable source/config layer for the Hermes `supply-chain-researcher` scheduled research system.

## Split of responsibilities

### Kept in AppData / Hermes internal storage

- Active cron job definitions: `C:/Users/enson/AppData/Local/hermes/profiles/supply-chain-researcher/cron/jobs.json`
- Cron outputs/logs/state/locks
- Hermes profile config, `.env`, sessions, memory, gateway files
- Hermes-installed skills and profile-local skill state
- Tiny cron wrapper scripts required by Hermes security policy

### Kept here for GitHub / user editing

- Prompt source copies under `prompts/`
- Source/watchlist configuration under `config/`
- Real pre-run source/context scripts under `scripts/`
- Example state schema under `state/state.example.json`

Hermes cron requires executable scripts to live inside the active Hermes profile's `scripts/` directory. Therefore the AppData scripts are wrappers only; the real logic lives here.

## Scheduled jobs

### Daily AI Supply Chain Database Maintenance

- Cron job ID: `fc249e0e53ab`
- Schedule: `0 8 * * *`
- AppData wrapper: `supply_chain_monitor_inputs.py`
- Source script: `scripts/supply_chain_monitor_inputs.py`
- Prompt source copy: `prompts/daily_ai_supply_chain_maintenance.md`
- Obsidian root: `C:/Users/enson/Documents/Obsidian Vault/AI Supply Chain Research`
- Discord alert channel for high-signal events only: `discord:1522119384477208596`

The source script emits JSON context for the LLM before each cron run: database paths, protocol/index excerpts, source categories, recent event/opportunity inventory, and lightweight run-state metadata. It does not contain secrets and does not send Discord alerts itself.

## Runtime state

`state/state.json` is intentionally ignored. It can store local run history, seen item IDs, and dedupe metadata. Commit `state/state.example.json`, not the live state file.

## Alerting policy

Routine maintenance is silent. Discord alerts are sent only by the LLM-driven cron run when an event satisfies the Obsidian `Discord Alert Protocol`.
