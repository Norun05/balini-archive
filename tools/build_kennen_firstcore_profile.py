import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "ai" / "builds" / "kennen_top_matches.json"
OUT = ROOT / "data" / "ai" / "builds" / "kennen_top_firstcore_profile.json"


def stat(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return {"n": 0, "avg": None, "median": None, "ahead": 0, "behind": 0, "even": 0}
    return {
        "n": len(vals),
        "avg": round(mean(vals), 2),
        "median": round(median(vals), 2),
        "ahead": sum(v > 0 for v in vals),
        "behind": sum(v < 0 for v in vals),
        "even": sum(v == 0 for v in vals),
    }


def pct(n, d):
    return round(n / d, 4) if d else None


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    matches = data.get("matches") or []

    groups = defaultdict(list)
    for m in matches:
        core = m.get("firstCore")
        if core:
            groups[core].append(m)

    out_groups = []
    for core, rows in groups.items():
        games = len(rows)
        wins = sum(bool(r.get("win")) for r in rows)
        purchase_minutes = [r.get("firstCoreTimestamp") / 60000 for r in rows if isinstance(r.get("firstCoreTimestamp"), (int, float))]

        second = Counter(r.get("secondCore") for r in rows if r.get("secondCore"))
        opponents = Counter(r.get("opponent") for r in rows if r.get("opponent"))

        cp = {}
        for minute in (5, 10, 15, 20):
            snaps = [(r.get("snapshots") or {}).get(str(minute)) or {} for r in rows]
            cp[str(minute)] = {
                "goldDiff": stat([s.get("goldDiff") for s in snaps]),
                "csDiff": stat([s.get("csDiff") for s in snaps]),
                "levelDiff": stat([s.get("levelDiff") for s in snaps]),
            }

        win_rows = [r for r in rows if r.get("win")]
        loss_rows = [r for r in rows if not r.get("win")]
        split = {}
        for label, subrows in (("wins", win_rows), ("losses", loss_rows)):
            split[label] = {}
            for minute in (10, 15, 20):
                snaps = [(r.get("snapshots") or {}).get(str(minute)) or {} for r in subrows]
                split[label][str(minute)] = {
                    "goldDiff": stat([s.get("goldDiff") for s in snaps]),
                    "csDiff": stat([s.get("csDiff") for s in snaps]),
                }

        earliest = min((r.get("gameCreation") for r in rows if isinstance(r.get("gameCreation"), (int, float))), default=None)
        latest = max((r.get("gameCreation") for r in rows if isinstance(r.get("gameCreation"), (int, float))), default=None)

        before_10 = sum(t <= 10 for t in purchase_minutes)
        before_12 = sum(t <= 12 for t in purchase_minutes)
        before_15 = sum(t <= 15 for t in purchase_minutes)

        out_groups.append({
            "firstCore": core,
            "games": games,
            "wins": wins,
            "losses": games - wins,
            "winRate": pct(wins, games),
            "avgFirstCoreMinute": round(mean(purchase_minutes), 2) if purchase_minutes else None,
            "medianFirstCoreMinute": round(median(purchase_minutes), 2) if purchase_minutes else None,
            "completion": {
                "by10": before_10,
                "by12": before_12,
                "by15": before_15,
                "withTimestamp": len(purchase_minutes),
            },
            "dateRange": {"earliestGameCreation": earliest, "latestGameCreation": latest},
            "topOpponents": [{"champion": k, "games": v} for k, v in opponents.most_common(30)],
            "secondCores": [{"item": k, "games": v} for k, v in second.most_common()],
            "checkpoints": cp,
            "resultSplit": split,
        })

    out_groups.sort(key=lambda g: (-g["games"], g["firstCore"]))

    payload = {
        "champion": "Kennen",
        "position": "TOP",
        "sampleCount": data.get("sampleCount"),
        "recognizedFirstCoreCount": sum(g["games"] for g in out_groups),
        "notes": [
            "Groups are based on first recognized completed core from ITEM_PURCHASED timestamps.",
            "Checkpoint diffs compare Kennen with the inferred TOP lane opponent.",
            "Checkpoint rows after exact match end are absent in source data.",
            "This is descriptive selection-pattern analysis, not causal item-performance analysis."
        ],
        "groups": out_groups,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Kennen first-core profile: {sum(g['games'] for g in out_groups)} matches across {len(out_groups)} cores")


if __name__ == "__main__":
    main()
