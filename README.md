# LifeHub

A personal "what's coming up" page for Sydney, refreshed every night by Claude.

It covers:

- **Manchester United** (featured) and **Sydney FC** fixtures, in Sydney time.
- **Big matches to watch** on Stan Sport, beIN Sports and Paramount+.
- **Around the neighbourhood**: local news and events near home, plus school community
  events.
- **Live sport near you**: football first, then tennis, rugby union and basketball.
- Things to do **for your son**, **for your daughter**, and **for everyone**, all
  reachable by train, metro or light rail.
- **Deals, sales and pop-ups**: sports gear, fun food, gaming, books and ticket deals,
  plus pop-up food stores, freebies and competitions.
- **Healthy specials this week** at Woolworths, Coles and Aldi.
- **On the horizon**: huge events in the next 1–2 years, with ticket and sign-up dates.

Live page: <https://utx.github.io/lifehub/>

## How it works

1. Every night around 2–3am Sydney time, the GitHub Actions workflow
   ([`.github/workflows/update.yml`](.github/workflows/update.yml)) runs Claude Code.
2. Claude reads [`interests.md`](interests.md) and the instructions in
   [`prompts/briefing.md`](prompts/briefing.md), searches the web, and writes
   [`data/briefing.json`](data/briefing.json).
3. [`scripts/build.py`](scripts/build.py) checks the data: it drops anything malformed,
   finished or without a source link, and converts every kick-off to Sydney time. Then
   it renders the page from [`site/`](site/).
4. The workflow commits the new briefing and publishes the page to GitHub Pages.

If a run fails, the previous page stays up. A banner appears on the page if it's
more than a day old.

## One-time setup

1. **Add a Claude token.** On a computer with Claude Code installed, run
   `claude setup-token` and copy the token it prints. In this repo, go to
   **Settings → Secrets and variables → Actions → New repository secret** and add
   it as `CLAUDE_CODE_OAUTH_TOKEN`. Runs then count against your Claude plan.
   (Or add an `ANTHROPIC_API_KEY` secret instead to pay per run through the API.)
2. **Turn on GitHub Pages.** Go to **Settings → Pages** and set
   **Source** to **GitHub Actions**.
3. **Add your private local details (optional).** Add a secret called `LOCAL_CONTEXT`
   with your street address (on a line starting `Address:`) and the schools to follow.
   It's only ever given to Claude during the nightly run and never written to the repo,
   and the run refuses to publish if the street address appears in the briefing.
4. **Do the first run.** Go to **Actions → Update LifeHub → Run workflow**.

## Everyday use

- **Refresh now:** Actions → Update LifeHub → Run workflow. This also works from the
  GitHub mobile app. Untick "research" to just rebuild the page without searching.
- **Change what it looks for:** edit [`interests.md`](interests.md). The next run
  picks it up.
- **Choose a model (optional):** set a repository variable `CLAUDE_MODEL` under
  Settings → Secrets and variables → Actions → Variables.

## Working on the page locally

```sh
python3 -m unittest discover -s tests   # tests
python3 scripts/build.py                # builds _site/index.html from data/briefing.json
python3 -m http.server -d _site         # view it at http://localhost:8000
```

Python 3.11+ with only the standard library. No other dependencies.
