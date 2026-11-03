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
# TOASTERS TRANSFER INTELLIGENCE — VERSION 2

    from collections import Counter

    owned_players = [
        player_lookup[pick["element"]]
        for pick in squad["picks"]
    ] if squad else []

    club_counts = Counter(
        player["team"] for player in owned_players
    )

    # Evaluate the next five gameweeks
    future_fixtures = {}

    for fixture in fixtures:
        gw = fixture.get("event")

        if gw is None or not (next_gw <= gw < next_gw + 5):
            continue

        for club_id, difficulty in [
            (fixture["team_h"], fixture["team_h_difficulty"]),
            (fixture["team_a"], fixture["team_a_difficulty"])
        ]:
            future_fixtures.setdefault(club_id, []).append(
                difficulty
            )

    # Build improved player rankings
    improved_rankings = []

    for player in players["elements"]:

        minutes = player["minutes"]

        # Exclude extremely small samples
        if minutes < 270:
            continue

        if player["status"] != "a":
            continue

        difficulties = future_fixtures.get(player["team"], [])

        if not difficulties:
            continue

        form = float(player["form"] or 0)

        xg = float(player.get("expected_goals") or 0)
        xa = float(player.get("expected_assists") or 0)

        xgi_per90 = (xg + xa) * 90 / minutes

        average_difficulty = (
            sum(difficulties) / len(difficulties)
        )

        fixture_score = (6 - average_difficulty) * 2

        # Heuristic scouting score, not predicted FPL points
        score = (
            form * 2
            + xgi_per90 * 5
            + fixture_score
        )

        already_owned = any(
            owned["id"] == player["id"]
            for owned in owned_players
        )

        club_full = (
            club_counts[player["team"]] >= 3
        )

        improved_rankings.append({
            "id": player["id"],
            "name": player["web_name"],
            "club": team_lookup.get(player["team"]),
            "club_id": player["team"],
            "position": player["element_type"],
            "price": player["now_cost"] / 10,
            "minutes": minutes,
            "form": form,
            "xgi_per90": round(xgi_per90, 2),
            "average_fixture_difficulty": round(
                average_difficulty, 2
            ),
            "fixtures_evaluated": len(difficulties),
            "score": round(score, 2),
            "already_owned": already_owned,
            "club_full": club_full
        })

    improved_rankings.sort(
        key=lambda player: player["score"],
        reverse=True
    )

    # Include defenders in captaincy scouting
    improved_captains = [
        player for player in improved_rankings
        if player["already_owned"]
        and player["position"] in (2, 3, 4)
    ]

    # Exclude owned players and clubs already at capacity
    legal_club_targets = [
        player for player in improved_rankings
        if not player["already_owned"]
        and not player["club_full"]
    ]

    save_data("transfer_intelligence.json", {
        "gameweek": next_gw,
        "squad_source_gameweek": squad_gw,
        "bank_millions_at_last_deadline":
            team["last_deadline_bank"] / 10,
        "methodology": (
            "Five-gameweek heuristic scouting scores. "
            "Minimum 270 season minutes. "
            "Excludes unavailable players and transfers "
            "into clubs already at the three-player limit. "
            "Does not yet validate individual transfer "
            "affordability or exact selling prices. "
            "Not projected FPL points."
        ),
        "captain_candidates": improved_captains[:15],
        "transfer_targets": legal_club_targets[:40],
        "club_counts": dict(club_counts)
    })
# TOASTERS LINEUP OPTIMIZER — VERSION 1
    # Uses the latest publicly available squad.
    # Scores are scouting estimates, NOT projected FPL points.

    from itertools import combinations

    if squad:
        owned_ids = {
            pick["element"]
            for pick in squad["picks"]
        }

        # Use our five-gameweek rankings as a starting point.
        # These scores will later be replaced with
        # gameweek-specific projected FPL points.
        ranked_owned = [
            player for player in improved_rankings
            if player["id"] in owned_ids
        ]

        by_position = {
            position: [
                player for player in ranked_owned
                if player["position"] == position
            ]
            for position in (1, 2, 3, 4)
        }

        best_lineup = None
        best_score = float("-inf")

        # Test every legal outfield formation.
        for defenders in range(3, 6):
            for midfielders in range(2, 6):
                forwards = 10 - defenders - midfielders

                if not 1 <= forwards <= 3:
                    continue

                if (
                    len(by_position[1]) < 1
                    or len(by_position[2]) < defenders
                    or len(by_position[3]) < midfielders
                    or len(by_position[4]) < forwards
                ):
                    continue

                selected = (
                    sorted(
                        by_position[1],
                        key=lambda p: p["score"],
                        reverse=True
                    )[:1]
                    + sorted(
                        by_position[2],
                        key=lambda p: p["score"],
                        reverse=True
                    )[:defenders]
                    + sorted(
                        by_position[3],
                        key=lambda p: p["score"],
                        reverse=True
                    )[:midfielders]
                    + sorted(
                        by_position[4],
                        key=lambda p: p["score"],
                        reverse=True
                    )[:forwards]
                )

                total_score = sum(
                    player["score"] for player in selected
                )

                if total_score > best_score:
                    best_score = total_score
                    best_lineup = {
                        "formation": (
                            f"{defenders}-{midfielders}-{forwards}"
                        ),
                        "players": selected,
                        "score": round(total_score, 2)
                    }

        if best_lineup:
            starter_ids = {
                player["id"]
                for player in best_lineup["players"]
            }

            bench = [
                player for player in ranked_owned
                if player["id"] not in starter_ids
            ]

            bench.sort(
                key=lambda p: (
                    p["position"] == 1,
                    -p["score"]
                )
            )

            # Captain and vice-captain from starting XI.
            captain_pool = [
                player for player in best_lineup["players"]
                if player["position"] in (2, 3, 4)
            ]

            captain_pool.sort(
                key=lambda p: p["score"],
                reverse=True
            )

            save_data("lineup_optimizer.json", {
                "gameweek": next_gw,
                "squad_source_gameweek": squad_gw,
                "methodology": (
                    "Formation optimization using five-week "
                    "heuristic scouting scores. Not projected "
                    "FPL points. Players excluded from the "
                    "rankings due to availability or minimum "
                    "minutes are not considered. Results "
                    "require manual review."
                ),
                "recommended_lineup": best_lineup,
                "bench": bench,
                "captain": captain_pool[0],
                "vice_captain": captain_pool[1]
                    if len(captain_pool) > 1 else None
            })

            print(
                "Recommended formation:",
                best_lineup["formation"]
            )
        else:
            print(
                "Lineup optimizer: insufficient eligible "
                "players for a legal formation."
            )
    # TOASTERS POINTS PREDICTOR — VERSION 1
    # Estimates next-GW FPL points, not guaranteed returns.

    import math

    def safe_float(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def project_player(player, fixture):
        position = player["element_type"]
        minutes = player["minutes"]

        if minutes <= 0:
            return None

        # Historical minutes provide a baseline.
        # This is not a confirmed lineup prediction.
        appearances = max(
            1,
            player.get("starts", 0)
            + player.get("sub_on", 0)
        )

        average_minutes = minutes / appearances

        expected_minutes = min(
            90,
            max(0, average_minutes)
        )

        # Adjust for availability.
        status = player["status"]

        if status in ("i", "s", "u", "n"):
            expected_minutes = 0

        elif status == "d":
            chance = player.get(
                "chance_of_playing_next_round"
            )

            if chance is not None:
                expected_minutes *= chance / 100
            else:
                expected_minutes *= 0.5

        # Attacking statistics per 90 minutes.
        xg90 = (
            safe_float(player.get("expected_goals"))
            * 90 / minutes
        )

        xa90 = (
            safe_float(player.get("expected_assists"))
            * 90 / minutes
        )

        difficulty = fixture["difficulty"]

        # Simple fixture adjustment.
        fixture_multiplier = {
            1: 1.25,
            2: 1.15,
            3: 1.00,
            4: 0.85,
            5: 0.75
        }.get(difficulty, 1.0)

        minutes_fraction = expected_minutes / 90

        # FPL goal points by position.
        goal_points = {
            1: 6,
            2: 6,
            3: 5,
            4: 4
        }

        attacking_points = (
            xg90 * goal_points[position]
            + xa90 * 3
        ) * fixture_multiplier * minutes_fraction

        # Appearance points.
        appearance_points = (
            2 * minutes_fraction
        )

        # Approximate clean-sheet probability.
        clean_sheet_probability = {
            1: 0.50,
            2: 0.42,
            3: 0.32,
            4: 0.22,
            5: 0.15
        }.get(difficulty, 0.25)

        clean_sheet_points = {
            1: 4,
            2: 4,
            3: 1,
            4: 0
        }

        clean_sheet_projection = (
            clean_sheet_probability
            * clean_sheet_points[position]
            * minutes_fraction
        )

        # Small form adjustment.
        form = safe_float(player["form"])

        form_adjustment = min(
            0.75,
            max(-0.5, (form - 4) * 0.12)
        ) * minutes_fraction

        projected_points = (
            appearance_points
            + attacking_points
            + clean_sheet_projection
            + form_adjustment
        )

        return {
            "id": player["id"],
            "name": player["web_name"],
            "club": team_lookup.get(player["team"]),
            "position": position,
            "price": player["now_cost"] / 10,
            "opponent": fixture["opponent"],
            "home": fixture["home"],
            "difficulty": difficulty,
            "expected_minutes": round(
                expected_minutes, 1
            ),
            "xg90": round(xg90, 3),
            "xa90": round(xa90, 3),
            "projected_points": round(
                projected_points, 2
            ),
            "status": status,
            "news": player["news"]
        }

    # Project every player with an upcoming fixture.
    projections = []

    for player in players["elements"]:
        fixture = fixture_lookup.get(player["team"])

        if not fixture:
            continue

        projection = project_player(player, fixture)

        if projection is not None:
            projections.append(projection)

    projections.sort(
        key=lambda p: p["projected_points"],
        reverse=True
    )

    # Identify our own players.
    owned_ids = {
        pick["element"]
        for pick in squad["picks"]
    } if squad else set()

    my_projections = [
        player for player in projections
        if player["id"] in owned_ids
    ]

    my_projections.sort(
        key=lambda p: p["projected_points"],
        reverse=True
    )

    save_data("points_projections.json", {
        "gameweek": next_gw,
        "squad_source_gameweek": squad_gw,
        "methodology": (
            "Experimental GW-specific estimates using "
            "historical minutes, xG, xA, fixture difficulty, "
            "clean-sheet assumptions, and recent form. "
            "Not backtested. Excludes bonus, saves, "
            "defensive contributions, cards, and several "
            "other scoring events."
        ),
        "my_players": my_projections,
        "top_players": projections[:50]
    })

    print(
        "Points projections generated for GW",
        next_gw
    )
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
