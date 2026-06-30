# Quant Research Hermes Workspace

This folder contains the GitHub-facing source/config layer for the Hermes `quant-researcher` scheduled research system.

## Split of responsibilities

### Kept in AppData / Hermes internal storage

- Active cron job definitions: `C:/Users/enson/AppData/Local/hermes/profiles/quant-researcher/cron/jobs.json`
- Cron outputs/logs/state/locks
- Hermes profile config, `.env`, sessions, memory, gateway files
- Tiny cron wrapper scripts required by Hermes security policy

### Kept here for GitHub / user editing

- Prompt source copies under `prompts/`
- Source collection configuration under `config/`
- Real pre-run source scripts under `scripts/`
- Example state schema under `state/state.example.json`

Hermes cron requires executable scripts to live inside the active Hermes profile's `scripts/` directory. Therefore the AppData scripts are wrappers only; the real logic lives here.

## Scheduled jobs

### daily-quant-research-collector

- Cron job ID: `1c3a1db27acf`
- Schedule: `0 8 * * *`
- AppData wrapper: `quant_research_collect_sources.py`
- Source script: `scripts/quant_research_collect_sources.py`

The source script emits JSON with RSS/feed leads, arXiv query leads, SSRN query links, asset focus, and quality filters. These are discovery inputs only, not evidence.

### weekly-quant-strategy-decay-review / synthesis review

- Cron job ID: `810de174cd0f`
- Schedule: `0 9 * * 0`
- AppData wrapper: `quant_research_decay_inputs.py`
- Source script: `scripts/quant_research_decay_inputs.py`

The source script emits JSON context for registry/coding queue/decay review plus framework synthesis, source-note concept overlaps, open questions, and adjacent-domain method leads.

## Runtime state

`state/state.json` is intentionally ignored. It can store local run history, seen item IDs, and dedupe metadata. Commit `state/state.example.json`, not the live state file.

## SSRN policy

SSRN is included as query-driven discovery only. Do not bulk ingest or scrape blindly. SSRN working papers should usually start as `Plausible but untested` unless replicated, published, highly cited, or foundational.
