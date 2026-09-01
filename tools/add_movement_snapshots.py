import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
MATCH_DETAILS_DIR = DATA_DIR / "matches"
MANIFEST_PATH = DATA_DIR / "manifest.json"
SMITE_ID = 11


def version_number(path: Path) -> int:
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
            timelines = archive / "data" / "raw" / "timelines"
            if not matches.is_dir() or not timelines.is_dir():
                continue

            key = str(matches.resolve())
            if key in seen:
                continue
            seen.add(key)

            count = sum(1 for _ in matches.glob("KR_*.json"))
            candidates.append((count, version_number(archive), archive, timelines))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0]


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_jungle_candidate(detail: dict) -> bool:
    me = detail.get("me") or {}
    spells = {me.get("summoner1Id"), me.get("summoner2Id")}
    return detail.get("position") == "JUNGLE" or SMITE_ID in spells


def movement_snapshots(timeline: dict, participant_id: int) -> list[dict]:
    frames = ((timeline.get("info") or {}).get("frames") or [])
    rows = []

    for frame in frames:
        timestamp = frame.get("timestamp")
        pframes = frame.get("participantFrames") or {}
        p = pframes.get(str(participant_id)) or pframes.get(participant_id)
        if not p:
            continue

        position = p.get("position") or {}
        x = position.get("x")
        y = position.get("y")
        if x is None or y is None:
            continue

        lane_cs = p.get("minionsKilled", 0) or 0
        jungle_cs = p.get("jungleMinionsKilled", 0) or 0

        rows.append({
            "timestamp": timestamp,
            "minute": round((timestamp or 0) / 60000, 2),
            "x": x,
            "y": y,
            "jungleCs": jungle_cs,
            "laneCs": lane_cs,
            "level": p.get("level"),
            "xp": p.get("xp"),
        })

    return rows


def update_manifest(updated_matches: int, snapshot_count: int):
    if not MANIFEST_PATH.exists():
        return

    try:
        manifest = read_json(MANIFEST_PATH)
    except Exception:
        return

    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 3)
    manifest["movementSummaryCount"] = updated_matches
    manifest["movementSnapshotCount"] = snapshot_count
    manifest["movementSnapshotField"] = "timeline.movementSnapshots"
    manifest["movementScope"] = "JUNGLE position or Smite spell"
    write_json(MANIFEST_PATH, manifest)


def main():
    found = find_archive()
    if not found:
        print("Could not find local raw Riot archive with timelines.")
        print("Expected a nearby balini-lol-archive-v*/data/raw/timelines folder.")
        return 2

    _, _, archive, timelines_dir = found
    print(f"Archive found: {archive}")
    print("Adding 1-minute movement snapshots to jungle/Smite match details...")

    updated_matches = 0
    snapshot_count = 0
    missing_timelines = 0

    for detail_path in sorted(MATCH_DETAILS_DIR.glob("KR_*.json")):
        try:
            detail = read_json(detail_path)
        except Exception:
            continue

        if not is_jungle_candidate(detail):
            continue

        me = detail.get("me") or {}
        participant_id = me.get("participantId")
        if not participant_id:
            continue

        timeline_path = timelines_dir / detail_path.name
        if not timeline_path.exists():
            missing_timelines += 1
            continue

        try:
            timeline = read_json(timeline_path)
        except Exception:
            missing_timelines += 1
            continue

        rows = movement_snapshots(timeline, participant_id)
        if not rows:
            continue

        summary = detail.get("timeline")
        if not isinstance(summary, dict):
            summary = {}
            detail["timeline"] = summary

        summary["movementSnapshots"] = rows
        summary["movementSource"] = "Riot Match-V5 timeline participantFrames"
        summary["movementFrameCadence"] = "about 1 minute"

        write_json(detail_path, detail)
        updated_matches += 1
        snapshot_count += len(rows)

    update_manifest(updated_matches, snapshot_count)

    print(f"Movement-enabled matches: {updated_matches}")
    print(f"Movement snapshots: {snapshot_count}")
    print(f"Missing/unreadable raw timelines: {missing_timelines}")
    print("Done. Commit the regenerated data files and Push origin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
