import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MATCHES_DIR = DATA / "matches"
STATS_DIR = DATA / "stats"
MANIFEST = DATA / "manifest.json"


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def avg(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def pct(n, d):
    return round(n * 100 / d, 2) if d else None


def participant_economy(detail, participant_id):
    participants = (((detail.get("timeline") or {}).get("itemEconomy") or {}).get("participants") or {})
    return participants.get(str(participant_id)) or {}


def main():
    by_first_core = defaultdict(list)
    by_second_core = defaultdict(list)
    by_matchup = defaultdict(list)
    rows = []

    for path in sorted(MATCHES_DIR.glob("KR_*.json")):
        try:
            d = read_json(path)
        except Exception:
            continue
        me = d.get("me") or {}
        opp = d.get("laneOpponent") or {}
        me_id = me.get("participantId")
        opp_id = opp.get("participantId")
        if not me_id:
            continue
        myeco = participant_economy(d, me_id)
        opeco = participant_economy(d, opp_id) if opp_id else {}
        first = myeco.get("firstCore")
        second = myeco.get("secondCore")
        opp_first = opeco.get("firstCore")
        champion = d.get("championName") or "Unknown"
        position = d.get("position") or "UNKNOWN"
        opponent = opp.get("championName") or "Unknown"
        row = {
            "matchId": d.get("matchId"),
            "champion": champion,
            "position": position,
            "opponent": opponent,
            "win": bool(d.get("win")),
            "firstCore": first,
            "secondCore": second,
            "opponentFirstCore": opp_first,
            "firstCoreLeadMs": ((opp_first or {}).get("timestamp") - (first or {}).get("timestamp")) if first and opp_first else None,
        }
        rows.append(row)
        if first and first.get("itemNameKo"):
            by_first_core[(champion, position, first["itemNameKo"])].append(row)
        if second and second.get("itemNameKo"):
            by_second_core[(champion, position, second["itemNameKo"])].append(row)
        by_matchup[(champion, position, opponent)].append(row)

    def item_groups(groups):
        result = []
        for (champ, pos, item), group in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            wins = sum(1 for r in group if r.get("win"))
            timestamps = []
            for r in group:
                core = r.get("firstCore") if groups is by_first_core else r.get("secondCore")
                if core and isinstance(core.get("timestamp"), (int, float)):
                    timestamps.append(core["timestamp"])
            result.append({
                "champion": champ,
                "position": pos,
                "item": item,
                "games": len(group),
                "wins": wins,
                "winRate": pct(wins, len(group)),
                "avgCompletionMs": avg(timestamps),
                "matchIds": [r["matchId"] for r in group],
            })
        return result

    matchup_rows = []
    for (champ, pos, opp), group in sorted(by_matchup.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        comparable = [r for r in group if isinstance(r.get("firstCoreLeadMs"), (int, float))]
        faster = sum(1 for r in comparable if r["firstCoreLeadMs"] > 0)
        slower = sum(1 for r in comparable if r["firstCoreLeadMs"] < 0)
        tied = len(comparable) - faster - slower
        matchup_rows.append({
            "champion": champ,
            "position": pos,
            "opponent": opp,
            "games": len(group),
            "comparableFirstCores": len(comparable),
            "firstCoreFaster": faster,
            "firstCoreSlower": slower,
            "firstCoreTie": tied,
            "firstCoreFasterRate": pct(faster, len(comparable)),
            "avgFirstCoreLeadMs": avg([r.get("firstCoreLeadMs") for r in comparable]),
            "matchIds": [r["matchId"] for r in group],
        })

    payload = {
        "schemaVersion": 1,
        "firstCore": item_groups(by_first_core),
        "secondCore": item_groups(by_second_core),
        "matchupFirstCoreTempo": matchup_rows,
        "notes": [
            "Core timings use timeline.itemEconomy heuristic completions, not a Riot-provided core-item field.",
            "Positive firstCoreLeadMs means the user completed the inferred first core earlier than the lane opponent.",
        ],
    }
    out_path = STATS_DIR / "item_timings.json"
    write_json(out_path, payload)

    index_path = STATS_DIR / "index.json"
    if index_path.exists():
        try:
            index = read_json(index_path)
            index.setdefault("files", {})["itemTimings"] = "stats/item_timings.json"
            write_json(index_path, index)
        except Exception:
            pass

    if MANIFEST.exists():
        try:
            manifest = read_json(MANIFEST)
        except Exception:
            manifest = {}
        manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 11)
        manifest["itemTimingStatsPath"] = "stats/item_timings.json"
        manifest["itemTimingStatsMatchCount"] = len(rows)
        write_json(MANIFEST, manifest)

    print(f"Item timing stats ready: {len(rows)} matches")
    print(f"First-core groups: {len(by_first_core)}")
    print(f"Second-core groups: {len(by_second_core)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
