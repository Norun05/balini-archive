import json
import re
from collections import defaultdict
from pathlib import Path

RIOT_GAME_NAME = "발린이"
RIOT_TAG_LINE = "극악무도"
SNAPSHOT_MINUTES = (5, 10, 15)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "data" / "ai" / "skills" / "kennen_top.json"

SKILL_NAMES = {1: "Q", 2: "W", 3: "E", 4: "R"}


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
            candidates.append((count, version_number(archive), archive, matches, timelines))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0]


def read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def find_me(participants):
    for p in participants:
        if p.get("riotIdGameName") == RIOT_GAME_NAME and p.get("riotIdTagline") == RIOT_TAG_LINE:
            return p
    return None


def normalized_position(p):
    if not p:
        return ""
    for key in ("teamPosition", "individualPosition", "positionAssignedByMatchmaking"):
        value = p.get(key)
        if value and value != "NONE":
            return value
    return ""


def find_lane_opponent(participants, me):
    my_pos = normalized_position(me)
    for p in participants:
        if p.get("teamId") != me.get("teamId") and normalized_position(p) == my_pos:
            return p
    return None


def skill_events(timeline, participant_id):
    out = []
    info = timeline.get("info") or {}
    for frame in info.get("frames") or []:
        for e in frame.get("events") or []:
            if e.get("type") != "SKILL_LEVEL_UP" or e.get("participantId") != participant_id:
                continue
            slot = e.get("skillSlot")
            if slot not in SKILL_NAMES:
                continue
            out.append({
                "timestamp": e.get("timestamp"),
                "slot": slot,
                "skill": SKILL_NAMES[slot],
                "levelUpType": e.get("levelUpType"),
            })
    out.sort(key=lambda x: x.get("timestamp") or 0)
    return out


def first_maxed_basic(events):
    ranks = {1: 0, 2: 0, 3: 0}
    for e in events:
        slot = e["slot"]
        if slot not in ranks:
            continue
        ranks[slot] += 1
        if ranks[slot] >= 5:
            return SKILL_NAMES[slot]
    # Short games may end before rank 5. Do not guess a max order.
    return None


def snapshot_diff(timeline, me_id, opp_id, minute):
    frames = (timeline.get("info") or {}).get("frames") or []
    if not frames or not opp_id:
        return None
    target = minute * 60 * 1000
    frame = min(frames, key=lambda f: abs((f.get("timestamp") or 0) - target))
    # Do not use a frame after a match that ended before this checkpoint.
    if (frame.get("timestamp") or 0) + 30000 < target:
        return None
    pframes = frame.get("participantFrames") or {}
    mef = pframes.get(str(me_id)) or {}
    oppf = pframes.get(str(opp_id)) or {}
    if not mef or not oppf:
        return None
    me_cs = (mef.get("minionsKilled") or 0) + (mef.get("jungleMinionsKilled") or 0)
    opp_cs = (oppf.get("minionsKilled") or 0) + (oppf.get("jungleMinionsKilled") or 0)
    return {
        "goldDiff": (mef.get("totalGold") or 0) - (oppf.get("totalGold") or 0),
        "csDiff": me_cs - opp_cs,
        "levelDiff": (mef.get("level") or 0) - (oppf.get("level") or 0),
    }


def bucket_add(bucket, key, row):
    if not key:
        return
    d = bucket[key]
    d["games"] += 1
    d["wins"] += int(row["win"])
    for minute in SNAPSHOT_MINUTES:
        snap = row["snapshots"].get(str(minute))
        if not snap:
            continue
        for metric in ("goldDiff", "csDiff", "levelDiff"):
            d["values"][str(minute)][metric].append(snap[metric])


def median(values):
    if not values:
        return None
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def finish_bucket(bucket):
    rows = []
    for key, d in bucket.items():
        games = d["games"]
        wins = d["wins"]
        checkpoints = {}
        for minute in SNAPSHOT_MINUTES:
            checkpoints[str(minute)] = {}
            for metric in ("goldDiff", "csDiff", "levelDiff"):
                vals = d["values"][str(minute)][metric]
                checkpoints[str(minute)][metric] = {
                    "n": len(vals),
                    "avg": round(sum(vals) / len(vals), 2) if vals else None,
                    "median": median(vals),
                }
        rows.append({
            "key": key,
            "games": games,
            "wins": wins,
            "losses": games - wins,
            "winRate": round(wins / games, 4) if games else None,
            "checkpoints": checkpoints,
        })
    rows.sort(key=lambda r: (-r["games"], -r["winRate"], r["key"]))
    return rows


def new_bucket():
    return defaultdict(lambda: {
        "games": 0,
        "wins": 0,
        "values": defaultdict(lambda: defaultdict(list)),
    })


def main():
    found = find_archive()
    if not found:
        print("Could not find local raw Riot archive next to this repository.")
        return 2

    _, _, archive, matches_dir, timelines_dir = found
    print(f"Archive found: {archive}")

    level1 = new_bucket()
    first3 = new_bucket()
    first6 = new_bucket()
    first_max = new_bucket()
    rows = []
    skipped_no_timeline = 0
    skipped_no_skill = 0

    for match_path in sorted(matches_dir.glob("KR_*.json")):
        try:
            match = read_json(match_path)
        except Exception:
            continue
        info = match.get("info") or {}
        participants = info.get("participants") or []
        me = find_me(participants)
        if not me or me.get("championName") != "Kennen" or normalized_position(me) != "TOP":
            continue

        timeline_path = timelines_dir / match_path.name
        if not timeline_path.exists():
            skipped_no_timeline += 1
            continue
        try:
            timeline = read_json(timeline_path)
        except Exception:
            skipped_no_timeline += 1
            continue

        events = skill_events(timeline, me.get("participantId"))
        if not events:
            skipped_no_skill += 1
            continue

        opp = find_lane_opponent(participants, me)
        seq = [e["skill"] for e in events]
        row = {
            "matchId": (match.get("metadata") or {}).get("matchId") or match_path.stem,
            "gameCreation": info.get("gameCreation"),
            "gameDuration": info.get("gameDuration"),
            "opponent": opp.get("championName") if opp else None,
            "win": bool(me.get("win")),
            "skills": seq,
            "level1": seq[0] if seq else None,
            "first3": "→".join(seq[:3]) if len(seq) >= 3 else None,
            "first6": "→".join(seq[:6]) if len(seq) >= 6 else None,
            "firstMaxedBasic": first_maxed_basic(events),
            "snapshots": {},
        }
        for minute in SNAPSHOT_MINUTES:
            snap = snapshot_diff(timeline, me.get("participantId"), opp.get("participantId") if opp else None, minute)
            if snap:
                row["snapshots"][str(minute)] = snap

        rows.append(row)
        bucket_add(level1, row["level1"], row)
        bucket_add(first3, row["first3"], row)
        bucket_add(first6, row["first6"], row)
        bucket_add(first_max, row["firstMaxedBasic"], row)

    rows.sort(key=lambda r: r.get("gameCreation") or 0, reverse=True)
    payload = {
        "champion": "Kennen",
        "position": "TOP",
        "sampleCount": len(rows),
        "notes": [
            "Skill order comes directly from raw Match-V5 SKILL_LEVEL_UP timeline events.",
            "Win rates are descriptive associations, not causal effects of skill order.",
            "firstMaxedBasic is recorded only when Q/W/E actually reaches rank 5 before match end.",
            "Checkpoint diffs compare Kennen with the inferred TOP opponent."
        ],
        "skippedNoTimeline": skipped_no_timeline,
        "skippedNoSkillEvents": skipped_no_skill,
        "level1": finish_bucket(level1),
        "first3": finish_bucket(first3),
        "first6": finish_bucket(first6),
        "firstMaxedBasic": finish_bucket(first_max),
        "matches": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Kennen TOP skill-order stats: {len(rows)} matches")
    print(f"Output: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
