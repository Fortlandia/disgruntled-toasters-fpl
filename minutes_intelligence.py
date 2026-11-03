import json
import time
from pathlib import Path
from statistics import mean

import requests

DATA = Path("data")
API = "https://fantasy.premierleague.com/api"


def load_json(filename):
    with open(DATA / filename, encoding="utf-8") as file:
        return json.load(file)


def save_json(filename, content):
    DATA.mkdir(exist_ok=True)

    with open(DATA / filename, "w", encoding="utf-8") as file:
        json.dump(content, file, indent=2, ensure_ascii=False)


def get_player_history(player_id):
    url = f"{API}/element-summary/{player_id}/"

    for attempt in range(3):
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            return response.json().get("history", [])

        except requests.RequestException:
            if attempt == 2:
                print(f"Could not retrieve player {player_id}")
                return None

            time.sleep(2 * (attempt + 1))


def analyze_player(player, history):
    # Include zero-minute matches when the player
    # was available but did not feature.
    recent = sorted(
        history,
        key=lambda match: (
            match.get("kickoff_time") or "",
            match.get("fixture", 0)
        )
    )[-5:]

    minutes = [
        match.get("minutes", 0)
        for match in recent
    ]

    if not minutes:
        return {
            "id": player["id"],
            "name": player["web_name"],
            "matches_analyzed": 0,
            "expected_minutes": 0,
            "rotation_risk": "Unknown",
            "status": player["status"]
        }

    average_minutes = mean(minutes)

    # FPL match history doesn't reliably expose
    # whether a player started, so these are
    # appearance-based indicators rather than
    # confirmed starting percentages.
    played_60 = sum(m >= 60 for m in minutes)
    played_any = sum(m > 0 for m in minutes)

    first_half = minutes[:max(1, len(minutes) // 2)]
    second_half = minutes[max(1, len(minutes) // 2):]

    early_average = mean(first_half)
    recent_average = (
        mean(second_half)
        if second_half else early_average
    )

    minutes_trend = recent_average - early_average

    # Recent minutes receive additional weight.
    weights = list(range(1, len(minutes) + 1))

    weighted_minutes = sum(
        m * w for m, w in zip(minutes, weights)
    ) / sum(weights)

    expected_minutes = weighted_minutes

    status = player["status"]

    if status in ("i", "s", "u", "n"):
        expected_minutes = 0

    elif status == "d":
        chance = player.get(
            "chance_of_playing_next_round"
        )

        expected_minutes *= (
            chance / 100
            if chance is not None else 0.5
        )

    expected_minutes = max(
        0, min(90, expected_minutes)
    )

    appearance_rate = played_any / len(minutes)
    sixty_minute_rate = played_60 / len(minutes)

    if status in ("i", "s", "u", "n"):
        rotation_risk = "Unavailable"

    elif status == "d":
        rotation_risk = "High"

    elif (
        appearance_rate >= 0.8
        and sixty_minute_rate >= 0.8
        and expected_minutes >= 65
    ):
        rotation_risk = "Low"

    elif (
        appearance_rate >= 0.6
        and expected_minutes >= 40
    ):
        rotation_risk = "Medium"

    else:
        rotation_risk = "High"

    return {
        "id": player["id"],
        "name": player["web_name"],
        "club_id": player["team"],
        "position": player["element_type"],
        "matches_analyzed": len(minutes),
        "last_five_minutes": minutes,
        "average_minutes": round(average_minutes, 1),
        "weighted_minutes": round(weighted_minutes, 1),
        "expected_minutes": round(expected_minutes, 1),
        "appearance_rate": round(appearance_rate, 2),
        "sixty_minute_rate": round(sixty_minute_rate, 2),
        "minutes_trend": round(minutes_trend, 1),
        "rotation_risk": rotation_risk,
        "status": status,
        "news": player.get("news", "")
    }


def main():
    print("Building Toasters Minutes Intelligence...")

    bootstrap = load_json("players.json")
    squad = load_json("squad.json")

    player_lookup = {
        player["id"]: player
        for player in bootstrap["elements"]
    }

    # Inspect our 15 players first.
    # This keeps API usage manageable.
    picks = squad["picks"]

    results = []
    failed_players = []

    for pick in picks:
        player_id = pick["element"]
        player = player_lookup[player_id]

        history = get_player_history(player_id)

        if history is None:
            failed_players.append(player["web_name"])
            continue

        results.append(
            analyze_player(player, history)
        )

        time.sleep(0.2)

    save_json("minutes_intelligence.json", {
        "methodology": (
            "Experimental recent-minutes estimates using "
            "up to five completed player match records, "
            "recency weighting and availability flags. "
            "Appearance rates are not confirmed start rates. "
            "Not backtested."
        ),
        "players": results,
        "failed_players": failed_players
    })

    print("Minutes intelligence complete!")

    for player in results:
        print(
            player["name"],
            player["expected_minutes"],
            "minutes |",
            player["rotation_risk"],
            "risk"
        )

    if failed_players:
        print("Failed player histories:", failed_players)


if __name__ == "__main__":
    main()
