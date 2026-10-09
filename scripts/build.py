#!/usr/bin/env python3
"""Validate data/briefing.json and render the LifeHub page into _site/.

Usage:
  python3 scripts/build.py                     validate, then render _site/
  python3 scripts/build.py --check             validate only
  python3 scripts/build.py --require-fresh 3   also fail if generated_at is over 3 hours old

Items that are malformed or already finished are dropped with a warning. Problems
that make the whole briefing unusable are errors and exit with status 1.
"""

from __future__ import annotations

import argparse
import calendar
import html
import json
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "briefing.json"
SITE_SRC = ROOT / "site"
OUT = ROOT / "_site"
SYDNEY = ZoneInfo("Australia/Sydney")

EVENT_SECTIONS = [
    ("live_sport", "Get out to a game", "Live sport near you", "Football first, then tennis, rugby union and basketball."),
    ("son", "For your son", "Sport, games and running", "Things a 9-year-old will be into."),
    ("daughter", "For your daughter", "Crafts, books and matcha", "Things a 12-year-old will be into."),
    ("family_fun", "For everyone", "Out and about", "Events, festivals, open days and school-holiday fun."),
    ("deals", "Deals and drops", "Sales, pop-ups and freebies", "Sales on sports gear, fun food and tickets, plus pop-up food stores and giveaways."),
]
SHORT_NAMES = {"man-utd": "Man Utd", "sydney-fc": "Sydney FC"}
TEAM_THEME = {"man-utd": "united", "sydney-fc": "sky"}
TRANSPORT = {"train": "Train", "metro": "Metro", "light rail": "Light rail"}
HORIZON_STATUS = {"new": "New", "updated": "Updated"}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
PARTIAL_RE = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def warn(self, message: str) -> None:
        self.warnings.append(message)


# --- Parsing helpers -------------------------------------------------------


def text(value, limit: int = 400) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def text_list(value, limit: int = 120) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (text(v, limit) for v in value) if t]


def as_list(value, where: str, report: Report) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        report.warn(f"{where}: expected a list, ignoring it")
        return []
    return value


def safe_url(value) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value.strip())
    return value.strip() if parsed.scheme in ("http", "https") and parsed.netloc else ""


def parse_dt(value) -> datetime | None:
    """Parse an ISO 8601 datetime that carries a UTC offset, keeping that offset."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def parse_moment(value) -> tuple[date, datetime | None] | None:
    """Parse YYYY-MM-DD or an ISO datetime into (Sydney date, Sydney datetime or None)."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if DATE_RE.fullmatch(value):
        try:
            return date.fromisoformat(value), None
        except ValueError:
            return None
    dt = parse_dt(value)
    if dt is None:
        return None
    dt = dt.astimezone(SYDNEY)
    return dt.date(), dt


def parse_partial(value) -> tuple[date, date, str] | None:
    """Parse YYYY, YYYY-MM or YYYY-MM-DD into (first day, last day, display label)."""
    if not isinstance(value, str):
        return None
    match = PARTIAL_RE.fullmatch(value.strip())
    if not match:
        return None
    year, month, day = (int(g) if g else None for g in match.groups())
    try:
        if day:
            d = date(year, month, day)
            return d, d, f"{d.day} {d:%b %Y}"
        if month:
            first = date(year, month, 1)
            last = date(year, month, calendar.monthrange(year, month)[1])
            return first, last, f"{first:%b %Y}"
        return date(year, 1, 1), date(year, 12, 31), str(year)
    except ValueError:
        return None


# --- Normalising the briefing ----------------------------------------------


def clean_fixture(raw, now: datetime, report: Report, where: str) -> dict | None:
    if not isinstance(raw, dict):
        report.warn(f"{where}: not an object")
        return None
    opponent = text(raw.get("opponent"), 80)
    kickoff = parse_dt(raw.get("kickoff"))
    if not opponent or kickoff is None:
        report.warn(f"{where}: needs 'opponent' and a 'kickoff' with a UTC offset")
        return None
    if kickoff < now - timedelta(hours=3):
        return None
    return {
        "opponent": opponent,
        "home": raw.get("home") is True,
        "competition": text(raw.get("competition"), 80),
        "kickoff": kickoff,
        "time_confirmed": raw.get("time_confirmed") is not False,
        "venue": text(raw.get("venue"), 80),
        "broadcast": text_list(raw.get("broadcast")),
        "preview": text(raw.get("preview"), 200),
        "talking_points": text_list(raw.get("talking_points"), 240)[:4],
        "url": safe_url(raw.get("url")),
    }


def clean_big_match(raw, now: datetime, report: Report, where: str) -> dict | None:
    if not isinstance(raw, dict):
        report.warn(f"{where}: not an object")
        return None
    title = text(raw.get("title"), 120)
    kickoff = parse_dt(raw.get("kickoff"))
    url = safe_url(raw.get("url"))
    if not title or kickoff is None or not url:
        report.warn(f"{where}: needs 'title', 'url' and a 'kickoff' with a UTC offset")
        return None
    if kickoff < now - timedelta(hours=3):
        return None
    return {
        "title": title,
        "sport": text(raw.get("sport"), 40),
        "competition": text(raw.get("competition"), 80),
        "kickoff": kickoff,
        "time_confirmed": raw.get("time_confirmed") is not False,
        "broadcast": text_list(raw.get("broadcast")),
        "why": text(raw.get("why")),
        "talking_points": text_list(raw.get("talking_points"), 240)[:3],
        "url": url,
    }


def clean_event(raw, today: date, report: Report, where: str) -> dict | None:
    if not isinstance(raw, dict):
        report.warn(f"{where}: not an object")
        return None
    title = text(raw.get("title"), 120)
    url = safe_url(raw.get("url"))
    start = parse_moment(raw.get("start"))
    end = parse_moment(raw.get("end")) if raw.get("end") else None
    if not title or not url or start is None:
        report.warn(f"{where}: needs 'title', 'url' and a 'start' date")
        return None
    if raw.get("end") and end is None:
        report.warn(f"{where}: 'end' is not a valid date, ignoring it")
    if (end or start)[0] < today:
        return None
    transport = text(raw.get("transport"), 20).lower()
    if transport and transport not in TRANSPORT:
        report.warn(f"{where}: unknown transport {transport!r}")
        transport = ""
    return {
        "title": title,
        "category": text(raw.get("category"), 40),
        "start": start,
        "end": end,
        "when": text(raw.get("when"), 120),
        "venue": text(raw.get("venue"), 100),
        "suburb": text(raw.get("suburb"), 60),
        "transport": transport,
        "nearest_station": text(raw.get("nearest_station"), 60),
        "trip": text(raw.get("trip"), 80),
        "cost": text(raw.get("cost"), 60),
        "summary": text(raw.get("summary")),
        "url": url,
    }


def clean_horizon(raw, today: date, report: Report, where: str) -> dict | None:
    if not isinstance(raw, dict):
        report.warn(f"{where}: not an object")
        return None
    title = text(raw.get("title"), 120)
    start = parse_partial(raw.get("start"))
    end = parse_partial(raw.get("end")) if raw.get("end") else None
    if not title or start is None:
        report.warn(f"{where}: needs 'title' and a 'start' of YYYY, YYYY-MM or YYYY-MM-DD")
        return None
    if (end or start)[1] < today:
        return None
    key_dates = []
    for i, kd in enumerate(as_list(raw.get("key_dates"), f"{where}.key_dates", report)):
        parsed = parse_partial(kd.get("date")) if isinstance(kd, dict) else None
        label = text(kd.get("label"), 120) if isinstance(kd, dict) else ""
        if parsed is None or not label:
            report.warn(f"{where}.key_dates[{i}]: needs 'date' and 'label'")
            continue
        if parsed[1] >= today:
            key_dates.append({"date": parsed, "label": label})
    key_dates.sort(key=lambda kd: kd["date"][0])
    status = text(raw.get("status"), 20).lower()
    return {
        "title": title,
        "category": text(raw.get("category"), 40),
        "start": start,
        "end": end,
        "location": text(raw.get("location"), 100),
        "status": status if status in HORIZON_STATUS else "",
        "key_dates": key_dates,
        "notes": text(raw.get("notes")),
        "url": safe_url(raw.get("url")),
    }


def clean_grocery(raw, today: date, report: Report, where: str) -> dict | None:
    if not isinstance(raw, dict):
        report.warn(f"{where}: not an object")
        return None
    item = text(raw.get("item"), 80)
    store = text(raw.get("store"), 40)
    price = text(raw.get("price"), 30)
    url = safe_url(raw.get("url"))
    if not item or not store or not price or not url:
        report.warn(f"{where}: needs 'item', 'store', 'price' and 'url'")
        return None
    ends = parse_moment(raw.get("ends")) if raw.get("ends") else None
    if ends and ends[0] < today:
        return None
    return {
        "item": item,
        "store": store,
        "price": price,
        "was": text(raw.get("was"), 30),
        "saving": text(raw.get("saving"), 30),
        "note": text(raw.get("note"), 120),
        "ends": ends[0] if ends else None,
        "url": url,
    }


def clean_items(raw, key: str, cleaner, context, report: Report) -> list[dict]:
    items = []
    for i, item in enumerate(as_list(raw.get(key), key, report)):
        cleaned = cleaner(item, context, report, f"{key}[{i}]")
        if cleaned:
            items.append(cleaned)
    return items


def normalize(raw, now: datetime) -> tuple[dict | None, Report]:
    report = Report()
    if not isinstance(raw, dict):
        report.errors.append("The briefing must be a JSON object.")
        return None, report
    today = now.astimezone(SYDNEY).date()

    generated_at = None
    if raw.get("generated_at") is not None:
        generated_at = parse_dt(raw["generated_at"])
        if generated_at is None:
            report.errors.append("'generated_at' must be an ISO 8601 datetime with a UTC offset.")

    teams = []
    for i, team in enumerate(as_list(raw.get("teams"), "teams", report)):
        where = f"teams[{i}]"
        if not isinstance(team, dict) or not text(team.get("name")):
            report.warn(f"{where}: needs a 'name'")
            continue
        fixtures = clean_items(team, "fixtures", clean_fixture, now, report)
        fixtures.sort(key=lambda f: f["kickoff"])
        teams.append({
            "id": re.sub(r"[^a-z0-9-]", "", text(team.get("id"), 40).lower()) or f"team-{i}",
            "name": text(team["name"], 60),
            "featured": team.get("featured") is True,
            "fixtures": fixtures[:6],
        })
    teams.sort(key=lambda t: not t["featured"])

    big_matches = clean_items(raw, "big_matches", clean_big_match, now, report)
    big_matches.sort(key=lambda m: m["kickoff"])

    briefing = {
        "generated_at": generated_at,
        "teams": teams,
        "big_matches": big_matches,
        "groceries": sorted(
            clean_items(raw, "groceries", clean_grocery, today, report),
            key=lambda g: (g["store"].lower(), g["item"].lower()),
        )[:16],
        "horizon": sorted(
            clean_items(raw, "horizon", clean_horizon, today, report),
            key=lambda h: h["start"][0],
        ),
        "notes": text_list(raw.get("notes"), 400),
    }
    for key, *_ in EVENT_SECTIONS:
        events = clean_items(raw, key, clean_event, today, report)
        events.sort(key=lambda ev: (ev["start"][0], ev["start"][1] or datetime.min.replace(tzinfo=timezone.utc)))
        briefing[key] = events
    return briefing, report


# --- Rendering ---------------------------------------------------------------


def e(value) -> str:
    return html.escape(str(value), quote=True)


def link(label: str, url: str) -> str:
    if not url:
        return e(label)
    return f'<a href="{e(url)}" target="_blank" rel="noopener">{e(label)}</a>'


def fmt_date(d: date, today: date) -> str:
    label = f"{d:%a} {d.day} {d:%b}"
    return label if d.year == today.year else f"{label} {d.year}"


def fmt_time(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt:%M}{'am' if dt.hour < 12 else 'pm'}"


def fmt_kickoff(kickoff: datetime, confirmed: bool, today: date) -> str:
    if not confirmed:
        # Unconfirmed kick-offs carry a placeholder time, so only the match-day date
        # (in the venue's own time zone) is meaningful.
        return f"{fmt_date(kickoff.date(), today)} · time TBC"
    local = kickoff.astimezone(SYDNEY)
    return f"{fmt_date(local.date(), today)} · {fmt_time(local)}"


def early_hours_badge(kickoff: datetime, confirmed: bool) -> str:
    local = kickoff.astimezone(SYDNEY)
    if not confirmed or local.hour >= 6:
        return ""
    night_before = (local - timedelta(days=1)).strftime("%a")
    return f' <span class="badge late">{e(night_before)} night</span>'


def time_parts(dt: datetime) -> tuple[str, str]:
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt:%M}", "am" if dt.hour < 12 else "pm"


def date_block(d: date, cls: str = "db") -> str:
    return (
        f'<span class="{cls}"><span class="db-dow">{d:%a}</span>'
        f'<span class="db-day">{d.day}</span><span class="db-mon">{d:%b}</span></span>'
    )


def kickoff_day(kickoff: datetime, confirmed: bool) -> date:
    # Unconfirmed kick-offs carry a placeholder time, so use the venue's match-day date.
    return kickoff.astimezone(SYDNEY).date() if confirmed else kickoff.date()


def tv_labels(values: list[str]) -> str:
    out = []
    for v in values:
        key = v.lower()
        brand = "stan" if "stan" in key else "bein" if "bein" in key else "paramount" if "paramount" in key else "other"
        out.append(f'<span class="tv tv--{brand}">{e(v)}</span>')
    return "".join(out)


def match_title(team: dict, fixture: dict) -> tuple[str, str]:
    short = SHORT_NAMES.get(team["id"], team["name"])
    return (short, fixture["opponent"]) if fixture["home"] else (fixture["opponent"], short)


def render_hero(team: dict, fixture: dict, today: date) -> str:
    theme = TEAM_THEME.get(team["id"], "neutral")
    left, right = match_title(team, fixture)
    confirmed = fixture["time_confirmed"]
    day = kickoff_day(fixture["kickoff"], confirmed)
    if confirmed:
        clock, meridiem = time_parts(fixture["kickoff"].astimezone(SYDNEY))
        time_html = f'{e(clock)}<small>{meridiem}</small>'
        countdown = f"""
        <div class="countdown" data-kickoff="{e(fixture['kickoff'].isoformat())}">
          <span><b data-unit="d">–</b>days</span><span><b data-unit="h">–</b>hrs</span><span><b data-unit="m">–</b>mins</span>
        </div>"""
    else:
        time_html = 'TBC'
        countdown = '<p class="hero-tbc">Kick-off time not announced yet</p>'
    label = " · ".join(filter(None, [team["name"], "Next match", fixture["competition"]]))
    venue = " · ".join(filter(None, [fixture["venue"], "Home" if fixture["home"] else "Away"]))
    title = f'{e(left)} <span class="hero-v">v</span> {e(right)}'
    if fixture["url"]:
        title = f'<a href="{e(fixture["url"])}" target="_blank" rel="noopener">{title}</a>'
    return f"""
    <article class="hero hero--{theme}{'' if team['featured'] else ' hero--compact'}">
      <p class="hero-label">{e(label)}</p>
      <h2 class="hero-match">{title}</h2>
      <div class="hero-grid">
        <div class="hero-main">
          <div class="hero-when">
            <span class="hero-time">{time_html}</span>
            <span class="hero-day">{e(fmt_date(day, today))}{early_hours_badge(fixture['kickoff'], confirmed)}</span>
          </div>
          {countdown}
          <p class="hero-meta">{e(venue)} {tv_labels(fixture['broadcast'])}</p>
        </div>
        {render_watch(fixture)}
      </div>
    </article>"""


def render_watch(fixture: dict) -> str:
    points = fixture["talking_points"]
    if not points and not fixture["preview"]:
        return ""
    intro = f'<p class="watch-intro">{e(fixture["preview"])}</p>' if fixture["preview"] else ""
    items = "".join(f"<li>{e(p)}</li>" for p in points)
    return f"""
        <aside class="hero-watch">
          <p class="watch-title">What to watch</p>
          {intro}
          {f'<ol class="watch-list">{items}</ol>' if items else ''}
        </aside>"""


def render_stub(team: dict, fixture: dict, today: date) -> str:
    left, right = match_title(team, fixture)
    confirmed = fixture["time_confirmed"]
    when = fmt_time(fixture["kickoff"].astimezone(SYDNEY)) if confirmed else "Time TBC"
    tag = "a" if fixture["url"] else "div"
    href = f' href="{e(fixture["url"])}" target="_blank" rel="noopener"' if fixture["url"] else ""
    return f"""
        <{tag} class="stub"{href}>
          {date_block(kickoff_day(fixture['kickoff'], confirmed))}
          <span class="stub-body">
            <span class="stub-comp">{e(fixture['competition'])}</span>
            <span class="stub-match">{e(left)} v {e(right)}</span>
            <span class="stub-time">{e(when)}{early_hours_badge(fixture['kickoff'], confirmed)}</span>
            {f'<span class="stub-preview">{e(fixture["preview"])}</span>' if fixture['preview'] else ''}
            {f'<span class="stub-tv">{tv_labels(fixture["broadcast"])}</span>' if fixture['broadcast'] else ''}
          </span>
        </{tag}>"""


def render_team(team: dict, today: date) -> str:
    fixtures = team["fixtures"]
    theme = TEAM_THEME.get(team["id"], "neutral")
    if not fixtures:
        body = f'<p class="empty">No upcoming {e(team["name"])} fixtures found.</p>'
    else:
        body = render_hero(team, fixtures[0], today)
        if len(fixtures) > 1:
            stubs = "".join(render_stub(team, f, today) for f in fixtures[1:])
            body += f'<div class="stubs stubs--{theme}">{stubs}</div>'
    return f'<section class="team" id="{e(team["id"])}">{body}</section>'


def bullet_list(points: list[str], cls: str) -> str:
    if not points:
        return ""
    return f'<ul class="{cls}">' + "".join(f"<li>{e(p)}</li>" for p in points) + "</ul>"


def render_big_matches(matches: list[dict], today: date) -> str:
    if not matches:
        rows = '<p class="empty">Nothing big found for the next few weeks.</p>'
    else:
        items = []
        for m in matches:
            confirmed = m["time_confirmed"]
            day = kickoff_day(m["kickoff"], confirmed)
            if confirmed:
                clock, meridiem = time_parts(m["kickoff"].astimezone(SYDNEY))
                time_html = f'{e(clock)}<small>{meridiem}</small>'
            else:
                time_html = "TBC"
            sub = " · ".join(filter(None, [m["sport"], m["competition"]]))
            items.append(f"""
          <li class="guide-row">
            <span class="guide-when">
              <span class="guide-time">{time_html}</span>
              <span class="guide-day">{e(fmt_date(day, today))}{early_hours_badge(m['kickoff'], confirmed)}</span>
            </span>
            <span class="guide-what">
              <span class="guide-comp">{e(sub)}</span>
              <a class="guide-title" href="{e(m['url'])}" target="_blank" rel="noopener">{e(m['title'])}</a>
              {f'<span class="guide-why">{e(m["why"])}</span>' if m['why'] else ''}
              {bullet_list(m['talking_points'], 'guide-points')}
            </span>
            <span class="guide-tv">{tv_labels(m['broadcast'])}</span>
          </li>""")
        rows = f'<ol class="guide-list">{"".join(items)}</ol>'
    return f"""
    <section class="guide" id="big-matches">
      <header class="section-head"><p class="kicker">On the box</p><h2>Big matches to watch</h2>
      <p class="lede">The must-sees on Stan Sport, beIN Sports and Paramount+, in Sydney time.</p></header>
      {rows}
    </section>"""


def weekend(today: date) -> tuple[date, date]:
    weekday = today.weekday()
    if weekday == 6:
        return today - timedelta(days=1), today
    saturday = today + timedelta(days=5 - weekday)
    return saturday, saturday + timedelta(days=1)


def fmt_event_when(ev: dict, today: date) -> str:
    start_day, start_dt = ev["start"]
    end_day = ev["end"][0] if ev["end"] else start_day
    if start_day < today:
        return f"On now · until {fmt_date(end_day, today)}"
    label = fmt_date(start_day, today)
    if start_dt:
        label += f" · {fmt_time(start_dt)}"
    if end_day != start_day:
        label += f" – {fmt_date(end_day, today)}"
    return label


def render_event(ev: dict, today: date) -> str:
    start_day = ev["start"][0]
    end_day = ev["end"][0] if ev["end"] else start_day
    sat, sun = weekend(today)
    stamps = []
    if start_day <= today <= end_day and ev["end"] and (end_day - today).days <= 2:
        stamps.append('<span class="stamp stamp--soon">Ends soon</span>')
    elif start_day <= today <= end_day:
        stamps.append('<span class="stamp stamp--now">On now</span>')
    elif start_day <= sun and end_day >= sat:
        stamps.append('<span class="stamp">This weekend</span>')
    if ev["cost"].lower().startswith("free"):
        stamps.append('<span class="stamp stamp--free">Free</span>')

    place = ", ".join(filter(None, [ev["venue"], ev["suburb"]]))
    travel = ""
    if ev["nearest_station"] or ev["trip"]:
        line = ev["transport"].replace(" ", "-") or "other"
        mode = TRANSPORT.get(ev["transport"], "")
        station = " ".join(filter(None, [ev["nearest_station"], mode.lower() if mode else ""]))
        bits = " · ".join(filter(None, [station, ev["trip"]]))
        travel = f'<p class="travel travel--{e(line)}"><span class="line-dot" aria-hidden="true"></span>{e(bits)}</p>'
    tags = "".join(f'<span class="tag">{e(t)}</span>' for t in [ev["category"]] if t)
    if ev["cost"] and not ev["cost"].lower().startswith("free"):
        tags += f'<span class="tag tag--cost">{e(ev["cost"])}</span>'

    return f"""
        <article class="card">
          {date_block(max(start_day, today))}
          <div class="card-body">
            {f'<p class="stamps">{"".join(stamps)}</p>' if stamps else ''}
            <h3><a href="{e(ev['url'])}" target="_blank" rel="noopener">{e(ev['title'])}</a></h3>
            <p class="card-when">{e(fmt_event_when(ev, today))}</p>
            {f'<p class="card-hours">{e(ev["when"])}</p>' if ev['when'] else ''}
            {f'<p class="card-place">{e(place)}</p>' if place else ''}
            {travel}
            {f'<p class="card-summary">{e(ev["summary"])}</p>' if ev['summary'] else ''}
            {f'<p class="tags">{tags}</p>' if tags else ''}
          </div>
        </article>"""


def render_event_section(key: str, kicker: str, title: str, lede: str, events: list[dict], today: date) -> str:
    if events:
        body = '<div class="cards">' + "".join(render_event(ev, today) for ev in events) + "</div>"
    else:
        body = '<p class="empty">Nothing found this time. Check back tomorrow.</p>'
    anchor = key.replace("_", "-")
    return f"""
    <section class="events events--{e(anchor)}" id="{e(anchor)}">
      <header class="section-head"><p class="kicker">{e(kicker)}</p><h2>{e(title)}</h2><p class="lede">{e(lede)}</p></header>
      {body}
    </section>"""


def store_key(store: str) -> str:
    name = store.lower()
    for key in ("woolworths", "coles", "aldi", "harris farm"):
        if key in name:
            return key.replace(" ", "-")
    return "other"


def render_groceries(items: list[dict], today: date) -> str:
    head = """<header class="section-head"><p class="kicker">In the trolley</p><h2>Healthy specials this week</h2>
      <p class="lede">The best healthy buys on special at Woolworths, Coles and Aldi.</p></header>"""
    if not items:
        return f'<section class="groceries" id="groceries">{head}<p class="empty">No specials found this time.</p></section>'
    tags = []
    for g in items:
        was = f'<span class="tag-was">Was {e(g["was"])}</span>' if g["was"] else ""
        saving = f'<span class="tag-save">{e(g["saving"])}</span>' if g["saving"] else ""
        ends = f'<span class="tag-ends">Ends {e(fmt_date(g["ends"], today))}</span>' if g["ends"] else ""
        tags.append(f"""
        <a class="shelf-tag shelf-tag--{store_key(g['store'])}" href="{e(g['url'])}" target="_blank" rel="noopener">
          <span class="tag-store">{e(g['store'])}</span>
          <span class="tag-item">{e(g['item'])}</span>
          <span class="tag-price">{e(g['price'])}</span>
          <span class="tag-meta">{was}{saving}</span>
          {f'<span class="tag-note">{e(g["note"])}</span>' if g['note'] else ''}
          {ends}
        </a>""")
    return f'<section class="groceries" id="groceries">{head}<div class="shelf">{"".join(tags)}</div></section>'


def render_horizon(items: list[dict], today: date) -> str:
    head = """<header class="section-head"><p class="kicker">Plan ahead</p><h2>On the horizon</h2>
      <p class="lede">The big ones in the next year or two, and when to grab tickets.</p></header>"""
    if not items:
        return f'<section class="horizon" id="horizon">{head}<p class="empty">Nothing listed yet.</p></section>'
    groups: dict[int, list[str]] = {}
    for h in items:
        start_first, _, start_label = h["start"]
        when = start_label
        if h["end"] and h["end"][2] != when:
            when += f" – {h['end'][2]}"
        days = (start_first - today).days
        countdown = f'<span class="days-to-go"><b>{days}</b> days to go</span>' if days > 0 else '<span class="days-to-go">Under way</span>'
        badge = f'<span class="flag flag--{e(h["status"])}">{e(HORIZON_STATUS[h["status"]])}</span>' if h["status"] else ""
        sub = " · ".join(filter(None, [h["category"], h["location"]]))
        key_dates = "".join(
            f'<li><span class="kd-date">{e(kd["date"][2])}</span><span>{e(kd["label"])}</span></li>' for kd in h["key_dates"]
        )
        groups.setdefault(start_first.year, []).append(f"""
          <article class="big-event">
            <p class="big-event-when">{e(when)} {badge}</p>
            <h3>{link(h['title'], h['url'])}</h3>
            {f'<p class="big-event-sub">{e(sub)}</p>' if sub else ''}
            {countdown}
            {f'<ul class="key-dates">{key_dates}</ul>' if key_dates else ''}
            {f'<p class="card-summary">{e(h["notes"])}</p>' if h['notes'] else ''}
          </article>""")
    years = "".join(
        f'<div class="year"><p class="year-label" aria-hidden="true">{year}</p><div class="year-items">{"".join(rows)}</div></div>'
        for year, rows in sorted(groups.items())
    )
    return f'<section class="horizon" id="horizon">{head}{years}</section>'


def render_page(briefing: dict, now: datetime) -> str:
    today = now.astimezone(SYDNEY).date()
    generated_at = briefing["generated_at"]
    if generated_at:
        local = generated_at.astimezone(SYDNEY)
        dateline = f"{local:%A} {local.day} {local:%B %Y}"
        updated = f"Updated {fmt_date(local.date(), today)}, {fmt_time(local)}"
        generated_attr = f' data-generated="{e(generated_at.isoformat())}"'
    else:
        dateline = f"{today:%A} {today.day} {today:%B %Y}"
        updated = "Waiting for the first nightly run"
        generated_attr = ""

    sections = [render_team(t, today) for t in briefing["teams"]]
    sections.append(render_big_matches(briefing["big_matches"], today))
    for key, kicker, title, lede in EVENT_SECTIONS:
        sections.append(render_event_section(key, kicker, title, lede, briefing[key], today))
    sections.append(render_groceries(briefing["groceries"], today))
    sections.append(render_horizon(briefing["horizon"], today))

    notes = ""
    if briefing["notes"]:
        notes = (
            '<section class="notes" id="notes"><h2>Notes from tonight\'s research</h2><ul>'
            + "".join(f"<li>{e(n)}</li>" for n in briefing["notes"])
            + "</ul></section>"
        )

    nav = "".join(
        f'<a href="#{e(anchor)}">{e(label)}</a>'
        for anchor, label in [
            *[(t["id"], SHORT_NAMES.get(t["id"], t["name"])) for t in briefing["teams"]],
            ("big-matches", "On TV"),
            ("live-sport", "Live sport"),
            ("son", "Son"),
            ("daughter", "Daughter"),
            ("family-fun", "Family"),
            ("deals", "Deals"),
            ("groceries", "Groceries"),
            ("horizon", "Horizon"),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LifeHub</title>
  <meta name="description" content="Fixtures, big matches and things to do around Sydney, updated every night.">
  <meta name="theme-color" content="#da291c">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23da291c'/%3E%3Cpath d='M9 8v16h12' stroke='%23fff' stroke-width='4' fill='none'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap">
  <link rel="stylesheet" href="style.css">
</head>
<body{generated_attr}>
  <header class="masthead">
    <div class="wrap">
      <p class="dateline"><span>{e(dateline)}</span><span>Sydney edition</span><span>{e(updated)}</span></p>
      <h1 class="wordmark">LifeHub</h1>
      <p class="tagline">Fixtures, big games and good things to do around Sydney</p>
    </div>
  </header>
  <nav class="section-nav"><div class="wrap">{nav}</div></nav>
  <p id="stale" class="stale" hidden>Heads up: this edition is more than a day old. The last nightly run may have failed.</p>
  <main class="wrap">
    {"".join(sections)}
    {notes}
  </main>
  <footer class="wrap">
    <p>Researched overnight by Claude. Times are Sydney time. Always check the linked source before heading out.</p>
  </footer>
  <script src="app.js"></script>
</body>
</html>
"""


# --- Entry point -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="validate only, don't render")
    parser.add_argument("--require-fresh", type=float, metavar="HOURS", help="fail if generated_at is older than this")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    try:
        raw = json.loads(args.data.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: {args.data} not found", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"error: {args.data} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    briefing, report = normalize(raw, now)
    if briefing and args.require_fresh is not None:
        generated_at = briefing["generated_at"]
        if generated_at is None or now - generated_at > timedelta(hours=args.require_fresh):
            report.errors.append(f"'generated_at' is missing or older than {args.require_fresh:g} hours.")

    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    if report.errors:
        return 1

    if briefing:
        counts = ", ".join(
            f"{key}={len(briefing[key])}" for key in ["big_matches", *(k for k, *_ in EVENT_SECTIONS), "groceries", "horizon"]
        )
        fixtures = ", ".join(f"{t['name']}={len(t['fixtures'])}" for t in briefing["teams"])
        print(f"ok: fixtures({fixtures}) {counts}; {len(report.warnings)} warning(s)")

    if args.check:
        return 0

    if args.out.exists():
        shutil.rmtree(args.out)
    shutil.copytree(SITE_SRC, args.out)
    (args.out / "index.html").write_text(render_page(briefing, now), encoding="utf-8")
    shutil.copy2(args.data, args.out / "briefing.json")
    print(f"built {args.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
