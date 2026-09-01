import json
import math
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MATCHES_DIR = DATA / "matches"
OUT = DATA / "stats"
MANIFEST = DATA / "manifest.json"

POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
SNAPSHOT_MINUTES = (2, 3, 4, 5, 6, 8, 10, 15, 20)


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slug(value):
    text = (value or "unknown").strip().lower()
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("-")
    text = "".join(out)
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "unknown"


def avg(values):
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(sum(values) / len(values), 2) if values else None


def pct(n, d):
    return round(n * 100 / d, 2) if d else None


def snapshot_at(detail, minute):
    timeline = detail.get("timeline") or {}
    candidates = timeline.get("earlySnapshots") or timeline.get("snapshots") or []
    return next((s for s in candidates if s.get("minute") == minute), None)


def player_riot_id(p):
    if not isinstance(p, dict):
        return None
    return p.get("riotId") or None


def summoner_key(p):
    spells = p.get("summonerSpells") or [] if isinstance(p, dict) else []
    names = [s.get("nameKo") for s in spells if isinstance(s, dict) and s.get("nameKo")]
    if not names:
        return None
    return " + ".join(sorted(names))


def first_completed_item_names(detail):
    me = detail.get("me") or {}
    names = me.get("itemNamesKo") or []
    return [name for name in names if name][:6]


def match_row(detail):
    me = detail.get("me") or {}
    opp = detail.get("laneOpponent") or {}
    row = {
        "matchId": detail.get("matchId"),
        "gameCreation": detail.get("gameCreation"),
        "duration": detail.get("gameDuration"),
        "champion": detail.get("championName"),
        "position": detail.get("position"),
        "opponent": opp.get("championName"),
        "win": bool(detail.get("win")),
        "kills": detail.get("kills", 0),
        "deaths": detail.get("deaths", 0),
        "assists": detail.get("assists", 0),
        "cs": detail.get("cs", 0),
        "gold": detail.get("gold", 0),
        "damage": detail.get("damage", 0),
        "summoners": summoner_key(me),
        "finalItems": first_completed_item_names(detail),
        "teammates": [player_riot_id(p) for p in detail.get("teammates") or [] if player_riot_id(p)],
        "snapshots": {},
    }
    for minute in SNAPSHOT_MINUTES:
        s = snapshot_at(detail, minute)
        if s:
            row["snapshots"][str(minute)] = {
                "goldDiff": s.get("goldDiff"),
                "csDiff": s.get("csDiff"),
                "levelDiff": s.get("levelDiff"),
                "xpDiff": s.get("xpDiff"),
            }
    levels = (detail.get("timeline") or {}).get("earlyLevelTimings") or {}
    row["level2Lead"] = (levels.get("2") or {}).get("lead")
    row["level3Lead"] = (levels.get("3") or {}).get("lead")
    return row


def aggregate(rows):
    games = len(rows)
    wins = sum(1 for r in rows if r.get("win"))
    deaths = sum(r.get("deaths", 0) or 0 for r in rows)
    return {
        "games": games,
        "wins": wins,
        "losses": games - wins,
        "winRate": pct(wins, games),
        "avgKills": avg([r.get("kills") for r in rows]),
        "avgDeaths": avg([r.get("deaths") for r in rows]),
        "avgAssists": avg([r.get("assists") for r in rows]),
        "kdaRatio": round((sum(r.get("kills", 0) or 0 for r in rows) + sum(r.get("assists", 0) or 0 for r in rows)) / max(1, deaths), 2),
        "avgCs": avg([r.get("cs") for r in rows]),
        "avgGold": avg([r.get("gold") for r in rows]),
        "avgDamage": avg([r.get("damage") for r in rows]),
        "lane": {
            str(minute): {
                "avgGoldDiff": avg([(r.get("snapshots") or {}).get(str(minute), {}).get("goldDiff") for r in rows]),
                "avgCsDiff": avg([(r.get("snapshots") or {}).get(str(minute), {}).get("csDiff") for r in rows]),
                "avgLevelDiff": avg([(r.get("snapshots") or {}).get(str(minute), {}).get("levelDiff") for r in rows]),
                "avgXpDiff": avg([(r.get("snapshots") or {}).get(str(minute), {}).get("xpDiff") for r in rows]),
            }
            for minute in SNAPSHOT_MINUTES
        },
        "level2": Counter(r.get("level2Lead") for r in rows if r.get("level2Lead")),
        "level3": Counter(r.get("level3Lead") for r in rows if r.get("level3Lead")),
    }


def counter_json(counter):
    return [{"name": name, "games": count} for name, count in counter.most_common()]


def normalize_counters(value):
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, dict):
        return {k: normalize_counters(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_counters(v) for v in value]
    return value


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    details = []
    for path in sorted(MATCHES_DIR.glob("KR_*.json")):
        try:
            details.append(read_json(path))
        except Exception:
            continue

    rows = [match_row(d) for d in details]
    rows.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)

    by_champion = defaultdict(list)
    by_position = defaultdict(list)
    by_champion_position = defaultdict(list)
    by_matchup = defaultdict(list)
    by_teammate = defaultdict(list)
    by_summoner = defaultdict(list)

    for row in rows:
        champion = row.get("champion") or "Unknown"
        position = row.get("position") or "UNKNOWN"
        opponent = row.get("opponent") or "Unknown"
        by_champion[champion].append(row)
        by_position[position].append(row)
        by_champion_position[(champion, position)].append(row)
        by_matchup[(champion, position, opponent)].append(row)
        if row.get("summoners"):
            by_summoner[(champion, position, row["summoners"])].append(row)
        for teammate in row.get("teammates") or []:
            by_teammate[teammate].append(row)

    overview = normalize_counters({
        **aggregate(rows),
        "generatedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
        "matchCount": len(rows),
        "championCount": len(by_champion),
        "positionCount": len(by_position),
        "teammateCount": len(by_teammate),
    })
    write_json(OUT / "overview.json", overview)

    champions = []
    for champion, group in sorted(by_champion.items(), key=lambda x: (-len(x[1]), x[0])):
        item = {"champion": champion, **normalize_counters(aggregate(group))}
        item["positions"] = {
            pos: normalize_counters(aggregate(by_champion_position[(champion, pos)]))
            for pos in POSITIONS
            if (champion, pos) in by_champion_position
        }
        champions.append(item)
    write_json(OUT / "champions.json", champions)

    positions = [
        {"position": position, **normalize_counters(aggregate(group))}
        for position, group in sorted(by_position.items(), key=lambda x: (-len(x[1]), x[0]))
    ]
    write_json(OUT / "positions.json", positions)

    matchup_index = []
    matchup_files = []
    matchup_groups = defaultdict(list)
    for (champion, position, opponent), group in by_matchup.items():
        matchup_groups[(champion, position)].append((opponent, group))

    for (champion, position), opponents in sorted(matchup_groups.items()):
        payload = {
            "champion": champion,
            "position": position,
            "opponents": [],
        }
        for opponent, group in sorted(opponents, key=lambda x: (-len(x[1]), x[0])):
            payload["opponents"].append({
                "opponent": opponent,
                **normalize_counters(aggregate(group)),
                "matchIds": [r["matchId"] for r in group],
            })
        champ_slug = slug(champion)
        pos_slug = slug(position)
        path = OUT / "matchups" / champ_slug / f"{pos_slug}.json"
        write_json(path, payload)
        rel = path.relative_to(DATA).as_posix()
        matchup_files.append(rel)
        matchup_index.append({
            "champion": champion,
            "position": position,
            "opponentCount": len(payload["opponents"]),
            "path": rel,
        })
    write_json(OUT / "matchups" / "index.json", matchup_index)

    teammate_rows = []
    for riot_id, group in sorted(by_teammate.items(), key=lambda x: (-len(x[1]), x[0].lower())):
        champ_pairs = Counter((r.get("champion"), r.get("position")) for r in group)
        teammate_rows.append({
            "riotId": riot_id,
            **normalize_counters(aggregate(group)),
            "myChampionPositionPairs": [
                {"champion": champ, "position": pos, "games": count}
                for (champ, pos), count in champ_pairs.most_common()
            ],
            "matchIds": [r["matchId"] for r in group],
        })
    write_json(OUT / "teammates.json", teammate_rows)

    summoners = []
    for (champion, position, spells), group in sorted(by_summoner.items(), key=lambda x: (-len(x[1]), x[0])):
        summoners.append({
            "champion": champion,
            "position": position,
            "summoners": spells,
            **normalize_counters(aggregate(group)),
        })
    write_json(OUT / "summoners.json", summoners)

    final_item_counter = Counter()
    for row in rows:
        for item in row.get("finalItems") or []:
            final_item_counter[(row.get("champion"), row.get("position"), item)] += 1
    builds = [
        {"champion": champ, "position": pos, "item": item, "games": count}
        for (champ, pos, item), count in final_item_counter.most_common()
    ]
    write_json(OUT / "builds.json", builds)

    index = {
        "generatedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
        "schemaVersion": 1,
        "matchCount": len(rows),
        "files": {
            "overview": "stats/overview.json",
            "champions": "stats/champions.json",
            "positions": "stats/positions.json",
            "matchups": "stats/matchups/index.json",
            "teammates": "stats/teammates.json",
            "summoners": "stats/summoners.json",
            "builds": "stats/builds.json",
        },
        "notes": [
            "Statistics are precomputed from generated match detail JSON.",
            "Matchup files include matchIds so AI can inspect only relevant games when deeper analysis is needed.",
            "Early-lane metrics use timeline snapshots and inherit Riot timeline cadence limitations.",
        ],
    }
    write_json(OUT / "index.json", index)

    if MANIFEST.exists():
        try:
            manifest = read_json(MANIFEST)
        except Exception:
            manifest = {}
        manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 7)
        manifest["statsIndexPath"] = "stats/index.json"
        manifest["statsMatchCount"] = len(rows)
        manifest["statsMatchupFileCount"] = len(matchup_files)
        write_json(MANIFEST, manifest)

    print(f"Stats ready: {len(rows)} matches")
    print(f"Champions: {len(by_champion)}")
    print(f"Matchup files: {len(matchup_files)}")
    print(f"Teammates: {len(by_teammate)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
