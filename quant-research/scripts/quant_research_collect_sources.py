#!/usr/bin/env python
"""Pre-run source collector for Hermes quant-research daily cron.

This script is source-controlled in C:/Users/enson/.hermes/quant-research.
Hermes cron executes a tiny AppData wrapper which delegates here.

Outputs JSON to stdout. Feed/arXiv/SSRN items are discovery leads only, not evidence.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config'
STATE_DIR = ROOT / 'state'
STATE_PATH = STATE_DIR / 'state.json'


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def stable_id(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update((part or '').encode('utf-8', errors='ignore'))
        h.update(b'\0')
    return h.hexdigest()[:16]


def parse_feed(url: str, *, max_entries: int) -> tuple[list[dict], str | None]:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'HermesQuantResearch/1.0'})
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        entries = []
        for item in root.findall('./channel/item')[:max_entries]:
            title = (item.findtext('title') or '').strip()
            link = (item.findtext('link') or '').strip()
            pub = item.findtext('pubDate') or item.findtext('published')
            published_iso = None
            if pub:
                try:
                    published_iso = parsedate_to_datetime(pub).isoformat()
                except Exception:
                    published_iso = None
            entries.append({'id': stable_id(title, link), 'title': title, 'link': link, 'published': pub, 'published_iso': published_iso})
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        if not entries:
            for entry in root.findall('atom:entry', ns)[:max_entries]:
                title = (entry.findtext('atom:title', default='', namespaces=ns) or '').strip()
                link_el = entry.find('atom:link', ns)
                link = link_el.attrib.get('href', '') if link_el is not None else ''
                pub = entry.findtext('atom:published', default='', namespaces=ns) or entry.findtext('atom:updated', default='', namespaces=ns)
                entries.append({'id': stable_id(title, link), 'title': title, 'link': link, 'published': pub, 'published_iso': pub or None})
        return entries, None
    except Exception as exc:
        return [], f'{type(exc).__name__}: {exc}'


def arxiv_api_url(query: str, max_results: int = 8) -> str:
    params = urllib.parse.urlencode({
        'search_query': query,
        'start': 0,
        'max_results': max_results,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending',
    })
    return 'https://export.arxiv.org/api/query?' + params


def collect():
    feed_cfg = read_json(CONFIG / 'feed_sources.json', {})
    watch_cfg = read_json(CONFIG / 'source_watchlist.json', {})
    ssrn_cfg = read_json(CONFIG / 'ssrn_queries.json', {})
    state = read_json(STATE_PATH, {'seen_item_ids': {}})

    max_entries = int(feed_cfg.get('max_entries_per_feed', 8))
    feeds_out = []
    for feed in feed_cfg.get('feeds', []):
        entries, error = parse_feed(feed['url'], max_entries=max_entries)
        feeds_out.append({**feed, 'ok': error is None, 'error': error, 'entries': entries})

    arxiv_leads = []
    for query in watch_cfg.get('arxiv_queries', []):
        url = arxiv_api_url(query)
        entries, error = parse_feed(url, max_entries=8)
        arxiv_leads.append({'query': query, 'api_url': url, 'ok': error is None, 'error': error, 'entries': entries})

    ssrn_leads = []
    for query in ssrn_cfg.get('queries', []):
        ssrn_leads.append({
            'query': query,
            'search_url': 'https://www.google.com/search?q=' + urllib.parse.quote_plus(query),
            'triage_rule': ssrn_cfg.get('triage_rule'),
        })

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'kind': 'quant_research_daily_pre_run_context',
        'workspace': str(ROOT),
        'asset_focus': watch_cfg.get('asset_focus', []),
        'research_themes': watch_cfg.get('research_themes', []),
        'quality_filters': watch_cfg.get('quality_filters', {}),
        'rss_feed_leads': feeds_out,
        'arxiv_query_leads': arxiv_leads,
        'ssrn_query_leads': ssrn_leads,
        'state_summary': {
            'state_path': str(STATE_PATH),
            'state_exists': STATE_PATH.exists(),
            'seen_item_buckets': sorted((state.get('seen_item_ids') or {}).keys()),
        },
        'instruction': 'Treat all leads as discovery inputs. Validate before adding to Obsidian notes or candidate registry; do not treat feed headlines as evidence.',
    }


if __name__ == '__main__':
    print(json.dumps(collect(), indent=2, ensure_ascii=False))
