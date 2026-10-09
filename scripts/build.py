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
    ("live_sport", "Live sport near you", "Football first, then tennis, rugby union and basketball."),
    ("son", "For your son", "Sport, gaming and running."),
    ("daughter", "For your daughter", "Arts and crafts, books and matcha."),
    ("family_fun", "Fun for everyone", "Events, pop-ups, freebies, competitions, sales and open days."),
]
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


def text_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (text(v, 120) for v in value) if t]


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
        "horizon": sorted(
            clean_items(raw, "horizon", clean_horizon, today, report),
            key=lambda h: h["start"][0],
        ),
        "notes": text_list(raw.get("notes")),
    }
    for key, _, _ in EVENT_SECTIONS:
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


def chips(values: list[str], cls: str = "chip") -> str:
    return "".join(f'<span class="{cls}">{e(v)}</span>' for v in values)


def render_next_match(fixture: dict, today: date) -> str:
    preposition = "vs" if fixture["home"] else "at"
    countdown = ""
    if fixture["time_confirmed"]:
        countdown = f'<p class="countdown" data-kickoff="{e(fixture["kickoff"].isoformat())}"></p>'
    meta = " · ".join(filter(None, [fixture["venue"], "Home" if fixture["home"] else "Away"]))
    return f"""
      <article class="next-match">
        <p class="eyebrow">Next match{' · ' + e(fixture['competition']) if fixture['competition'] else ''}</p>
        <p class="matchup">{e(preposition)} {link(fixture['opponent'], fixture['url'])}</p>
        <p class="kickoff">{e(fmt_kickoff(fixture['kickoff'], fixture['time_confirmed'], today))}{early_hours_badge(fixture['kickoff'], fixture['time_confirmed'])}</p>
        {countdown}
        <p class="meta">{e(meta)} {chips(fixture['broadcast'], 'chip tv')}</p>
      </article>"""


def render_fixture_row(fixture: dict, today: date) -> str:
    preposition = "vs" if fixture["home"] else "at"
    return f"""
        <li>
          <span class="when">{e(fmt_kickoff(fixture['kickoff'], fixture['time_confirmed'], today))}{early_hours_badge(fixture['kickoff'], fixture['time_confirmed'])}</span>
          <span class="what">{e(preposition)} {link(fixture['opponent'], fixture['url'])}</span>
          <span class="meta">{e(fixture['competition'])} {chips(fixture['broadcast'], 'chip tv')}</span>
        </li>"""


def render_team(team: dict, today: date) -> str:
    cls = "team featured" if team["featured"] else "team"
    fixtures = team["fixtures"]
    if not fixtures:
        body = '<p class="empty">No upcoming fixtures found.</p>'
    else:
        body = render_next_match(fixtures[0], today)
        if len(fixtures) > 1:
            rows = "".join(render_fixture_row(f, today) for f in fixtures[1:])
            body += f'<h3>Coming up</h3><ol class="rows">{rows}</ol>'
    return f'<section class="{cls}" id="{e(team["id"])}"><h2>{e(team["name"])}</h2>{body}</section>'


def render_big_matches(matches: list[dict], today: date) -> str:
    if not matches:
        rows = '<p class="empty">Nothing big found for the next few weeks.</p>'
    else:
        items = []
        for m in matches:
            sub = " · ".join(filter(None, [m["sport"], m["competition"]]))
            items.append(f"""
        <li>
          <span class="when">{e(fmt_kickoff(m['kickoff'], m['time_confirmed'], today))}{early_hours_badge(m['kickoff'], m['time_confirmed'])}</span>
          <span class="what">{link(m['title'], m['url'])}</span>
          <span class="meta">{e(sub)} {chips(m['broadcast'], 'chip tv')}</span>
          {f'<span class="why">{e(m["why"])}</span>' if m['why'] else ''}
        </li>""")
        rows = f'<ol class="rows">{"".join(items)}</ol>'
    return f'<section id="big-matches"><h2>Big matches to watch</h2><p class="lede">Must-see games on Stan Sport, beIN Sports and Paramount+.</p>{rows}</section>'


def fmt_event_when(ev: dict, today: date) -> str:
    start_day, start_dt = ev["start"]
    label = fmt_date(start_day, today)
    if start_dt:
        label += f" · {fmt_time(start_dt)}"
    if ev["end"] and ev["end"][0] != start_day:
        label += f" – {fmt_date(ev['end'][0], today)}"
    if start_day < today:
        label = f"On now · until {fmt_date(ev['end'][0], today)}"
    return label


def render_event(ev: dict, today: date) -> str:
    place = ", ".join(filter(None, [ev["venue"], ev["suburb"]]))
    getting_there = ""
    if ev["nearest_station"] or ev["trip"]:
        mode = TRANSPORT.get(ev["transport"], "Nearest stop")
        parts = [f"{mode}: {ev['nearest_station']}" if ev["nearest_station"] else "", ev["trip"]]
        getting_there = f'<p class="travel">{e(" · ".join(filter(None, parts)))}</p>'
    tags = chips([t for t in [ev["category"]] if t]) + chips([ev["cost"]] if ev["cost"] else [], "chip cost")
    return f"""
        <article class="card">
          <p class="eyebrow">{e(fmt_event_when(ev, today))}</p>
          <h3>{link(ev['title'], ev['url'])}</h3>
          {f'<p class="when-note">{e(ev["when"])}</p>' if ev['when'] else ''}
          {f'<p class="place">{e(place)}</p>' if place else ''}
          {getting_there}
          {f'<p class="summary">{e(ev["summary"])}</p>' if ev['summary'] else ''}
          {f'<p class="tags">{tags}</p>' if tags else ''}
        </article>"""


def render_event_section(key: str, title: str, lede: str, events: list[dict], today: date) -> str:
    if events:
        body = '<div class="cards">' + "".join(render_event(ev, today) for ev in events) + "</div>"
    else:
        body = '<p class="empty">Nothing found this time.</p>'
    return f'<section id="{e(key.replace("_", "-"))}"><h2>{e(title)}</h2><p class="lede">{e(lede)}</p>{body}</section>'


def render_horizon(items: list[dict]) -> str:
    if not items:
        return '<section id="horizon"><h2>On the horizon</h2><p class="empty">Nothing listed yet.</p></section>'
    rows = []
    for h in items:
        when = h["start"][2]
        if h["end"] and h["end"][2] != when:
            when += f" – {h['end'][2]}"
        badge = f' <span class="badge {e(h["status"])}">{e(HORIZON_STATUS[h["status"]])}</span>' if h["status"] else ""
        sub = " · ".join(filter(None, [h["category"], h["location"]]))
        key_dates = "".join(
            f'<li><span class="kd-date">{e(kd["date"][2])}</span> {e(kd["label"])}</li>' for kd in h["key_dates"]
        )
        rows.append(f"""
        <li class="horizon-item">
          <p class="eyebrow">{e(when)}</p>
          <h3>{link(h['title'], h['url'])}{badge}</h3>
          {f'<p class="meta">{e(sub)}</p>' if sub else ''}
          {f'<ul class="key-dates">{key_dates}</ul>' if key_dates else ''}
          {f'<p class="summary">{e(h["notes"])}</p>' if h['notes'] else ''}
        </li>""")
    return f'<section id="horizon"><h2>On the horizon</h2><p class="lede">The big ones for the next 1–2 years, with ticket and sign-up dates.</p><ol class="timeline">{"".join(rows)}</ol></section>'


def render_page(briefing: dict, now: datetime) -> str:
    today = now.astimezone(SYDNEY).date()
    generated_at = briefing["generated_at"]
    if generated_at:
        local = generated_at.astimezone(SYDNEY)
        updated = f"Updated {fmt_date(local.date(), today)}, {fmt_time(local)}"
        generated_attr = f' data-generated="{e(generated_at.isoformat())}"'
    else:
        updated = "Waiting for the first nightly run"
        generated_attr = ""

    sections = [render_team(t, today) for t in briefing["teams"]]
    sections.append(render_big_matches(briefing["big_matches"], today))
    for key, title, lede in EVENT_SECTIONS:
        sections.append(render_event_section(key, title, lede, briefing[key], today))
    sections.append(render_horizon(briefing["horizon"]))

    notes = ""
    if briefing["notes"]:
        notes = '<section id="notes"><h2>Notes</h2><ul>' + "".join(f"<li>{e(n)}</li>" for n in briefing["notes"]) + "</ul></section>"

    nav = "".join(
        f'<a href="#{e(anchor)}">{e(label)}</a>'
        for anchor, label in [
            *[(t["id"], t["name"]) for t in briefing["teams"]],
            ("big-matches", "Big matches"),
            ("live-sport", "Sport"),
            ("son", "Son"),
            ("daughter", "Daughter"),
            ("family-fun", "Fun"),
            ("horizon", "Horizon"),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LifeHub</title>
  <meta name="description" content="What's coming up: fixtures, big matches and things to do around Sydney.">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='%23da291c'/%3E%3C/svg%3E">
  <link rel="stylesheet" href="style.css">
</head>
<body{generated_attr}>
  <header class="top">
    <div class="wrap">
      <h1>LifeHub</h1>
      <p class="updated">{e(updated)} · Sydney time</p>
      <nav>{nav}</nav>
    </div>
  </header>
  <p id="stale" class="stale" hidden>This briefing is more than a day old. The last nightly run may have failed.</p>
  <main class="wrap">
    {"".join(sections)}
    {notes}
  </main>
  <footer class="wrap">
    <p>Researched overnight by Claude. Always check the linked source before you go.</p>
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
            f"{key}={len(briefing[key])}" for key in ["big_matches", *(k for k, _, _ in EVENT_SECTIONS), "horizon"]
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
