"""Add ESPN cup fixtures to data/football_calendar.json without replacing CL data.

ESPN's undocumented scoreboard endpoints can change. This script is best-effort:
failed or empty responses preserve existing calendar entries. Run AFTER
fetch_football_calendar.py and BEFORE fixture_intelligence.py.
"""
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path('data')
CALENDAR = DATA / 'football_calendar.json'
SOURCE = 'ESPN scoreboard (unofficial)'
COMPETITIONS = {
    'uefa.europa': 'UEFA Europa League',
    'uefa.europa.conf': 'UEFA Conference League',
    'eng.fa': 'FA Cup',
    'eng.league_cup': 'Carabao Cup',
}
ALIASES = {
    'manchester city': 'Man City', 'man city': 'Man City',
    'manchester united': 'Man Utd', 'man united': 'Man Utd',
    'tottenham hotspur': 'Spurs', 'tottenham': 'Spurs',
    'nottingham forest': "Nott'm Forest", 'nottm forest': "Nott'm Forest",
    'brighton and hove albion': 'Brighton', 'brighton': 'Brighton',
    'newcastle united': 'Newcastle', 'newcastle': 'Newcastle',
    'west ham united': 'West Ham', 'west ham': 'West Ham',
    'wolverhampton wanderers': 'Wolves', 'wolverhampton': 'Wolves',
    'afc bournemouth': 'Bournemouth', 'bournemouth': 'Bournemouth',
    'leeds united': 'Leeds', 'leeds': 'Leeds',
    'sunderland afc': 'Sunderland', 'sunderland': 'Sunderland',
    'crystal palace': 'Crystal Palace',
    'aston villa': 'Aston Villa', 'arsenal': 'Arsenal',
    'liverpool': 'Liverpool', 'chelsea': 'Chelsea', 'fulham': 'Fulham',
    'brentford': 'Brentford', 'everton': 'Everton', 'burnley': 'Burnley',
    'ipswich town': 'Ipswich Town', 'hull city': 'Hull City',
    'coventry city': 'Coventry City',
}


def norm(name):
    name = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode()
    name = name.lower().replace('&', ' and ')
    name = re.sub(r'\b(fc|afc|football club)\b', '', name)
    return re.sub(r'[^a-z0-9]+', ' ', name).strip()


def match_club(competitor, clubs):
    team = competitor.get('team') or {}
    for candidate in (team.get('displayName'), team.get('name'), team.get('shortDisplayName')):
        key = norm(candidate)
        club = ALIASES.get(key)
        if club in clubs:
            return club
        for fpl in clubs:
            if norm(fpl) == key:
                return fpl
    return None


def fetch(code, start, end):
    """Probe a few ESPN scoreboard date formats; never mask HTTP failures."""
    base = f'https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard'
    probes = [
        ('single-day', {'dates': f'{start:%Y%m%d}', 'limit': 100}),
        ('month', {'dates': f'{start:%Y%m}', 'limit': 100}),
        ('no-dates', {'limit': 100}),
    ]
    failures = []
    for label, params in probes:
        url = base + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; ToastersFixtureBot/1.0)',
            'Accept': 'application/json',
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.load(response)
            if not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
                raise ValueError('JSON response missing events list')
            events = payload['events']
            print(f'ESPN {code}: {label} probe OK ({len(events)} events)')
            # A single-day response does not cover our 45-day horizon.
            # Return probe data for diagnosis only; do not replace existing
            # calendar entries unless a full-range query is proven to work.
            return events, label
        except urllib.error.HTTPError as exc:
            excerpt = exc.read(120).decode('utf-8', errors='replace')
            excerpt = ''.join(ch if ch.isprintable() else ' ' for ch in excerpt)
            failures.append(f'{label}=HTTP {exc.code} ({excerpt[:70]})')
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            failures.append(f'{label}={type(exc).__name__}: {str(exc)[:90]}')
    raise ValueError('; '.join(failures))


def parse_events(raw, code, competition, clubs, today):
    result = []
    for event in raw:
        comps = event.get('competitions') or []
        if not comps:
            continue
        competitors = comps[0].get('competitors') or []
        if len(competitors) < 2:
            continue
        affected = sorted(set(filter(None, (match_club(c, clubs) for c in competitors))))
        if not affected:
            continue
        kickoff = event.get('date') or comps[0].get('date')
        if not kickoff or len(kickoff) < 10 or kickoff[:10] < today:
            continue
        home = next((c for c in competitors if c.get('homeAway') == 'home'), competitors[0])
        away = next((c for c in competitors if c.get('homeAway') == 'away'), competitors[1])
        def label(c):
            t = c.get('team') or {}
            return t.get('displayName') or t.get('name') or 'TBD'
        status = (event.get('status') or {}).get('type') or {}
        state = status.get('name') or status.get('state') or 'UNKNOWN'
        if state.lower() in ('post', 'final', 'finished', 'completed'):
            continue
        result.append({
            'date': kickoff[:10], 'competition': competition,
            'description': f'{label(home)} vs {label(away)} — {kickoff} (UTC)',
            'status': state, 'source': SOURCE,
            'fixture_id': str(event.get('id', '')),
            'espn_league': code, 'premier_league_clubs': affected,
        })
    return result


def main():
    clubs = {t['name'] for t in json.loads((DATA / 'players.json').read_text(encoding='utf-8'))['teams']}
    existing = json.loads(CALENDAR.read_text(encoding='utf-8')) if CALENDAR.exists() else {'events': []}
    old = existing.get('events', [])
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=45)
    updated = list(old)
    for code, name in COMPETITIONS.items():
        try:
            raw, probe = fetch(code, now, end)
            new = parse_events(raw, code, name, clubs, now.date().isoformat())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            print(f'WARNING: {name}: fetch failed ({type(exc).__name__}: {str(exc)[:450]}); preserving previous data')
            continue
        # An empty response could mean ESPN has no fixtures published, or its API
        # changed. Preserve old records rather than silently deleting them.
        if not raw:
            print(f'NOTE: {name}: ESPN returned zero events; preserving previous data')
            continue
        print(f'{name}: probe={probe}; {len(raw)} ESPN events, {len(new)} PL-club matches; diagnostic only, preserving existing calendar until full-range retrieval is validated')
    updated.sort(key=lambda e: (e.get('date', ''), e.get('competition', ''), str(e.get('fixture_id', ''))))
    CALENDAR.write_text(json.dumps({'events': updated}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Calendar saved: {len(updated)} total entries (including existing CL fixtures)')


if __name__ == '__main__':
    main()
