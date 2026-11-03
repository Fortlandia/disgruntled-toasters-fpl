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
                print(
                    f"Could not retrieve player {player_id}"
                )
                return None

            time.sleep(2 * (attempt + 1))


def get_recent_team_fixtures(team_id, fixtures):
    completed = [
        match for match in fixtures
        if match.get("finished")
        and (
            match["team_h"] == team_id
            or match["team_a"] == team_id
        )
    ]

    completed.sort(
        key=lambda match: (
            match.get("kickoff_time") or "",
            match["id"]
        )
    )

    return completed[-5:]


def analyze_player(player, history, team_fixtures):
    # Match player history against actual club fixtures.
    history_lookup = {
        match["fixture"]: match
        for match in history
    }

    recent = []

    for fixture in team_fixtures:
        fixture_id = fixture["id"]
        record = history_lookup.get(fixture_id)

        recent.append({
            "fixture_id": fixture_id,
            "gameweek": fixture.get("event"),
            "minutes": (
                record.get("minutes", 0)
                if record else 0
            ),
            "history_record_found": record is not None
        })

    minutes = [
        match["minutes"]
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

    played_any = sum(
        m > 0 for m in minutes
    )

    played_60 = sum(
        m >= 60 for m in minutes
    )

    weights = list(range(1, len(minutes) + 1))

    weighted_minutes = sum(
        m * w
        for m, w in zip(minutes, weights)
    ) / sum(weights)

    first_half = minutes[:max(1, len(minutes) // 2)]
    second_half = minutes[max(1, len(minutes) // 2):]

    early_average = mean(first_half)

    recent_average = (
        mean(second_half)
        if second_half else early_average
    )

    minutes_trend = recent_average - early_average

    appearance_rate = played_any / len(minutes)
    sixty_minute_rate = played_60 / len(minutes)

    status = player["status"]
    expected_minutes = weighted_minutes

    # Apply current availability adjustments.
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

    # Classify statistical playing-time risk.
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

    # Flag recent missed matches.
    missed_recently = any(
        m == 0 for m in minutes[-3:]
    )

    if (
        missed_recently
        and rotation_risk == "Low"
    ):
        rotation_risk = "Medium"

    missing_history = sum(
        not match["history_record_found"]
        for match in recent
    )

    return {
        "id": player["id"],
        "name": player["web_name"],
        "club_id": player["team"],
        "position": player["element_type"],
        "matches_analyzed": len(minutes),
        "last_five_minutes": minutes,
        "fixture_details": recent,
        "missing_history_records": missing_history,
        "average_minutes": round(average_minutes, 1),
        "weighted_minutes": round(weighted_minutes, 1),
        "expected_minutes": round(expected_minutes, 1),
        "appearance_rate": round(appearance_rate, 2),
        "sixty_minute_rate": round(sixty_minute_rate, 2),
        "minutes_trend": round(minutes_trend, 1),
        "missed_recently": missed_recently,
        "rotation_risk": rotation_risk,
        "status": status,
        "news": player.get("news", "")
    }


def main():
    print("Building Minutes Intelligence 2.0...")

    bootstrap = load_json("players.json")
    squad = load_json("squad.json")
    fixtures = load_json("fixtures.json")

    player_lookup = {
        player["id"]: player
        for player in bootstrap["elements"]
    }

    results = []
    failed_players = []

    for pick in squad["picks"]:
        player_id = pick["element"]
        player = player_lookup[player_id]

        history = get_player_history(player_id)

        if history is None:
            failed_players.append(
                player["web_name"]
            )
            continue

        team_fixtures = get_recent_team_fixtures(
            player["team"],
            fixtures
        )

        results.append(
            analyze_player(
                player,
                history,
                team_fixtures
            )
        )

        time.sleep(0.2)

    save_json("minutes_intelligence.json", {
        "version": 2,
        "methodology": (
            "Recent playing-time estimates matched "
            "against each club's last five completed "
            "Premier League fixtures. Missing player "
            "history records count as zero minutes. "
            "Availability flags are applied. "
            "Rotation ratings are heuristic, not "
            "confirmed starting probabilities. "
            "Not backtested."
        ),
        "players": results,
        "failed_players": failed_players
    })

    print("Minutes Intelligence 2.0 complete!")

    for player in results:
        print(
            player["name"],
            player["expected_minutes"],
            "minutes |",
            player["rotation_risk"],
            "risk |",
            "missing records:",
            player.get("missing_history_records", 0)
        )

    if failed_players:
        print(
            "Failed player histories:",
            failed_players
        )


if __name__ == "__main__":
    main()
