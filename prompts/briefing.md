# LifeHub nightly briefing

You are refreshing LifeHub, a public web page that lists what's coming up that its
owner cares about. The page is built from one file, `data/briefing.json`, which you
write. You are running unattended overnight: nobody can answer questions, so make
sensible calls and note anything uncertain in `notes`.

## Steps

1. Read `interests.md`. It is the source of truth for what to look for.
2. Read the existing `data/briefing.json`. Use its `horizon` list as the starting
   point for this run's horizon list (see below).
3. Research each section with WebSearch and WebFetch. Prefer official sources: club,
   league and venue sites, ticketing pages, broadcasters' guides and event organisers.
   Use news and listings sites to discover things, then confirm the details at the source.
   - Be thorough. This runs overnight and there's no rush. For each of `live_sport`,
     `local`, `son`, `daughter`, `family_fun`, `deals` and `groceries`, run at least 6 different searches from
     different angles (specific interests, venues, "this weekend", "school holidays",
     "free", and so on) before deciding what to include.
   - Good places to discover Sydney events: City of Sydney What's On, Sydney.com,
     NSW Government events, Time Out Sydney, Concrete Playground, Broadsheet,
     Eventbrite, ellaslist, Kidtown, the State Library and City of Sydney libraries,
     Carriageworks, the Powerhouse, the Australian Museum, Westfield centre events,
     and major stores' event pages (EB Games, JB Hi-Fi, Kinokuniya, Dymocks).
   - Good places to find deals: OzBargain (Sydney and online deals), Rebel Sport,
     Nike, Adidas, Puma, The Athlete's Foot, Ticketek and Ticketmaster offers,
     Broadsheet and Time Out food news, Concrete Playground, Instagram-announced
     pop-ups reported by news sites.
   - For fixtures, use official sources (manutd.com, premierleague.com, uefa.com,
     sydneyfc.com, aleagues.com.au) in preference to blogs and aggregators.
   - Aim for roughly the upper end of each section's limit, but never pad a section
     with weak, stale or unconfirmed items.
4. Write the complete new `data/briefing.json` in the format below.
5. Run `python3 scripts/build.py --check`. Fix every error and warning it reports, and
   run it again until it passes cleanly.

## Accuracy rules

- Every item needs a `url` for a page you actually opened that confirms its details.
  Never invent events, dates, times, prices or links. Leaving something out is better
  than guessing.
- Only include things that haven't finished yet. Events must start within the next
  4 weeks or still be running.
- **Fixture and kick-off times:** take them from an official source. Write `kickoff`
  as ISO 8601 with the correct UTC offset for the place the match is played, e.g.
  `2026-10-18T16:30:00+01:00` for 4:30pm in Manchester during BST. The page converts
  to Sydney time itself, so don't convert it yourself.
- If the date is set but the kick-off time isn't (common while TV picks are pending),
  set `time_confirmed` to `false` and use 12:00 local time on the scheduled day.
- **Broadcasters:** for Australia, check which of Stan Sport, beIN Sports or
  Paramount+ is showing each match. If you can't confirm, leave `broadcast` empty.
  Don't guess.
- Things to do in person must be reachable by train, metro or light rail. Give the
  nearest station or stop and a realistic trip time from home (see `interests.md`).

## Sections

- `teams`: Manchester United (`"featured": true`) then Sydney FC. Up to the next 5
  fixtures each, in date order.
  - **Match previews.** For each team's **next** fixture, write a one-sentence
    `preview` and 3–4 `talking_points`: the big things to watch for. Think current
    form and league position, injuries and suspensions, key players and match-ups,
    head-to-head record, what's at stake, new signings or a new manager, and any
    storyline people are talking about. For the **other** fixtures, write a
    one-sentence `preview` only.
  - Base these on reporting from this week (club sites, BBC Sport, Sky Sports, The
    Athletic, Manchester Evening News, The Guardian; for Sydney FC: KEEPUP, the
    A-Leagues site, the Sydney Morning Herald, the club site). Open the articles you
    rely on. Never present a guess about team news as fact. If the line-up or an
    injury isn't confirmed, say so ("doubtful", "expected to").
  - Keep each talking point to one punchy sentence, under about 30 words.
- `big_matches`: about 5–10 must-see events in the next 3–4 weeks, any sport, that are
  shown in Australia on Stan Sport, beIN Sports or Paramount+. Say in one line why
  each one matters. For football matches, also add 2–3 short `talking_points`
  (same rules as the match previews above).
- `local`: up to 12 items of local news and events around the home suburb (see
  "Around the neighbourhood" in `interests.md`, and the private local context below if
  there is one).
  - Look at: City of Sydney news and What's On for Alexandria, Erskineville, Eveleigh,
    Redfern and Waterloo; South Eveleigh's own events page; local news (City Hub,
    the Inner West Courier, SMH local stories); and the schools' public websites,
    newsletters and event calendars.
  - Events use the normal event fields. For **news** (something that happened or was
    announced, without a date to go to), set `"kind": "news"`, set `start` to the date
    it was reported, and keep it only if it was reported in the last 7 days.
  - For school events, name the school in `venue` and describe the event, but **never**
    mention a child, which child goes there, or anything about the family. Never write
    the home street address anywhere; refer to "home" instead.
  - For things within walking distance, set `trip` to something like "about 10 min walk".
- `live_sport`: up to 10 events in Sydney (football first, then tennis, rugby union,
  basketball; never AFL or NRL).
- `son`: up to 8 things for a 9-year-old boy (sport, gaming, running).
- `daughter`: up to 8 things for a 12-year-old girl (arts and crafts, books, matcha).
- `family_fun`: up to 12 fun things for a parent and kids (events, festivals, open
  days, school-holiday activities).
- `deals`: up to 12 good sales and pop-ups (see `interests.md`): sports gear and
  clothing, fun food, gaming, books, craft supplies, ticket deals, pop-up food
  stores, freebies and competitions. Online sales are fine. Use `start` for when the
  deal starts (today's date if it's already running) and `end` for when it finishes;
  put the discount in `summary` (e.g. "Up to 40% off football boots") and the price in
  `cost` where it applies. For online deals, set `venue` to "Online" and leave
  `transport`, `nearest_station` and `trip` as `null`.
- `groceries`: up to 16 of the best **healthy** items on special this week at
  Woolworths, Coles and Aldi (see `interests.md`). Half-price and big discounts first,
  spread across stores and food types.
  - Sources: the stores' weekly specials and catalogue pages (woolworths.com.au,
    coles.com.au, aldi.com.au "Special Buys" and catalogue), catalogue sites such as
    SaleFinder and Lasoo, and OzBargain half-price posts. Supermarket sites sometimes
    block automated access; if so, use the catalogue sites. Only list items you can see
    with a price for this week.
  - Weekly specials usually run Wednesday to Tuesday. Set `ends` to the last day of
    the special (YYYY-MM-DD).
- `horizon`: up to 15 huge events in the next 1–2 years.
  - Start from the previous run's list: keep entries that still apply, update any
    details that changed, and drop ones that are over.
  - Mark each entry's `status`: `"new"` (not in the previous list), `"updated"`
    (something important changed, such as a new ticket date) or `"unchanged"`.
  - Look for and list `key_dates`: ticket ballots, on-sale dates, registration
    deadlines and the event itself.
- `notes`: short notes for the reader. Use them for anything you couldn't confirm
  (e.g. "Sydney FC v Wellington kick-off time not yet announced"). Leave the list
  empty if there's nothing to say.

Don't repeat an item across sections. Put it where it fits best.

## Format of `data/briefing.json`

```json
{
  "generated_at": "2026-10-10T03:40:00+11:00",
  "teams": [
    {
      "id": "man-utd",
      "name": "Manchester United",
      "featured": true,
      "fixtures": [
        {
          "opponent": "Liverpool",
          "home": true,
          "competition": "Premier League",
          "kickoff": "2026-10-18T16:30:00+01:00",
          "time_confirmed": true,
          "venue": "Old Trafford",
          "broadcast": ["Stan Sport"],
          "preview": "<one sentence setting up the match>",
          "talking_points": [
            "<one punchy sentence about form or what's at stake>",
            "<one punchy sentence about team news, e.g. a key player doubtful>"
          ],
          "url": "https://www.manutd.com/en/matches/fixtures-and-results"
        }
      ]
    },
    { "id": "sydney-fc", "name": "Sydney FC", "featured": false, "fixtures": [] }
  ],
  "big_matches": [
    {
      "title": "Real Madrid v Barcelona",
      "sport": "Football",
      "competition": "LaLiga (El Clásico)",
      "kickoff": "2026-10-25T16:15:00+01:00",
      "time_confirmed": true,
      "broadcast": ["beIN Sports"],
      "why": "First Clásico of the season, top two separated by a point.",
      "talking_points": ["<one punchy sentence>"],
      "url": "https://..."
    }
  ],
  "live_sport": [
    {
      "title": "Matildas v Brazil",
      "category": "Football",
      "start": "2026-10-28T19:30:00+11:00",
      "end": null,
      "when": null,
      "venue": "Allianz Stadium",
      "suburb": "Moore Park",
      "transport": "light rail",
      "nearest_station": "Moore Park",
      "trip": "about 25 min from Redfern",
      "cost": "From $35",
      "summary": "International friendly.",
      "url": "https://..."
    }
  ],
  "local": [
    {
      "title": "Sydney Park playground reopens",
      "kind": "news",
      "category": "News",
      "start": "2026-10-08",
      "end": null,
      "when": null,
      "venue": "Sydney Park",
      "suburb": "Alexandria",
      "transport": null,
      "nearest_station": null,
      "trip": "about 15 min walk",
      "cost": null,
      "summary": "The upgraded playground has reopened after six months of works.",
      "url": "https://..."
    }
  ],
  "son": [],
  "daughter": [],
  "family_fun": [],
  "deals": [],
  "groceries": [
    {
      "item": "Blueberries 125g punnet",
      "store": "Woolworths",
      "price": "$2.50",
      "was": "$5.00",
      "saving": "Half price",
      "note": null,
      "ends": "2026-10-13",
      "url": "https://..."
    }
  ],
  "horizon": [
    {
      "title": "Rugby World Cup 2027",
      "category": "Rugby union",
      "start": "2027-10",
      "end": "2027-11",
      "location": "Australia (final in Sydney)",
      "status": "unchanged",
      "key_dates": [
        { "date": "2027-02", "label": "General ticket sale opens" }
      ],
      "notes": "Sign up on the official site for ballot alerts.",
      "url": "https://..."
    }
  ],
  "notes": []
}
```

Field rules:

- `generated_at`: the current time, ISO 8601 with offset.
- Event `start` and `end` (sections other than `teams`, `big_matches` and `horizon`):
  either a date `YYYY-MM-DD` or an ISO 8601 datetime with offset. `end` is optional
  (use `null`). For something that runs over several days with set hours, give the
  date range and describe the hours in `when` (e.g. "Weekends 10am–4pm").
- `transport`: one of `"train"`, `"metro"`, `"light rail"`, or `null` for walking distance.
- `kind`: optional. Use `"news"` for local news items (see `local`).
- `cost`: short text like `"Free"`, `"From $25"` or `"$10 kids"`. Use `null` if unknown.
- Horizon `start`, `end` and key-date `date`: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`,
  whichever is as precise as is actually known.
- Keep `summary`, `why`, `preview` and `notes` text to one or two short sentences.
- `preview` and `talking_points` are optional on fixtures and big matches; leave them
  out (or empty) rather than guess.
