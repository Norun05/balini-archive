import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHAMPIONS = DATA / "champions"
OUT = DATA / "ai" / "recent20"


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


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    index = []
    for recent in sorted(CHAMPIONS.glob("*/*/recent.json")):
        payload = json.loads(recent.read_text(encoding="utf-8"))
        matches = payload.get("matches") if isinstance(payload, dict) else payload
        matches = matches or []
        compact = [compact_match(m) for m in matches[:20]]
        champ = recent.parent.parent.name
        pos = recent.parent.name
        out_name = f"{champ}_{pos}.json"
        (OUT / out_name).write_text(
            json.dumps({
                "champion": champ,
                "position": pos,
                "availableCount": payload.get("count", len(matches)) if isinstance(payload, dict) else len(matches),
                "count": len(compact),
                "matches": compact,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        index.append({"champion": champ, "position": pos, "file": out_name, "count": len(compact)})

    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Recent-20 indexes ready: {len(index)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
