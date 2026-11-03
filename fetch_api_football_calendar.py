"""Best-effort API-FOOTBALL cup calendar ingestion. Preserves Champions League and other sources."""
import json
import os
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

CALENDAR = Path("data/football_calendar.json")
SOURCE = "API-FOOTBALL (api-sports.io)"
TARGETS = {
    "UEFA Europa League": ("europa", None),
    "UEFA Conference League": ("conference", None),
    "FA Cup": ("fa cup", "England"),
    "Carabao Cup": ("league cup", "England"),
}
# Find competition IDs dynamically; do not assume IDs are valid for the season.
def get(path, params, key):
    url = "https://v3.football.api-sports.io/" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise ValueError("API errors: " + str(payload["errors"])[:400])
    return payload.get("response", [])

def normalize(name):
    import re
    s = (name or "").lower().replace("&", "and")
    s = re.sub(r"\\b(fc|afc|football club)\\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)

ALIASES = {
    "manchestercity": "Man City", "manchesterunited": "Man Utd",
    "tottenhamhotspur": "Spurs", "nottinghamforest": "Nott'm Forest",
    "brightonandhovealbion": "Brighton", "newcastleunited": "Newcastle",
    "westhamunited": "West Ham", "wolverhamptonwanderers": "Wolves",
    "leedsunited": "Leeds", "sunderland": "Sunderland",
    "bournemouth": "Bournemouth", "afcbournemouth": "Bournemouth",
}
def club(name, clubs):
    key = normalize(name)
    if key in ALIASES and ALIASES[key] in clubs:
        return ALIASES[key]
    return next((c for c in clubs if normalize(c) == key), None)

def main():
    key = os.getenv("API_FOOTBALL_KEY", "")
    if not key:
        print("WARNING: API_FOOTBALL_KEY missing; preserving calendar")
        return
    clubs = {t["name"] for t in json.loads(Path("data/players.json").read_text())["teams"]}
    existing = json.loads(CALENDAR.read_text()) if CALENDAR.exists() else {"events": []}
    events = existing.get("events", [])
    today = datetime.now(timezone.utc).date()
    season = today.year if today.month >= 7 else today.year - 1
    until = today + timedelta(days=60)
    for label, (search, country) in TARGETS.items():
        try:
            options = get("leagues", {"search": search, "season": season}, key)
            matches = [o for o in options if (not country or (o.get("country") or {}).get("name") == country)]
            # Match full competition name where possible, avoiding similarly named regional cups.
            if label == "Carabao Cup":
                matches = [o for o in matches if "league cup" in (o.get("league") or {}).get("name", "").lower() or "efl cup" in (o.get("league") or {}).get("name", "").lower()]
            elif label == "FA Cup":
                matches = [o for o in matches if (o.get("league") or {}).get("name", "").lower() == "fa cup"]
            elif label == "UEFA Europa League":
                matches = [o for o in matches if (o.get("league") or {}).get("name", "").lower() == "uefa europa league" or (o.get("league") or {}).get("name", "").lower() == "europa league"]
            else:
                matches = [o for o in matches if "conference league" in (o.get("league") or {}).get("name", "").lower() and (o.get("country") or {}).get("name") in ("World", "Europe")]
            if not matches:
                print(f"WARNING: {label}: no competition for season {season}; keeping old data")
                continue
            league_id = matches[0]["league"]["id"]
            fixtures = get("fixtures", {"league": league_id, "season": season, "from": str(today), "to": str(until)}, key)
            new = []
            for f in fixtures:
                teams = f.get("teams") or {}
                home, away = (teams.get("home") or {}).get("name", ""), (teams.get("away") or {}).get("name", "")
                affected = sorted({c for n in (home, away) if (c := club(n, clubs))})
                if not affected:
                    continue
                fx = f.get("fixture") or {}
                kickoff = fx.get("date", "")
                if not kickoff:
                    continue
                new.append({"date": kickoff[:10], "competition": label,
                    "description": f"{home} vs {away} — {kickoff}",
                    "status": (fx.get("status") or {}).get("short", "UNKNOWN"),
                    "source": SOURCE, "fixture_id": fx.get("id"),
                    "premier_league_clubs": affected})
            # Only replace existing API-FOOTBALL records when the request succeeded.
            events = [e for e in events if not (e.get("source") == SOURCE and e.get("competition") == label)]
            events.extend(new)
            print(f"{label}: league_id={league_id}, {len(fixtures)} fixtures, {len(new)} involving PL clubs")
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            print(f"WARNING: {label}: {type(exc).__name__}: {str(exc)[:250]}; preserving previous data")
    events.sort(key=lambda e: (e.get("date", ""), e.get("competition", ""), str(e.get("fixture_id", ""))))
    CALENDAR.write_text(json.dumps({"events": events}, indent=2, ensure_ascii=False) + "\n")
    print(f"Calendar: {len(events)} total entries; {sum(e.get('source') == SOURCE for e in events)} API-FOOTBALL entries")

if __name__ == "__main__":
    main()
