import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "champions" / "veigar" / "middle"
MATCH_SRC = ROOT / "data" / "matches"
OUT = ROOT / "data" / "ai" / "builds" / "veigar_middle.json"
DETAIL_OUT = ROOT / "data" / "ai" / "builds" / "veigar_middle_matches.json"

# Veigar가 실제로 1코어 후보로 갈 수 있거나, 과거 기록에서 등장할 수 있는 주요 완성 아이템.
# 구매 타임스탬프 순서로 첫 완성 코어를 판정한다.
MAJOR_ITEMS = {
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
}

BOOTS = {
    3020: "마법사의 신발",
    3111: "헤르메스의 발걸음",
    3047: "판금 장화",
    3158: "명석함의 아이오니아 장화",
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
    rows.sort(key=lambda r: (-r["games"], -r["winRate"], str(r["key"])))
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


def purchase_time(match, item_id):
    events = ((match.get("timeline") or {}).get("itemEvents") or [])
    times = [e.get("timestamp") for e in events if e.get("type") == "ITEM_PURCHASED" and e.get("itemId") == item_id]
    times = [t for t in times if isinstance(t, (int, float))]
    return min(times) if times else None


def rune_info(match_id):
    if not match_id:
        return None
    path = MATCH_SRC / f"{match_id}.json"
    if not path.exists():
        return None
    try:
        detail = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    styles = ((detail.get("me") or {}).get("perkStyles") or [])
    if not styles:
        return None
    rows = []
    for style in styles:
        rows.append({
            "style": style.get("style"),
            "description": style.get("description"),
            "perks": style.get("perks") or [],
        })
    primary = next((s for s in rows if s.get("description") == "primaryStyle"), rows[0] if rows else None)
    secondary = next((s for s in rows if s.get("description") == "subStyle"), rows[1] if len(rows) > 1 else None)
    return {
        "styles": rows,
        "primaryStyle": primary.get("style") if primary else None,
        "keystone": (primary.get("perks") or [None])[0] if primary else None,
        "primaryPerks": primary.get("perks") if primary else [],
        "secondaryStyle": secondary.get("style") if secondary else None,
        "secondaryPerks": secondary.get("perks") if secondary else [],
    }


def rune_summary(rows):
    keystones = defaultdict(lambda: {"games": 0, "wins": 0})
    style_pairs = defaultdict(lambda: {"games": 0, "wins": 0})
    exact_pages = defaultdict(lambda: {"games": 0, "wins": 0})
    with_runes = 0
    for r in rows:
        rune = r.get("runes") or {}
        if not rune:
            continue
        with_runes += 1
        win = bool(r.get("win"))
        key = rune.get("keystone")
        if key is not None:
            add(keystones, str(key), win)
        p = rune.get("primaryStyle")
        s = rune.get("secondaryStyle")
        if p is not None and s is not None:
            add(style_pairs, f"{p}+{s}", win)
        pp = rune.get("primaryPerks") or []
        sp = rune.get("secondaryPerks") or []
        if pp or sp:
            add(exact_pages, "/".join(map(str, pp)) + "+" + "/".join(map(str, sp)), win)
    return {
        "matchesWithRunes": with_runes,
        "keystones": finish(keystones),
        "stylePairs": finish(style_pairs),
        "exactPages": finish(exact_pages),
    }


def main():
    matches = load_matches()
    first_core = defaultdict(lambda: {"games": 0, "wins": 0})
    two_core = defaultdict(lambda: {"games": 0, "wins": 0})
    boots = defaultdict(lambda: {"games": 0, "wins": 0})
    final_presence = defaultdict(lambda: {"games": 0, "wins": 0})
    match_rows = []
    with_core = 0
    with_two_core = 0

    for m in matches:
        win = bool(m.get("win"))
        majors = purchase_order(m, MAJOR_ITEMS)
        shoe_order = purchase_order(m, BOOTS)

        first_name = None
        second_name = None
        if majors:
            with_core += 1
            first_name = MAJOR_ITEMS[majors[0]]
            add(first_core, first_name, win)
            if len(majors) >= 2:
                second_name = MAJOR_ITEMS[majors[1]]
                with_two_core += 1
                add(two_core, f"{first_name} → {second_name}", win)

        if shoe_order:
            add(boots, BOOTS[shoe_order[0]], win)

        final_ids = set(m.get("items") or [])
        for item_id, name in {**MAJOR_ITEMS, **BOOTS}.items():
            if item_id in final_ids:
                add(final_presence, name, win)

        match_rows.append({
            "matchId": m.get("matchId"),
            "gameCreation": m.get("gameCreation"),
            "gameDuration": m.get("gameDuration"),
            "opponent": m.get("opponent"),
            "win": win,
            "kills": m.get("kills"),
            "deaths": m.get("deaths"),
            "assists": m.get("assists"),
            "cs": m.get("cs"),
            "firstCore": first_name,
            "firstCoreTimestamp": purchase_time(m, majors[0]) if majors else None,
            "secondCore": second_name,
            "secondCoreTimestamp": purchase_time(m, majors[1]) if len(majors) >= 2 else None,
            "boots": BOOTS[shoe_order[0]] if shoe_order else None,
            "runes": rune_info(m.get("matchId")),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "champion": "Veigar",
        "position": "MIDDLE",
        "sampleCount": len(matches),
        "matchesWithRecognizedFirstCore": with_core,
        "matchesWithRecognizedTwoCore": with_two_core,
        "notes": [
            "firstCore/twoCore use ITEM_PURCHASED timestamps, not final inventory order.",
            "finalPresence is descriptive only and is strongly affected by game length and gold income.",
            "Only the listed major completed items are recognized as cores."
        ],
        "firstCore": finish(first_core),
        "twoCoreOrder": finish(two_core),
        "boots": finish(boots),
        "finalItemPresence": finish(final_presence),
        "runes": rune_summary(match_rows),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    match_rows.sort(key=lambda r: r.get("gameCreation") or 0, reverse=True)
    DETAIL_OUT.write_text(json.dumps({
        "champion": "Veigar",
        "position": "MIDDLE",
        "sampleCount": len(match_rows),
        "runeSummary": rune_summary(match_rows),
        "matches": match_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Veigar MIDDLE build stats: {len(matches)} matches")
    print(f"Recognized first core: {with_core}")
    print(f"Recognized two core: {with_two_core}")
    print(f"Matches with runes: {rune_summary(match_rows)['matchesWithRunes']}")


if __name__ == "__main__":
    main()
