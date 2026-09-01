import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATS = DATA / "stats"
OUT = DATA / "search"
MANIFEST = DATA / "manifest.json"


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def norm(value):
    text = (value or "").strip().lower()
    out = []
    dash = False
    for ch in text:
        if ch.isalnum():
            out.append(ch)
            dash = False
        elif not dash:
            out.append("-")
            dash = True
    return "".join(out).strip("-")


def main():
    stats_index_path = STATS / "index.json"
    matchup_index_path = STATS / "matchups" / "index.json"
    teammates_path = STATS / "teammates.json"
    champions_path = STATS / "champions.json"

    required = (stats_index_path, matchup_index_path, teammates_path, champions_path)
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        print("Missing generated stats files. Run tools/build_stats.py first.")
        for path in missing:
            print(f"  - {path}")
        return 2

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    stats_index = read_json(stats_index_path)
    matchup_index = read_json(matchup_index_path)
    teammates = read_json(teammates_path)
    champions = read_json(champions_path)

    matchup_routes = {}
    for entry in matchup_index:
        champion = entry.get("champion")
        position = entry.get("position")
        path = entry.get("path")
        if not champion or not position or not path:
            continue
        ckey = norm(champion)
        pkey = norm(position)
        matchup_routes.setdefault(ckey, {})[pkey] = {
            "champion": champion,
            "position": position,
            "path": path,
            "opponentCount": entry.get("opponentCount", 0),
        }
    write_json(OUT / "matchup_routes.json", matchup_routes)

    champion_routes = {}
    for entry in champions:
        champion = entry.get("champion")
        if not champion:
            continue
        positions = sorted((entry.get("positions") or {}).keys())
        champion_routes[norm(champion)] = {
            "champion": champion,
            "games": entry.get("games", 0),
            "positions": positions,
            "statsPath": "stats/champions.json",
            "matchupPositions": {
                norm(position): (matchup_routes.get(norm(champion), {}).get(norm(position)) or {}).get("path")
                for position in positions
                if (matchup_routes.get(norm(champion), {}).get(norm(position)) or {}).get("path")
            },
        }
    write_json(OUT / "champions.json", champion_routes)

    player_aliases = {}
    player_count = 0
    for entry in teammates:
        riot_id = entry.get("riotId")
        if not riot_id:
            continue
        player_count += 1
        safe_name = norm(riot_id) or f"player-{player_count}"
        player_path = OUT / "players" / f"{safe_name}.json"
        write_json(player_path, entry)
        rel = player_path.relative_to(DATA).as_posix()

        aliases = {riot_id}
        if "#" in riot_id:
            game_name, tag = riot_id.rsplit("#", 1)
            aliases.add(game_name)
            aliases.add(f"{game_name}#{tag}")

        for alias in aliases:
            key = norm(alias)
            if not key:
                continue
            current = player_aliases.get(key)
            candidate = {
                "riotId": riot_id,
                "games": entry.get("games", 0),
                "path": rel,
            }
            if current is None or candidate["games"] > current.get("games", 0):
                player_aliases[key] = candidate
    write_json(OUT / "players.json", player_aliases)

    index = {
        "schemaVersion": 1,
        "purpose": "Tiny routing indexes for AI queries; open routed stats files instead of scanning catalog.json.",
        "statsIndexPath": "stats/index.json",
        "routes": {
            "champions": "search/champions.json",
            "matchups": "search/matchup_routes.json",
            "players": "search/players.json",
        },
        "queryExamples": {
            "championPositionOpponent": [
                "Normalize champion and position, open the routed matchup file, then select only the requested opponent entry.",
                "Example: Kennen + TOP -> stats/matchups/kennen/top.json -> Volibear entry.",
            ],
            "teammate": [
                "Normalize Riot ID or game name, look it up in search/players.json, then open only that player's file.",
                "Example: DTC Soul -> search/players.json -> one search/players/*.json file.",
            ],
            "deepMatchReview": [
                "Use matchIds from a stats/player entry and open only data/matches/{matchId}.json for the few relevant games.",
            ],
        },
        "statsSchemaVersion": stats_index.get("schemaVersion"),
        "championRouteCount": len(champion_routes),
        "matchupRouteCount": sum(len(v) for v in matchup_routes.values()),
        "playerAliasCount": len(player_aliases),
        "playerFileCount": player_count,
    }
    write_json(OUT / "index.json", index)

    if MANIFEST.exists():
        try:
            manifest = read_json(MANIFEST)
        except Exception:
            manifest = {}
        manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 8)
        manifest["searchIndexPath"] = "search/index.json"
        manifest["searchChampionRoutePath"] = "search/champions.json"
        manifest["searchMatchupRoutePath"] = "search/matchup_routes.json"
        manifest["searchPlayerRoutePath"] = "search/players.json"
        manifest["searchPlayerFilePattern"] = "search/players/{normalizedRiotId}.json"
        write_json(MANIFEST, manifest)

    print(f"Search routes ready: {len(champion_routes)} champions")
    print(f"Matchup routes: {sum(len(v) for v in matchup_routes.values())}")
    print(f"Player files: {player_count}")
    print(f"Player aliases: {len(player_aliases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
