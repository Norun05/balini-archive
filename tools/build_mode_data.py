import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from game_modes import classify_mode

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CATALOG = DATA / "catalog.json"
MATCHES = DATA / "matches"
OUT = DATA / "modes.json"
MANIFEST = DATA / "manifest.json"


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(n, d):
    return round(n * 100 / d, 2) if d else None


def detail_for_row(row):
    rel = row.get("detailPath") or f"matches/{row.get('matchId')}.json"
    path = DATA / rel
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except Exception:
        return {}


def main():
    if not CATALOG.exists():
        print("Missing data/catalog.json. Run build_site_data_incremental.py first.")
        return 2

    catalog = read_json(CATALOG)
    if not isinstance(catalog, list):
        print("data/catalog.json is not a list.")
        return 2

    mode_rows = defaultdict(list)
    mode_meta = {}
    rule_counts = defaultdict(Counter)
    signature_counts = defaultdict(Counter)
    queue_counts = defaultdict(Counter)
    game_mode_counts = defaultdict(Counter)
    map_counts = defaultdict(Counter)

    changed = 0
    for row in catalog:
        detail = detail_for_row(row)
        meta = classify_mode(
            queue_id=row.get("queueId"),
            game_mode=row.get("gameMode"),
            map_id=detail.get("mapId"),
            game_version=detail.get("gameVersion"),
            game_creation=row.get("gameCreation"),
        )

        flat = {
            "modeKey": meta["modeKey"],
            "modeNameKo": meta["modeNameKo"],
            "modeFamily": meta["modeFamily"],
            "rulesetKey": meta["rulesetKey"],
            "rulesetNameKo": meta["rulesetNameKo"],
            "isStandardRift": meta["isStandardRift"],
            "hasStandardPositions": meta["hasStandardPositions"],
            "modeConfidence": meta["modeConfidence"],
            "queueSignature": meta["queueSignature"],
        }
        if any(row.get(k) != v for k, v in flat.items()):
            row.update(flat)
            changed += 1

        key = meta["modeKey"]
        mode_rows[key].append(row)
        mode_meta[key] = meta
        rule_counts[key][meta["rulesetKey"]] += 1
        signature_counts[key][meta["queueSignature"]] += 1
        if row.get("queueId") is not None:
            queue_counts[key][str(row.get("queueId"))] += 1
        if row.get("gameMode"):
            game_mode_counts[key][str(row.get("gameMode"))] += 1
        if detail.get("mapId") is not None:
            map_counts[key][str(detail.get("mapId"))] += 1

    write_json(CATALOG, catalog)

    modes = []
    for key, rows in sorted(mode_rows.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        meta = mode_meta[key]
        wins = sum(1 for r in rows if r.get("win"))
        dates = [r.get("gameCreation") for r in rows if isinstance(r.get("gameCreation"), (int, float))]
        samples = {}
        for row in rows:
            sig = row.get("queueSignature")
            if sig and sig not in samples:
                samples[sig] = row.get("matchId")
        rulesets = []
        for ruleset_key, games in rule_counts[key].most_common():
            sample_row = next((r for r in rows if r.get("rulesetKey") == ruleset_key), None)
            rulesets.append({
                "rulesetKey": ruleset_key,
                "rulesetNameKo": (sample_row or {}).get("rulesetNameKo") or ruleset_key,
                "games": games,
            })

        modes.append({
            "modeKey": key,
            "modeNameKo": meta["modeNameKo"],
            "modeFamily": meta["modeFamily"],
            "games": len(rows),
            "wins": wins,
            "losses": len(rows) - wins,
            "winRate": pct(wins, len(rows)),
            "isStandardRift": meta["isStandardRift"],
            "hasStandardPositions": meta["hasStandardPositions"],
            "queueIds": [{"queueId": int(q), "games": n} for q, n in queue_counts[key].most_common()],
            "gameModes": [{"gameMode": gm, "games": n} for gm, n in game_mode_counts[key].most_common()],
            "mapIds": [{"mapId": int(mid), "games": n} for mid, n in map_counts[key].most_common()],
            "queueSignatures": [
                {"signature": sig, "games": n, "sampleMatchId": samples.get(sig)}
                for sig, n in signature_counts[key].most_common()
            ],
            "rulesets": rulesets,
            "earliestGameCreation": min(dates) if dates else None,
            "latestGameCreation": max(dates) if dates else None,
        })

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "schemaVersion": 1,
        "generatedAt": now_ms,
        "matchCount": len(catalog),
        "modeCount": len(modes),
        "modes": modes,
        "notes": [
            "Mode labels are archive-normalized; Riot queue IDs can be reused or changed over time.",
            "Classification uses gameMode before queueId for known reused/alternate cases such as observed Swiftplay queue 890.",
            "rulesetKey separates materially different rule eras without forcing separate top-level UI modes.",
            "League's Match-V5 gameMode value CLASSIC is not the 2026 product mode named League Classic.",
        ],
    }
    write_json(OUT, payload)

    manifest = read_json(MANIFEST) if MANIFEST.exists() else {}
    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 12)
    manifest["modeIndexPath"] = "modes.json"
    manifest["modeClassificationVersion"] = 1
    manifest["modeClassifiedMatchCount"] = len(catalog)
    manifest["modeCount"] = len(modes)
    manifest["modeKeys"] = [m["modeKey"] for m in modes]
    manifest["modeCatalogFields"] = [
        "modeKey",
        "modeNameKo",
        "modeFamily",
        "rulesetKey",
        "rulesetNameKo",
        "isStandardRift",
        "hasStandardPositions",
        "modeConfidence",
        "queueSignature",
    ]
    write_json(MANIFEST, manifest)

    print(f"Mode classification ready: {len(catalog)} matches")
    print(f"Modes: {len(modes)}")
    print(f"Catalog rows updated: {changed}")
    for mode in modes:
        print(f"  {mode['modeNameKo']}: {mode['games']} games")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
