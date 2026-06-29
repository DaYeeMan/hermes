#!/usr/bin/env python
"""Pre-run source script for the Hermes daily market intelligence briefing.

This source-controlled script lives under C:/Users/enson/.hermes/stock-briefing.
Hermes cron executes a tiny AppData wrapper which delegates here, so the real
logic stays editable and Git-friendly in .hermes.

The cron-compatible wrapper filename is historical, but this script no longer
selects a rotating theme. The user wants a consistent daily structure focused on
company catalysts: M&A, partnerships, technological innovations, government
contracts, regulatory catalysts, supply-chain developments, and watchlist news.

Why this script fetches news: scheduled cron runs may not always expose live
web/search tools to the model. To avoid an empty briefing, this pre-run step
collects current RSS headlines with source links and injects them into the cron
prompt. The agent can use web/search tools if available, but this payload should
be sufficient to produce a sourced briefing.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("STOCK_BRIEFING_ROOT", "C:/Users/enson/.hermes/stock-briefing"))
CONFIG_PATH = ROOT / "watchlist.json"
STATE_PATH = ROOT / "state.json"

# Keep each query bounded, but do not let early categories consume the entire
# budget before later categories (especially supply-chain / real-world drivers)
# get represented.
MAX_ITEMS_PER_BASE_QUERY = 8
MAX_ITEMS_PER_WATCHLIST_QUERY = 5
MAX_TOTAL_ITEMS = 70

LOW_VALUE_TITLE_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in [
        r"\bstock price, news & analysis\b",
        r"\bprice to earnings forward\b",
        r"\bsample grant proposal\b",
        r"\bbasketball news roundup\b",
        r"\bhoroscope\b",
    ]
]

LOW_VALUE_SOURCES = {
    "fundsforngos",
}

AGGREGATOR_SOURCES = {
    "kavout | ai",
    "simplywall.st",
    "insider monkey",
    "intellectia ai",
    "moomoo",
    "marketbeat",
    "tradingview",
    "stock titan",
}

BASE_QUERY_TEMPLATES = [
    {
        "category": "m_and_a_partnerships",
        "label": "M&A / partnerships / strategic investments",
        "query": '("merger" OR "acquisition" OR "strategic investment" OR "joint venture" OR IPO OR SPAC OR "activist stake") (stock OR shares OR "public company") when:{when}',
    },
    {
        "category": "government_contracts",
        "label": "Government contracts / procurement / grants",
        "query": '("government contract" OR procurement OR "contract award" OR grant OR "public-private" OR "defense contract") (defense OR aerospace OR AI OR cloud OR energy OR infrastructure OR semiconductor OR cybersecurity) when:{when}',
    },
    {
        "category": "technology_innovation",
        "label": "Technology / product / innovation signals",
        "query": '(innovation OR "product launch" OR breakthrough OR "commercial milestone" OR "FDA breakthrough" OR "AI platform") (AI OR semiconductor OR robotics OR autonomy OR cybersecurity OR biotech OR medtech OR energy OR space OR defense) when:{when}',
    },
    {
        "category": "regulatory_legal",
        "label": "Regulatory / legal catalysts",
        "query": '("export controls" OR tariff OR sanctions OR antitrust OR CFIUS OR FDA OR FTC OR DOJ OR SEC OR lawsuit OR settlement OR approval OR ban) (company OR stock OR shares OR supplier) when:{when}',
    },
    {
        "category": "private_company_readthrough",
        "label": "Major private-company public-market read-throughs",
        "query": '(SpaceX OR Starlink OR OpenAI OR Anthropic OR Databricks OR Stripe) (supplier OR contract OR partnership OR IPO OR valuation OR public company OR stock) when:{when}',
    },
    {
        "category": "ai_infrastructure",
        "label": "AI infrastructure / data-center / semiconductor capex",
        "query": '("data center" OR "cloud capex" OR GPU OR "AI infrastructure" OR semiconductor OR "advanced packaging") (contract OR partnership OR supplier OR earnings OR capacity OR power) when:{when}',
    },
    {
        "category": "supply_chain_operations",
        "label": "Supply chain / real-world operating drivers",
        "query": '("supply chain" OR logistics OR cyberattack OR labor OR strike OR "manufacturing capacity" OR commodity OR shipping OR grid OR power) (company OR stock OR shares OR supplier OR customer) when:{when}',
    },
]


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def lookback_days(now: datetime, config: dict) -> int:
    """Return Google News RSS when:N d value from config/date.

    The user preference is 24 hours normally and 72 hours on Mondays / after
    market holidays. We can reliably detect Mondays here. If the config later
    adds explicit ISO holiday dates, the script will also use a 72h lookback on
    the first run after those dates.
    """
    news_lookback = config.get("news_lookback", {}) or {}
    default_hours = int(news_lookback.get("default_hours", 24))
    extended_hours = int(news_lookback.get("monday_or_after_market_holiday_hours", 72))

    configured_holidays = set(config.get("market_holidays", []) or [])
    yesterday = now.date().toordinal() - 1
    holiday_yesterday = any(
        datetime.fromisoformat(str(day)).date().toordinal() == yesterday
        for day in configured_holidays
        if isinstance(day, str)
    )

    hours = extended_hours if now.weekday() == 0 or holiday_yesterday else default_hours
    return max(1, round(hours / 24))


def rss_search(query: str, *, max_items: int, category: str, category_label: str) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "HermesMarketBriefing/1.1 (+https://hermes-agent.nousresearch.com)"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()

    root = ET.fromstring(data)
    items: list[dict] = []
    for item in root.findall("./channel/item")[: max_items * 3]:
        title = item.findtext("title") or ""
        source = item.find("source")
        source_name = source.text if source is not None else None
        source_url = source.attrib.get("url") if source is not None else None
        if is_low_value(title, source_name):
            continue

        pub_date = item.findtext("pubDate")
        published_iso = None
        if pub_date:
            try:
                published_iso = parsedate_to_datetime(pub_date).isoformat()
            except Exception:
                published_iso = None

        items.append(
            {
                "category": category,
                "category_label": category_label,
                "query": query,
                "title": title,
                "source": source_name,
                "source_url": source_url,
                "source_quality_hint": source_quality_hint(source_name),
                "link": item.findtext("link"),
                "published": pub_date,
                "published_iso": published_iso,
            }
        )
        if len(items) >= max_items:
            break
    return items


def is_low_value(title: str, source_name: str | None) -> bool:
    source_key = (source_name or "").strip().lower()
    if source_key in LOW_VALUE_SOURCES:
        return True
    return any(pattern.search(title or "") for pattern in LOW_VALUE_TITLE_PATTERNS)


def source_quality_hint(source_name: str | None) -> str:
    source_key = (source_name or "").strip().lower()
    if not source_key:
        return "unknown"
    if source_key in AGGREGATOR_SOURCES:
        return "secondary/aggregator; verify before treating as material"
    return "standard"


def build_queries(config: dict, when_days: int) -> list[dict]:
    when = f"{when_days}d"
    queries = [
        {
            "category": item["category"],
            "label": item["label"],
            "query": item["query"].format(when=when),
            "max_items": MAX_ITEMS_PER_BASE_QUERY,
        }
        for item in BASE_QUERY_TEMPLATES
    ]

    seen_tickers: set[str] = set()
    for ticker in (config.get("priority_watch") or []) + (config.get("always_watch") or []):
        safe_ticker = str(ticker).strip().upper()
        if not safe_ticker or safe_ticker in seen_tickers:
            continue
        seen_tickers.add(safe_ticker)
        queries.append(
            {
                "category": "watchlist",
                "label": f"Watchlist: {safe_ticker}",
                "query": f'({safe_ticker} stock OR {safe_ticker} company) (contract OR partnership OR acquisition OR product OR regulation OR earnings OR guidance OR lawsuit) when:{when}',
                "max_items": MAX_ITEMS_PER_WATCHLIST_QUERY,
            }
        )
    return queries


def collect_news(config: dict, now: datetime) -> tuple[list[dict], list[str], list[dict], int]:
    when_days = lookback_days(now, config)
    queries = build_queries(config, when_days)

    seen: set[str] = set()
    by_query: list[tuple[dict, list[dict]]] = []
    errors: list[str] = []
    for query_def in queries:
        query = query_def["query"]
        try:
            query_results = rss_search(
                query,
                max_items=int(query_def["max_items"]),
                category=query_def["category"],
                category_label=query_def["label"],
            )
            by_query.append((query_def, query_results))
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {exc}")
            by_query.append((query_def, []))

    # Interleave one item per query per pass so every category gets a chance to
    # appear before broad categories fill the total budget.
    results: list[dict] = []
    max_depth = max((len(items) for _, items in by_query), default=0)
    for index in range(max_depth):
        for _, items in by_query:
            if index >= len(items):
                continue
            result = items[index]
            key = (result.get("title") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            results.append(result)
            if len(results) >= MAX_TOTAL_ITEMS:
                return results, errors, queries, when_days
    return results, errors, queries, when_days


def main() -> None:
    config = read_json(CONFIG_PATH, {})
    state = read_json(STATE_PATH, {})

    timezone = config.get("timezone", "America/New_York")
    now = datetime.now(ZoneInfo(timezone))
    today = now.date().isoformat()
    news_results, news_errors, queries, when_days = collect_news(config, now)

    last_summary = state.get("last_briefing_summary")
    stale_previous_summary = bool(
        isinstance(last_summary, dict) and last_summary.get("date") and last_summary.get("date") != state.get("last_run_date")
    )

    payload = {
        "date": today,
        "timezone": timezone,
        "collected_at": now.isoformat(),
        "news_lookback": config.get("news_lookback", {}),
        "effective_news_search_when": f"{when_days}d",
        "always_watch": config.get("always_watch", []),
        "priority_watch": config.get("priority_watch", []),
        "focus_categories": config.get("focus_categories", []),
        "deprioritized_topics": config.get("deprioritized_topics", []),
        "market_impact_topics_always_scan": config.get("market_impact_topics_always_scan", []),
        "current_news_queries": queries,
        "current_news_seed_results": news_results,
        "current_news_collection_errors": news_errors,
        "previous_briefing_summary": last_summary,
        "previous_briefing_summary_is_stale": stale_previous_summary,
        "source_handling_note": "RSS seed results are raw discovery inputs, not all recommended inclusions. Prefer official/company/government/SEC/reputable media; verify or down-rank secondary/aggregator items and omit irrelevant SEO/noise results.",
        "explicit_user_preference": "Do not include stock-of-the-day or rotating-theme sections. Keep the structure consistent and focus on company catalysts: M&A, partnerships, technological innovations, government contracts/procurement, regulatory catalysts, supply-chain/real-world developments, and watchlist news. Deprioritize routine Fed/rates commentary and generic market-tone labels unless directly tied to a concrete company or sector catalyst.",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
