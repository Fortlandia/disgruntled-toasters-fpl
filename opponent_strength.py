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


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def main():
    print("Building opponent strength intelligence...")

    league = load_json("league_table.json")
    projections = load_json("points_projections.json")

    teams = {team["team"]: team for team in league}

    # League averages calculated from completed matches.
    total_matches = sum(t["played"] for t in league) / 2

    if not total_matches:
        raise ValueError("No completed matches available.")

    league_goals = sum(t["goals_for"] for t in league)
    average_goals = league_goals / (total_matches * 2)

    # Shrink team averages toward the league average.
    # This reduces overreaction to small samples.
    prior_matches = 6

    def adjusted_rate(goals, played):
        return (
            goals + prior_matches * average_goals
        ) / (played + prior_matches)

    strength = {}

    for team in league:
        name = team["team"]

        attack = adjusted_rate(
            team["goals_for"], team["played"]
        )

        defense = adjusted_rate(
            team["goals_against"], team["played"]
        )

        strength[name] = {
            "position": team["position"],
            "attack_goals_per_match": round(attack, 3),
            "conceded_goals_per_match": round(defense, 3),
            "attack_index": round(attack / average_goals, 3),
            "defensive_vulnerability_index": round(
                defense / average_goals, 3
            )
        }

    def adjust_projection(player):
        result = player.copy()
        opponent = player.get("opponent")

        if opponent not in strength:
            result["strength_adjusted_points"] = (
                player["projected_points"]
            )
            result["opponent_adjustment"] = 0
            result["adjustment_note"] = (
                "Opponent not matched; original projection retained."
            )
            return result

        opponent_stats = strength[opponent]
        position = player["position"]

        # Higher defensive vulnerability benefits attackers.
        attack_factor = clamp(
            opponent_stats["defensive_vulnerability_index"],
            0.75,
            1.25
        )

        # Higher opponent attacking strength hurts defenders.
        defense_factor = clamp(
            2 - opponent_stats["attack_index"],
            0.75,
            1.25
        )

        # Apply modest adjustments to the existing projection.
        # This is a provisional heuristic, not a calibrated model.
        if position in (3, 4):
            factor = 1 + 0.35 * (attack_factor - 1)
        else:
            factor = 1 + 0.25 * (
                (attack_factor + defense_factor) / 2 - 1
            )

        original = player["projected_points"]

        adjusted = round(original * factor, 2)

        result["strength_adjusted_points"] = adjusted
        result["opponent_adjustment"] = round(
            adjusted - original, 2
        )
        result["opponent_league_position"] = (
            opponent_stats["position"]
        )
        result["opponent_attack_index"] = (
            opponent_stats["attack_index"]
        )
        result["opponent_defensive_vulnerability_index"] = (
            opponent_stats["defensive_vulnerability_index"]
        )

        return result

    my_players = [
        adjust_projection(p)
        for p in projections["my_players"]
    ]

    my_players.sort(
        key=lambda p: p["strength_adjusted_points"],
        reverse=True
    )

    top_players = [
        adjust_projection(p)
        for p in projections["top_players"]
    ]

    top_players.sort(
        key=lambda p: p["strength_adjusted_points"],
        reverse=True
    )

    save_json("opponent_strength.json", {
        "gameweek": projections["gameweek"],
        "methodology": (
            "Experimental opponent-strength adjustment "
            "using season goals scored/conceded, "
            "six-match shrinkage toward league averages, "
            "and capped multipliers. Not backtested. "
            "Does not replace the baseline projections."
        ),
        "league_average_goals_per_team_match": round(
            average_goals, 3
        ),
        "team_strength": strength,
        "my_players": my_players,
        "top_players": top_players
    })

    print("Opponent strength intelligence generated!")

    for player in my_players[:10]:
        print(
            player["name"],
            player["projected_points"],
            "->",
            player["strength_adjusted_points"]
        )


if __name__ == "__main__":
    main()
