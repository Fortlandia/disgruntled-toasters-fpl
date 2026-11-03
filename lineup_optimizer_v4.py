import json
from pathlib import Path

from lineup_optimizer_v3 import optimize_lineup

DATA = Path("data")


def load_json(filename):
    with open(DATA / filename, encoding="utf-8") as file:
        return json.load(file)


def save_json(filename, content):
    DATA.mkdir(exist_ok=True)

    with open(DATA / filename, "w", encoding="utf-8") as file:
        json.dump(content, file, indent=2, ensure_ascii=False)


def adjust_player(player, minutes_data):
    updated = player.copy()

    original_points = player["strength_adjusted_points"]
    original_minutes = player.get("expected_minutes", 90)

    recent_minutes = minutes_data["expected_minutes"]
    rotation_risk = minutes_data["rotation_risk"]

    # The existing projection already includes playing time.
    # Adjust relative to its original minutes estimate,
    # rather than multiplying by minutes / 90.
    if original_minutes > 0:
        raw_factor = recent_minutes / original_minutes
    else:
        raw_factor = 1.0

    # Limit adjustments until the model is backtested.
    adjustment_factor = max(
        0.80,
        min(1.10, raw_factor)
    )

    # Unavailable players should not be recommended
    # unless the squad cannot form a valid XI.
    if rotation_risk == "Unavailable":
        adjustment_factor = 0.0

    adjusted_points = original_points * adjustment_factor

    updated["v3_points"] = original_points
    updated["original_expected_minutes"] = original_minutes
    updated["recent_expected_minutes"] = recent_minutes
    updated["minutes_adjustment_factor"] = round(
        adjustment_factor, 3
    )
    updated["rotation_risk"] = rotation_risk
    updated["recent_minutes"] = minutes_data.get(
        "last_five_minutes", []
    )
    updated["minutes_adjusted_points"] = round(
        adjusted_points, 2
    )

    # Reuse the existing V3 optimizer with a new score.
    updated["strength_adjusted_points"] = round(
        adjusted_points, 2
    )

    return updated


def main():
    print("Running Toasters Optimizer 4.0...")

    opponent_data = load_json("opponent_strength.json")
    minutes_data = load_json("minutes_intelligence.json")
    previous = load_json("lineup_optimizer_v3.json")

    players = opponent_data["my_players"]

    if len(players) != 15:
        raise ValueError(
            f"Expected 15 players, found {len(players)}"
        )

    if opponent_data["gameweek"] != previous["gameweek"]:
        raise ValueError("Gameweek mismatch")

    if minutes_data.get("version") != 2:
        raise ValueError(
            "Minutes Intelligence 2.0 is required"
        )

    minutes_lookup = {
        player["id"]: player
        for player in minutes_data["players"]
    }

    # Require complete data rather than silently
    # generating recommendations from missing records.
    missing = [
        player["name"]
        for player in players
        if player["id"] not in minutes_lookup
    ]

    if missing:
        raise ValueError(
            f"Missing minutes data for: {missing}"
        )

    adjusted_players = [
        adjust_player(
            player,
            minutes_lookup[player["id"]]
        )
        for player in players
    ]

    optimized = optimize_lineup(adjusted_players)

    old_lineup = previous["recommended_lineup"]
    new_lineup = optimized["recommended_lineup"]

    old_ids = {
        player["id"]
        for player in old_lineup["players"]
    }

    new_ids = {
        player["id"]
        for player in new_lineup["players"]
    }

    player_lookup = {
        player["id"]: player
        for player in adjusted_players
    }

    players_added = [
        player_lookup[player_id]["name"]
        for player_id in sorted(new_ids - old_ids)
    ]

    players_removed = [
        player_lookup[player_id]["name"]
        for player_id in sorted(old_ids - new_ids)
    ]

    comparison = {
        "previous_formation": old_lineup["formation"],
        "new_formation": new_lineup["formation"],
        "previous_projected_points":
            old_lineup["projected_points"],
        "new_projected_points":
            new_lineup["projected_points"],
        "players_added": players_added,
        "players_removed": players_removed,
        "captain_changed": (
            previous["captain"]["id"]
            != optimized["captain"]["id"]
        ),
        "vice_captain_changed": (
            previous["vice_captain"]["id"]
            != optimized["vice_captain"]["id"]
        )
    }

    save_json("lineup_optimizer_v4.json", {
        "version": 4,
        "gameweek": opponent_data["gameweek"],
        "methodology": (
            "Experimental lineup optimization using "
            "opponent-adjusted points and relative "
            "playing-time adjustments. Adjustments "
            "are capped between 0.80 and 1.10 for "
            "available players. Unavailable players "
            "receive zero projected points. "
            "Does not fully model substitution rules, "
            "captain availability, or injury uncertainty. "
            "Not backtested."
        ),
        **optimized,
        "comparison_to_v3": comparison,
        "player_adjustments": [
            {
                "name": player["name"],
                "v3_points": player["v3_points"],
                "v4_points":
                    player["minutes_adjusted_points"],
                "original_expected_minutes":
                    player["original_expected_minutes"],
                "recent_expected_minutes":
                    player["recent_expected_minutes"],
                "adjustment_factor":
                    player["minutes_adjustment_factor"],
                "rotation_risk":
                    player["rotation_risk"]
            }
            for player in adjusted_players
        ]
    })

    print("Optimizer 4.0 complete!")
    print("Gameweek:", opponent_data["gameweek"])
    print("Formation:", new_lineup["formation"])
    print("Projected points:", new_lineup["projected_points"])
    print("Captain:", optimized["captain"]["name"])
    print("Vice:", optimized["vice_captain"]["name"])
    print("Players added:", players_added)
    print("Players removed:", players_removed)


if __name__ == "__main__":
    main()
