import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from build_veigar_build_stats import MAJOR_ITEMS, purchase_order, purchase_time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "champions" / "veigar" / "middle"
OUT = ROOT / "data" / "ai" / "builds" / "veigar_middle_two_core.json"


def load_matches():
    rows = []
    seen = set()
    for path in sorted(SRC.glob("page-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for m in data.get("matches") or []:
            mid = m.get("matchId")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            rows.append(m)
    return rows


def snapshot_at(match, minute):
    duration = match.get("gameDuration") or 0
    if isinstance(duration, (int, float)) and duration < minute * 60:
        return None
    for s in ((match.get("timeline") or {}).get("snapshots") or []):
        if s.get("minute") == minute:
            return {
                "goldDiff": s.get("goldDiff"),
                "csDiff": s.get("csDiff"),
                "levelDiff": s.get("levelDiff"),
            }
    return None


def metric_summary(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return {"n": 0, "avg": None, "median": None, "ahead": 0, "behind": 0, "even": 0}
    return {
        "n": len(vals),
        "avg": round(sum(vals) / len(vals), 2),
        "median": median(vals),
        "ahead": sum(v > 0 for v in vals),
        "behind": sum(v < 0 for v in vals),
        "even": sum(v == 0 for v in vals),
    }


def main():
    matches = load_matches()
    groups = defaultdict(list)

    for m in matches:
        majors = purchase_order(m, MAJOR_ITEMS)
        if len(majors) < 2:
            continue
        first_id, second_id = majors[0], majors[1]
        combo = f"{MAJOR_ITEMS[first_id]} → {MAJOR_ITEMS[second_id]}"
        groups[combo].append({
            "matchId": m.get("matchId"),
            "gameCreation": m.get("gameCreation"),
            "gameDuration": m.get("gameDuration"),
            "opponent": m.get("opponent"),
            "win": bool(m.get("win")),
            "kills": m.get("kills"),
            "deaths": m.get("deaths"),
            "assists": m.get("assists"),
            "firstCoreTimestamp": purchase_time(m, first_id),
            "secondCoreTimestamp": purchase_time(m, second_id),
            "snapshots": {str(minute): snapshot_at(m, minute) for minute in (10, 15, 20)},
        })

    summaries = []
    for combo, rows in groups.items():
        wins = sum(r["win"] for r in rows)
        opponents = Counter(r.get("opponent") or "Unknown" for r in rows)
        checkpoints = {}
        for minute in (10, 15, 20):
            ss = [r["snapshots"].get(str(minute)) for r in rows]
            ss = [s for s in ss if s]
            checkpoints[str(minute)] = {
                "goldDiff": metric_summary([s.get("goldDiff") for s in ss]),
                "csDiff": metric_summary([s.get("csDiff") for s in ss]),
                "levelDiff": metric_summary([s.get("levelDiff") for s in ss]),
            }
        second_times = [r.get("secondCoreTimestamp") for r in rows if isinstance(r.get("secondCoreTimestamp"), (int, float))]
        summaries.append({
            "combo": combo,
            "games": len(rows),
            "wins": wins,
            "losses": len(rows) - wins,
            "winRate": round(wins / len(rows), 4),
            "avgSecondCoreMinute": round((sum(second_times) / len(second_times)) / 60000, 2) if second_times else None,
            "opponents": [{"champion": c, "games": n} for c, n in opponents.most_common()],
            "checkpoints": checkpoints,
            "matches": sorted(rows, key=lambda r: r.get("gameCreation") or 0, reverse=True),
        })

    summaries.sort(key=lambda r: (-r["games"], r["combo"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "champion": "Veigar",
        "position": "MIDDLE",
        "sampleCount": len(matches),
        "matchesWithRecognizedTwoCore": sum(len(v) for v in groups.values()),
        "notes": [
            "Two-core order is based on ITEM_PURCHASED timestamps.",
            "Checkpoint diffs compare Veigar with the inferred MIDDLE lane opponent.",
            "Only checkpoints before the exact match end are included.",
            "Two-core samples exclude games that ended before a second recognized core was completed."
        ],
        "groups": summaries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Veigar two-core analysis: {len(matches)} matches, {sum(len(v) for v in groups.values())} with two cores")


if __name__ == "__main__":
    main()
