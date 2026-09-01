import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
CHAMPION_ROOT = ROOT / "data" / "champions"
OUT_ROOT = ROOT / "data" / "ai" / "builds"

# Completed core items recognized from ITEM_PURCHASED events.
# Keep these champion-specific so first-core detection does not mistake boots,
# components, starting items, or unrelated completed items for a core.
CORE_ITEMS = {
    "kennen": {
        3152: "마법공학 로켓 벨트",
        6653: "리안드리의 고통",
        3157: "존야의 모래시계",
        4645: "그림자불꽃",
        4646: "폭풍쇄도",
        3089: "라바돈의 죽음모자",
        3135: "공허의 지팡이",
        3137: "무덤꽃",
        3165: "모렐로노미콘",
        3102: "밴시의 장막",
        3115: "내셔의 이빨",
        3100: "리치베인",
        4628: "지평선의 초점",
        4633: "균열 생성기",
        3116: "라일라이의 수정홀",
        3146: "마법공학 총검",
    },
    "veigar": {
        6655: "루덴의 동반자",
        2503: "검은불꽃 횃불",
        6657: "영겁의 지팡이",
        3003: "대천사의 지팡이",
        3040: "대천사의 포옹",
        3118: "악의",
        4645: "그림자불꽃",
        4646: "폭풍쇄도",
        3089: "라바돈의 죽음모자",
        3157: "존야의 모래시계",
        3135: "공허의 지팡이",
        3137: "무덤꽃",
        3165: "모렐로노미콘",
        3102: "밴시의 장막",
        4628: "지평선의 초점",
        4629: "우주의 추진력",
        3116: "라일라이의 수정홀",
        3100: "리치베인",
        4633: "균열 생성기",
    },
}

CHAMPION_NAMES = {
    "kennen": "Kennen",
    "veigar": "Veigar",
}


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


def load_matches(src):
    matches = []
    seen = set()
    for path in sorted(src.glob("page-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for match in data.get("matches") or []:
            match_id = match.get("matchId")
            if not match_id or match_id in seen:
                continue
            seen.add(match_id)
            matches.append(match)
    return matches


def purchase_order(match, allowed):
    events = ((match.get("timeline") or {}).get("itemEvents") or [])
    bought = []
    seen = set()
    for event in sorted(events, key=lambda e: e.get("timestamp") or 0):
        if event.get("type") != "ITEM_PURCHASED":
            continue
        item_id = event.get("itemId")
        if item_id in allowed and item_id not in seen:
            seen.add(item_id)
            bought.append((item_id, event.get("timestamp")))
    return bought


def snapshot_diffs(match):
    out = {}
    duration = match.get("gameDuration") or 0
    for snap in ((match.get("timeline") or {}).get("snapshots") or []):
        minute = snap.get("minute")
        if minute not in (5, 10, 15, 20):
            continue
        if isinstance(duration, (int, float)) and duration < minute * 60:
            continue
        out[str(minute)] = {
            "goldDiff": snap.get("goldDiff"),
            "csDiff": snap.get("csDiff"),
            "levelDiff": snap.get("levelDiff"),
        }
    return out


def build_rows(matches, item_names):
    rows = []
    for match in matches:
        order = purchase_order(match, item_names)
        if not order:
            continue
        first_id, first_ts = order[0]
        second_id, second_ts = order[1] if len(order) >= 2 else (None, None)
        rows.append({
            "matchId": match.get("matchId"),
            "gameCreation": match.get("gameCreation"),
            "gameDuration": match.get("gameDuration"),
            "opponent": match.get("opponent"),
            "win": bool(match.get("win")),
            "firstCore": item_names[first_id],
            "firstCoreTimestamp": first_ts,
            "secondCore": item_names.get(second_id),
            "secondCoreTimestamp": second_ts,
            "snapshots": snapshot_diffs(match),
        })
    return rows


def build_profile(champion_key, position_key, matches):
    item_names = CORE_ITEMS[champion_key]
    rows = build_rows(matches, item_names)
    groups = defaultdict(list)
    for row in rows:
        groups[row["firstCore"]].append(row)

    out_groups = []
    for core, core_rows in groups.items():
        games = len(core_rows)
        wins = sum(bool(r.get("win")) for r in core_rows)
        purchase_minutes = [
            r["firstCoreTimestamp"] / 60000
            for r in core_rows
            if isinstance(r.get("firstCoreTimestamp"), (int, float))
        ]
        second = Counter(r.get("secondCore") for r in core_rows if r.get("secondCore"))
        opponents = Counter(r.get("opponent") for r in core_rows if r.get("opponent"))

        checkpoints = {}
        for minute in (5, 10, 15, 20):
            snaps = [(r.get("snapshots") or {}).get(str(minute)) or {} for r in core_rows]
            checkpoints[str(minute)] = {
                "goldDiff": stat([s.get("goldDiff") for s in snaps]),
                "csDiff": stat([s.get("csDiff") for s in snaps]),
                "levelDiff": stat([s.get("levelDiff") for s in snaps]),
            }

        result_split = {}
        for label, subrows in (
            ("wins", [r for r in core_rows if r.get("win")]),
            ("losses", [r for r in core_rows if not r.get("win")]),
        ):
            result_split[label] = {}
            for minute in (10, 15, 20):
                snaps = [(r.get("snapshots") or {}).get(str(minute)) or {} for r in subrows]
                result_split[label][str(minute)] = {
                    "goldDiff": stat([s.get("goldDiff") for s in snaps]),
                    "csDiff": stat([s.get("csDiff") for s in snaps]),
                }

        earliest = min(
            (r.get("gameCreation") for r in core_rows if isinstance(r.get("gameCreation"), (int, float))),
            default=None,
        )
        latest = max(
            (r.get("gameCreation") for r in core_rows if isinstance(r.get("gameCreation"), (int, float))),
            default=None,
        )

        out_groups.append({
            "firstCore": core,
            "games": games,
            "wins": wins,
            "losses": games - wins,
            "winRate": pct(wins, games),
            "avgFirstCoreMinute": round(mean(purchase_minutes), 2) if purchase_minutes else None,
            "medianFirstCoreMinute": round(median(purchase_minutes), 2) if purchase_minutes else None,
            "completion": {
                "by10": sum(t <= 10 for t in purchase_minutes),
                "by12": sum(t <= 12 for t in purchase_minutes),
                "by15": sum(t <= 15 for t in purchase_minutes),
                "withTimestamp": len(purchase_minutes),
            },
            "dateRange": {
                "earliestGameCreation": earliest,
                "latestGameCreation": latest,
            },
            "topOpponents": [
                {"champion": name, "games": count}
                for name, count in opponents.most_common(30)
            ],
            "secondCores": [
                {"item": name, "games": count}
                for name, count in second.most_common()
            ],
            "checkpoints": checkpoints,
            "resultSplit": result_split,
        })

    out_groups.sort(key=lambda g: (-g["games"], g["firstCore"]))

    return {
        "champion": CHAMPION_NAMES[champion_key],
        "position": position_key.upper(),
        "sampleCount": len(matches),
        "recognizedFirstCoreCount": len(rows),
        "notes": [
            "Groups are based on first recognized completed core from ITEM_PURCHASED timestamps.",
            "ALL combines every recorded position for this champion; INVALID keeps matches without a reliable role classification.",
            "Checkpoint diffs use the lane-opponent snapshot stored by the archive when available.",
            "Checkpoint rows after exact match end are absent in source data.",
            "This is descriptive selection-pattern analysis, not causal item-performance analysis.",
        ],
        "groups": out_groups,
    }


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    generated = 0

    for champion_key in ("kennen", "veigar"):
        champion_dir = CHAMPION_ROOT / champion_key
        if not champion_dir.exists():
            continue

        for position_dir in sorted(p for p in champion_dir.iterdir() if p.is_dir()):
            if not any(position_dir.glob("page-*.json")):
                continue

            position_key = position_dir.name.lower()
            matches = load_matches(position_dir)
            payload = build_profile(champion_key, position_key, matches)
            out_path = OUT_ROOT / f"{champion_key}_{position_key}_firstcore_profile.json"
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            generated += 1
            print(
                f"{CHAMPION_NAMES[champion_key]} {position_key.upper()} first-core profile: "
                f"{payload['recognizedFirstCoreCount']}/{payload['sampleCount']} matches, "
                f"{len(payload['groups'])} cores"
            )

    print(f"Generated {generated} first-core profile files")


if __name__ == "__main__":
    main()
