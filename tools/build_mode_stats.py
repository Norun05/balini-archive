import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import build_item_stats as item_stats
import build_stats as stats
from game_modes import STANDARD_RIFT_RULE_MODES, classify_detail

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MATCHES_DIR = DATA / "matches"
STATS_DIR = DATA / "stats"
OUT = STATS_DIR / "by-mode"
MODE_INDEX = STATS_DIR / "modes.json"
SEARCH_DIR = DATA / "search"
SEARCH_MODE_ROUTES = SEARCH_DIR / "modes.json"
SEARCH_INDEX = SEARCH_DIR / "index.json"
MANIFEST = DATA / "manifest.json"

STANDARD_POSITIONS = set(stats.POSITIONS)


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(n, d):
    return round(n * 100 / d, 2) if d else None


def item_groups(details):
    first = defaultdict(list)
    second = defaultdict(list)

    for detail in details:
        me = detail.get("me") or {}
        pid = me.get("participantId")
        if not pid:
            continue
        eco = item_stats.participant_economy(detail, pid)
        champion = detail.get("championName") or "Unknown"
        position = detail.get("position") if detail.get("position") in STANDARD_POSITIONS else None
        win = bool(detail.get("win"))
        match_id = detail.get("matchId")

        for slot_name, target in (("firstCore", first), ("secondCore", second)):
            core = eco.get(slot_name)
            if not core or not core.get("itemNameKo"):
                continue
            target[(champion, position, core["itemNameKo"])].append({
                "matchId": match_id,
                "win": win,
                "timestamp": core.get("timestamp"),
            })

    def pack(groups):
        rows = []
        for (champion, position, item), group in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            wins = sum(1 for r in group if r["win"])
            timestamps = [r["timestamp"] for r in group if isinstance(r.get("timestamp"), (int, float))]
            rows.append({
                "champion": champion,
                "position": position,
                "item": item,
                "games": len(group),
                "wins": wins,
                "losses": len(group) - wins,
                "winRate": pct(wins, len(group)),
                "avgCompletionMs": stats.avg(timestamps),
                "matchIds": [r["matchId"] for r in group],
            })
        return rows

    return {"firstCore": pack(first), "secondCore": pack(second)}


def build_matchup_files(mode_dir: Path, rows, has_standard_positions):
    matchup_index = []
    if not has_standard_positions:
        write_json(mode_dir / "matchups" / "index.json", matchup_index)
        return matchup_index

    groups = defaultdict(list)
    for row in rows:
        position = row.get("position")
        if position not in STANDARD_POSITIONS:
            continue
        opponent = row.get("opponent")
        if not opponent:
            continue
        groups[(row.get("champion") or "Unknown", position, opponent)].append(row)

    by_champ_pos = defaultdict(list)
    for (champion, position, opponent), group in groups.items():
        by_champ_pos[(champion, position)].append((opponent, group))

    for (champion, position), opponents in sorted(by_champ_pos.items()):
        payload = {
            "champion": champion,
            "position": position,
            "opponents": [],
        }
        for opponent, group in sorted(opponents, key=lambda x: (-len(x[1]), x[0])):
            payload["opponents"].append({
                "opponent": opponent,
                **stats.normalize_counters(stats.aggregate(group)),
                "matchIds": [r["matchId"] for r in group],
            })
        path = mode_dir / "matchups" / stats.slug(champion) / f"{stats.slug(position)}.json"
        write_json(path, payload)
        matchup_index.append({
            "champion": champion,
            "position": position,
            "opponentCount": len(payload["opponents"]),
            "path": path.relative_to(DATA).as_posix(),
        })

    write_json(mode_dir / "matchups" / "index.json", matchup_index)
    return matchup_index


def write_mode_bundle(mode_key, mode_name_ko, mode_family, has_standard_positions, pairs, synthetic=False):
    mode_dir = OUT / mode_key
    mode_dir.mkdir(parents=True, exist_ok=True)

    rows = [row for _, row in pairs]
    details = [detail for detail, _ in pairs]
    rows.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)

    overview = {
        "modeKey": mode_key,
        "modeNameKo": mode_name_ko,
        "modeFamily": mode_family,
        "synthetic": synthetic,
        **stats.normalize_counters(stats.aggregate(rows)),
        "generatedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
        "matchCount": len(rows),
    }
    write_json(mode_dir / "overview.json", overview)

    by_champion = defaultdict(list)
    by_position = defaultdict(list)
    by_champion_position = defaultdict(list)
    for row in rows:
        champion = row.get("champion") or "Unknown"
        by_champion[champion].append(row)
        if has_standard_positions and row.get("position") in STANDARD_POSITIONS:
            by_position[row["position"]].append(row)
            by_champion_position[(champion, row["position"])].append(row)

    champions = []
    for champion, group in sorted(by_champion.items(), key=lambda x: (-len(x[1]), x[0])):
        entry = {
            "champion": champion,
            **stats.normalize_counters(stats.aggregate(group)),
            "matchIds": [r["matchId"] for r in group],
        }
        entry["positions"] = {
            pos: stats.normalize_counters(stats.aggregate(by_champion_position[(champion, pos)]))
            for pos in stats.POSITIONS
            if (champion, pos) in by_champion_position
        }
        champions.append(entry)
    write_json(mode_dir / "champions.json", champions)

    positions = [
        {"position": position, **stats.normalize_counters(stats.aggregate(group))}
        for position, group in sorted(by_position.items(), key=lambda x: (-len(x[1]), x[0]))
    ]
    write_json(mode_dir / "positions.json", positions)

    matchup_index = build_matchup_files(mode_dir, rows, has_standard_positions)

    timing_payload = {
        "schemaVersion": 1,
        "modeKey": mode_key,
        "modeNameKo": mode_name_ko,
        **item_groups(details),
        "notes": [
            "Core timings are separated by normalized game mode.",
            "Special modes without standard lanes expose position as null instead of Invalid.",
            "Core completion still inherits timeline.itemEconomy heuristic limitations.",
        ],
    }
    write_json(mode_dir / "item_timings.json", timing_payload)

    return {
        "modeKey": mode_key,
        "modeNameKo": mode_name_ko,
        "modeFamily": mode_family,
        "games": len(rows),
        "synthetic": synthetic,
        "hasStandardPositions": has_standard_positions,
        "files": {
            "overview": (mode_dir / "overview.json").relative_to(DATA).as_posix(),
            "champions": (mode_dir / "champions.json").relative_to(DATA).as_posix(),
            "positions": (mode_dir / "positions.json").relative_to(DATA).as_posix(),
            "matchups": (mode_dir / "matchups" / "index.json").relative_to(DATA).as_posix(),
            "itemTimings": (mode_dir / "item_timings.json").relative_to(DATA).as_posix(),
        },
        "matchupFileCount": len(matchup_index),
    }


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    pairs_by_mode = defaultdict(list)
    meta_by_mode = {}

    for path in sorted(MATCHES_DIR.glob("KR_*.json")):
        try:
            detail = read_json(path)
        except Exception:
            continue
        meta = classify_detail(detail)
        row = stats.match_row(detail)
        row.update({
            "modeKey": meta["modeKey"],
            "modeNameKo": meta["modeNameKo"],
            "rulesetKey": meta["rulesetKey"],
            "isStandardRift": meta["isStandardRift"],
        })
        pairs_by_mode[meta["modeKey"]].append((detail, row))
        meta_by_mode[meta["modeKey"]] = meta

    bundles = []
    for mode_key, pairs in sorted(pairs_by_mode.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        meta = meta_by_mode[mode_key]
        bundles.append(write_mode_bundle(
            mode_key,
            meta["modeNameKo"],
            meta["modeFamily"],
            meta["hasStandardPositions"],
            pairs,
        ))

    standard_pairs = []
    for mode_key, pairs in pairs_by_mode.items():
        if mode_key in STANDARD_RIFT_RULE_MODES:
            standard_pairs.extend(pairs)
    if standard_pairs:
        bundles.insert(0, write_mode_bundle(
            "standard_rift",
            "소환사의 협곡 · 일반 규칙",
            "summoners_rift",
            True,
            standard_pairs,
            synthetic=True,
        ))

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    index_payload = {
        "schemaVersion": 1,
        "generatedAt": now_ms,
        "defaultAnalysisMode": "standard_rift" if standard_pairs else None,
        "modes": bundles,
        "notes": [
            "Use by-mode stats for champion, lane, matchup, and item analysis; do not mix special modes into standard Rift conclusions.",
            "When the user asks for ordinary lane/build analysis without naming a mode, prefer standard_rift.",
            "Swiftplay remains separate from standard_rift because its economy/objective rules materially differ.",
            "Arena/ARAM/URF have no standard lane position stats.",
        ],
    }
    write_json(MODE_INDEX, index_payload)

    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    routes = {
        bundle["modeKey"]: {
            "modeNameKo": bundle["modeNameKo"],
            "games": bundle["games"],
            "synthetic": bundle["synthetic"],
            **bundle["files"],
        }
        for bundle in bundles
    }
    write_json(SEARCH_MODE_ROUTES, {
        "schemaVersion": 1,
        "defaultAnalysisMode": index_payload["defaultAnalysisMode"],
        "routes": routes,
        "aliases": {
            "일반": "normal_draft",
            "일반전": "normal_draft",
            "교차선택": "normal_draft",
            "솔랭": "ranked_solo",
            "솔로랭크": "ranked_solo",
            "자랭": "ranked_flex",
            "신속": "swiftplay",
            "신속전": "swiftplay",
            "칼바람": "aram",
            "증강칼바람": "aram_mayhem",
            "아레나": "arena",
            "우르프": "arurf",
            "협곡": "standard_rift",
            "일반규칙협곡": "standard_rift"
        },
        "notes": [
            "Resolve the requested mode here before opening mode-specific stats.",
            "If no mode is named for ordinary champion/lane/build analysis, use defaultAnalysisMode.",
        ],
    })

    if SEARCH_INDEX.exists():
        try:
            search_index = read_json(SEARCH_INDEX)
        except Exception:
            search_index = {}
        search_index.setdefault("routes", {})["modes"] = "search/modes.json"
        search_index.setdefault("queryExamples", {})["modeAwareAnalysis"] = [
            "Resolve mode through search/modes.json before opening champion, matchup, or item statistics.",
            "For an unspecified ordinary Rift analysis, prefer standard_rift instead of all-mode aggregate stats.",
        ]
        search_index["modeRouteCount"] = len(routes)
        search_index["defaultAnalysisMode"] = index_payload["defaultAnalysisMode"]
        write_json(SEARCH_INDEX, search_index)

    manifest = read_json(MANIFEST) if MANIFEST.exists() else {}
    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 13)
    manifest["modeStatsIndexPath"] = "stats/modes.json"
    manifest["modeStatsRoutePath"] = "search/modes.json"
    manifest["modeStatsModeCount"] = len(bundles)
    manifest["defaultAnalysisMode"] = index_payload["defaultAnalysisMode"]
    write_json(MANIFEST, manifest)

    print(f"Mode stats ready: {sum(len(v) for v in pairs_by_mode.values())} matches")
    for bundle in bundles:
        print(f"  {bundle['modeNameKo']}: {bundle['games']} games")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
