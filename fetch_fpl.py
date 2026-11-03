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


def main():
    print("Fetching Disgruntled Toasters FPL data...")

    players = get_data("bootstrap-static/")
    team = get_data(f"entry/{TEAM_ID}/")
    fixtures = get_data("fixtures/")

    save_data("players.json", players)
    save_data("team.json", team)
    save_data("fixtures.json", fixtures)

    current_gw = team["current_event"]

    if current_gw:
        picks = get_data(
            f"entry/{TEAM_ID}/event/{current_gw}/picks/"
        )
        save_data("squad.json", picks)

    standings = get_data(
        f"leagues-h2h-matches/league/{LEAGUE_ID}/"
        f"?entry={TEAM_ID}&page=1"
    )
    save_data("matchups.json", standings)

    save_data("last_updated.json", {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "team_id": TEAM_ID,
        "league_id": LEAGUE_ID,
        "gameweek": current_gw
    })

    print("FPL data successfully updated!")


if __name__ == "__main__":
    main()
