import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import build_site_data as base
import incremental_state as inc

STAGE = "build_site_data"


def build_detail(match_path: Path, timeline_path: Path, puuid):
    match = base.read_json(match_path)
    info = match.get("info") or {}
    participants = info.get("participants") or []
    me = base.find_me(participants, puuid)
    if not me:
        return None

    opponent = base.find_lane_opponent(participants, me)
    teammates = [p for p in participants if p.get("teamId") == me.get("teamId") and p is not me]
    enemies = [p for p in participants if p.get("teamId") != me.get("teamId")]

    detail = {
        "matchId": (match.get("metadata") or {}).get("matchId") or match_path.stem,
        "gameCreation": info.get("gameCreation"),
        "gameStartTimestamp": info.get("gameStartTimestamp"),
        "gameEndTimestamp": info.get("gameEndTimestamp"),
        "gameDuration": info.get("gameDuration"),
        "gameVersion": info.get("gameVersion"),
        "queueId": info.get("queueId"),
        "gameMode": info.get("gameMode"),
        "mapId": info.get("mapId"),
        "championName": me.get("championName"),
        "position": base.normalized_position(me),
        "kills": me.get("kills", 0),
        "deaths": me.get("deaths", 0),
        "assists": me.get("assists", 0),
        "cs": (me.get("totalMinionsKilled", 0) or 0) + (me.get("neutralMinionsKilled", 0) or 0),
        "gold": me.get("goldEarned", 0),
        "damage": me.get("totalDamageDealtToChampions", 0),
        "win": bool(me.get("win")),
        "me": base.compact_participant(me),
        "laneOpponent": base.compact_participant(opponent),
        "teammates": [base.compact_participant(p) for p in teammates],
        "enemies": [base.compact_participant(p) for p in enemies],
    }

    if timeline_path.exists():
        try:
            timeline = base.read_json(timeline_path)
            detail["timeline"] = base.timeline_summary(
                timeline,
                me.get("participantId"),
                opponent.get("participantId") if opponent else None,
            )
        except Exception:
            detail["timeline"] = None
    else:
        detail["timeline"] = None
    return detail


def rebuild_indexes(details):
    catalog = [base.catalog_row(d) for d in details]
    analysis_rows = [base.analysis_row(d) for d in details]
    catalog.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)
    analysis_rows.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)
    base.write_json(base.OUTPUT_CATALOG, catalog)

    if base.CHAMPIONS_DIR.exists():
        shutil.rmtree(base.CHAMPIONS_DIR)
    base.CHAMPIONS_DIR.mkdir(parents=True, exist_ok=True)

    groups = defaultdict(list)
    for row in analysis_rows:
        champ_slug = base.slugify(row.get("championName"))
        pos_slug = base.POSITION_SLUGS.get(row.get("position"), base.slugify(row.get("position") or "unknown"))
        groups[(champ_slug, "all")].append(row)
        groups[(champ_slug, pos_slug)].append(row)

    champion_index = {}
    for (champ_slug, pos_slug), rows in sorted(groups.items()):
        out_dir = base.CHAMPIONS_DIR / champ_slug / pos_slug
        pages = base.write_pages(out_dir, rows)
        champ_name = rows[0].get("championName") if rows else champ_slug
        entry = champion_index.setdefault(champ_slug, {
            "championName": champ_name,
            "slug": champ_slug,
            "count": 0,
            "positions": {},
        })
        if pos_slug == "all":
            entry["count"] = len(rows)
            entry["all"] = {
                "recent": f"champions/{champ_slug}/all/recent.json",
                "pages": [f"champions/{champ_slug}/all/{p}" for p in pages],
            }
        else:
            entry["positions"][pos_slug] = {
                "count": len(rows),
                "recent": f"champions/{champ_slug}/{pos_slug}/recent.json",
                "pages": [f"champions/{champ_slug}/{pos_slug}/{p}" for p in pages],
            }

    base.write_json(base.OUTPUT_CHAMPION_INDEX, {
        "generatedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
        "champions": sorted(champion_index.values(), key=lambda x: (-x["count"], x["championName"])),
    })
    return catalog


def main():
    found = base.find_archive()
    if not found:
        print("Could not find the local Riot archive.")
        return 2

    file_count, _, archive, matches_dir, timelines_dir = found
    print(f"Archive found: {archive}")
    print(f"Match JSON files: {file_count}")
    print("Incremental mode: unchanged match details are reused.")

    puuid = None
    account_file = archive / "data" / "meta" / "account.json"
    if account_file.exists():
        try:
            puuid = base.read_json(account_file).get("puuid")
        except Exception:
            pass

    base.MATCH_DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    if base.LEGACY_MATCHES.exists():
        base.LEGACY_MATCHES.unlink()

    old_signatures = inc.cached_signatures(STAGE)
    new_signatures = {}
    source_names = set()
    processed = 0
    skipped = 0
    broken = []
    missing_me = []

    files = sorted(matches_dir.glob("KR_*.json"))
    total = len(files)
    for idx, match_path in enumerate(files, 1):
        source_names.add(match_path.name)
        timeline_path = timelines_dir / match_path.name
        sig = inc.source_signature(match_path, timeline_path)
        new_signatures[match_path.stem] = sig
        output_path = base.MATCH_DETAILS_DIR / match_path.name

        can_skip = old_signatures.get(match_path.stem) == sig and output_path.exists()
        if not can_skip and match_path.stem not in old_signatures and output_path.exists():
            can_skip = inc.output_is_newer(output_path, match_path, timeline_path)

        if can_skip:
            skipped += 1
        else:
            try:
                detail = build_detail(match_path, timeline_path, puuid)
            except Exception as exc:
                broken.append({"file": match_path.name, "error": type(exc).__name__})
                continue
            if not detail:
                missing_me.append(match_path.name)
                continue
            base.write_json(output_path, detail)
            processed += 1

        if idx % 100 == 0 or idx == total:
            print(f"Base details checked {idx}/{total} (processed {processed}, skipped {skipped})")

    removed = 0
    for output_path in base.MATCH_DETAILS_DIR.glob("KR_*.json"):
        if output_path.name not in source_names:
            output_path.unlink(missing_ok=True)
            removed += 1

    details = []
    unreadable_details = []
    for path in sorted(base.MATCH_DETAILS_DIR.glob("KR_*.json")):
        try:
            details.append(base.read_json(path))
        except Exception as exc:
            unreadable_details.append({"file": path.name, "error": type(exc).__name__})

    catalog = rebuild_indexes(details)
    timeline_count = sum(1 for d in details if isinstance(d.get("timeline"), dict))
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    base.write_json(base.OUTPUT_PROFILE, {
        "riotId": f"{base.RIOT_GAME_NAME}#{base.RIOT_TAG_LINE}",
        "region": "KR",
        "source": "Riot Match-V5 local archive",
        "updatedAt": now_ms,
        "archivedMatches": len(catalog),
        "timelineSummaries": timeline_count,
        "note": "Generated incrementally from stored Riot Match-V5 JSON. Raw files are not published.",
    })

    manifest = {}
    if base.OUTPUT_MANIFEST.exists():
        try:
            manifest = base.read_json(base.OUTPUT_MANIFEST)
        except Exception:
            manifest = {}
    manifest.update({
        "schemaVersion": max(int(manifest.get("schemaVersion") or 0), 2),
        "generatedAt": now_ms,
        "matchCount": len(catalog),
        "timelineSummaryCount": timeline_count,
        "brokenJsonCount": len(broken) + len(unreadable_details),
        "missingUserCount": len(missing_me),
        "catalogPath": "catalog.json",
        "championIndexPath": "champions/index.json",
        "matchDetailPattern": "matches/{matchId}.json",
        "recentLimit": base.RECENT_LIMIT,
        "pageSize": base.PAGE_SIZE,
        "incrementalBuild": True,
        "incrementalBaseProcessed": processed,
        "incrementalBaseSkipped": skipped,
        "incrementalBaseRemoved": removed,
        "brokenFiles": (broken + unreadable_details)[:50],
        "missingUserFiles": missing_me[:50],
    })
    base.write_json(base.OUTPUT_MANIFEST, manifest)
    inc.save_stage(STAGE, new_signatures)

    print(f"Base detail processed: {processed}")
    print(f"Base detail skipped: {skipped}")
    print(f"Stale details removed: {removed}")
    print(f"Catalog matches: {len(catalog)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
