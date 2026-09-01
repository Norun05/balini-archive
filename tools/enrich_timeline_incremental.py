from pathlib import Path

import add_movement_snapshots as movement
import build_site_data as base
import enrich_early_laning as early
import enrich_full_events as full
import incremental_state as inc

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DETAILS = DATA / "matches"
MANIFEST = DATA / "manifest.json"
STAGE = "timeline_enrichment"


def marker_complete(detail):
    timeline = detail.get("timeline") or {}
    me = detail.get("me") or {}
    return (
        timeline.get("eventScope") == "all participants"
        and isinstance(timeline.get("earlyLaningSnapshots"), list)
        and isinstance(timeline.get("movementSnapshots"), list)
        and isinstance(me.get("summonerSpells"), list)
    )


def process_one(detail_path, raw_match_path, timeline_path):
    detail = base.read_json(detail_path)
    raw_match = base.read_json(raw_match_path)
    raw_timeline = base.read_json(timeline_path)

    participants = ((raw_match.get("info") or {}).get("participants") or [])
    participant_map = {
        p.get("participantId"): p
        for p in participants
        if p.get("participantId") is not None
    }

    compact_players = []
    if detail.get("me"):
        compact_players.append(detail["me"])
    if detail.get("laneOpponent"):
        compact_players.append(detail["laneOpponent"])
    compact_players.extend(detail.get("teammates") or [])
    compact_players.extend(detail.get("enemies") or [])

    for compact in compact_players:
        raw = participant_map.get(compact.get("participantId"))
        if raw:
            full.enrich_compact_participant(compact, raw)

    frames = ((raw_timeline.get("info") or {}).get("frames") or [])
    events = []
    counts = {"events": 0, "kills": 0, "items": 0, "levels": 0, "snapshots": 0, "milestones": 0, "movement": 0, "jumps": 0}
    for frame in frames:
        for event in frame.get("events") or []:
            event_type = event.get("type")
            if event_type not in full.KEEP_EVENT_TYPES:
                continue
            events.append(full.compact_event(event, participant_map))
            counts["events"] += 1
            if event_type == "CHAMPION_KILL":
                counts["kills"] += 1
            elif event_type in full.ITEM_EVENT_TYPES:
                counts["items"] += 1
            elif event_type == "SKILL_LEVEL_UP":
                counts["levels"] += 1

    timeline = detail.get("timeline")
    if not isinstance(timeline, dict):
        timeline = {}
        detail["timeline"] = timeline
    timeline["events"] = events
    timeline["eventScope"] = "all participants"
    timeline["eventTypes"] = sorted(full.KEEP_EVENT_TYPES)

    me = detail.get("me") or {}
    opponent = detail.get("laneOpponent") or {}
    me_id = me.get("participantId")
    opponent_id = opponent.get("participantId")

    snapshots = []
    for minute in early.SNAPSHOT_MINUTES:
        frame = early.frame_at_minute(frames, minute, detail.get("gameDuration"))
        if not frame:
            continue
        row = early.snapshot_payload(frame, me_id, opponent_id)
        if row:
            row["minute"] = minute
            snapshots.append(row)
    milestones = early.milestone_comparison(frames, me_id, opponent_id) if me_id is not None else {}
    timeline["earlyLaningSnapshots"] = snapshots
    timeline["earlyLaningSnapshotMinutes"] = list(early.SNAPSHOT_MINUTES)
    timeline["levelMilestones"] = milestones
    timeline["levelMilestoneNote"] = (
        "Level 2/3 timestamps are approximate. Riot Match-V5 participantFrames are about 1 minute apart."
    )
    counts["snapshots"] = len(snapshots)
    counts["milestones"] = sum(1 for row in milestones.values() if row.get("me") or row.get("opponent"))

    if me_id is not None:
        rows = movement.movement_snapshots(raw_timeline, me_id)
        jumps = movement.displacement_events(rows)
    else:
        rows = []
        jumps = []
    timeline["movementSnapshots"] = rows
    timeline["largeDisplacements"] = jumps
    timeline["movementSource"] = "Riot Match-V5 timeline participantFrames"
    timeline["movementFrameCadence"] = "about 1 minute"
    timeline["movementScope"] = "user participant for this match"
    timeline["movementCaveat"] = (
        "Adjacent frame positions do not reveal the path or cause of movement. Large displacement is heuristic only."
    )
    counts["movement"] = len(rows)
    counts["jumps"] = len(jumps)

    base.write_json(detail_path, detail)
    return counts


def main():
    found = base.find_archive()
    if not found:
        print("Could not find the local Riot archive.")
        return 2
    _, _, archive, matches_dir, timelines_dir = found
    print(f"Archive found: {archive}")
    print("Incremental timeline enrichment: events + early lane + movement in one pass.")

    old_signatures = inc.cached_signatures(STAGE)
    new_signatures = {}
    processed = 0
    skipped = 0
    missing = 0
    processed_counts = {"events": 0, "kills": 0, "items": 0, "levels": 0, "snapshots": 0, "milestones": 0, "movement": 0, "jumps": 0}

    detail_paths = sorted(DETAILS.glob("KR_*.json"))
    total = len(detail_paths)
    for idx, detail_path in enumerate(detail_paths, 1):
        raw_match_path = matches_dir / detail_path.name
        timeline_path = timelines_dir / detail_path.name
        if not raw_match_path.exists() or not timeline_path.exists():
            missing += 1
            continue

        sig = inc.source_signature(raw_match_path, timeline_path)
        new_signatures[detail_path.stem] = sig
        can_skip = old_signatures.get(detail_path.stem) == sig
        if can_skip:
            try:
                can_skip = marker_complete(base.read_json(detail_path))
            except Exception:
                can_skip = False
        elif detail_path.stem not in old_signatures and inc.output_is_newer(detail_path, raw_match_path, timeline_path):
            try:
                can_skip = marker_complete(base.read_json(detail_path))
            except Exception:
                can_skip = False

        if can_skip:
            skipped += 1
        else:
            try:
                counts = process_one(detail_path, raw_match_path, timeline_path)
            except Exception as exc:
                print(f"  WARN {detail_path.stem}: {type(exc).__name__}")
                missing += 1
                continue
            processed += 1
            for key, value in counts.items():
                processed_counts[key] += value

        if idx % 100 == 0 or idx == total:
            print(f"Timeline checked {idx}/{total} (processed {processed}, skipped {skipped})")

    manifest = {}
    if MANIFEST.exists():
        try:
            manifest = base.read_json(MANIFEST)
        except Exception:
            manifest = {}
    manifest["schemaVersion"] = max(int(manifest.get("schemaVersion") or 0), 7)
    manifest["participantRiotIdField"] = "me/teammates/enemies/laneOpponent.riotId"
    manifest["participantSummonerSpellField"] = "me/teammates/enemies/laneOpponent.summonerSpells"
    manifest["fullTimelineEventField"] = "timeline.events"
    manifest["fullTimelineEventTypes"] = sorted(full.KEEP_EVENT_TYPES)
    manifest["earlyLaningSnapshotMinutes"] = list(early.SNAPSHOT_MINUTES)
    manifest["earlyLaningSnapshotField"] = "timeline.earlyLaningSnapshots"
    manifest["levelMilestoneField"] = "timeline.levelMilestones"
    manifest["levelMilestonePrecision"] = "approximately 1 minute from Riot participantFrames"
    manifest["movementSnapshotField"] = "timeline.movementSnapshots"
    manifest["movementScope"] = "all archived user matches, regardless of position"
    manifest["movementFrameCadence"] = "about 1 minute (Riot Match-V5 participantFrames)"
    manifest["movementDisplacementField"] = "timeline.largeDisplacements"
    manifest["movementLargeDisplacementThreshold"] = movement.LARGE_DISPLACEMENT_THRESHOLD
    manifest["incrementalTimelineProcessed"] = processed
    manifest["incrementalTimelineSkipped"] = skipped
    manifest["incrementalTimelineMissing"] = missing
    manifest["incrementalTimelineProcessedCounts"] = processed_counts
    base.write_json(MANIFEST, manifest)
    inc.save_stage(STAGE, new_signatures)

    print(f"Timeline matches processed: {processed}")
    print(f"Timeline matches skipped: {skipped}")
    print(f"Missing/unreadable: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
