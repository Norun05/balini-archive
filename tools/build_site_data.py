import json
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RIOT_GAME_NAME = "발린이"
RIOT_TAG_LINE = "극악무도"
SNAPSHOT_MINUTES = (5, 10, 15, 20)
RECENT_LIMIT = 50
PAGE_SIZE = 50

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
OUTPUT_PROFILE = DATA_DIR / "profile.json"
OUTPUT_MANIFEST = DATA_DIR / "manifest.json"
OUTPUT_CATALOG = DATA_DIR / "catalog.json"
OUTPUT_CHAMPION_INDEX = DATA_DIR / "champions" / "index.json"
LEGACY_MATCHES = DATA_DIR / "matches.json"
MATCH_DETAILS_DIR = DATA_DIR / "matches"
CHAMPIONS_DIR = DATA_DIR / "champions"

POSITION_SLUGS = {
    "TOP": "top",
    "JUNGLE": "jungle",
    "MIDDLE": "middle",
    "BOTTOM": "bottom",
    "UTILITY": "utility",
}


def version_number(path: Path) -> int:
    m = re.search(r"-v(\d+)$", path.name, flags=re.I)
    return int(m.group(1)) if m else 0


def find_archive():
    candidates = []
    seen = set()
    bases = [REPO_ROOT, *REPO_ROOT.parents]
    for base in bases:
        try:
            dirs = list(base.glob("balini-lol-archive-v*")) + list(base.glob("balini-lol-archive"))
        except OSError:
            continue
        for archive in dirs:
            matches = archive / "data" / "raw" / "matches"
            if not matches.is_dir():
                continue
            key = str(matches.resolve())
            if key in seen:
                continue
            seen.add(key)
            count = sum(1 for _ in matches.glob("KR_*.json"))
            timelines = archive / "data" / "raw" / "timelines"
            candidates.append((count, version_number(archive), archive, matches, timelines))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0]


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value, *, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    value = (value or "unknown").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "unknown"


def compact_participant(p):
    if not p:
        return None
    challenges = p.get("challenges") or {}
    keep_challenges = {}
    for key in (
        "killParticipation",
        "laneMinionsFirst10Minutes",
        "maxCsAdvantageOnLaneOpponent",
        "maxLevelLeadLaneOpponent",
        "soloKills",
        "turretPlatesTaken",
        "teamDamagePercentage",
        "damagePerMinute",
        "goldPerMinute",
        "earlyLaningPhaseGoldExpAdvantage",
        "laningPhaseGoldExpAdvantage",
        "visionScorePerMinute",
    ):
        if key in challenges:
            keep_challenges[key] = challenges[key]

    perk_styles = []
    for style in (p.get("perks") or {}).get("styles", []):
        perk_styles.append({
            "style": style.get("style"),
            "description": style.get("description"),
            "perks": [x.get("perk") for x in style.get("selections", []) if x.get("perk") is not None],
        })

    return {
        "participantId": p.get("participantId"),
        "teamId": p.get("teamId"),
        "championName": p.get("championName"),
        "championId": p.get("championId"),
        "teamPosition": p.get("teamPosition"),
        "individualPosition": p.get("individualPosition"),
        "positionAssignedByMatchmaking": p.get("positionAssignedByMatchmaking"),
        "kills": p.get("kills", 0),
        "deaths": p.get("deaths", 0),
        "assists": p.get("assists", 0),
        "totalMinionsKilled": p.get("totalMinionsKilled", 0),
        "neutralMinionsKilled": p.get("neutralMinionsKilled", 0),
        "goldEarned": p.get("goldEarned", 0),
        "goldSpent": p.get("goldSpent", 0),
        "totalDamageDealtToChampions": p.get("totalDamageDealtToChampions", 0),
        "damageDealtToTurrets": p.get("damageDealtToTurrets", 0),
        "totalDamageTaken": p.get("totalDamageTaken", 0),
        "totalHeal": p.get("totalHeal", 0),
        "timeCCingOthers": p.get("timeCCingOthers", 0),
        "visionScore": p.get("visionScore", 0),
        "wardsPlaced": p.get("wardsPlaced", 0),
        "wardsKilled": p.get("wardsKilled", 0),
        "champLevel": p.get("champLevel"),
        "win": p.get("win"),
        "items": [p.get(f"item{i}", 0) for i in range(7)],
        "summoner1Id": p.get("summoner1Id"),
        "summoner2Id": p.get("summoner2Id"),
        "perkStyles": perk_styles,
        "challenges": keep_challenges,
    }


def find_me(participants, puuid):
    if puuid:
        for p in participants:
            if p.get("puuid") == puuid:
                return p
    for p in participants:
        if p.get("riotIdGameName") == RIOT_GAME_NAME and p.get("riotIdTagline") == RIOT_TAG_LINE:
            return p
    return None


def normalized_position(p):
    if not p:
        return ""
    for key in ("teamPosition", "individualPosition", "positionAssignedByMatchmaking"):
        value = p.get(key)
        if value and value != "NONE":
            return value
    return ""


def find_lane_opponent(participants, me):
    if not me:
        return None
    my_pos = normalized_position(me)
    enemies = [p for p in participants if p.get("teamId") != me.get("teamId")]
    if my_pos:
        for p in enemies:
            if normalized_position(p) == my_pos:
                return p
    return None


def frame_summary(frame):
    if not frame:
        return None
    damage = frame.get("damageStats") or {}
    position = frame.get("position") or {}
    lane_cs = frame.get("minionsKilled", 0) or 0
    jungle_cs = frame.get("jungleMinionsKilled", 0) or 0
    return {
        "gold": frame.get("totalGold", 0),
        "currentGold": frame.get("currentGold", 0),
        "cs": lane_cs + jungle_cs,
        "laneCs": lane_cs,
        "jungleCs": jungle_cs,
        "level": frame.get("level"),
        "xp": frame.get("xp"),
        "damageToChampions": damage.get("totalDamageDoneToChampions", 0),
        "position": {"x": position.get("x"), "y": position.get("y")} if position else None,
    }


def compact_event(e):
    compact = {"type": e.get("type"), "timestamp": e.get("timestamp")}
    for key in (
        "killerId", "victimId", "assistingParticipantIds", "participantId",
        "itemId", "beforeId", "afterId", "goldGain", "bounty",
        "buildingType", "towerType", "laneType", "teamId",
        "monsterType", "monsterSubType", "killType",
    ):
        if key in e:
            compact[key] = e[key]
    if e.get("position"):
        compact["position"] = e["position"]
    return compact


def timeline_summary(timeline, me_id, opponent_id):
    info = timeline.get("info") or {}
    frames = info.get("frames") or []
    if not frames or not me_id:
        return None

    snapshots = []
    for minute in SNAPSHOT_MINUTES:
        target = minute * 60 * 1000
        frame = min(frames, key=lambda f: abs((f.get("timestamp") or 0) - target))
        pframes = frame.get("participantFrames") or {}
        mef = frame_summary(pframes.get(str(me_id)))
        oppf = frame_summary(pframes.get(str(opponent_id))) if opponent_id else None
        snap = {
            "minute": minute,
            "timestamp": frame.get("timestamp"),
            "me": mef,
            "opponent": oppf,
        }
        if mef and oppf:
            snap["goldDiff"] = (mef.get("gold") or 0) - (oppf.get("gold") or 0)
            snap["csDiff"] = (mef.get("cs") or 0) - (oppf.get("cs") or 0)
            if mef.get("level") is not None and oppf.get("level") is not None:
                snap["levelDiff"] = mef["level"] - oppf["level"]
        snapshots.append(snap)

    events = []
    for frame in frames:
        for e in frame.get("events") or []:
            et = e.get("type")
            keep = False
            if et == "CHAMPION_KILL":
                keep = (
                    e.get("killerId") == me_id
                    or e.get("victimId") == me_id
                    or me_id in (e.get("assistingParticipantIds") or [])
                )
            elif et in ("ITEM_PURCHASED", "ITEM_SOLD", "ITEM_DESTROYED", "ITEM_UNDO"):
                keep = e.get("participantId") == me_id
            elif et in ("BUILDING_KILL", "ELITE_MONSTER_KILL"):
                keep = True

            if keep:
                events.append(compact_event(e))

    return {"snapshots": snapshots, "events": events}


def analysis_timeline(timeline, me_id):
    if not timeline:
        return None
    events = timeline.get("events") or []
    champion_events = [e for e in events if e.get("type") == "CHAMPION_KILL"]
    item_events = [e for e in events if e.get("type") in ("ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO")]
    objective_events = [e for e in events if e.get("type") in ("BUILDING_KILL", "ELITE_MONSTER_KILL")]

    first_kill = next((e.get("timestamp") for e in champion_events if e.get("killerId") == me_id), None)
    first_death = next((e.get("timestamp") for e in champion_events if e.get("victimId") == me_id), None)
    first_assist = next(
        (e.get("timestamp") for e in champion_events if me_id in (e.get("assistingParticipantIds") or [])),
        None,
    )

    return {
        "snapshots": timeline.get("snapshots") or [],
        "firstKillTimestamp": first_kill,
        "firstDeathTimestamp": first_death,
        "firstAssistTimestamp": first_assist,
        "championEvents": champion_events,
        "itemEvents": item_events,
        "objectiveEvents": objective_events,
    }


def catalog_row(detail):
    opp = detail.get("laneOpponent") or {}
    return {
        "matchId": detail.get("matchId"),
        "gameCreation": detail.get("gameCreation"),
        "gameDuration": detail.get("gameDuration"),
        "queueId": detail.get("queueId"),
        "gameMode": detail.get("gameMode"),
        "championName": detail.get("championName"),
        "position": detail.get("position"),
        "opponent": opp.get("championName"),
        "kills": detail.get("kills", 0),
        "deaths": detail.get("deaths", 0),
        "assists": detail.get("assists", 0),
        "cs": detail.get("cs", 0),
        "gold": detail.get("gold", 0),
        "damage": detail.get("damage", 0),
        "win": detail.get("win", False),
        "detailPath": f"matches/{detail.get('matchId')}.json",
    }


def analysis_row(detail):
    me = detail.get("me") or {}
    opp = detail.get("laneOpponent") or {}
    return {
        **catalog_row(detail),
        "items": me.get("items") or [],
        "meChallenges": me.get("challenges") or {},
        "laneOpponent": {
            "championName": opp.get("championName"),
            "kills": opp.get("kills"),
            "deaths": opp.get("deaths"),
            "assists": opp.get("assists"),
            "cs": (opp.get("totalMinionsKilled", 0) or 0) + (opp.get("neutralMinionsKilled", 0) or 0),
            "gold": opp.get("goldEarned"),
            "damage": opp.get("totalDamageDealtToChampions"),
            "items": opp.get("items") or [],
            "challenges": opp.get("challenges") or {},
        } if opp else None,
        "timeline": analysis_timeline(detail.get("timeline"), me.get("participantId")),
    }


def reset_generated_dirs():
    for directory in (MATCH_DETAILS_DIR, CHAMPIONS_DIR):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)


def write_pages(base_dir: Path, rows):
    rows = sorted(rows, key=lambda x: x.get("gameCreation") or 0, reverse=True)
    recent = rows[:RECENT_LIMIT]
    write_json(base_dir / "recent.json", {
        "count": len(rows),
        "recentCount": len(recent),
        "pageSize": PAGE_SIZE,
        "matches": recent,
    })

    pages = []
    for page_num, start in enumerate(range(0, len(rows), PAGE_SIZE), 1):
        page_rows = rows[start:start + PAGE_SIZE]
        name = f"page-{page_num:03d}.json"
        write_json(base_dir / name, {
            "count": len(rows),
            "page": page_num,
            "pageSize": PAGE_SIZE,
            "matches": page_rows,
        })
        pages.append(name)
    return pages


def main():
    found = find_archive()
    if not found:
        print("Could not find balini-lol-archive-v*/data/raw/matches near this repository.")
        print("Expected layout: ...\\lol\\balini-lol-archive-v4 and ...\\lol\\balini-archive\\balini-archive")
        return 2

    file_count, version, archive, matches_dir, timelines_dir = found
    print(f"Archive found: {archive}")
    print(f"Match JSON files: {file_count}")

    puuid = None
    account_file = archive / "data" / "meta" / "account.json"
    if account_file.exists():
        try:
            puuid = read_json(account_file).get("puuid")
        except Exception:
            pass

    reset_generated_dirs()
    if LEGACY_MATCHES.exists():
        LEGACY_MATCHES.unlink()

    catalog = []
    analysis_rows = []
    broken = []
    missing_me = []
    timeline_count = 0

    files = sorted(matches_dir.glob("KR_*.json"))
    total = len(files)
    for idx, path in enumerate(files, 1):
        try:
            match = read_json(path)
        except Exception as exc:
            broken.append({"file": path.name, "error": type(exc).__name__})
            continue

        info = match.get("info") or {}
        participants = info.get("participants") or []
        me = find_me(participants, puuid)
        if not me:
            missing_me.append(path.name)
            continue

        opponent = find_lane_opponent(participants, me)
        teammates = [p for p in participants if p.get("teamId") == me.get("teamId") and p is not me]
        enemies = [p for p in participants if p.get("teamId") != me.get("teamId")]

        detail = {
            "matchId": (match.get("metadata") or {}).get("matchId") or path.stem,
            "gameCreation": info.get("gameCreation"),
            "gameStartTimestamp": info.get("gameStartTimestamp"),
            "gameEndTimestamp": info.get("gameEndTimestamp"),
            "gameDuration": info.get("gameDuration"),
            "gameVersion": info.get("gameVersion"),
            "queueId": info.get("queueId"),
            "gameMode": info.get("gameMode"),
            "mapId": info.get("mapId"),
            "championName": me.get("championName"),
            "position": normalized_position(me),
            "kills": me.get("kills", 0),
            "deaths": me.get("deaths", 0),
            "assists": me.get("assists", 0),
            "cs": (me.get("totalMinionsKilled", 0) or 0) + (me.get("neutralMinionsKilled", 0) or 0),
            "gold": me.get("goldEarned", 0),
            "damage": me.get("totalDamageDealtToChampions", 0),
            "win": bool(me.get("win")),
            "me": compact_participant(me),
            "laneOpponent": compact_participant(opponent),
            "teammates": [compact_participant(p) for p in teammates],
            "enemies": [compact_participant(p) for p in enemies],
        }

        timeline_file = timelines_dir / f"{path.stem}.json"
        if timeline_file.exists():
            try:
                timeline = read_json(timeline_file)
                detail["timeline"] = timeline_summary(
                    timeline,
                    me.get("participantId"),
                    opponent.get("participantId") if opponent else None,
                )
                if detail["timeline"]:
                    timeline_count += 1
            except Exception:
                detail["timeline"] = None
        else:
            detail["timeline"] = None

        write_json(MATCH_DETAILS_DIR / f"{detail['matchId']}.json", detail)
        catalog.append(catalog_row(detail))
        analysis_rows.append(analysis_row(detail))

        if idx % 50 == 0 or idx == total:
            print(f"Processed {idx}/{total}")

    catalog.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)
    analysis_rows.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)
    write_json(OUTPUT_CATALOG, catalog)

    groups = defaultdict(list)
    for row in analysis_rows:
        champ_slug = slugify(row.get("championName"))
        pos_slug = POSITION_SLUGS.get(row.get("position"), slugify(row.get("position") or "unknown"))
        groups[(champ_slug, "all")].append(row)
        groups[(champ_slug, pos_slug)].append(row)

    champion_index = {}
    for (champ_slug, pos_slug), rows in sorted(groups.items()):
        base = CHAMPIONS_DIR / champ_slug / pos_slug
        pages = write_pages(base, rows)
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

    write_json(OUTPUT_CHAMPION_INDEX, {
        "generatedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
        "champions": sorted(champion_index.values(), key=lambda x: (-x["count"], x["championName"])),
    })

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    profile = {
        "riotId": f"{RIOT_GAME_NAME}#{RIOT_TAG_LINE}",
        "region": "KR",
        "source": "Riot Match-V5 local archive",
        "updatedAt": now_ms,
        "archivedMatches": len(catalog),
        "timelineSummaries": timeline_count,
        "note": "Generated locally from stored Riot Match-V5 JSON. Raw files are not published.",
    }
    write_json(OUTPUT_PROFILE, profile)

    manifest = {
        "schemaVersion": 2,
        "generatedAt": now_ms,
        "matchCount": len(catalog),
        "timelineSummaryCount": timeline_count,
        "brokenJsonCount": len(broken),
        "missingUserCount": len(missing_me),
        "catalogPath": "catalog.json",
        "championIndexPath": "champions/index.json",
        "matchDetailPattern": "matches/{matchId}.json",
        "recentLimit": RECENT_LIMIT,
        "pageSize": PAGE_SIZE,
        "brokenFiles": broken[:50],
        "missingUserFiles": missing_me[:50],
    }
    write_json(OUTPUT_MANIFEST, manifest)

    catalog_mb = OUTPUT_CATALOG.stat().st_size / (1024 * 1024)
    detail_count = sum(1 for _ in MATCH_DETAILS_DIR.glob("KR_*.json"))
    champion_file_count = sum(1 for p in CHAMPIONS_DIR.rglob("*.json") if p != OUTPUT_CHAMPION_INDEX)

    print()
    print(f"DONE: {len(catalog)} matches indexed")
    print(f"Timeline summaries: {timeline_count}")
    print(f"Broken JSON skipped: {len(broken)}")
    print(f"Catalog size: {catalog_mb:.2f} MB")
    print(f"Match detail files: {detail_count}")
    print(f"Champion analysis files: {champion_file_count}")
    print("Legacy data/matches.json removed.")
    print("Open GitHub Desktop, commit all generated data changes, then Push origin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
