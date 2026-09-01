import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data" / "ai" / "summary"
OUT = ROOT / "data" / "ai" / "compact"


def snapshot(s):
    me = s.get("me") or {}
    opp = s.get("opponent") or {}
    return {
        "minute": s.get("minute"),
        "goldDiff": s.get("goldDiff"),
        "csDiff": s.get("csDiff"),
        "levelDiff": s.get("levelDiff"),
        "myGold": me.get("gold"),
        "oppGold": opp.get("gold"),
        "myCs": me.get("cs"),
        "oppCs": opp.get("cs"),
        "myLevel": me.get("level"),
        "oppLevel": opp.get("level"),
        "myDamageToChampions": me.get("damageToChampions"),
        "oppDamageToChampions": opp.get("damageToChampions"),
    }


def event(e, other_key):
    if not e:
        return None
    return {
        "timestamp": e.get("timestamp"),
        other_key: e.get(other_key),
        "bounty": e.get("bounty"),
    }


def top_threat(players):
    if not players:
        return None
    p = max(players, key=lambda x: (x or {}).get("gold", 0) or 0)
    if not p:
        return None
    return {
        "championName": p.get("championName"),
        "kills": p.get("kills", 0),
        "deaths": p.get("deaths", 0),
        "assists": p.get("assists", 0),
        "gold": p.get("gold", 0),
        "damage": p.get("damage", 0),
    }


def compact(r):
    me = r.get("me") or {}
    opp = r.get("laneOpponent") or {}
    allies = r.get("teamComp") or []
    enemies = r.get("enemyComp") or []
    my_team = [me] + allies
    team_kills = sum((p or {}).get("kills", 0) or 0 for p in my_team)
    enemy_kills = sum((p or {}).get("kills", 0) or 0 for p in enemies)
    deaths = [event(e, "killerChampion") for e in (r.get("deathsTimeline") or [])]
    kills = [event(e, "victimChampion") for e in (r.get("killsTimeline") or [])]
    assists = [t for t in (r.get("assistTimestamps") or []) if t is not None]

    def before(events, minutes):
        limit = minutes * 60 * 1000
        return sum(1 for e in events if (e or {}).get("timestamp") is not None and e["timestamp"] < limit)

    challenges = me.get("challenges") or {}
    return {
        "matchId": r.get("matchId"),
        "gameCreation": r.get("gameCreation"),
        "gameDuration": r.get("gameDuration"),
        "gameVersion": r.get("gameVersion"),
        "queueId": r.get("queueId"),
        "win": r.get("win"),
        "kda": [r.get("kills", 0), r.get("deaths", 0), r.get("assists", 0)],
        "cs": r.get("cs", 0),
        "gold": r.get("gold", 0),
        "damage": r.get("damage", 0),
        "turretDamage": me.get("turretDamage", 0),
        "opponent": {
            "championName": opp.get("championName"),
            "kda": [opp.get("kills", 0), opp.get("deaths", 0), opp.get("assists", 0)],
            "cs": opp.get("cs", 0),
            "gold": opp.get("gold", 0),
            "damage": opp.get("damage", 0),
            "turretDamage": opp.get("turretDamage", 0),
            "soloKills": (opp.get("challenges") or {}).get("soloKills"),
        },
        "teamKills": team_kills,
        "enemyKills": enemy_kills,
        "allyTopGold": top_threat(my_team),
        "enemyTopGold": top_threat(enemies),
        "laneIndicators": {
            "laneMinionsFirst10Minutes": challenges.get("laneMinionsFirst10Minutes"),
            "maxCsAdvantageOnLaneOpponent": challenges.get("maxCsAdvantageOnLaneOpponent"),
            "maxLevelLeadLaneOpponent": challenges.get("maxLevelLeadLaneOpponent"),
            "soloKills": challenges.get("soloKills"),
            "turretPlatesTaken": challenges.get("turretPlatesTaken"),
            "earlyLaningPhaseGoldExpAdvantage": challenges.get("earlyLaningPhaseGoldExpAdvantage"),
            "laningPhaseGoldExpAdvantage": challenges.get("laningPhaseGoldExpAdvantage"),
        },
        "snapshots": [snapshot(s) for s in (r.get("snapshots") or [])],
        "firstDeath": deaths[0] if deaths else None,
        "deaths": deaths,
        "kills": kills,
        "assistTimestamps": assists,
        "deathsBefore10": before(r.get("deathsTimeline") or [], 10),
        "deathsBefore15": before(r.get("deathsTimeline") or [], 15),
        "deathsBefore20": before(r.get("deathsTimeline") or [], 20),
        "killsBefore10": before(r.get("killsTimeline") or [], 10),
        "killsBefore15": before(r.get("killsTimeline") or [], 15),
        "killsBefore20": before(r.get("killsTimeline") or [], 20),
        "assistsBefore10": sum(1 for t in assists if t < 10 * 60 * 1000),
        "assistsBefore15": sum(1 for t in assists if t < 15 * 60 * 1000),
        "assistsBefore20": sum(1 for t in assists if t < 20 * 60 * 1000),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted(SUMMARY.glob("*_recent20.json")):
        rows = json.loads(src.read_text(encoding="utf-8"))
        out = OUT / src.name
        out.write_text(json.dumps([compact(r) for r in rows], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        count += 1
    print(f"Compact AI comparison files: {count}")


if __name__ == "__main__":
    main()
