import json
from pathlib import Path

DATA = Path("data")


def load_json(filename):
    with open(DATA / filename, encoding="utf-8") as file:
        return json.load(file)


def save_json(filename, content):
    DATA.mkdir(exist_ok=True)

    with open(DATA / filename, "w", encoding="utf-8") as file:
        json.dump(content, file, indent=2, ensure_ascii=False)


def main():
    print("Building Premier League intelligence database...")

    bootstrap = load_json("players.json")
    fixtures = load_json("fixtures.json")

    teams = {
        team["id"]: team["name"]
        for team in bootstrap["teams"]
    }

    stats = {}

    for team_id, name in teams.items():
        stats[team_id] = {
            "team": name,
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "goals_for": 0,
            "goals_against": 0,
            "clean_sheets": 0,
            "home_played": 0,
            "home_goals_for": 0,
            "home_goals_against": 0,
            "away_played": 0,
            "away_goals_for": 0,
            "away_goals_against": 0,
            "results": []
        }

    # Process completed matches only.
    completed = [
        fixture for fixture in fixtures
        if fixture.get("finished")
        and fixture.get("team_h_score") is not None
        and fixture.get("team_a_score") is not None
    ]

    completed.sort(
        key=lambda match: (
            match.get("kickoff_time") or "",
            match["id"]
        )
    )

    for match in completed:
        home_id = match["team_h"]
        away_id = match["team_a"]

        if home_id not in stats or away_id not in stats:
            continue

        home_goals = match["team_h_score"]
        away_goals = match["team_a_score"]

        home = stats[home_id]
        away = stats[away_id]

        home["played"] += 1
        away["played"] += 1

        home["goals_for"] += home_goals
        home["goals_against"] += away_goals

        away["goals_for"] += away_goals
        away["goals_against"] += home_goals

        home["home_played"] += 1
        home["home_goals_for"] += home_goals
        home["home_goals_against"] += away_goals

        away["away_played"] += 1
        away["away_goals_for"] += away_goals
        away["away_goals_against"] += home_goals

        if away_goals == 0:
            home["clean_sheets"] += 1

        if home_goals == 0:
            away["clean_sheets"] += 1

        if home_goals > away_goals:
            home["wins"] += 1
            away["losses"] += 1
            home_result = "W"
            away_result = "L"

        elif home_goals < away_goals:
            away["wins"] += 1
            home["losses"] += 1
            home_result = "L"
            away_result = "W"

        else:
            home["draws"] += 1
            away["draws"] += 1
            home_result = "D"
            away_result = "D"

        home["results"].append(home_result)
        away["results"].append(away_result)

    # Calculate season and recent-form statistics.
    for team in stats.values():
        played = team["played"]

        team["points"] = (
            team["wins"] * 3 + team["draws"]
        )

        team["goal_difference"] = (
            team["goals_for"] - team["goals_against"]
        )

        team["goals_per_match"] = round(
            team["goals_for"] / played, 2
        ) if played else 0

        team["conceded_per_match"] = round(
            team["goals_against"] / played, 2
        ) if played else 0

        team["clean_sheet_rate"] = round(
            team["clean_sheets"] / played, 3
        ) if played else 0

        last_five = team["results"][-5:]

        team["last_five"] = "".join(last_five)

        team["last_five_points"] = sum(
            3 if result == "W" else
            1 if result == "D" else 0
            for result in last_five
        )

        team["home_goals_per_match"] = round(
            team["home_goals_for"] / team["home_played"], 2
        ) if team["home_played"] else 0

        team["home_conceded_per_match"] = round(
            team["home_goals_against"] / team["home_played"], 2
        ) if team["home_played"] else 0

        team["away_goals_per_match"] = round(
            team["away_goals_for"] / team["away_played"], 2
        ) if team["away_played"] else 0

        team["away_conceded_per_match"] = round(
            team["away_goals_against"] / team["away_played"], 2
        ) if team["away_played"] else 0

        # Remove internal match history from final output.
        del team["results"]

    # Build league table.
    league_table = sorted(
        stats.values(),
        key=lambda team: (
            -team["points"],
            -team["goal_difference"],
            -team["goals_for"],
            team["team"]
        )
    )

    for position, team in enumerate(league_table, start=1):
        team["position"] = position

    # Separate offensive and defensive rankings.
    offensive_rankings = sorted(
        league_table,
        key=lambda team: team["goals_per_match"],
        reverse=True
    )

    defensive_rankings = sorted(
        league_table,
        key=lambda team: team["conceded_per_match"]
    )

    save_json("league_table.json", league_table)

    save_json("team_stats.json", {
        "teams": league_table,
        "best_attacks": [
            team["team"]
            for team in offensive_rankings[:5]
        ],
        "best_defenses": [
            team["team"]
            for team in defensive_rankings[:5]
        ],
        "worst_defenses": [
            team["team"]
            for team in defensive_rankings[-5:][::-1]
        ]
    })

    print("League intelligence successfully generated!")
    print("Top five teams:")

    for team in league_table[:5]:
        print(
            team["position"],
            team["team"],
            team["points"],
            "points"
        )


if __name__ == "__main__":
    main()
