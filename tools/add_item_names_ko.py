import json
import re
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
MATCH_DETAILS_DIR = DATA_DIR / "matches"
MANIFEST_PATH = DATA_DIR / "manifest.json"

DDRAGON_BASE = "https://ddragon.leagueoflegends.com/cdn"
ITEM_EVENT_TYPES = {"ITEM_PURCHASED", "ITEM_SOLD", "ITEM_DESTROYED", "ITEM_UNDO"}


def version_number(path):
    m = re.search(r"-v(\d+)$", path.name, flags=re.I)
    return int(m.group(1)) if m else 0


def find_archive():
    candidates = []
    seen = set()
    bases = [REPO_ROOT, *REPO_ROOT.parents]

    for base in bases:
        try:
            dirs = list(base.glob("balini-lol-archive-v*")) + list(base.glob("balini-lol-archive"))
        except OSError:
            continue

        for archive in dirs:
            matches = archive / "data" / "raw" / "matches"
            if not matches.is_dir():
                continue

            key = str(matches.resolve())
            if key in seen:
                continue
            seen.add(key)

            count = sum(1 for _ in matches.glob("KR_*.json"))
            candidates.append((count, version_number(archive), archive))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def read_json(path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ddragon_version(game_version):
    if not game_version:
        return None
    parts = str(game_version).split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return f"{parts[0]}.{parts[1]}.1"


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "balini-archive-item-name-builder/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def load_item_map(version, cache_dir):
    cache_path = cache_dir / f"{version}.json" if cache_dir else None
    if cache_path and cache_path.exists():
        try:
            payload = read_json(cache_path)
            if isinstance(payload, dict) and payload:
                return payload
        except Exception:
            pass

    url = f"{DDRAGON_BASE}/{version}/data/ko_KR/item.json"
    payload = fetch_json(url)
    data = payload.get("data") or {}
    item_map = {
        str(item_id): item.get("name")
        for item_id, item in data.items()
        if item.get("name")
    }

    if cache_path and item_map:
        write_json(cache_path, item_map)

    return item_map


def latest_ddragon_version():
    versions = fetch_json("https://ddragon.leagueoflegends.com/api/versions.json")
    if not versions:
        raise RuntimeError("Data Dragon returned no versions")
    return str(versions[0])


def item_name(item_id, item_map):
    if item_id in (None, 0, "0"):
        return None
    return item_map.get(str(item_id))


def enrich_participant(participant, item_map):
    if not isinstance(participant, dict):
        return 0

    items = participant.get("items") or []
    names = [item_name(item_id, item_map) for item_id in items]
    participant["itemNamesKo"] = names
    return sum(1 for item_id, name in zip(items, names) if item_id not in (None, 0, "0") and not name)


def enrich_event(event, item_map):
    if event.get("type") not in ITEM_EVENT_TYPES:
        return 0

    unknown = 0
    fields = (
        ("itemId", "itemNameKo"),
        ("beforeId", "beforeItemNameKo"),
        ("afterId", "afterItemNameKo"),
    )
    for id_key, name_key in fields:
        if id_key not in event:
            continue
        item_id = event.get(id_key)
        name = item_name(item_id, item_map)
        event[name_key] = name
        if item_id not in (None, 0, "0") and not name:
            unknown += 1
    return unknown


def update_manifest(enriched_matches, enriched_events, unknown_ids, versions):
    if not MANIFEST_PATH.exists():
        return
    try:
        manifest = read_json(MANIFEST_PATH)
    except Exception:
        return

    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 4)
    manifest["itemNameLanguage"] = "ko_KR"
    manifest["itemNameSource"] = "Riot Data Dragon"
    manifest["itemNameMatchCount"] = enriched_matches
    manifest["itemNameEventCount"] = enriched_events
    manifest["itemNameUnknownIdCount"] = unknown_ids
    manifest["itemNameVersions"] = versions
    manifest["itemNameEventField"] = "timeline.events[].itemNameKo"
    manifest["participantItemNameField"] = "itemNamesKo"
    write_json(MANIFEST_PATH, manifest)


def main():
    detail_paths = sorted(MATCH_DETAILS_DIR.glob("KR_*.json"))
    if not detail_paths:
        print("No generated match detail JSON files found.")
        print("Run tools/build_site_data.py first.")
        return 2

    archive = find_archive()
    cache_dir = None
    if archive:
        cache_dir = archive / "data" / "meta" / "ddragon-items-ko"
        cache_dir.mkdir(parents=True, exist_ok=True)

    details = []
    needed_versions = set()
    for path in detail_paths:
        try:
            detail = read_json(path)
        except Exception:
            continue
        details.append((path, detail))
        version = ddragon_version(detail.get("gameVersion"))
        if version:
            needed_versions.add(version)

    maps = {}
    failed_versions = []
    print(f"Loading Korean item names for {len(needed_versions)} Data Dragon versions...")
    for version in sorted(needed_versions):
        try:
            maps[version] = load_item_map(version, cache_dir)
        except Exception as exc:
            failed_versions.append(version)
            print(f"  WARN: {version} failed ({type(exc).__name__})")

    fallback_map = None
    fallback_version = None
    if failed_versions:
        try:
            fallback_version = latest_ddragon_version()
            fallback_map = load_item_map(fallback_version, cache_dir)
            print(f"Using latest Data Dragon {fallback_version} as fallback.")
        except Exception as exc:
            print(f"Could not load fallback item data: {type(exc).__name__}")

    enriched_matches = 0
    enriched_events = 0
    unknown_ids = 0

    for path, detail in details:
        version = ddragon_version(detail.get("gameVersion"))
        item_map = maps.get(version) or fallback_map or {}
        if not item_map:
            continue

        unknown_ids += enrich_participant(detail.get("me"), item_map)
        unknown_ids += enrich_participant(detail.get("laneOpponent"), item_map)
        for participant in detail.get("teammates") or []:
            unknown_ids += enrich_participant(participant, item_map)
        for participant in detail.get("enemies") or []:
            unknown_ids += enrich_participant(participant, item_map)

        timeline = detail.get("timeline") or {}
        for event in timeline.get("events") or []:
            if event.get("type") in ITEM_EVENT_TYPES:
                enriched_events += 1
                unknown_ids += enrich_event(event, item_map)

        detail["itemNameLanguage"] = "ko_KR"
        detail["itemDataVersion"] = version if version in maps else fallback_version
        write_json(path, detail)
        enriched_matches += 1

    versions_used = sorted(maps)
    if fallback_version and fallback_version not in versions_used:
        versions_used.append(fallback_version)
    update_manifest(enriched_matches, enriched_events, unknown_ids, versions_used)

    print(f"Item-name enriched matches: {enriched_matches}")
    print(f"Item events enriched: {enriched_events}")
    print(f"Unknown item IDs: {unknown_ids}")
    if failed_versions:
        print("Historical Data Dragon versions that needed fallback: " + ", ".join(failed_versions))
    print("Done. Korean item names are now stored beside Riot item IDs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
