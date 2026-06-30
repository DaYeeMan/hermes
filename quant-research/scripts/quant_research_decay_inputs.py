#!/usr/bin/env python
"""Pre-run context builder for weekly quant synthesis + strategy/model decay review.
Outputs JSON for Hermes cron; does not modify Obsidian files.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config'
VAULT_ROOT = Path('C:/Users/enson/Documents/Obsidian Vault/Quant Research')
REGISTRY = VAULT_ROOT / '01 Research Candidate Registry.md'
QUEUE = VAULT_ROOT / '09 Coding-Ready Backtest Queue.md'
REVIEWS = VAULT_ROOT / '06 Research Reviews'
SOURCE_DIR = VAULT_ROOT / '01 Sources'
STRATEGY_DIR = VAULT_ROOT / '02 Strategy Ideas'
SYNTHESIS_DIR = VAULT_ROOT / '07 Literature Synthesis'
FRAMEWORK_REGISTRY = SYNTHESIS_DIR / 'Framework Candidate Registry.md'
OPEN_QUESTIONS = SYNTHESIS_DIR / 'Open Research Questions.md'


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


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
    return [safe_text(p, limit=7000) for p in files]


def note_inventory(folder: Path, max_files: int = 20, limit: int = 3500):
    if not folder.exists():
        return []
    files = sorted(folder.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    return [safe_text(p, limit=limit) for p in files]


def arxiv_api_url(query: str, max_results: int = 5) -> str:
    params = urllib.parse.urlencode({
        'search_query': query,
        'start': 0,
        'max_results': max_results,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending',
    })
    return 'https://export.arxiv.org/api/query?' + params


def parse_arxiv(url: str, max_entries: int = 5) -> tuple[list[dict], str | None]:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'HermesQuantResearch/1.0'})
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = []
        for entry in root.findall('atom:entry', ns)[:max_entries]:
            title = (entry.findtext('atom:title', default='', namespaces=ns) or '').strip().replace('\n', ' ')
            link_el = entry.find('atom:link', ns)
            link = link_el.attrib.get('href', '') if link_el is not None else ''
            pub = entry.findtext('atom:published', default='', namespaces=ns) or entry.findtext('atom:updated', default='', namespaces=ns)
            summary = (entry.findtext('atom:summary', default='', namespaces=ns) or '').strip().replace('\n', ' ')
            entries.append({'title': title, 'link': link, 'published': pub, 'summary': summary[:700]})
        return entries, None
    except Exception as exc:
        return [], f'{type(exc).__name__}: {exc}'


def adjacent_domain_leads():
    cfg = read_json(CONFIG / 'source_watchlist.json', {})
    out = []
    for query in cfg.get('adjacent_domain_queries', []):
        url = arxiv_api_url(query, max_results=5)
        entries, error = parse_arxiv(url)
        out.append({'query': query, 'api_url': url, 'ok': error is None, 'error': error, 'entries': entries})
    return out


def main():
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'kind': 'quant_research_weekly_synthesis_decay_pre_run_context',
        'workspace': str(ROOT),
        'registry': safe_text(REGISTRY),
        'coding_queue': safe_text(QUEUE),
        'framework_registry': safe_text(FRAMEWORK_REGISTRY),
        'open_research_questions': safe_text(OPEN_QUESTIONS),
        'recent_reviews': recent_reviews(),
        'recent_source_notes': note_inventory(SOURCE_DIR, max_files=20, limit=3500),
        'recent_strategy_notes': note_inventory(STRATEGY_DIR, max_files=12, limit=3500),
        'adjacent_domain_method_leads': adjacent_domain_leads(),
        'synthesis_checks': [
            'Which new item reinforces, contradicts, or supplies missing validation for an existing candidate?',
            'Can two or more saved notes form a falsifiable framework candidate?',
            'Can an adjacent-domain method improve signal extraction, uncertainty estimation, causal validation, regime detection, network modeling, optimization, or stress testing?',
            'Is the proposed connection a true mechanism or only a metaphor?',
            'What minimum viable backtest or validation would falsify the framework?',
        ],
        'decay_review_checks': [
            'post-publication decay or crowding',
            'market-structure change, especially 0DTE/options and crypto venues',
            'transaction costs, spreads, borrow, funding, slippage, market impact',
            'data accessibility and survivorship/lookahead/leakage risk',
            'complex model not justified versus simpler baseline',
            'retail-practical vs retail-adaptable vs institutional-only classification drift',
        ],
        'instruction': 'Use this as context for the weekly combined synthesis+decay review. Update Obsidian only through the agent run, not this pre-run script.',
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
