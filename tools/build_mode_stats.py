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
MODE_OUT = STATS_DIR / "by-mode"
RULESET_OUT = STATS_DIR / "by-ruleset"
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


def safe_tuple_sort_key(values):
    """Return a deterministic comparison key even when tuple members are None."""
    return tuple("" if value is None else str(value) for value in values)


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
        for (champion, position, item), group in sorted(
            groups.items(),
            key=lambda kv: (-len(kv[1]), safe_tuple_sort_key(kv[0])),
        ):
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


def build_matchup_files(bundle_dir: Path, rows, has_standard_positions):
    matchup_index = []
    if not has_standard_positions:
        write_json(bundle_dir / "matchups" / "index.json", matchup_index)
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
        path = bundle_dir / "matchups" / stats.slug(champion) / f"{stats.slug(position)}.json"
        write_json(path, payload)
        matchup_index.append({
            "champion": champion,
            "position": position,
            "opponentCount": len(payload["opponents"]),
            "path": path.relative_to(DATA).as_posix(),
        })

    write_json(bundle_dir / "matchups" / "index.json", matchup_index)
    return matchup_index


def write_bundle(root_dir, key, name_ko, family, has_standard_positions, pairs, *, kind, synthetic=False):
    bundle_dir = root_dir / key
    bundle_dir.mkdir(parents=True, exist_ok=True)

    rows = [row for _, row in pairs]
    details = [detail for detail, _ in pairs]
    rows.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)

    overview = {
        f"{kind}Key": key,
        f"{kind}NameKo": name_ko,
        "modeFamily": family,
        "synthetic": synthetic,
        **stats.normalize_counters(stats.aggregate(rows)),
        "generatedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
        "matchCount": len(rows),
    }
    write_json(bundle_dir / "overview.json", overview)

    by_champion = defaultdict(list)
    by_position = defaultdict(list)
    by_champion_position = defaultdict(list)
    by_summoner = defaultdict(list)
    for row in rows:
        champion = row.get("champion") or "Unknown"
        by_champion[champion].append(row)
        position = row.get("position") if has_standard_positions and row.get("position") in STANDARD_POSITIONS else None
        if position:
            by_position[position].append(row)
            by_champion_position[(champion, position)].append(row)
        if row.get("summoners"):
            by_summoner[(champion, position, row["summoners"])].append(row)

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
    write_json(bundle_dir / "champions.json", champions)

    positions = [
        {"position": position, **stats.normalize_counters(stats.aggregate(group))}
        for position, group in sorted(by_position.items(), key=lambda x: (-len(x[1]), x[0]))
    ]
    write_json(bundle_dir / "positions.json", positions)

    summoners = []
    for (champion, position, spells), group in sorted(
        by_summoner.items(),
        key=lambda x: (-len(x[1]), safe_tuple_sort_key(x[0])),
    ):
        summoners.append({
            "champion": champion,
            "position": position,
            "summoners": spells,
            **stats.normalize_counters(stats.aggregate(group)),
        })
    write_json(bundle_dir / "summoners.json", summoners)

    matchup_index = build_matchup_files(bundle_dir, rows, has_standard_positions)

    timing_payload = {
        "schemaVersion": 1,
        f"{kind}Key": key,
        f"{kind}NameKo": name_ko,
        **item_groups(details),
        "notes": [
            "Core timings are separated by normalized mode/ruleset.",
            "Special modes without standard lanes expose position as null instead of Invalid.",
            "Core completion still inherits timeline.itemEconomy heuristic limitations.",
        ],
    }
    write_json(bundle_dir / "item_timings.json", timing_payload)

    return {
        f"{kind}Key": key,
        f"{kind}NameKo": name_ko,
        "modeFamily": family,
        "games": len(rows),
        "synthetic": synthetic,
        "hasStandardPositions": has_standard_positions,
        "files": {
            "overview": (bundle_dir / "overview.json").relative_to(DATA).as_posix(),
            "champions": (bundle_dir / "champions.json").relative_to(DATA).as_posix(),
            "positions": (bundle_dir / "positions.json").relative_to(DATA).as_posix(),
            "summoners": (bundle_dir / "summoners.json").relative_to(DATA).as_posix(),
            "matchups": (bundle_dir / "matchups" / "index.json").relative_to(DATA).as_posix(),
            "itemTimings": (bundle_dir / "item_timings.json").relative_to(DATA).as_posix(),
        },
        "matchupFileCount": len(matchup_index),
    }


def main():
    for out in (MODE_OUT, RULESET_OUT):
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)

    pairs_by_mode = defaultdict(list)
    pairs_by_ruleset = defaultdict(list)
    meta_by_mode = {}
    meta_by_ruleset = {}

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
            "rulesetNameKo": meta["rulesetNameKo"],
            "isStandardRift": meta["isStandardRift"],
        })
        pair = (detail, row)
        pairs_by_mode[meta["modeKey"]].append(pair)
        pairs_by_ruleset[meta["rulesetKey"]].append(pair)
        meta_by_mode[meta["modeKey"]] = meta
        meta_by_ruleset[meta["rulesetKey"]] = meta

    ruleset_bundles = {}
    for ruleset_key, pairs in sorted(pairs_by_ruleset.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        meta = meta_by_ruleset[ruleset_key]
        ruleset_bundles[ruleset_key] = write_bundle(
            RULESET_OUT,
            ruleset_key,
            meta["rulesetNameKo"],
            meta["modeFamily"],
            meta["hasStandardPositions"],
            pairs,
            kind="ruleset",
        )

    mode_bundles = []
    for mode_key, pairs in sorted(pairs_by_mode.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        meta = meta_by_mode[mode_key]
        bundle = write_bundle(
            MODE_OUT,
            mode_key,
            meta["modeNameKo"],
            meta["modeFamily"],
            meta["hasStandardPositions"],
            pairs,
            kind="mode",
        )
        rule_keys = sorted({row["rulesetKey"] for _, row in pairs})
        bundle["rulesets"] = [
            ruleset_bundles[key]
            for key in rule_keys
            if key in ruleset_bundles
        ]
        mode_bundles.append(bundle)

    standard_pairs = []
    for mode_key, pairs in pairs_by_mode.items():
        if mode_key in STANDARD_RIFT_RULE_MODES:
            standard_pairs.extend(pairs)
    if standard_pairs:
        mode_bundles.insert(0, write_bundle(
            MODE_OUT,
            "standard_rift",
            "소환사의 협곡 · 일반 규칙",
            "summoners_rift",
            True,
            standard_pairs,
            kind="mode",
            synthetic=True,
        ))

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    index_payload = {
        "schemaVersion": 2,
        "generatedAt": now_ms,
        "defaultAnalysisMode": "standard_rift" if standard_pairs else None,
        "modes": mode_bundles,
        "rulesets": list(ruleset_bundles.values()),
        "notes": [
            "Use by-mode stats for champion, lane, matchup, summoner-spell, and item analysis; do not mix special modes into standard Rift conclusions.",
            "Use by-ruleset stats when the same named mode changed materially across patches (for example Swiftplay 2025 vs 2026 or Arena queue generations).",
            "When the user asks for ordinary lane/build analysis without naming a mode, prefer standard_rift.",
            "Swiftplay remains separate from standard_rift because its economy/objective rules materially differ.",
            "Arena/ARAM/URF have no standard lane position stats.",
        ],
    }
    write_json(MODE_INDEX, index_payload)

    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    mode_routes = {}
    for bundle in mode_bundles:
        route = {
            "modeNameKo": bundle["modeNameKo"],
            "games": bundle["games"],
            "synthetic": bundle["synthetic"],
            **bundle["files"],
        }
        if bundle.get("rulesets"):
            route["rulesets"] = {
                r["rulesetKey"]: {
                    "rulesetNameKo": r["rulesetNameKo"],
                    "games": r["games"],
                    **r["files"],
                }
                for r in bundle["rulesets"]
            }
        mode_routes[bundle["modeKey"]] = route

    rule_routes = {
        key: {
            "rulesetNameKo": bundle["rulesetNameKo"],
            "games": bundle["games"],
            **bundle["files"],
        }
        for key, bundle in ruleset_bundles.items()
    }

    write_json(SEARCH_MODE_ROUTES, {
        "schemaVersion": 2,
        "defaultAnalysisMode": index_payload["defaultAnalysisMode"],
        "routes": mode_routes,
        "rulesetRoutes": rule_routes,
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
        "rulesetAliases": {
            "구신속": "swiftplay_2025",
            "신속2025": "swiftplay_2025",
            "신신속": "swiftplay_2026",
            "신속2026": "swiftplay_2026",
            "구아레나": "arena_1700",
            "3인아레나": "arena_1750"
        },
        "notes": [
            "Resolve the requested mode here before opening mode-specific stats.",
            "If the user distinguishes an old/new ruleset, use rulesetRoutes instead of the combined mode route.",
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
            "Resolve mode through search/modes.json before opening champion, matchup, summoner-spell, or item statistics.",
            "If the named mode has multiple rulesets and the question is era-sensitive, use the matching ruleset route.",
            "For an unspecified ordinary Rift analysis, prefer standard_rift instead of all-mode aggregate stats.",
        ]
        search_index["modeRouteCount"] = len(mode_routes)
        search_index["rulesetRouteCount"] = len(rule_routes)
        search_index["defaultAnalysisMode"] = index_payload["defaultAnalysisMode"]
        write_json(SEARCH_INDEX, search_index)

    manifest = read_json(MANIFEST) if MANIFEST.exists() else {}
    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 13)
    manifest["modeStatsIndexPath"] = "stats/modes.json"
    manifest["modeStatsRoutePath"] = "search/modes.json"
    manifest["modeStatsModeCount"] = len(mode_bundles)
    manifest["modeStatsRulesetCount"] = len(rule_routes)
    manifest["defaultAnalysisMode"] = index_payload["defaultAnalysisMode"]
    write_json(MANIFEST, manifest)

    print(f"Mode stats ready: {sum(len(v) for v in pairs_by_mode.values())} matches")
    for bundle in mode_bundles:
        print(f"  {bundle['modeNameKo']}: {bundle['games']} games")
    print(f"Rulesets: {len(rule_routes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())