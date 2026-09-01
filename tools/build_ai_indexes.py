import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCE = DATA / "matches.json"
OUT = DATA / "ai"
SUMMARY_OUT = OUT / "summary"

IMPORTANT_CHALLENGES = (
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
)


def slug(text):
    text = (text or "unknown").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unknown"


def picked_challenges(p):
    c = (p or {}).get("challenges") or {}
    return {k: c[k] for k in IMPORTANT_CHALLENGES if k in c}


def simple_player(p):
    if not p:
        return None
    return {
        "participantId": p.get("participantId"),
        "championName": p.get("championName"),
        "position": p.get("teamPosition") or p.get("individualPosition") or p.get("positionAssignedByMatchmaking") or "",
        "kills": p.get("kills", 0),
        "deaths": p.get("deaths", 0),
        "assists": p.get("assists", 0),
        "cs": (p.get("totalMinionsKilled", 0) or 0) + (p.get("neutralMinionsKilled", 0) or 0),
        "gold": p.get("goldEarned", 0),
        "damage": p.get("totalDamageDealtToChampions", 0),
        "turretDamage": p.get("damageDealtToTurrets", 0),
        "damageTaken": p.get("totalDamageTaken", 0),
        "heal": p.get("totalHeal", 0),
        "visionScore": p.get("visionScore", 0),
        "level": p.get("champLevel"),
        "win": p.get("win"),
        "challenges": picked_challenges(p),
    }


def compact_event(e, participant_map, me_id):
    out = {"type": e.get("type"), "timestamp": e.get("timestamp")}
    for key in (
        "killerId", "victimId", "assistingParticipantIds", "participantId", "itemId",
        "beforeId", "afterId", "goldGain", "bounty", "buildingType", "towerType",
        "laneType", "teamId", "monsterType", "monsterSubType", "position"
    ):
        if key in e:
            out[key] = e[key]

    if e.get("type") == "CHAMPION_KILL":
        killer = participant_map.get(e.get("killerId"))
        victim = participant_map.get(e.get("victimId"))
        out["killerChampion"] = killer.get("championName") if killer else None
        out["victimChampion"] = victim.get("championName") if victim else None
        out["isMyKill"] = e.get("killerId") == me_id
        out["isMyDeath"] = e.get("victimId") == me_id
        out["isMyAssist"] = me_id in (e.get("assistingParticipantIds") or [])
    return out


def make_ai_row(row):
    me = row.get("me") or {}
    opponent = row.get("laneOpponent")
    players = [me] + (row.get("teammates") or []) + (row.get("enemies") or [])
    participant_map = {p.get("participantId"): p for p in players if p and p.get("participantId") is not None}
    me_id = me.get("participantId")
    timeline = row.get("timeline") or {}
    events = [compact_event(e, participant_map, me_id) for e in (timeline.get("events") or [])]

    my_deaths = [e for e in events if e.get("type") == "CHAMPION_KILL" and e.get("isMyDeath")]
    my_kills = [e for e in events if e.get("type") == "CHAMPION_KILL" and e.get("isMyKill")]
    my_assists = [e for e in events if e.get("type") == "CHAMPION_KILL" and e.get("isMyAssist")]
    item_events = [e for e in events if e.get("type", "").startswith("ITEM_")]
    objectives = [e for e in events if e.get("type") in ("BUILDING_KILL", "ELITE_MONSTER_KILL")]

    return {
        "matchId": row.get("matchId"),
        "gameCreation": row.get("gameCreation"),
        "gameStartTimestamp": row.get("gameStartTimestamp"),
        "gameDuration": row.get("gameDuration"),
        "gameVersion": row.get("gameVersion"),
        "queueId": row.get("queueId"),
        "gameMode": row.get("gameMode"),
        "championName": row.get("championName"),
        "position": row.get("position"),
        "kills": row.get("kills", 0),
        "deaths": row.get("deaths", 0),
        "assists": row.get("assists", 0),
        "cs": row.get("cs", 0),
        "gold": row.get("gold", 0),
        "damage": row.get("damage", 0),
        "win": row.get("win"),
        "me": simple_player(me),
        "laneOpponent": simple_player(opponent),
        "teammates": [simple_player(p) for p in (row.get("teammates") or [])],
        "enemies": [simple_player(p) for p in (row.get("enemies") or [])],
        "snapshots": timeline.get("snapshots") or [],
        "firstDeath": my_deaths[0] if my_deaths else None,
        "deathsTimeline": my_deaths,
        "killsTimeline": my_kills,
        "assistsTimeline": my_assists,
        "itemEvents": item_events,
        "objectiveEvents": objectives,
    }


def tiny_player(p):
    if not p:
        return None
    return {
        "championName": p.get("championName"),
        "position": p.get("position"),
        "kills": p.get("kills", 0),
        "deaths": p.get("deaths", 0),
        "assists": p.get("assists", 0),
        "cs": p.get("cs", 0),
        "gold": p.get("gold", 0),
        "damage": p.get("damage", 0),
        "turretDamage": p.get("turretDamage", 0),
        "level": p.get("level"),
        "challenges": p.get("challenges") or {},
    }


def analysis_event(e):
    if not e:
        return None
    keep = {
        "type": e.get("type"),
        "timestamp": e.get("timestamp"),
    }
    for key in (
        "killerChampion", "victimChampion", "isMyKill", "isMyDeath", "isMyAssist",
        "itemId", "bounty", "buildingType", "towerType", "laneType", "teamId",
        "monsterType", "monsterSubType", "position"
    ):
        if key in e:
            keep[key] = e[key]
    return keep


def analysis_row(row):
    return {
        "matchId": row.get("matchId"),
        "gameCreation": row.get("gameCreation"),
        "gameStartTimestamp": row.get("gameStartTimestamp"),
        "gameDuration": row.get("gameDuration"),
        "gameVersion": row.get("gameVersion"),
        "queueId": row.get("queueId"),
        "gameMode": row.get("gameMode"),
        "championName": row.get("championName"),
        "position": row.get("position"),
        "kills": row.get("kills", 0),
        "deaths": row.get("deaths", 0),
        "assists": row.get("assists", 0),
        "cs": row.get("cs", 0),
        "gold": row.get("gold", 0),
        "damage": row.get("damage", 0),
        "win": row.get("win"),
        "me": tiny_player(row.get("me")),
        "laneOpponent": tiny_player(row.get("laneOpponent")),
        "teamComp": [tiny_player(p) for p in (row.get("teammates") or [])],
        "enemyComp": [tiny_player(p) for p in (row.get("enemies") or [])],
        "snapshots": row.get("snapshots") or [],
        "firstDeath": analysis_event(row.get("firstDeath")),
        "deathsTimeline": [analysis_event(e) for e in (row.get("deathsTimeline") or [])],
        "killsTimeline": [analysis_event(e) for e in (row.get("killsTimeline") or [])],
        "assistTimestamps": [e.get("timestamp") for e in (row.get("assistsTimeline") or [])],
        "itemPurchases": [analysis_event(e) for e in (row.get("itemEvents") or []) if e.get("type") == "ITEM_PURCHASED"],
        "objectiveEvents": [analysis_event(e) for e in (row.get("objectiveEvents") or [])],
    }


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if not SOURCE.exists():
        raise SystemExit("data/matches.json not found. Run build_site_data.py first.")

    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    ai_rows = [make_ai_row(r) for r in rows]
    ai_rows.sort(key=lambda r: r.get("gameCreation") or 0, reverse=True)

    groups = defaultdict(list)
    for row in ai_rows:
        key = (slug(row.get("championName")), slug(row.get("position")))
        groups[key].append(row)

    generated = []
    summary_files = []
    for (champ, pos), group in sorted(groups.items()):
        name = f"{champ}_{pos}.json"
        write_json(OUT / name, group)
        generated.append({"file": name, "count": len(group), "champion": champ, "position": pos})

        summary_name = f"{champ}_{pos}_recent20.json"
        write_json(SUMMARY_OUT / summary_name, [analysis_row(r) for r in group[:20]])
        summary_files.append({"file": f"summary/{summary_name}", "count": min(20, len(group)), "champion": champ, "position": pos})

    write_json(OUT / "recent.json", ai_rows[:100])
    write_json(OUT / "index.json", {
        "generatedAt": int(datetime.now(timezone.utc).timestamp() * 1000),
        "matchCount": len(ai_rows),
        "files": generated,
        "summaryFiles": summary_files,
        "recentFile": "recent.json",
        "note": "AI-friendly indexes derived from data/matches.json. Raw Riot timelines are not published."
    })

    print(f"AI indexes ready: {len(generated)} champion/position files")
    print(f"Recent-20 analysis files: {len(summary_files)}")
    print(f"Kennen TOP: {len(groups.get(('kennen', 'top'), []))} matches")
    print(f"Veigar MIDDLE: {len(groups.get(('veigar', 'middle'), []))} matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
