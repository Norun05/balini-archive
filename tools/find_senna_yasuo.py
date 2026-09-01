import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "ai" / "role_matchups.json"
OUT = ROOT / "data" / "ai" / "senna_vs_yasuo_matches.json"


def main():
    payload = json.loads(SRC.read_text(encoding="utf-8"))
    found = []
    for m in payload.get("matches") or []:
        mid = (m.get("roles") or {}).get("MIDDLE") or {}
        if mid.get("ally") == "Senna" and mid.get("enemy") == "Yasuo":
            found.append(m)
    OUT.write_text(json.dumps({"count": len(found), "matches": found}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Senna mid vs Yasuo mid matches: {len(found)}")


if __name__ == "__main__":
    main()
