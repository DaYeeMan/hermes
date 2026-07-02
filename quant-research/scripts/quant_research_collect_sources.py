#!/usr/bin/env python
"""Pre-run source collector for Hermes quant-research daily cron.

This script is source-controlled in C:/Users/enson/.hermes/quant-research.
Hermes cron executes a tiny AppData wrapper which delegates here.

Outputs JSON to stdout. Feed/arXiv/SSRN/adjacent-domain items are discovery
leads only, not evidence. It maintains lightweight local seen-state in
state/state.json so the agent can distinguish new leads from recurring ones.

RSS/practitioner feeds are collected through blogwatcher-cli when available.
The old stdlib feed parsing path remains only as a degraded fallback and is
flagged explicitly in the JSON so the LLM does not mistake fallback output for
the intended persistent feed-monitor state.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config'
STATE_DIR = ROOT / 'state'
STATE_PATH = STATE_DIR / 'state.json'
BLOGWATCHER_DB = STATE_DIR / 'blogwatcher-cli.db'
VAULT_ROOT = Path('C:/Users/enson/Documents/Obsidian Vault/Quant Research')
REGISTRY = VAULT_ROOT / '01 Research Candidate Registry.md'
FRAMEWORK_REGISTRY = VAULT_ROOT / '07 Literature Synthesis' / 'Framework Candidate Registry.md'
OPEN_QUESTIONS = VAULT_ROOT / '07 Literature Synthesis' / 'Open Research Questions.md'
SOURCE_DIR = VAULT_ROOT / '01 Sources'


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def safe_text(path: Path, limit: int = 6000) -> dict:
    if not path.exists():
        return {'path': str(path), 'exists': False, 'text': ''}
    text = path.read_text(encoding='utf-8', errors='replace')
    if len(text) > limit:
        text = text[:limit] + '\n...[truncated by pre-run script]...'
    return {'path': str(path), 'exists': True, 'text': text}


def source_note_inventory(max_notes: int = 40) -> list[dict]:
    if not SOURCE_DIR.exists():
        return []
    files = sorted(SOURCE_DIR.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)[:max_notes]
    out = []
    for p in files:
        text = p.read_text(encoding='utf-8', errors='replace')[:2500]
        concepts = []
        for line in text.splitlines():
            if line.startswith('concepts:') or line.startswith('tags:'):
                concepts.append(line.strip())
        out.append({'note': p.stem, 'path': str(p), 'frontmatter_hints': concepts, 'excerpt': text})
    return out


def stable_id(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update((part or '').encode('utf-8', errors='ignore'))
        h.update(b'\0')
    return h.hexdigest()[:16]


def mark_seen(item: dict, bucket: str, state: dict) -> dict:
    seen = state.setdefault('seen_item_ids', {}).setdefault(bucket, [])
    first_seen = state.setdefault('seen_item_first_seen', {})
    item_id = item.get('id') or stable_id(item.get('title', ''), item.get('link', '') or item.get('url', ''))
    is_new = item_id not in seen
    if is_new:
        seen.append(item_id)
        first_seen[item_id] = datetime.now(timezone.utc).isoformat()
    item['seen_before'] = not is_new
    item['first_seen_at'] = first_seen.get(item_id)
    return item


def parse_feed(url: str, *, max_entries: int) -> tuple[list[dict], str | None]:
    """Degraded fallback feed parser used only when blogwatcher-cli is missing/failing."""
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
                title = (entry.findtext('atom:title', default='', namespaces=ns) or '').strip().replace('\n', ' ')
                link_el = entry.find('atom:link', ns)
                link = link_el.attrib.get('href', '') if link_el is not None else ''
                pub = entry.findtext('atom:published', default='', namespaces=ns) or entry.findtext('atom:updated', default='', namespaces=ns)
                entries.append({'id': stable_id(title, link), 'title': title, 'link': link, 'published': pub, 'published_iso': pub or None})
        return entries, None
    except Exception as exc:
        return [], f'{type(exc).__name__}: {exc}'


def find_blogwatcher_cli() -> str | None:
    candidates = [
        os.environ.get('BLOGWATCHER_CLI'),
        shutil.which('blogwatcher-cli'),
        shutil.which('blogwatcher-cli.exe'),
        str(Path.home() / '.local' / 'bin' / 'blogwatcher-cli.exe'),
        str(Path.home() / '.local' / 'bin' / 'blogwatcher-cli'),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def run_cmd(args: list[str], timeout: int = 60) -> dict:
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=timeout, encoding='utf-8', errors='replace')
        return {'ok': p.returncode == 0, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    except Exception as exc:
        return {'ok': False, 'returncode': None, 'stdout': '', 'stderr': f'{type(exc).__name__}: {exc}'}


def ensure_blogwatcher_blogs(cli: str, feed_cfg: dict) -> list[dict]:
    BLOGWATCHER_DB.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for feed in feed_cfg.get('feeds', []):
        name = feed.get('name') or feed.get('url')
        url = feed.get('url')
        if not url:
            continue
        # Use the feed URL as the canonical blog URL. blogwatcher-cli enforces URL uniqueness,
        # and several arXiv categories share the same site homepage.
        args = [cli, '--db', str(BLOGWATCHER_DB), 'add', name, url, '--feed-url', url]
        res = run_cmd(args, timeout=45)
        duplicate = 'already exists' in (res.get('stderr') or '')
        results.append({'name': name, 'url': url, 'ok': res['ok'] or duplicate, 'already_exists': duplicate, 'stderr': res.get('stderr', '').strip()})
    return results


def parse_blogwatcher_articles(text: str, state: dict) -> list[dict]:
    articles = []
    current = None
    title_re = re.compile(r'^\s*\[(?P<id>\d+)\]\s+\[(?P<status>[^\]]+)\]\s+(?P<title>.+?)\s*$')
    for line in text.splitlines():
        m = title_re.match(line)
        if m:
            if current:
                articles.append(current)
            current = {'blogwatcher_id': m.group('id'), 'status': m.group('status'), 'title': m.group('title')}
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith('Blog:'):
            current['blog'] = stripped.split(':', 1)[1].strip()
        elif stripped.startswith('URL:'):
            current['link'] = stripped.split(':', 1)[1].strip()
        elif stripped.startswith('Published:'):
            current['published'] = stripped.split(':', 1)[1].strip()
        elif stripped.startswith('Categories:'):
            current['categories'] = [x.strip() for x in stripped.split(':', 1)[1].split(',') if x.strip()]
    if current:
        articles.append(current)
    for item in articles:
        item['id'] = stable_id(item.get('title', ''), item.get('link', ''))
        mark_seen(item, 'blogwatcher-cli:articles', state)
    return articles


def collect_blogwatcher(feed_cfg: dict, state: dict) -> dict:
    cli = find_blogwatcher_cli()
    if not cli:
        return {'available': False, 'error': 'blogwatcher-cli executable not found', 'entries': []}
    ensure = ensure_blogwatcher_blogs(cli, feed_cfg)
    scan = run_cmd([cli, '--db', str(BLOGWATCHER_DB), 'scan', '--workers', '4'], timeout=180)
    since = (datetime.now(timezone.utc) - timedelta(days=14)).date().isoformat()
    articles = run_cmd([cli, '--db', str(BLOGWATCHER_DB), 'articles', '--all', '--since', since], timeout=60)
    entries = parse_blogwatcher_articles(articles.get('stdout', ''), state) if articles.get('ok') else []
    return {
        'available': True,
        'cli_path': cli,
        'db_path': str(BLOGWATCHER_DB),
        'since': since,
        'ensure_blogs': ensure,
        'scan_ok': scan.get('ok'),
        'scan_stdout': scan.get('stdout', '')[-5000:],
        'scan_stderr': scan.get('stderr', '')[-2000:],
        'articles_ok': articles.get('ok'),
        'articles_stdout_excerpt': articles.get('stdout', '')[:6000],
        'articles_stderr': articles.get('stderr', '')[-2000:],
        'entries': entries,
        'note': 'RSS/practitioner feeds came from persistent blogwatcher-cli state. Treat entries as discovery leads only, not evidence.',
    }


def collect_fallback_feeds(feed_cfg: dict, state: dict) -> list[dict]:
    max_entries = int(feed_cfg.get('max_entries_per_feed', 8))
    feeds_out = []
    for feed in feed_cfg.get('feeds', []):
        entries, error = parse_feed(feed['url'], max_entries=max_entries)
        bucket = 'feed:' + feed.get('name', feed['url'])
        entries = [mark_seen(e, bucket, state) for e in entries]
        feeds_out.append({**feed, 'ok': error is None, 'error': error, 'entries': entries, 'degraded_fallback': True})
    return feeds_out


def arxiv_api_url(query: str, max_results: int = 8) -> str:
    params = urllib.parse.urlencode({
        'search_query': query,
        'start': 0,
        'max_results': max_results,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending',
    })
    return 'https://export.arxiv.org/api/query?' + params


def collect_arxiv_queries(queries: list[str], bucket_prefix: str, state: dict, max_results: int = 8) -> list[dict]:
    out = []
    for query in queries:
        url = arxiv_api_url(query, max_results=max_results)
        entries, error = parse_feed(url, max_entries=max_results)
        bucket = bucket_prefix + ':' + stable_id(query)
        entries = [mark_seen(e, bucket, state) for e in entries]
        out.append({'query': query, 'api_url': url, 'ok': error is None, 'error': error, 'entries': entries})
    return out


def collect():
    feed_cfg = read_json(CONFIG / 'feed_sources.json', {})
    watch_cfg = read_json(CONFIG / 'source_watchlist.json', {})
    ssrn_cfg = read_json(CONFIG / 'ssrn_queries.json', {})
    state = read_json(STATE_PATH, {'seen_item_ids': {}, 'seen_item_first_seen': {}})

    blogwatcher = collect_blogwatcher(feed_cfg, state)
    fallback_feeds = [] if blogwatcher.get('available') and blogwatcher.get('articles_ok') else collect_fallback_feeds(feed_cfg, state)

    arxiv_leads = collect_arxiv_queries(watch_cfg.get('arxiv_queries', []), 'arxiv', state, max_results=8)
    adjacent_leads = collect_arxiv_queries(watch_cfg.get('adjacent_domain_queries', []), 'adjacent_arxiv', state, max_results=5)

    ssrn_leads = []
    for query in ssrn_cfg.get('queries', []):
        ssrn_leads.append({
            'query': query,
            'search_url': 'https://www.google.com/search?q=' + urllib.parse.quote_plus(query),
            'triage_rule': ssrn_cfg.get('triage_rule'),
        })

    state['last_run_date'] = datetime.now(timezone.utc).isoformat()
    state['last_registry_snapshot_hash'] = stable_id(safe_text(REGISTRY, 20000).get('text', ''))
    write_json(STATE_PATH, state)

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'kind': 'quant_research_daily_pre_run_context',
        'workspace': str(ROOT),
        'asset_focus': watch_cfg.get('asset_focus', []),
        'research_themes': watch_cfg.get('research_themes', []),
        'quality_filters': watch_cfg.get('quality_filters', {}),
        'existing_library_context': {
            'candidate_registry': safe_text(REGISTRY, limit=8000),
            'framework_registry': safe_text(FRAMEWORK_REGISTRY, limit=5000),
            'open_research_questions': safe_text(OPEN_QUESTIONS, limit=4000),
            'recent_source_note_inventory': source_note_inventory(max_notes=12),
        },
        'blogwatcher_feed_leads': blogwatcher,
        'rss_feed_leads': fallback_feeds,
        'arxiv_query_leads': arxiv_leads,
        'adjacent_domain_arxiv_leads': adjacent_leads,
        'ssrn_query_leads': ssrn_leads,
        'state_summary': {
            'state_path': str(STATE_PATH),
            'state_exists': STATE_PATH.exists(),
            'seen_item_buckets': sorted((state.get('seen_item_ids') or {}).keys()),
            'new_vs_seen_semantics': 'Each entry has seen_before and first_seen_at fields based on local state/state.json.',
            'blogwatcher_db': str(BLOGWATCHER_DB),
        },
        'instruction': 'Treat all leads as discovery inputs. Validate before adding to Obsidian. Use blogwatcher_feed_leads as the primary persistent RSS/practitioner feed context; rss_feed_leads appears only when blogwatcher-cli is unavailable/failing. Use existing_library_context to find cross-paper/framework connections; do not treat outside-domain leads as trading evidence unless translated into falsifiable market hypotheses.',
    }


if __name__ == '__main__':
    print(json.dumps(collect(), indent=2, ensure_ascii=False))
