import json
from collections import defaultdict
from pathlib import Path

import add_item_names_ko as items

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MATCHES_DIR = DATA / "matches"
MANIFEST = DATA / "manifest.json"
ITEM_EVENT_TYPES = {"ITEM_PURCHASED", "ITEM_SOLD", "ITEM_DESTROYED", "ITEM_UNDO"}
INITIAL_BUY_CUTOFF_MS = 90000
SHOP_CLUSTER_MS = 5000
CORE_MIN_GOLD = 2000


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_meta(version, cache_dir):
    cache_path = cache_dir / f"{version}.json" if cache_dir else None
    if cache_path and cache_path.exists():
        try:
            payload = read_json(cache_path)
            if isinstance(payload, dict) and payload:
                return payload
        except Exception:
            pass

    payload = items.fetch_json(f"{items.DDRAGON_BASE}/{version}/data/ko_KR/item.json")
    data = payload.get("data") or {}
    out = {}
    for item_id, item in data.items():
        gold = item.get("gold") or {}
        out[str(item_id)] = {
            "nameKo": item.get("name"),
            "totalGold": gold.get("total"),
            "baseGold": gold.get("base"),
            "purchasable": bool(gold.get("purchasable", True)),
            "tags": item.get("tags") or [],
            "into": item.get("into") or [],
            "from": item.get("from") or [],
        }
    if cache_path and out:
        write_json(cache_path, out)
    return out


def is_boot(meta):
    return "Boots" in (meta or {}).get("tags", [])


def is_core(meta):
    if not meta:
        return False
    if not meta.get("purchasable", True):
        return False
    if is_boot(meta):
        return False
    if meta.get("into"):
        return False
    total = meta.get("totalGold")
    return isinstance(total, (int, float)) and total >= CORE_MIN_GOLD


def participant_lookup(detail):
    result = {}
    for p in [detail.get("me"), detail.get("laneOpponent"), *(detail.get("teammates") or []), *(detail.get("enemies") or [])]:
        if not isinstance(p, dict) or p.get("participantId") is None:
            continue
        result[p["participantId"]] = {
            "riotId": p.get("riotId"),
            "championName": p.get("championName"),
            "position": p.get("teamPosition") or p.get("individualPosition"),
        }
    return result


def event_row(event, meta_map):
    item_id = event.get("itemId")
    meta = meta_map.get(str(item_id)) if item_id not in (None, 0, "0") else None
    return {
        "type": event.get("type"),
        "timestamp": event.get("timestamp"),
        "itemId": item_id,
        "itemNameKo": event.get("itemNameKo") or (meta or {}).get("nameKo"),
        "beforeId": event.get("beforeId"),
        "beforeItemNameKo": event.get("beforeItemNameKo"),
        "afterId": event.get("afterId"),
        "afterItemNameKo": event.get("afterItemNameKo"),
        "totalGold": (meta or {}).get("totalGold"),
        "isBoot": is_boot(meta),
        "isCoreCandidate": is_core(meta),
    }


def first_back_cluster(rows):
    purchases = [r for r in rows if r.get("type") == "ITEM_PURCHASED" and (r.get("timestamp") or 0) > INITIAL_BUY_CUTOFF_MS]
    if not purchases:
        return None
    first_ts = purchases[0].get("timestamp") or 0
    cluster = [r for r in purchases if 0 <= (r.get("timestamp") or 0) - first_ts <= SHOP_CLUSTER_MS]
    return {
        "timestamp": first_ts,
        "items": [{"itemId": r.get("itemId"), "itemNameKo": r.get("itemNameKo")} for r in cluster],
        "note": "First post-opening purchase cluster; used as a first-return purchase heuristic.",
    }


def first_boot(rows):
    for r in rows:
        if r.get("type") == "ITEM_PURCHASED" and r.get("isBoot"):
            return {"timestamp": r.get("timestamp"), "itemId": r.get("itemId"), "itemNameKo": r.get("itemNameKo")}
    return None


def core_completions(rows):
    seen = set()
    out = []
    for r in rows:
        if r.get("type") != "ITEM_PURCHASED" or not r.get("isCoreCandidate"):
            continue
        item_id = r.get("itemId")
        if item_id in seen:
            continue
        seen.add(item_id)
        out.append({
            "timestamp": r.get("timestamp"),
            "itemId": item_id,
            "itemNameKo": r.get("itemNameKo"),
            "totalGold": r.get("totalGold"),
        })
    return out


def main():
    detail_paths = sorted(MATCHES_DIR.glob("KR_*.json"))
    if not detail_paths:
        print("No generated match details found.")
        return 2

    archive = items.find_archive()
    cache_dir = archive / "data" / "meta" / "ddragon-item-details-ko" if archive else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)

    meta_maps = {}
    updated = 0
    participant_summaries = 0
    core_count = 0
    unknown_ids = set()

    for path in detail_paths:
        try:
            detail = read_json(path)
        except Exception:
            continue

        version = items.ddragon_version(detail.get("gameVersion"))
        if version and version not in meta_maps:
            try:
                meta_maps[version] = load_meta(version, cache_dir)
            except Exception as exc:
                print(f"WARN: item metadata {version} failed ({type(exc).__name__})")
                meta_maps[version] = {}
        meta_map = meta_maps.get(version, {})

        timeline = detail.get("timeline") or {}
        source_events = [e for e in timeline.get("events") or [] if e.get("type") in ITEM_EVENT_TYPES]
        grouped = defaultdict(list)
        for event in source_events:
            pid = event.get("participantId")
            if not isinstance(pid, int) or not (1 <= pid <= 10):
                continue
            row = event_row(event, meta_map)
            grouped[pid].append(row)
            iid = row.get("itemId")
            if iid not in (None, 0, "0") and not row.get("itemNameKo"):
                unknown_ids.add(iid)

        players = participant_lookup(detail)
        summaries = {}
        for pid, rows in grouped.items():
            rows.sort(key=lambda r: r.get("timestamp") or 0)
            cores = core_completions(rows)
            summaries[str(pid)] = {
                **players.get(pid, {}),
                "events": rows,
                "firstBackPurchase": first_back_cluster(rows),
                "firstBootPurchase": first_boot(rows),
                "coreCompletions": cores,
                "firstCore": cores[0] if len(cores) >= 1 else None,
                "secondCore": cores[1] if len(cores) >= 2 else None,
            }
            participant_summaries += 1
            core_count += len(cores)

        timeline["itemEconomy"] = {
            "participants": summaries,
            "coreRule": f"Purchased terminal non-boots item with Data Dragon totalGold >= {CORE_MIN_GOLD}.",
            "firstBackRule": f"First ITEM_PURCHASED after {INITIAL_BUY_CUTOFF_MS // 1000}s, grouped within {SHOP_CLUSTER_MS // 1000}s.",
            "limitations": [
                "Core completion is a heuristic, not a Riot-provided semantic field.",
                "ITEM_UNDO, unusual transformations, support/jungle upgrades, and mode-specific items can make inferred build order imperfect.",
                "Gold spent should be read from event chronology rather than naively summing item totalGold.",
            ],
        }
        detail["timeline"] = timeline
        write_json(path, detail)
        updated += 1

    if MANIFEST.exists():
        try:
            manifest = read_json(MANIFEST)
        except Exception:
            manifest = {}
        manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 10)
        manifest["itemEconomyField"] = "timeline.itemEconomy.participants"
        manifest["itemEconomyMatchCount"] = updated
        manifest["itemEconomyParticipantSummaryCount"] = participant_summaries
        manifest["itemEconomyCoreCompletionCount"] = core_count
        manifest["itemEconomyCoreMinGold"] = CORE_MIN_GOLD
        manifest["itemNameUnknownIds"] = sorted(unknown_ids)
        manifest["itemNameUnknownUniqueIdCount"] = len(unknown_ids)
        write_json(MANIFEST, manifest)

    print(f"Item economy enriched matches: {updated}")
    print(f"Participant item timelines: {participant_summaries}")
    print(f"Core completion candidates: {core_count}")
    print(f"Unknown unique item IDs: {len(unknown_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
