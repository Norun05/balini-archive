import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MATCHES_DIR = DATA / "matches"
STATS_DIR = DATA / "stats"
OUT = STATS_DIR / "teammates.json"
MANIFEST = DATA / "manifest.json"


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(n, d):
    return round(n * 100 / d, 2) if d else None


def normalized_position(player):
    if not isinstance(player, dict):
        return ""
    return player.get("teamPosition") or player.get("individualPosition") or player.get("positionAssignedByMatchmaking") or ""


def main():
    players = defaultdict(list)

    for path in sorted(MATCHES_DIR.glob("KR_*.json")):
        try:
            detail = read_json(path)
        except Exception:
            continue

        my_champ = detail.get("championName") or "Unknown"
        my_pos = detail.get("position") or "UNKNOWN"
        win = bool(detail.get("win"))
        match_id = detail.get("matchId")
        creation = detail.get("gameCreation")

        for teammate in detail.get("teammates") or []:
            riot_id = teammate.get("riotId") if isinstance(teammate, dict) else None
            if not riot_id:
                continue
            players[riot_id].append({
                "matchId": match_id,
                "gameCreation": creation,
                "win": win,
                "myChampion": my_champ,
                "myPosition": my_pos,
                "theirChampion": teammate.get("championName") or "Unknown",
                "theirPosition": normalized_position(teammate) or "UNKNOWN",
            })

    rows = []
    for riot_id, games in sorted(players.items(), key=lambda x: (-len(x[1]), x[0].lower())):
        games.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)
        wins = sum(1 for g in games if g.get("win"))
        my_pairs = Counter((g["myChampion"], g["myPosition"]) for g in games)
        their_pairs = Counter((g["theirChampion"], g["theirPosition"]) for g in games)
        duo_pairs = Counter((g["myChampion"], g["myPosition"], g["theirChampion"], g["theirPosition"]) for g in games)

        combo_stats = []
        combo_groups = defaultdict(list)
        for g in games:
            key = (g["myChampion"], g["myPosition"], g["theirChampion"], g["theirPosition"])
            combo_groups[key].append(g)
        for key, grouped in sorted(combo_groups.items(), key=lambda x: (-len(x[1]), x[0])):
            combo_wins = sum(1 for g in grouped if g.get("win"))
            combo_stats.append({
                "myChampion": key[0],
                "myPosition": key[1],
                "theirChampion": key[2],
                "theirPosition": key[3],
                "games": len(grouped),
                "wins": combo_wins,
                "losses": len(grouped) - combo_wins,
                "winRate": pct(combo_wins, len(grouped)),
                "matchIds": [g["matchId"] for g in grouped],
            })

        rows.append({
            "riotId": riot_id,
            "games": len(games),
            "wins": wins,
            "losses": len(games) - wins,
            "winRate": pct(wins, len(games)),
            "myChampionPositionPairs": [
                {"champion": champ, "position": pos, "games": count}
                for (champ, pos), count in my_pairs.most_common()
            ],
            "theirChampionPositionPairs": [
                {"champion": champ, "position": pos, "games": count}
                for (champ, pos), count in their_pairs.most_common()
            ],
            "duoCombinations": combo_stats,
            "matchIds": [g["matchId"] for g in games],
            "recentMatches": games[:20],
        })

    write_json(OUT, rows)

    if MANIFEST.exists():
        try:
            manifest = read_json(MANIFEST)
        except Exception:
            manifest = {}
        manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 9)
        manifest["playerStatsPath"] = "stats/teammates.json"
        manifest["playerStatsCount"] = len(rows)
        manifest["playerDuoCombinationField"] = "duoCombinations"
        write_json(MANIFEST, manifest)

    print(f"Detailed teammate stats ready: {len(rows)} players")
    print(f"Duo combinations: {sum(len(r.get('duoCombinations') or []) for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
