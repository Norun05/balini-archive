import json
from pathlib import Path

import build_site_data as base

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MATCH_DETAILS_DIR = DATA / "matches"
MANIFEST_PATH = DATA / "manifest.json"

SNAPSHOT_MINUTES = (2, 3, 4, 5, 6, 8, 10, 15, 20)
LEVEL_MILESTONES = (2, 3)


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def participant_frame(pframes, participant_id):
    if participant_id is None:
        return None
    return pframes.get(str(participant_id)) or pframes.get(participant_id)


def frame_at_minute(frames, minute, game_duration):
    target = minute * 60 * 1000
    if isinstance(game_duration, (int, float)) and game_duration * 1000 < target:
        return None
    return min(frames, key=lambda f: abs((f.get("timestamp") or 0) - target)) if frames else None


def snapshot_payload(frame, me_id, opponent_id):
    if not frame:
        return None
    pframes = frame.get("participantFrames") or {}
    mef = base.frame_summary(participant_frame(pframes, me_id))
    oppf = base.frame_summary(participant_frame(pframes, opponent_id)) if opponent_id else None
    out = {
        "timestamp": frame.get("timestamp"),
        "me": mef,
        "opponent": oppf,
    }
    if mef and oppf:
        out["goldDiff"] = (mef.get("gold") or 0) - (oppf.get("gold") or 0)
        out["currentGoldDiff"] = (mef.get("currentGold") or 0) - (oppf.get("currentGold") or 0)
        out["csDiff"] = (mef.get("cs") or 0) - (oppf.get("cs") or 0)
        out["xpDiff"] = (mef.get("xp") or 0) - (oppf.get("xp") or 0)
        if mef.get("level") is not None and oppf.get("level") is not None:
            out["levelDiff"] = mef["level"] - oppf["level"]
    return out


def first_frame_reaching_level(frames, participant_id, target_level):
    for frame in frames:
        pframes = frame.get("participantFrames") or {}
        pf = participant_frame(pframes, participant_id)
        if not pf:
            continue
        level = pf.get("level")
        if isinstance(level, (int, float)) and level >= target_level:
            return {
                "level": target_level,
                "timestamp": frame.get("timestamp"),
                "minute": round((frame.get("timestamp") or 0) / 60000, 2),
                "observedLevel": level,
                "xp": pf.get("xp"),
            }
    return None


def milestone_comparison(frames, me_id, opponent_id):
    out = {}
    for level in LEVEL_MILESTONES:
        me = first_frame_reaching_level(frames, me_id, level)
        opponent = first_frame_reaching_level(frames, opponent_id, level) if opponent_id else None
        row = {
            "me": me,
            "opponent": opponent,
            "source": "Riot Match-V5 participantFrames",
            "precision": "approximately 1 minute; first frame observed at or above target level",
        }
        if me and opponent and me.get("timestamp") is not None and opponent.get("timestamp") is not None:
            row["observedLeadMs"] = opponent["timestamp"] - me["timestamp"]
            if row["observedLeadMs"] > 0:
                row["observedFirst"] = "me"
            elif row["observedLeadMs"] < 0:
                row["observedFirst"] = "opponent"
            else:
                row["observedFirst"] = "same_frame"
        out[str(level)] = row
    return out


def update_manifest(updated_matches, snapshot_count, milestone_count):
    if not MANIFEST_PATH.exists():
        return
    try:
        manifest = read_json(MANIFEST_PATH)
    except Exception:
        return

    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 6)
    manifest["earlyLaningSnapshotMinutes"] = list(SNAPSHOT_MINUTES)
    manifest["earlyLaningSnapshotField"] = "timeline.earlyLaningSnapshots"
    manifest["earlyLaningSnapshotMatchCount"] = updated_matches
    manifest["earlyLaningSnapshotCount"] = snapshot_count
    manifest["levelMilestoneField"] = "timeline.levelMilestones"
    manifest["levelMilestones"] = list(LEVEL_MILESTONES)
    manifest["levelMilestonePrecision"] = "approximately 1 minute from Riot participantFrames"
    manifest["levelMilestoneCount"] = milestone_count
    write_json(MANIFEST_PATH, manifest)


def main():
    found = base.find_archive()
    if not found:
        print("Could not find the local Riot archive.")
        return 2

    _, _, archive, matches_dir, timelines_dir = found
    print(f"Archive found: {archive}")
    print("Adding dense early-laning snapshots and approximate level-2/3 milestones...")

    updated_matches = 0
    snapshot_count = 0
    milestone_count = 0
    missing_timeline = 0

    for detail_path in sorted(MATCH_DETAILS_DIR.glob("KR_*.json")):
        timeline_path = timelines_dir / detail_path.name
        if not timeline_path.exists():
            missing_timeline += 1
            continue

        try:
            detail = read_json(detail_path)
            raw_timeline = read_json(timeline_path)
        except Exception:
            missing_timeline += 1
            continue

        frames = ((raw_timeline.get("info") or {}).get("frames") or [])
        if not frames:
            missing_timeline += 1
            continue

        me = detail.get("me") or {}
        opponent = detail.get("laneOpponent") or {}
        me_id = me.get("participantId")
        opponent_id = opponent.get("participantId")
        if me_id is None:
            continue

        snapshots = []
        for minute in SNAPSHOT_MINUTES:
            frame = frame_at_minute(frames, minute, detail.get("gameDuration"))
            if not frame:
                continue
            row = snapshot_payload(frame, me_id, opponent_id)
            if row:
                row["minute"] = minute
                snapshots.append(row)

        milestones = milestone_comparison(frames, me_id, opponent_id)

        timeline = detail.get("timeline")
        if not isinstance(timeline, dict):
            timeline = {}
            detail["timeline"] = timeline
        timeline["earlyLaningSnapshots"] = snapshots
        timeline["earlyLaningSnapshotMinutes"] = list(SNAPSHOT_MINUTES)
        timeline["levelMilestones"] = milestones
        timeline["levelMilestoneNote"] = (
            "Level 2/3 timestamps are approximate. Riot Match-V5 participantFrames are about 1 minute apart, "
            "so this records the first frame where the player is observed at or above the target level."
        )

        write_json(detail_path, detail)
        updated_matches += 1
        snapshot_count += len(snapshots)
        milestone_count += sum(1 for row in milestones.values() if row.get("me") or row.get("opponent"))

    update_manifest(updated_matches, snapshot_count, milestone_count)

    print(f"Early-laning matches updated: {updated_matches}")
    print(f"Early-laning snapshots: {snapshot_count}")
    print(f"Level milestone rows: {milestone_count}")
    print(f"Missing/unreadable timelines: {missing_timeline}")
    print("Done. These fields are ready for later statistics generation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
