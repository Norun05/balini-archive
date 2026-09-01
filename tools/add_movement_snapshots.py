import json
import math
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
MATCH_DETAILS_DIR = DATA_DIR / "matches"
MANIFEST_PATH = DATA_DIR / "manifest.json"

# Riot Match-V5 participantFrames are usually spaced about one minute apart.
# This threshold is only a heuristic for unusually large observed displacement
# between adjacent frames. It must not be interpreted as proof of Teleport,
# Shen R, recall, death/respawn, or any other specific cause.
LARGE_DISPLACEMENT_THRESHOLD = 6000


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

        row = {
            "timestamp": timestamp,
            "minute": round((timestamp or 0) / 60000, 2),
            "x": x,
            "y": y,
            "jungleCs": jungle_cs,
            "laneCs": lane_cs,
            "level": p.get("level"),
            "xp": p.get("xp"),
        }

        if rows:
            prev = rows[-1]
            dx = x - prev["x"]
            dy = y - prev["y"]
            distance = round(math.hypot(dx, dy), 1)
            elapsed_ms = (timestamp or 0) - (prev.get("timestamp") or 0)
            row["fromPrevious"] = {
                "distance": distance,
                "elapsedMs": elapsed_ms,
                "largeDisplacement": distance >= LARGE_DISPLACEMENT_THRESHOLD,
            }

        rows.append(row)

    return rows


def displacement_events(rows: list[dict]) -> list[dict]:
    events = []
    for idx, row in enumerate(rows):
        movement = row.get("fromPrevious") or {}
        if not movement.get("largeDisplacement") or idx == 0:
            continue
        prev = rows[idx - 1]
        events.append({
            "fromTimestamp": prev.get("timestamp"),
            "toTimestamp": row.get("timestamp"),
            "fromMinute": prev.get("minute"),
            "toMinute": row.get("minute"),
            "from": {"x": prev.get("x"), "y": prev.get("y")},
            "to": {"x": row.get("x"), "y": row.get("y")},
            "distance": movement.get("distance"),
            "note": "Large displacement between Riot timeline frames; cause is not identifiable from Match-V5 alone.",
        })
    return events


def update_manifest(updated_matches: int, snapshot_count: int, displacement_count: int):
    if not MANIFEST_PATH.exists():
        return

    try:
        manifest = read_json(MANIFEST_PATH)
    except Exception:
        return

    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 7)
    manifest["movementSummaryCount"] = updated_matches
    manifest["movementSnapshotCount"] = snapshot_count
    manifest["movementSnapshotField"] = "timeline.movementSnapshots"
    manifest["movementScope"] = "all archived user matches, regardless of position"
    manifest["movementFrameCadence"] = "about 1 minute (Riot Match-V5 participantFrames)"
    manifest["movementDisplacementField"] = "timeline.largeDisplacements"
    manifest["movementLargeDisplacementCount"] = displacement_count
    manifest["movementLargeDisplacementThreshold"] = LARGE_DISPLACEMENT_THRESHOLD
    manifest["movementLargeDisplacementMeaning"] = (
        "Heuristic only: unusually large coordinate difference between adjacent timeline frames. "
        "Does not identify Teleport, champion abilities, recall, death/respawn, or another cause."
    )
    write_json(MANIFEST_PATH, manifest)


def main():
    found = find_archive()
    if not found:
        print("Could not find local raw Riot archive with timelines.")
        print("Expected a nearby balini-lol-archive-v*/data/raw/timelines folder.")
        return 2

    _, _, archive, timelines_dir = found
    print(f"Archive found: {archive}")
    print("Adding ~1-minute movement snapshots to every archived user match...")

    updated_matches = 0
    snapshot_count = 0
    displacement_count = 0
    missing_timelines = 0

    for detail_path in sorted(MATCH_DETAILS_DIR.glob("KR_*.json")):
        try:
            detail = read_json(detail_path)
        except Exception:
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

        jumps = displacement_events(rows)

        summary = detail.get("timeline")
        if not isinstance(summary, dict):
            summary = {}
            detail["timeline"] = summary

        summary["movementSnapshots"] = rows
        summary["largeDisplacements"] = jumps
        summary["movementSource"] = "Riot Match-V5 timeline participantFrames"
        summary["movementFrameCadence"] = "about 1 minute"
        summary["movementScope"] = "user participant for this match"
        summary["movementCaveat"] = (
            "Adjacent frame positions do not reveal the path or cause of movement. "
            "Large displacement is a heuristic and must not be treated as proof of Teleport or a champion ability."
        )

        write_json(detail_path, detail)
        updated_matches += 1
        snapshot_count += len(rows)
        displacement_count += len(jumps)

    update_manifest(updated_matches, snapshot_count, displacement_count)

    print(f"Movement-enabled matches: {updated_matches}")
    print(f"Movement snapshots: {snapshot_count}")
    print(f"Large displacement flags: {displacement_count}")
    print(f"Missing/unreadable raw timelines: {missing_timelines}")
    print("Done. Movement is now generated for every position, not just jungle/Smite matches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
