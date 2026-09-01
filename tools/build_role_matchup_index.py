import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "team_context" / "matches"
OUT = ROOT / "data" / "ai" / "role_matchups.json"
ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def snap_at(match, minute):
    return next((s for s in (match.get("snapshots") or []) if s.get("minute") == minute), None)


def role_pair(snapshot, role):
    data = ((snapshot or {}).get("roles") or {}).get(role) or {}
    if not data:
        return None
    return {
        "ally": data.get("allyChampion"),
        "enemy": data.get("enemyChampion"),
        "goldDiff": data.get("goldDiff"),
        "csDiff": data.get("csDiff"),
        "levelDiff": data.get("levelDiff"),
    }


def main():
    rows = []
    for path in sorted(SRC.glob("KR_*.json")):
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        s5 = snap_at(m, 5)
        s10 = snap_at(m, 10)
        source = s5 or s10
        if not source:
            continue
        roles = {role: role_pair(source, role) for role in ROLES}
        rows.append({
            "matchId": m.get("matchId"),
            "gameCreation": m.get("gameCreation"),
            "gameDuration": m.get("gameDuration"),
            "championName": m.get("championName"),
            "position": m.get("position"),
            "opponent": m.get("opponent"),
            "win": m.get("win"),
            "roles": roles,
            "minute5": {
                "teamGoldDiff": (s5 or {}).get("teamGoldDiff"),
                "killDiff": (s5 or {}).get("killDiff"),
                "middle": role_pair(s5, "MIDDLE"),
                "bottom": role_pair(s5, "BOTTOM"),
                "utility": role_pair(s5, "UTILITY"),
            } if s5 else None,
            "minute10": {
                "teamGoldDiff": (s10 or {}).get("teamGoldDiff"),
                "killDiff": (s10 or {}).get("killDiff"),
                "middle": role_pair(s10, "MIDDLE"),
                "bottom": role_pair(s10, "BOTTOM"),
                "utility": role_pair(s10, "UTILITY"),
            } if s10 else None,
        })
    rows.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"count": len(rows), "matches": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Role matchup index ready: {len(rows)} matches")


if __name__ == "__main__":
    main()
