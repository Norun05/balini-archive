import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHAMPIONS = DATA / "champions"
OUT = DATA / "ai" / "recent20"
SUMMARY_OUT = DATA / "ai" / "summary20"


def keep_timeline(timeline):
    timeline = timeline or {}
    return {
        "snapshots": timeline.get("snapshots") or [],
        "firstKillTimestamp": timeline.get("firstKillTimestamp"),
        "firstDeathTimestamp": timeline.get("firstDeathTimestamp"),
        "firstAssistTimestamp": timeline.get("firstAssistTimestamp"),
        "championEvents": timeline.get("championEvents") or [],
        "itemEvents": [
            e for e in (timeline.get("itemEvents") or [])
            if e.get("type") in ("ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO")
        ],
        "objectiveEvents": timeline.get("objectiveEvents") or [],
    }


def compact_match(m):
    lane = m.get("laneOpponent") or None
    return {
        "matchId": m.get("matchId"),
        "gameCreation": m.get("gameCreation"),
        "gameDuration": m.get("gameDuration"),
        "queueId": m.get("queueId"),
        "gameMode": m.get("gameMode"),
        "championName": m.get("championName"),
        "position": m.get("position"),
        "opponent": m.get("opponent"),
        "kills": m.get("kills", 0),
        "deaths": m.get("deaths", 0),
        "assists": m.get("assists", 0),
        "cs": m.get("cs", 0),
        "gold": m.get("gold", 0),
        "damage": m.get("damage", 0),
        "win": m.get("win"),
        "items": m.get("items") or [],
        "meChallenges": m.get("meChallenges") or {},
        "laneOpponent": lane,
        "timeline": keep_timeline(m.get("timeline")),
    }


def summary_match(m):
    timeline = m.get("timeline") or {}
    lane = m.get("laneOpponent") or {}
    snapshots = []
    for s in timeline.get("snapshots") or []:
        me = s.get("me") or {}
        opp = s.get("opponent") or {}
        snapshots.append({
            "minute": s.get("minute"),
            "goldDiff": s.get("goldDiff"),
            "csDiff": s.get("csDiff"),
            "levelDiff": s.get("levelDiff"),
            "myGold": me.get("gold"),
            "myCs": me.get("cs"),
            "myLevel": me.get("level"),
            "oppGold": opp.get("gold"),
            "oppCs": opp.get("cs"),
            "oppLevel": opp.get("level"),
        })
    return {
        "matchId": m.get("matchId"),
        "gameCreation": m.get("gameCreation"),
        "gameDuration": m.get("gameDuration"),
        "queueId": m.get("queueId"),
        "gameMode": m.get("gameMode"),
        "opponent": m.get("opponent"),
        "win": m.get("win"),
        "kills": m.get("kills", 0),
        "deaths": m.get("deaths", 0),
        "assists": m.get("assists", 0),
        "cs": m.get("cs", 0),
        "gold": m.get("gold", 0),
        "damage": m.get("damage", 0),
        "soloKills": (m.get("meChallenges") or {}).get("soloKills"),
        "killParticipation": (m.get("meChallenges") or {}).get("killParticipation"),
        "teamDamagePercentage": (m.get("meChallenges") or {}).get("teamDamagePercentage"),
        "laneMinionsFirst10Minutes": (m.get("meChallenges") or {}).get("laneMinionsFirst10Minutes"),
        "opponentFinal": {
            "kills": lane.get("kills"),
            "deaths": lane.get("deaths"),
            "assists": lane.get("assists"),
            "cs": lane.get("cs"),
            "gold": lane.get("gold"),
            "damage": lane.get("damage"),
        } if lane else None,
        "firstKillTimestamp": timeline.get("firstKillTimestamp"),
        "firstDeathTimestamp": timeline.get("firstDeathTimestamp"),
        "firstAssistTimestamp": timeline.get("firstAssistTimestamp"),
        "snapshots": snapshots,
    }


def main():
    for path in (OUT, SUMMARY_OUT):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    index = []
    for recent in sorted(CHAMPIONS.glob("*/*/recent.json")):
        payload = json.loads(recent.read_text(encoding="utf-8"))
        matches = payload.get("matches") if isinstance(payload, dict) else payload
        matches = matches or []
        compact = [compact_match(m) for m in matches[:20]]
        summaries = [summary_match(m) for m in matches[:20]]
        champ = recent.parent.parent.name
        pos = recent.parent.name
        out_name = f"{champ}_{pos}.json"
        base = {
            "champion": champ,
            "position": pos,
            "availableCount": payload.get("count", len(matches)) if isinstance(payload, dict) else len(matches),
            "count": len(compact),
        }
        (OUT / out_name).write_text(
            json.dumps({**base, "matches": compact}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (SUMMARY_OUT / out_name).write_text(
            json.dumps({**base, "matches": summaries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        index.append({"champion": champ, "position": pos, "file": out_name, "count": len(compact)})

    for path in (OUT / "index.json", SUMMARY_OUT / "index.json"):
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Recent-20 indexes ready: {len(index)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
