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


def optimize_lineup(players):
    by_position = {
        position: sorted(
            [
                p for p in players
                if p["position"] == position
            ],
            key=lambda p: p["strength_adjusted_points"],
            reverse=True
        )
        for position in (1, 2, 3, 4)
    }

    best_lineup = None
    best_score = float("-inf")

    # Evaluate every legal formation.
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

            starters = (
                by_position[1][:1]
                + by_position[2][:defenders]
                + by_position[3][:midfielders]
                + by_position[4][:forwards]
            )

            score = sum(
                p["strength_adjusted_points"]
                for p in starters
            )

            if score > best_score:
                best_score = score
                best_lineup = {
                    "formation":
                        f"{defenders}-{midfielders}-{forwards}",
                    "players": starters,
                    "projected_points": round(score, 2)
                }

    if best_lineup is None:
        raise ValueError(
            "Insufficient players for a legal formation."
        )

    starter_ids = {
        p["id"] for p in best_lineup["players"]
    }

    bench = [
        p for p in players
        if p["id"] not in starter_ids
    ]

    # Outfield substitutes first; reserve goalkeeper last.
    bench.sort(
        key=lambda p: (
            p["position"] == 1,
            -p["strength_adjusted_points"]
        )
    )

    captain_candidates = sorted(
        best_lineup["players"],
        key=lambda p: p["strength_adjusted_points"],
        reverse=True
    )

    return {
        "recommended_lineup": best_lineup,
        "bench": bench,
        "captain": captain_candidates[0],
        "vice_captain": captain_candidates[1],
        "captain_adjusted_total": round(
            best_score
            + captain_candidates[0]["strength_adjusted_points"],
            2
        )
    }


def main():
    print("Running Toasters Lineup Optimizer 3.0...")

    intelligence = load_json("opponent_strength.json")
    previous = load_json("lineup_optimizer_v2.json")

    players = intelligence["my_players"]

    if len(players) != 15:
        raise ValueError(
            f"Expected 15 squad players; found {len(players)}."
        )

    if intelligence["gameweek"] != previous["gameweek"]:
        raise ValueError(
            "Gameweek mismatch between projection models."
        )

    optimized = optimize_lineup(players)

    old_lineup = previous["recommended_lineup"]
    new_lineup = optimized["recommended_lineup"]

    old_ids = {
        p["id"] for p in old_lineup["players"]
    }

    new_ids = {
        p["id"] for p in new_lineup["players"]
    }

    player_lookup = {
        p["id"]: p for p in players
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

    save_json("lineup_optimizer_v3.json", {
        "gameweek": intelligence["gameweek"],
        "methodology": (
            "Experimental formation optimization using "
            "opponent-adjusted projected points. "
            "Not backtested. Uses latest published squad."
        ),
        **optimized,
        "comparison_to_v2": comparison
    })

    print("Optimizer 3.0 complete!")
    print("Formation:", new_lineup["formation"])
    print("Projected points:", new_lineup["projected_points"])
    print("Captain:", optimized["captain"]["name"])
    print("Vice:", optimized["vice_captain"]["name"])
    print("Players added:", players_added)
    print("Players removed:", players_removed)


if __name__ == "__main__":
    main()
