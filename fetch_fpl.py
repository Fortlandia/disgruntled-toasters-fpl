import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TEAM_ID = 649129
LEAGUE_ID = 182069

BASE_URL = "https://fantasy.premierleague.com/api/"
OUTPUT = Path("data")
OUTPUT.mkdir(exist_ok=True)


def get_data(endpoint):
    request = urllib.request.Request(
        BASE_URL + endpoint,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def save_data(filename, data):
    with open(OUTPUT / filename, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def get_latest_picks(entry_id, gameweek):
    for gw in range(gameweek, 0, -1):
        try:
            picks = get_data(f"entry/{entry_id}/event/{gw}/picks/")
            return gw, picks
        except Exception as error:
            print(f"Picks unavailable for GW{gw}: {error}")

    return None, None


def main():
    print("Fetching Disgruntled Toasters FPL data...")

    players = get_data("bootstrap-static/")
    team = get_data(f"entry/{TEAM_ID}/")
    fixtures = get_data("fixtures/")

    save_data("players.json", players)
    save_data("team.json", team)
    save_data("fixtures.json", fixtures)

    player_lookup = {
        player["id"]: player
        for player in players["elements"]
    }

    team_lookup = {
        club["id"]: club["name"]
        for club in players["teams"]
    }

    current_gw = team["current_event"] or 1

    # Find the next unfinished gameweek
    upcoming_events = [
        event for event in players["events"]
        if not event["finished"]
    ]

    next_gw = (
        upcoming_events[0]["id"]
        if upcoming_events
        else current_gw
    )

    # Retrieve latest publicly available squad
    squad_gw, squad = get_latest_picks(TEAM_ID, current_gw)

    if squad:
        save_data("squad.json", squad)

    # Retrieve league matchups
    matchups = get_data(
        f"leagues-h2h-matches/league/{LEAGUE_ID}/"
        f"?entry={TEAM_ID}&page=1"
    )

    save_data("matchups.json", matchups)

    # Identify next opponent
    next_match = next(
        (
            match for match in matchups["results"]
            if match["event"] == next_gw
        ),
        None
    )

    opponent_id = None
    opponent_name = None

    if next_match:
        if next_match["entry_1_entry"] == TEAM_ID:
            opponent_id = next_match["entry_2_entry"]
            opponent_name = next_match["entry_2_name"]
        else:
            opponent_id = next_match["entry_1_entry"]
            opponent_name = next_match["entry_1_name"]

    opponent_squad = None
    opponent_squad_gw = None

    if opponent_id:
        opponent_squad_gw, opponent_squad = get_latest_picks(
            opponent_id,
            current_gw
        )

        if opponent_squad:
            save_data("opponent_squad.json", opponent_squad)

    # Create readable player statistics
    player_stats = []

    for player in players["elements"]:
        player_stats.append({
            "id": player["id"],
            "name": player["web_name"],
            "club": team_lookup.get(player["team"]),
            "position": player["element_type"],
            "price": player["now_cost"] / 10,
            "total_points": player["total_points"],
            "form": player["form"],
            "points_per_game": player["points_per_game"],
            "expected_goals": player.get("expected_goals"),
            "expected_assists": player.get("expected_assists"),
            "minutes": player["minutes"],
            "status": player["status"],
            "news": player["news"],
            "chance_next_round": player.get(
                "chance_of_playing_next_round"
            )
        })

    save_data("player_stats.json", player_stats)

    # Convert squad IDs to player names
    def describe_squad(picks):
        if not picks:
            return []

        described = []

        for pick in picks["picks"]:
            player = player_lookup.get(pick["element"])

            if not player:
                continue

            described.append({
                "name": player["web_name"],
                "club": team_lookup.get(player["team"]),
                "position": pick["position"],
                "captain": pick["is_captain"],
                "vice_captain": pick["is_vice_captain"],
                "total_points": player["total_points"],
                "form": player["form"],
                "status": player["status"],
                "news": player["news"]
            })

        return described

    my_squad = describe_squad(squad)
    their_squad = describe_squad(opponent_squad)

    # Identify shared players
    my_names = {player["name"] for player in my_squad}
    their_names = {player["name"] for player in their_squad}

    shared_players = sorted(my_names & their_names)

    # Upcoming fixtures
    upcoming_fixtures = []

    for fixture in fixtures:
        if fixture["event"] == next_gw:
            upcoming_fixtures.append({
                "home": team_lookup.get(fixture["team_h"]),
                "away": team_lookup.get(fixture["team_a"]),
                "kickoff": fixture["kickoff_time"],
                "home_difficulty": fixture["team_h_difficulty"],
                "away_difficulty": fixture["team_a_difficulty"]
            })

    # Build scouting report
    report = {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "team": team["name"],
        "next_gameweek": next_gw,
        "league_position": next(
            (
                league["entry_rank"]
                for league in team["leagues"]["h2h"]
                if league["id"] == LEAGUE_ID
            ),
            None
        ),
        "total_points": team["summary_overall_points"],
        "bank_millions": team["last_deadline_bank"] / 10,
        "my_squad_gameweek": squad_gw,
        "my_squad": my_squad,
        "opponent": {
            "name": opponent_name,
            "team_id": opponent_id,
            "squad_gameweek": opponent_squad_gw,
            "squad": their_squad
        },
        "shared_players": shared_players,
        "fixtures": upcoming_fixtures
    }

    save_data("scouting_report.json", report)
    # TOASTERS ANALYTICS ENGINE

    fixture_lookup = {}

    for fixture in fixtures:
        if fixture["event"] == next_gw:
            fixture_lookup[fixture["team_h"]] = {
                "opponent": team_lookup.get(fixture["team_a"]),
                "difficulty": fixture["team_h_difficulty"],
                "home": True
            }

            fixture_lookup[fixture["team_a"]] = {
                "opponent": team_lookup.get(fixture["team_h"]),
                "difficulty": fixture["team_a_difficulty"],
                "home": False
            }

    analytics = []

    for player in players["elements"]:
        fixture = fixture_lookup.get(player["team"])

        if not fixture:
            continue

        if player["status"] == "u":
            continue

        form = float(player["form"] or 0)
        xg = float(player.get("expected_goals") or 0)
        xa = float(player.get("expected_assists") or 0)

        minutes = player["minutes"]

        # Simple scouting score, not a predicted FPL points total.
        # Season-long xG and xA are normalized per 90 minutes.
        xgi_per90 = (
            (xg + xa) * 90 / minutes
            if minutes > 0 else 0
        )

        score = (
            form * 2
            + xgi_per90 * 5
            + (6 - fixture["difficulty"]) * 2
        )

        analytics.append({
            "id": player["id"],
            "name": player["web_name"],
            "club": team_lookup.get(player["team"]),
            "position": player["element_type"],
            "price": player["now_cost"] / 10,
            "form": form,
            "xgi_per90": round(xgi_per90, 2),
            "fixture": fixture["opponent"],
            "home": fixture["home"],
            "difficulty": fixture["difficulty"],
            "status": player["status"],
            "news": player["news"],
            "score": round(score, 2)
        })

    analytics.sort(
        key=lambda player: player["score"],
        reverse=True
    )

    squad_ids = {
        pick["element"]
        for pick in squad["picks"]
    } if squad else set()

    captain_candidates = [
        player for player in analytics
        if player["id"] in squad_ids
        and player["position"] in (3, 4)
        and player["status"] == "a"
    ]

    transfer_targets = [
        player for player in analytics
        if player["id"] not in squad_ids
        and player["status"] == "a"
    ]

    save_data("analytics.json", {
        "gameweek": next_gw,
        "methodology": (
            "Heuristic scouting scores based on form, "
            "season xGI per 90, and next fixture difficulty. "
            "Not projected FPL points."
        ),
        "captain_candidates": captain_candidates[:10],
        "transfer_targets": transfer_targets[:30],
        "all_players": analytics
    })

    save_data("last_updated.json", {
        "updated_utc": report["updated_utc"],
        "team_id": TEAM_ID,
        "league_id": LEAGUE_ID,
        "gameweek": current_gw,
        "next_gameweek": next_gw
    })

    print("FPL data successfully updated!")
    print(f"Next gameweek: GW{next_gw}")
    print(f"Opponent: {opponent_name}")
    print(f"Shared players: {shared_players}")


if __name__ == "__main__":
    main()
