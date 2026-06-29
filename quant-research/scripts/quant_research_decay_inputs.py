#!/usr/bin/env python
"""Pre-run context builder for weekly quant strategy/model decay review.
Outputs JSON for Hermes cron; does not modify files.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = Path('C:/Users/enson/Documents/Obsidian Vault/Quant Research')
REGISTRY = VAULT_ROOT / '01 Research Candidate Registry.md'
QUEUE = VAULT_ROOT / '09 Coding-Ready Backtest Queue.md'
REVIEWS = VAULT_ROOT / '06 Research Reviews'


def safe_text(path: Path, limit: int = 12000) -> dict:
    if not path.exists():
        return {'path': str(path), 'exists': False, 'text': ''}
    text = path.read_text(encoding='utf-8', errors='replace')
    if len(text) > limit:
        text = text[:limit] + '\n...[truncated by pre-run script]...'
    return {'path': str(path), 'exists': True, 'text': text}


def recent_reviews(max_files: int = 8):
    if not REVIEWS.exists():
        return []
    files = sorted(REVIEWS.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    return [safe_text(p, limit=6000) for p in files]


def main():
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'kind': 'quant_research_weekly_decay_pre_run_context',
        'workspace': str(ROOT),
        'registry': safe_text(REGISTRY),
        'coding_queue': safe_text(QUEUE),
        'recent_reviews': recent_reviews(),
        'decay_review_checks': [
            'post-publication decay or crowding',
            'market-structure change, especially 0DTE/options and crypto venues',
            'transaction costs, spreads, borrow, funding, slippage, market impact',
            'data accessibility and survivorship/lookahead/leakage risk',
            'complex model not justified versus simpler baseline',
            'retail-practical vs retail-adaptable vs institutional-only classification drift',
        ],
        'instruction': 'Use this as context for the weekly review. Update Obsidian only through the agent run, not this pre-run script.',
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
