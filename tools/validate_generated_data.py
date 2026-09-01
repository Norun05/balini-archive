import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORT = DATA / "validation.json"


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add(items, code, message, **extra):
    row = {"code": code, "message": message}
    row.update(extra)
    items.append(row)


def main():
    errors = []
    warnings = []
    checks = {}

    required = [
        DATA / "manifest.json",
        DATA / "catalog.json",
        DATA / "stats" / "index.json",
        DATA / "stats" / "overview.json",
        DATA / "stats" / "teammates.json",
        DATA / "stats" / "item_timings.json",
        DATA / "search" / "index.json",
        DATA / "search" / "champions.json",
        DATA / "search" / "matchup_routes.json",
        DATA / "search" / "players.json",
    ]
    missing = [p.relative_to(ROOT).as_posix() for p in required if not p.exists()]
    checks["requiredFiles"] = {"ok": not missing, "missing": missing}
    if missing:
        add(errors, "missing-required-files", "Generated output is incomplete.", files=missing)

    manifest = read_json(DATA / "manifest.json") if (DATA / "manifest.json").exists() else {}
    catalog = read_json(DATA / "catalog.json") if (DATA / "catalog.json").exists() else []
    detail_files = sorted((DATA / "matches").glob("KR_*.json"))

    catalog_count = len(catalog) if isinstance(catalog, list) else 0
    manifest_count = int(manifest.get("matchCount") or 0)
    detail_count = len(detail_files)
    counts_ok = manifest_count == catalog_count == detail_count and detail_count > 0
    checks["matchCounts"] = {
        "ok": counts_ok,
        "manifest": manifest_count,
        "catalog": catalog_count,
        "detailFiles": detail_count,
    }
    if not counts_ok:
        add(errors, "match-count-mismatch", "Manifest, catalog, and detail match counts do not agree.", manifest=manifest_count, catalog=catalog_count, detailFiles=detail_count)

    stats_count = int(manifest.get("statsMatchCount") or 0)
    if stats_count and stats_count != detail_count:
        add(errors, "stats-count-mismatch", "Precomputed stats do not cover the same number of matches.", stats=stats_count, details=detail_count)
    checks["statsCount"] = {"ok": not stats_count or stats_count == detail_count, "stats": stats_count, "details": detail_count}

    latest = None
    if isinstance(catalog, list) and catalog:
        latest_row = max(catalog, key=lambda x: x.get("gameCreation") or 0)
        latest_path = DATA / (latest_row.get("detailPath") or f"matches/{latest_row.get('matchId')}.json")
        if latest_path.exists():
            latest = read_json(latest_path)

    if latest:
        participants = [latest.get("me"), *(latest.get("teammates") or []), *(latest.get("enemies") or [])]
        participants = [p for p in participants if isinstance(p, dict)]
        riot_id_count = sum(1 for p in participants if p.get("riotId"))
        spell_count = sum(1 for p in participants if p.get("summonerSpells"))
        timeline = latest.get("timeline") or {}
        events = timeline.get("events") or []
        types = {e.get("type") for e in events if isinstance(e, dict)}
        early = timeline.get("earlySnapshots") or []
        movement = timeline.get("movementSnapshots") or []
        item_economy = latest.get("itemEconomy") or timeline.get("itemEconomy")

        checks["latestMatch"] = {
            "matchId": latest.get("matchId"),
            "participantCount": len(participants),
            "riotIdCount": riot_id_count,
            "summonerSpellCount": spell_count,
            "eventTypes": sorted(x for x in types if x),
            "earlySnapshotMinutes": [x.get("minute") for x in early if isinstance(x, dict)],
            "movementSnapshotCount": len(movement),
            "hasItemEconomy": bool(item_economy),
        }
        if len(participants) < 10:
            add(warnings, "participant-count-low", "Latest match does not expose all 10 participants.", count=len(participants))
        if riot_id_count < len(participants):
            add(warnings, "riot-id-incomplete", "Some latest-match participants are missing Riot IDs.", withRiotId=riot_id_count, participants=len(participants))
        if spell_count < len(participants):
            add(warnings, "summoner-spells-incomplete", "Some latest-match participants are missing readable summoner spells.", withSpells=spell_count, participants=len(participants))
        for required_type in ("CHAMPION_KILL", "ITEM_PURCHASED", "SKILL_LEVEL_UP"):
            if required_type not in types:
                add(warnings, "event-type-missing", f"Latest match has no {required_type} event; this can be legitimate for unusual games, but inspect if unexpected.", eventType=required_type)
        expected_early = {2, 3, 4, 5, 6, 8, 10, 15, 20}
        actual_early = {x.get("minute") for x in early if isinstance(x, dict)}
        missing_early = sorted(expected_early - actual_early)
        if missing_early:
            add(warnings, "early-snapshots-incomplete", "Some requested early-game snapshots are unavailable in the latest match.", missingMinutes=missing_early)
        if not movement:
            add(warnings, "movement-missing", "Latest match has no movement snapshots.")
        if not item_economy:
            add(warnings, "item-economy-missing", "Latest match has no item economy summary.")
    else:
        add(errors, "latest-detail-unreadable", "Could not open the newest match detail JSON from catalog.json.")

    route_checks = []
    matchup_routes_path = DATA / "search" / "matchup_routes.json"
    if matchup_routes_path.exists():
        routes = read_json(matchup_routes_path)
        for champion_key, positions in list((routes or {}).items())[:10]:
            if not isinstance(positions, dict):
                continue
            for position_key, route in list(positions.items())[:3]:
                rel = route.get("path") if isinstance(route, dict) else None
                ok = bool(rel and (DATA / rel).exists())
                route_checks.append({"type": "matchup", "champion": champion_key, "position": position_key, "path": rel, "ok": ok})
                if not ok:
                    add(errors, "broken-matchup-route", "A matchup search route points to a missing file.", champion=champion_key, position=position_key, path=rel)
    players_path = DATA / "search" / "players.json"
    if players_path.exists():
        players = read_json(players_path)
        for alias, route in list((players or {}).items())[:20]:
            rel = route.get("path") if isinstance(route, dict) else None
            ok = bool(rel and (DATA / rel).exists())
            route_checks.append({"type": "player", "alias": alias, "path": rel, "ok": ok})
            if not ok:
                add(errors, "broken-player-route", "A player search route points to a missing file.", alias=alias, path=rel)
    checks["sampleRoutes"] = route_checks

    merge_index_candidates = [
        ROOT.parent / "balini-lol-archive-v999" / "data" / "meta" / "merge-index.json",
        DATA / "_merged_archive" / "data" / "meta" / "merge-index.json",
    ]
    merge_index = next((p for p in merge_index_candidates if p.exists()), None)
    if merge_index:
        merged = read_json(merge_index)
        checks["archiveMerge"] = {
            "ok": True,
            "archiveCount": merged.get("archiveCount"),
            "matchCount": merged.get("matchCount"),
            "timelineCount": merged.get("timelineCount"),
        }
    else:
        checks["archiveMerge"] = {"ok": False}
        add(warnings, "merge-index-missing", "Merged-archive report was not found; old-archive coverage cannot be verified.")

    report = {
        "schemaVersion": 1,
        "ok": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "notes": [
            "Errors fail update_site_data.bat; warnings are written for inspection but do not fail the build.",
            "Ability and summoner-spell cast timestamps are not inferred from Match-V5 when Riot does not provide them explicitly.",
        ],
    }
    write_json(REPORT, report)

    print(f"Validation errors: {len(errors)}")
    print(f"Validation warnings: {len(warnings)}")
    print(f"Report: {REPORT}")
    if errors:
        for row in errors:
            print(f"ERROR [{row['code']}] {row['message']}")
        return 2
    for row in warnings:
        print(f"WARN  [{row['code']}] {row['message']}")
    print("Generated data validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
