import json
from pathlib import Path

import build_site_data as base

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MATCH_DETAILS_DIR = DATA / "matches"
MANIFEST_PATH = DATA / "manifest.json"

ITEM_EVENT_TYPES = {"ITEM_PURCHASED", "ITEM_SOLD", "ITEM_DESTROYED", "ITEM_UNDO"}
KEEP_EVENT_TYPES = {
    "CHAMPION_KILL",
    "ITEM_PURCHASED",
    "ITEM_SOLD",
    "ITEM_DESTROYED",
    "ITEM_UNDO",
    "SKILL_LEVEL_UP",
    "BUILDING_KILL",
    "ELITE_MONSTER_KILL",
}

SUMMONER_SPELL_NAMES_KO = {
    1: "정화",
    3: "탈진",
    4: "점멸",
    6: "유체화",
    7: "회복",
    11: "강타",
    12: "순간이동",
    13: "총명",
    14: "점화",
    21: "방어막",
    32: "표식",
}


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def riot_id_text(player: dict):
    game_name = player.get("riotIdGameName")
    tag_line = player.get("riotIdTagline")
    if game_name and tag_line:
        return f"{game_name}#{tag_line}"
    return game_name or player.get("summonerName")


def spell_payload(spell_id):
    if spell_id is None:
        return None
    return {
        "id": spell_id,
        "nameKo": SUMMONER_SPELL_NAMES_KO.get(spell_id),
    }


def enrich_compact_participant(compact: dict, raw: dict):
    if not isinstance(compact, dict) or not isinstance(raw, dict):
        return

    compact["riotIdGameName"] = raw.get("riotIdGameName")
    compact["riotIdTagline"] = raw.get("riotIdTagline")
    compact["riotId"] = riot_id_text(raw)
    compact["summonerName"] = raw.get("summonerName")

    spell1 = raw.get("summoner1Id")
    spell2 = raw.get("summoner2Id")
    compact["summoner1Id"] = spell1
    compact["summoner2Id"] = spell2
    compact["summonerSpells"] = [
        payload
        for payload in (spell_payload(spell1), spell_payload(spell2))
        if payload is not None
    ]


def compact_event(event: dict, participant_map: dict):
    out = {
        "type": event.get("type"),
        "timestamp": event.get("timestamp"),
    }

    for key in (
        "killerId",
        "victimId",
        "assistingParticipantIds",
        "participantId",
        "itemId",
        "beforeId",
        "afterId",
        "goldGain",
        "bounty",
        "shutdownBounty",
        "buildingType",
        "towerType",
        "laneType",
        "teamId",
        "monsterType",
        "monsterSubType",
        "killType",
        "skillSlot",
        "levelUpType",
    ):
        if key in event:
            out[key] = event[key]

    if event.get("position"):
        out["position"] = event["position"]

    event_type = event.get("type")
    if event_type == "CHAMPION_KILL":
        killer = participant_map.get(event.get("killerId"))
        victim = participant_map.get(event.get("victimId"))
        assists = [
            participant_map.get(pid)
            for pid in (event.get("assistingParticipantIds") or [])
        ]
        out["killerChampion"] = killer.get("championName") if killer else None
        out["killerRiotId"] = riot_id_text(killer) if killer else None
        out["victimChampion"] = victim.get("championName") if victim else None
        out["victimRiotId"] = riot_id_text(victim) if victim else None
        out["assistingChampions"] = [p.get("championName") for p in assists if p]
        out["assistingRiotIds"] = [riot_id_text(p) for p in assists if p]
    elif event_type in ITEM_EVENT_TYPES or event_type == "SKILL_LEVEL_UP":
        actor = participant_map.get(event.get("participantId"))
        if actor:
            out["championName"] = actor.get("championName")
            out["riotId"] = riot_id_text(actor)

    return out


def update_manifest(match_count: int, event_count: int, kill_count: int, item_count: int, level_count: int):
    if not MANIFEST_PATH.exists():
        return
    try:
        manifest = read_json(MANIFEST_PATH)
    except Exception:
        return

    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 5)
    manifest["participantRiotIdField"] = "me/teammates/enemies/laneOpponent.riotId"
    manifest["participantSummonerSpellField"] = "me/teammates/enemies/laneOpponent.summonerSpells"
    manifest["fullTimelineEventField"] = "timeline.events"
    manifest["fullTimelineEventTypes"] = sorted(KEEP_EVENT_TYPES)
    manifest["fullTimelineMatchCount"] = match_count
    manifest["fullTimelineEventCount"] = event_count
    manifest["fullChampionKillEventCount"] = kill_count
    manifest["fullItemEventCount"] = item_count
    manifest["skillLevelUpEventCount"] = level_count
    write_json(MANIFEST_PATH, manifest)


def main():
    found = base.find_archive()
    if not found:
        print("Could not find the local Riot archive.")
        return 2

    _, _, archive, matches_dir, timelines_dir = found
    print(f"Archive found: {archive}")
    print("Restoring participant Riot IDs, summoner spell names, and full analysis events...")

    updated_matches = 0
    total_events = 0
    kill_events = 0
    item_events = 0
    level_events = 0
    missing_raw = 0
    missing_timeline = 0

    for detail_path in sorted(MATCH_DETAILS_DIR.glob("KR_*.json")):
        raw_match_path = matches_dir / detail_path.name
        if not raw_match_path.exists():
            missing_raw += 1
            continue

        try:
            detail = read_json(detail_path)
            raw_match = read_json(raw_match_path)
        except Exception:
            missing_raw += 1
            continue

        participants = ((raw_match.get("info") or {}).get("participants") or [])
        participant_map = {
            p.get("participantId"): p
            for p in participants
            if p.get("participantId") is not None
        }

        compact_players = []
        if detail.get("me"):
            compact_players.append(detail["me"])
        if detail.get("laneOpponent"):
            compact_players.append(detail["laneOpponent"])
        compact_players.extend(detail.get("teammates") or [])
        compact_players.extend(detail.get("enemies") or [])

        for compact in compact_players:
            raw = participant_map.get(compact.get("participantId"))
            if raw:
                enrich_compact_participant(compact, raw)

        timeline_path = timelines_dir / detail_path.name
        if timeline_path.exists():
            try:
                raw_timeline = read_json(timeline_path)
                frames = ((raw_timeline.get("info") or {}).get("frames") or [])
                events = []
                for frame in frames:
                    for event in frame.get("events") or []:
                        event_type = event.get("type")
                        if event_type not in KEEP_EVENT_TYPES:
                            continue
                        events.append(compact_event(event, participant_map))
                        total_events += 1
                        if event_type == "CHAMPION_KILL":
                            kill_events += 1
                        elif event_type in ITEM_EVENT_TYPES:
                            item_events += 1
                        elif event_type == "SKILL_LEVEL_UP":
                            level_events += 1

                timeline = detail.get("timeline")
                if not isinstance(timeline, dict):
                    timeline = {}
                    detail["timeline"] = timeline
                timeline["events"] = events
                timeline["eventScope"] = "all participants"
                timeline["eventTypes"] = sorted(KEEP_EVENT_TYPES)
            except Exception:
                missing_timeline += 1
        else:
            missing_timeline += 1

        write_json(detail_path, detail)
        updated_matches += 1

    update_manifest(updated_matches, total_events, kill_events, item_events, level_events)

    print(f"Updated match details: {updated_matches}")
    print(f"Full timeline events: {total_events}")
    print(f"Champion kills: {kill_events}")
    print(f"Item events: {item_events}")
    print(f"Skill level-ups: {level_events}")
    print(f"Missing raw matches: {missing_raw}")
    print(f"Missing/unreadable timelines: {missing_timeline}")
    print("Done. Run add_item_names_ko.py after this step so all participants' item events receive Korean names.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
