"""Disgruntled Toasters: FPL fixture and calendar awareness (no projection changes)."""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path('data')
WINDOW = 6


def read(name, default=None):
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def write(name, value):
    DATA.mkdir(exist_ok=True)
    (DATA / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    bootstrap = read('players.json')
    fixtures = read('fixtures.json')
    squad = read('squad.json', {})
    if not bootstrap or fixtures is None:
        raise RuntimeError('Run fetch_fpl.py before fixture_intelligence.py')
    clubs = {t['id']: t['name'] for t in bootstrap['teams']}
    players = {p['id']: p for p in bootstrap['elements']}
    events = sorted(bootstrap['events'], key=lambda e: e['id'])
    upcoming = [e for e in events if not e.get('finished')]
    if not upcoming:
        print('Season complete; reporting final gameweeks')
        upcoming = events[-WINDOW:]
    focus = upcoming[0]['id']
    weeks = [e for e in events if focus <= e['id'] < focus + WINDOW]
    fixture_by_gw = defaultdict(lambda: defaultdict(list))
    current_snapshot = {}
    unassigned = []
    for f in fixtures:
        fid = str(f['id'])
        snapshot = {'event': f.get('event'), 'kickoff_time': f.get('kickoff_time'),
                    'team_h': f['team_h'], 'team_a': f['team_a'], 'finished': f.get('finished', False)}
        current_snapshot[fid] = snapshot
        if f.get('event') is None and not f.get('finished'):
            unassigned.append({'fixture_id': f['id'], 'home': clubs[f['team_h']],
                               'away': clubs[f['team_a']], 'kickoff': f.get('kickoff_time'),
                               'status': 'Unassigned to an FPL gameweek; rescheduling not confirmed'})
        if f.get('event') is not None:
            for club_id, opponent_id, home in ((f['team_h'], f['team_a'], True),
                                                (f['team_a'], f['team_h'], False)):
                fixture_by_gw[f['event']][club_id].append({
                    'fixture_id': f['id'], 'opponent': clubs[opponent_id],
                    'home': home, 'kickoff': f.get('kickoff_time'),
                    'finished': f.get('finished', False)})

    owned = defaultdict(list)
    for pick in squad.get('picks', []):
        player = players.get(pick['element'])
        if player:
            owned[player['team']].append(player['web_name'])

    gw_reports = []
    for e in weeks:
        gw = e['id']
        entries = []
        for cid, name in sorted(clubs.items(), key=lambda x: x[1]):
            games = sorted(fixture_by_gw[gw][cid], key=lambda x: x['kickoff'] or '')
            count = len(games)
            entries.append({'club': name, 'club_id': cid, 'fixture_count': count,
                            'status': 'BLANK' if count == 0 else 'DOUBLE_OR_MORE' if count >= 2 else 'NORMAL',
                            'fixtures': games, 'owned_players': owned[cid]})
        gw_reports.append({'gameweek': gw, 'deadline': e.get('deadline_time'),
                           'finished': e.get('finished', False),
                           'blanks': [x for x in entries if x['fixture_count'] == 0],
                           'doubles': [x for x in entries if x['fixture_count'] >= 2],
                           'clubs': entries})

    old_snapshot = read('fixture_snapshot.json', {})
    changes = []
    for fid, new in current_snapshot.items():
        old = old_snapshot.get(fid)
        if old is None:
            continue  # New fixture records are not necessarily reschedules.
        if old.get('event') != new.get('event') or old.get('kickoff_time') != new.get('kickoff_time'):
            changes.append({'fixture_id': int(fid), 'home': clubs[new['team_h']],
                            'away': clubs[new['team_a']],
                            'previous_gameweek': old.get('event'), 'new_gameweek': new.get('event'),
                            'previous_kickoff': old.get('kickoff_time'), 'new_kickoff': new.get('kickoff_time'),
                            'note': 'FPL fixture record changed; check official confirmation'})

    # Optional human-maintained calendar. Do not invent competition dates or call-ups.
    calendar = read('football_calendar.json', {'events': []})
    calendar_events = calendar.get('events', []) if isinstance(calendar, dict) else []
    if not isinstance(calendar_events, list):
        raise ValueError('football_calendar.json must have an events array')
    for item in calendar_events:
        if not all(key in item for key in ('date', 'competition', 'description', 'status')):
            raise ValueError('Calendar events require date, competition, description and status')
    calendar_events.sort(key=lambda item: item['date'])

    result = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'source': 'Official FPL API via fetch_fpl.py; optional manually maintained football_calendar.json',
        'current_gameweek': focus,
        'squad_source_gameweek': squad.get('entry_history', {}).get('event'),
        'lookahead_gameweeks': len(weeks),
        'gameweeks': gw_reports,
        'unassigned_fixtures': unassigned,
        'fixture_changes_since_previous_run': changes,
        'calendar_events': calendar_events,
        'calendar_coverage': 'Optional curated calendar only; external cup/international fixtures not automatically fetched',
        'notes': [
            'A blank/double is confirmed only in the sense that the current FPL API assigns zero/multiple fixtures; future schedules can change.',
            'An unassigned fixture is not assumed to be a confirmed blank or double in any particular future gameweek.',
            'Squad data uses the latest publicly available picks and may lag private transfers.',
            'Fixture intelligence is informational and does not modify lineup projections.',
            'The chip reset after GW19 is user-provided league planning context; verify rules in FPL before relying on it.'
        ]
    }
    write('fixture_intelligence.json', result)
    write('fixture_snapshot.json', current_snapshot)

    lines = ['# 🍞 Disgruntled Toasters — Fixture Command Center', '',
             f"Updated (UTC): {result['generated_utc']}",
             f"**Next unfinished GW:** {focus} · **Squad snapshot:** GW{result['squad_source_gameweek'] or '?'}", '',
             '## Six-gameweek fixture watch', '',
             '| GW | Deadline (UTC) | Blank teams | Double teams | Toasters affected |',
             '|---|---|---|---|---|']
    for report in gw_reports:
        blanks = report['blanks']
        doubles = report['doubles']
        affected = [f"{entry['club']}: {', '.join(entry['owned_players'])}" for entry in blanks + doubles
                    if entry['owned_players']]
        lines.append(f"| {report['gameweek']} | {report['deadline'] or 'TBC'} | "
                     f"{', '.join(x['club'] for x in blanks) or '—'} | "
                     f"{', '.join(x['club'] for x in doubles) or '—'} | "
                     f"{'<br>'.join(affected) or '—'} |")
    lines.extend(['', '## Fixture changes since previous run', ''])
    if changes:
        for c in changes:
            lines.append(f"- **{c['home']} vs {c['away']}**: GW {c['previous_gameweek']} → "
                         f"GW {c['new_gameweek']}; kickoff {c['previous_kickoff']} → {c['new_kickoff']}.")
    else:
        lines.append('No changes detected (or this is the first run).')
    lines.extend(['', '## Fixtures awaiting gameweek assignment', ''])
    if unassigned:
        for f in unassigned:
            lines.append(f"- {f['home']} vs {f['away']} — kickoff {f['kickoff'] or 'TBC'}; GW unassigned.")
    else:
        lines.append('None currently listed in the FPL feed.')
    lines.extend(['', '## International breaks and other competitions', ''])
    if calendar_events:
        for e in calendar_events:
            lines.append(f"- **{e['date']} · {e['competition']}** — {e['description']} "
                         f"(**{e['status']}**; source: {e.get('source', 'not specified')})")
    else:
        lines.append('**Not yet populated.** International, UEFA and domestic cup schedules require '
                     'a verified calendar feed or curated entries; no events have been assumed.')
    lines.extend(['', '## Chip planning', '',
                  '- Keep an eye on potential blanks/doubles before using Free Hit, Triple Captain or other chips.',
                  '- User-reported first-half chip reset: after GW19. **Verify current FPL rules.**',
                  '', '## Important caveats', '',
                  '- Future blanks/doubles reflect **current FPL fixture assignments**, not guaranteed final schedules.',
                  '- Club competition dates do not establish that an individual player was selected or played.',
                  '- The squad is based on the latest publicly available picks; private transfers may not appear yet.',
                  '- This report does **not** change optimizer projections.', ''])
    (DATA / 'TOASTERS_FIXTURE_REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Fixture Command Center complete: GW{focus}, {len(weeks)} weeks, '
          f'{len(changes)} fixture changes, {len(unassigned)} unassigned fixtures')


if __name__ == '__main__':
    main()
