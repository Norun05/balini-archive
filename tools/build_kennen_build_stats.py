import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "champions" / "kennen" / "top"
OUT = ROOT / "data" / "ai" / "builds" / "kennen_top.json"

MAJOR_ITEMS = {
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
}

BOOTS = {
    3020: "마법사의 신발",
    3111: "헤르메스의 발걸음",
    3047: "판금 장화",
    3158: "명석함의 아이오니아 장화",
    3006: "광전사의 군화",
    3009: "신속의 장화",
}


def add(bucket, key, win):
    d = bucket[key]
    d["games"] += 1
    d["wins"] += int(bool(win))


def finish(bucket):
    rows = []
    for key, d in bucket.items():
        games = d["games"]
        wins = d["wins"]
        rows.append({
            "key": key,
            "games": games,
            "wins": wins,
            "losses": games - wins,
            "winRate": round(wins / games, 4) if games else None,
        })
    rows.sort(key=lambda r: (-r["games"], -r["winRate"], r["key"]))
    return rows


def load_matches():
    out = []
    seen = set()
    for path in sorted(SRC.glob("page-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for m in data.get("matches") or []:
            mid = m.get("matchId")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            out.append(m)
    return out


def purchase_order(match, allowed):
    events = ((match.get("timeline") or {}).get("itemEvents") or [])
    bought = []
    seen = set()
    for e in sorted(events, key=lambda x: x.get("timestamp") or 0):
        if e.get("type") != "ITEM_PURCHASED":
            continue
        item = e.get("itemId")
        if item in allowed and item not in seen:
            seen.add(item)
            bought.append(item)
    return bought


def main():
    matches = load_matches()

    first_core = defaultdict(lambda: {"games": 0, "wins": 0})
    two_core = defaultdict(lambda: {"games": 0, "wins": 0})
    boots = defaultdict(lambda: {"games": 0, "wins": 0})
    final_presence = defaultdict(lambda: {"games": 0, "wins": 0})

    with_core = 0
    with_two_core = 0

    for m in matches:
        win = bool(m.get("win"))
        majors = purchase_order(m, MAJOR_ITEMS)
        shoe_order = purchase_order(m, BOOTS)

        if majors:
            with_core += 1
            add(first_core, MAJOR_ITEMS[majors[0]], win)
        if len(majors) >= 2:
            with_two_core += 1
            add(two_core, f"{MAJOR_ITEMS[majors[0]]} → {MAJOR_ITEMS[majors[1]]}", win)
        if shoe_order:
            add(boots, BOOTS[shoe_order[0]], win)

        final_ids = set(m.get("items") or [])
        for item_id, name in {**MAJOR_ITEMS, **BOOTS}.items():
            if item_id in final_ids:
                add(final_presence, name, win)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "champion": "Kennen",
        "position": "TOP",
        "sampleCount": len(matches),
        "matchesWithRecognizedFirstCore": with_core,
        "matchesWithRecognizedTwoCore": with_two_core,
        "notes": [
            "firstCore/twoCore use ITEM_PURCHASED timestamps, not final inventory order.",
            "finalPresence is descriptive only and is strongly affected by game length and gold income.",
            "Only the major AP items listed in this script are recognized as cores.",
        ],
        "firstCore": finish(first_core),
        "twoCoreOrder": finish(two_core),
        "boots": finish(boots),
        "finalItemPresence": finish(final_presence),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Kennen TOP build stats: {len(matches)} matches")
    print(f"Recognized first core: {with_core}")
    print(f"Recognized two core: {with_two_core}")


if __name__ == "__main__":
    main()
