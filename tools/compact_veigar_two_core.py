import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "ai" / "builds" / "veigar_middle_two_core.json"
OUT = ROOT / "data" / "ai" / "builds" / "veigar_middle_two_core_compact.json"


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    groups = []
    for g in data.get("groups") or []:
        groups.append({
            "combo": g.get("combo"),
            "games": g.get("games"),
            "wins": g.get("wins"),
            "losses": g.get("losses"),
            "winRate": g.get("winRate"),
            "avgSecondCoreMinute": g.get("avgSecondCoreMinute"),
            "topOpponents": (g.get("opponents") or [])[:12],
            "checkpoints": g.get("checkpoints"),
        })
    OUT.write_text(json.dumps({
        "champion": data.get("champion"),
        "position": data.get("position"),
        "sampleCount": data.get("sampleCount"),
        "matchesWithRecognizedTwoCore": data.get("matchesWithRecognizedTwoCore"),
        "groups": groups,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
