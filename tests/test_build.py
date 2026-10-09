import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402

# 8pm Thursday 15 October 2026 in Sydney (AEDT, UTC+11).
NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


def sample() -> dict:
    return {
        "generated_at": "2026-10-15T03:30:00+11:00",
        "teams": [
            {"id": "sydney-fc", "name": "Sydney FC", "featured": False, "fixtures": []},
            {
                "id": "man-utd",
                "name": "Manchester United",
                "featured": True,
                "fixtures": [
                    {
                        "opponent": "Arsenal",
                        "home": False,
                        "competition": "Premier League",
                        "kickoff": "2026-10-25T16:30:00+00:00",
                        "url": "https://example.com/arsenal",
                    },
                    {
                        "opponent": "Liverpool",
                        "home": True,
                        "competition": "Premier League",
                        "kickoff": "2026-10-18T16:30:00+01:00",
                        "broadcast": ["Stan Sport"],
                        "url": "https://example.com/liverpool",
                    },
                    {
                        "opponent": "Chelsea",
                        "home": True,
                        "kickoff": "2026-10-01T20:00:00+01:00",
                    },
                ],
            },
        ],
        "big_matches": [],
        "live_sport": [
            {
                "title": "Matildas v Brazil",
                "start": "2026-10-28T19:30:00+11:00",
                "transport": "light rail",
                "nearest_station": "Moore Park",
                "url": "https://example.com/matildas",
            },
            {"title": "Finished yesterday", "start": "2026-10-14", "url": "https://example.com/old"},
            {"title": "No link", "start": "2026-10-20"},
            {"title": "Bad link", "start": "2026-10-20", "url": "javascript:alert(1)"},
        ],
        "son": [],
        "daughter": [
            {
                "title": "Craft <b>fair</b>",
                "start": "2026-10-10",
                "end": "2026-10-20",
                "url": "https://example.com/craft",
            }
        ],
        "family_fun": [],
        "horizon": [
            {
                "title": "Rugby World Cup 2027",
                "start": "2027-10",
                "end": "2027-11",
                "status": "new",
                "key_dates": [
                    {"date": "2027-02", "label": "Tickets on sale"},
                    {"date": "2026-01", "label": "Already happened"},
                ],
            },
            {"title": "Over", "start": "2026-07"},
        ],
        "notes": [],
    }


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self.briefing, self.report = build.normalize(sample(), NOW)

    def test_featured_team_first_and_fixtures_sorted(self):
        teams = self.briefing["teams"]
        self.assertEqual(teams[0]["name"], "Manchester United")
        self.assertEqual([f["opponent"] for f in teams[0]["fixtures"]], ["Liverpool", "Arsenal"])

    def test_past_and_invalid_items_dropped(self):
        self.assertEqual([ev["title"] for ev in self.briefing["live_sport"]], ["Matildas v Brazil"])
        self.assertEqual(len(self.report.warnings), 2)  # "No link" and "Bad link"
        self.assertEqual(self.report.errors, [])

    def test_running_event_kept(self):
        self.assertEqual(len(self.briefing["daughter"]), 1)

    def test_horizon_filters_past(self):
        horizon = self.briefing["horizon"]
        self.assertEqual([h["title"] for h in horizon], ["Rugby World Cup 2027"])
        self.assertEqual([kd["label"] for kd in horizon[0]["key_dates"]], ["Tickets on sale"])

    def test_naive_generated_at_is_an_error(self):
        data = sample()
        data["generated_at"] = "2026-10-15T03:30:00"
        _, report = build.normalize(data, NOW)
        self.assertTrue(report.errors)


class FormatTests(unittest.TestCase):
    def test_kickoff_shown_in_sydney_time(self):
        kickoff = build.parse_dt("2026-10-18T16:30:00+01:00")
        self.assertEqual(build.fmt_kickoff(kickoff, True, NOW.date()), "Mon 19 Oct · 2:30am")
        self.assertIn("Sun night", build.early_hours_badge(kickoff, True))

    def test_unconfirmed_kickoff_uses_venue_date(self):
        kickoff = build.parse_dt("2026-10-18T12:00:00+01:00")
        self.assertEqual(build.fmt_kickoff(kickoff, False, NOW.date()), "Sun 18 Oct · time TBC")
        self.assertEqual(build.early_hours_badge(kickoff, False), "")

    def test_partial_dates(self):
        self.assertEqual(build.parse_partial("2027-10")[2], "Oct 2027")
        self.assertEqual(build.parse_partial("2027")[1].isoformat(), "2027-12-31")
        self.assertIsNone(build.parse_partial("late 2027"))


class RenderTests(unittest.TestCase):
    def test_page_escapes_text_and_drops_unsafe_links(self):
        briefing, _ = build.normalize(sample(), NOW)
        page = build.render_page(briefing, NOW)
        self.assertIn("Craft &lt;b&gt;fair&lt;/b&gt;", page)
        self.assertNotIn("javascript:", page)
        self.assertIn("Moore Park light rail", page)
        self.assertIn("On now · until Tue 20 Oct", page)

    def write_seed(self, tmp: str) -> Path:
        seed = Path(tmp) / "briefing.json"
        seed.write_text(json.dumps({"generated_at": None, "teams": [], "notes": ["First run pending."]}))
        return seed

    def test_deal_ending_soon_and_online(self):
        data = sample()
        data["deals"] = [
            {
                "title": "Boot sale",
                "start": "2026-10-10",
                "end": "2026-10-16",
                "venue": "Online",
                "summary": "Up to 40% off football boots.",
                "url": "https://example.com/boots",
            }
        ]
        briefing, report = build.normalize(data, NOW)
        self.assertEqual(report.warnings[-1:], ["live_sport[3]: needs 'title', 'url' and a 'start' date"])
        page = build.render_page(briefing, NOW)
        self.assertIn("Ends soon", page)
        self.assertIn('id="deals"', page)
        self.assertNotIn("ticker", page)

    def test_seed_briefing_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = self.write_seed(tmp)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "build.py"), "--data", str(seed), "--out", str(Path(tmp) / "site")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            page = (Path(tmp) / "site" / "index.html").read_text()
            self.assertIn("Waiting for the first nightly run", page)

    def test_require_fresh_rejects_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = self.write_seed(tmp)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "build.py"), "--check", "--data", str(seed), "--require-fresh", "3"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)

    def test_invalid_json_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "briefing.json"
            bad.write_text("{not json")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "build.py"), "--check", "--data", str(bad)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("not valid JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
