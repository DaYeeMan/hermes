#!/usr/bin/env python
"""Pre-run context collector for Hermes supply-chain-researcher cron.

This script is source-controlled in C:/Users/enson/.hermes/supply-chain-research.
Hermes cron executes a tiny AppData wrapper which delegates here.

Outputs JSON to stdout. The output is context for the LLM, not evidence by
itself. The LLM must validate material events using primary/high-quality sources
before updating Obsidian or sending Discord alerts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
STATE_PATH = STATE_DIR / "state.json"
VAULT_ROOT = Path("C:/Users/enson/Documents/Obsidian Vault/AI Supply Chain Research")

KEY_FILES = [
    "00 Dashboard.md",
    "01 Sources/Source Watchlist.md",
    "01 Supply Chain Map/AI Supply Chain Master Map.md",
    "04 Events/Event Registry.md",
    "05 Opportunity Watchlist/Active Opportunities.md",
    "_System/Protocols/Daily Monitoring Protocol.md",
    "_System/Protocols/Event Retention Policy.md",
    "_System/Protocols/Opportunity Evaluation Protocol.md",
    "_System/Protocols/Discord Alert Protocol.md",
]


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def safe_text(path: Path, limit: int = 6000) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False, "text": ""}
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        text = text[:limit] + "\n...[truncated by pre-run script]..."
    return {"path": str(path), "exists": True, "text": text}


def inventory_md(rel_dir: str, max_files: int = 40) -> list[dict]:
    directory = VAULT_ROOT / rel_dir
    if not directory.exists():
        return []
    files = sorted(directory.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    out = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:1200]
            first_heading = next((line.strip() for line in text.splitlines() if line.startswith("#")), p.stem)
            out.append({
                "path": str(p),
                "note": p.stem,
                "modified_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
                "heading": first_heading,
                "excerpt": text,
            })
        except Exception as exc:
            out.append({"path": str(p), "error": f"{type(exc).__name__}: {exc}"})
    return out


def collect():
    now = datetime.now(timezone.utc).isoformat()
    state = read_json(STATE_PATH, {"run_count": 0, "last_run_at": None})
    source_cfg = read_json(CONFIG_DIR / "source_watchlist.json", {})

    context = {
        "generated_at": now,
        "kind": "ai_supply_chain_daily_pre_run_context",
        "workspace": str(ROOT),
        "obsidian_root": str(VAULT_ROOT),
        "discord_alert_target": "discord:1522119384477208596",
        "state_before": state,
        "source_watchlist_config": source_cfg,
        "key_file_excerpts": {rel: safe_text(VAULT_ROOT / rel, limit=7000) for rel in KEY_FILES},
        "recent_events_inventory": inventory_md("04 Events", max_files=30),
        "opportunity_watchlist_inventory": inventory_md("05 Opportunity Watchlist", max_files=20),
        "segment_inventory": inventory_md("03 Segments", max_files=20),
        "instructions": [
            "Use this JSON as context only; validate any event through primary/high-quality sources before changing Obsidian.",
            "Routine maintenance must remain silent; send Discord only for high-signal events that satisfy the alert protocol.",
            "Avoid duplicate event notes; update existing notes and change logs when the event already exists.",
        ],
    }

    state["run_count"] = int(state.get("run_count", 0)) + 1
    state["last_run_at"] = now
    write_json(STATE_PATH, state)
    return context


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2, ensure_ascii=False))
