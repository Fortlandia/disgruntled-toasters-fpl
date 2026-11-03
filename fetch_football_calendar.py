"""Fetch Champions League fixture dates for the Toasters calendar.

Run after fetch_fpl.py and before fixture_intelligence.py.
Requires FOOTBALL_DATA_API_KEY as a GitHub Actions secret.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path('data')
API = 'https://api.football-data.org/v4/competitions/CL/matches'


def main():
    key = os.getenv('FOOTBALL_DATA_API_KEY', '').strip()
    if not key:
        print('No FOOTBALL_DATA_API_KEY configured; leaving calendar unchanged.')
        return

    bootstrap = json.loads((DATA / 'players.json').read_text(encoding='utf-8'))
    premier_clubs = {team['name'] for team in bootstrap['teams']}
    # Names used by football-data.org can differ from official FPL labels.
    aliases = {
        'Arsenal FC': 'Arsenal', 'Aston Villa FC': 'Aston Villa',
        'Chelsea FC': 'Chelsea', 'Liverpool FC': 'Liverpool',
        'Manchester City FC': 'Man City', 'Manchester United FC': 'Man Utd',
        'Newcastle United FC': 'Newcastle', 'Tottenham Hotspur FC': 'Spurs',
        'Nottingham Forest FC': "Nott'm Forest", 'Brighton & Hove Albion FC': 'Brighton',
        'Crystal Palace FC': 'Crystal Palace', 'Fulham FC': 'Fulham',
        'Leeds United FC': 'Leeds', 'Everton FC': 'Everton',
        'AFC Bournemouth': 'Bournemouth', 'Brentford FC': 'Brentford',
        'Sunderland AFC': 'Sunderland', 'West Ham United FC': 'West Ham',
        'Wolverhampton Wanderers FC': 'Wolves', 'Burnley FC': 'Burnley',
        'Ipswich Town FC': 'Ipswich Town', 'Hull City AFC': 'Hull City',
        'Coventry City FC': 'Coventry City',
    }

    now = datetime.now(timezone.utc)
    date_from = now.date().isoformat()
    date_to = (now + timedelta(days=45)).date().isoformat()
    query = urllib.parse.urlencode({'dateFrom': date_from, 'dateTo': date_to})
    request = urllib.request.Request(
        f'{API}?{query}',
        headers={'X-Auth-Token': key, 'User-Agent': 'Toasters-FPL-Calendar/1.0'},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        # Don't destroy previously collected calendar data on API errors.
        print(f'WARNING: Football-data.org calendar fetch failed: {exc}')
        return

    matches = payload.get('matches', [])
    events = []
    for match in matches:
        home = match.get('homeTeam') or {}
        away = match.get('awayTeam') or {}
        home_name = home.get('name') or home.get('shortName') or 'TBD'
        away_name = away.get('name') or away.get('shortName') or 'TBD'
        home_fpl = aliases.get(home_name, home_name)
        away_fpl = aliases.get(away_name, away_name)
        affected = [name for name in (home_fpl, away_fpl) if name in premier_clubs]
        if not affected:
            continue
        kickoff = match.get('utcDate')
        if not kickoff:
            continue
        status = match.get('status', 'UNKNOWN')
        events.append({
            'date': kickoff[:10],
            'competition': 'UEFA Champions League',
            'description': f'{home_name} vs {away_name} — {kickoff} (UTC)',
            'status': status,
            'source': 'football-data.org v4 (API)',
            'fixture_id': match.get('id'),
            'premier_league_clubs': affected,
        })

    path = DATA / 'football_calendar.json'
    existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'events': []}
    # Preserve curated calendar entries and replace only API-generated entries.
    curated = [e for e in existing.get('events', [])
               if e.get('source') != 'football-data.org v4 (API)']
    combined = sorted(curated + events, key=lambda e: (e['date'], e['competition']))
    path.write_text(json.dumps({'events': combined}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Football calendar updated: {len(events)} upcoming CL fixtures involving PL clubs; '
          f'{len(curated)} curated entries preserved.')
    if not matches:
        print('NOTE: API returned no matches for this date window; check competition coverage.')


if __name__ == '__main__':
    main()
