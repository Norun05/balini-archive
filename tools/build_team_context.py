import json
import shutil
from collections import defaultdict
from pathlib import Path

import build_site_data as base

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_MATCHES = DATA / "team_context" / "matches"
OUT_RECENT = DATA / "ai" / "team20"
OUT_METRICS = DATA / "ai" / "team20metrics"
SNAPSHOT_MINUTES = (5, 10, 15, 20)
ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
RECENT_LIMIT = 20


def num(value):
    return value if isinstance(value, (int, float)) else None


def avg(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def frame_for_minute(frames, minute, game_duration):
    target = minute * 60 * 1000
    if not isinstance(game_duration, (int, float)) or game_duration * 1000 < target:
        return None
    return min(frames, key=lambda f: abs((f.get("timestamp") or 0) - target))


def participant_by_role(participants, team_id, role):
    for p in participants:
        if p.get("teamId") == team_id and base.normalized_position(p) == role:
            return p
    return None


def role_snapshot(pframes, ally, enemy):
    if not ally or not enemy:
        return None
    af = base.frame_summary(pframes.get(str(ally.get("participantId"))))
    ef = base.frame_summary(pframes.get(str(enemy.get("participantId"))))
    if not af or not ef:
        return None
    out = {
        "allyChampion": ally.get("championName"),
        "enemyChampion": enemy.get("championName"),
        "allyGold": af.get("gold"),
        "enemyGold": ef.get("gold"),
        "goldDiff": (af.get("gold") or 0) - (ef.get("gold") or 0),
        "allyCs": af.get("cs"),
        "enemyCs": ef.get("cs"),
        "csDiff": (af.get("cs") or 0) - (ef.get("cs") or 0),
        "allyLevel": af.get("level"),
        "enemyLevel": ef.get("level"),
    }
    if af.get("level") is not None and ef.get("level") is not None:
        out["levelDiff"] = af.get("level") - ef.get("level")
    return out


def final_role(participants, my_team, enemy_team, role):
    ally = participant_by_role(participants, my_team, role)
    enemy = participant_by_role(participants, enemy_team, role)
    if not ally or not enemy:
        return None
    ally_cs = (ally.get("totalMinionsKilled", 0) or 0) + (ally.get("neutralMinionsKilled", 0) or 0)
    enemy_cs = (enemy.get("totalMinionsKilled", 0) or 0) + (enemy.get("neutralMinionsKilled", 0) or 0)
    return {
        "allyChampion": ally.get("championName"),
        "enemyChampion": enemy.get("championName"),
        "allyKda": [ally.get("kills", 0), ally.get("deaths", 0), ally.get("assists", 0)],
        "enemyKda": [enemy.get("kills", 0), enemy.get("deaths", 0), enemy.get("assists", 0)],
        "allyGold": ally.get("goldEarned", 0),
        "enemyGold": enemy.get("goldEarned", 0),
        "goldDiff": (ally.get("goldEarned", 0) or 0) - (enemy.get("goldEarned", 0) or 0),
        "allyCs": ally_cs,
        "enemyCs": enemy_cs,
        "csDiff": ally_cs - enemy_cs,
        "allyDamage": ally.get("totalDamageDealtToChampions", 0),
        "enemyDamage": enemy.get("totalDamageDealtToChampions", 0),
    }


def build_match_context(match, timeline, puuid):
    info = match.get("info") or {}
    participants = info.get("participants") or []
    me = base.find_me(participants, puuid)
    if not me:
        return None
    frames = (timeline.get("info") or {}).get("frames") or []
    if not frames:
        return None

    my_team = me.get("teamId")
    enemy_team = next((p.get("teamId") for p in participants if p.get("teamId") != my_team), None)
    my_role = base.normalized_position(me)
    opponent = base.find_lane_opponent(participants, me)
    pid_team = {p.get("participantId"): p.get("teamId") for p in participants}

    kill_events = []
    for frame in frames:
        for event in frame.get("events") or []:
            if event.get("type") == "CHAMPION_KILL":
                kill_events.append(event)

    snapshots = []
    game_duration = info.get("gameDuration")
    for minute in SNAPSHOT_MINUTES:
        frame = frame_for_minute(frames, minute, game_duration)
        if frame is None:
            continue
        timestamp = frame.get("timestamp") or 0
        pframes = frame.get("participantFrames") or {}
        roles = {}
        for role in ROLES:
            ally = participant_by_role(participants, my_team, role)
            enemy = participant_by_role(participants, enemy_team, role)
            roles[role] = role_snapshot(pframes, ally, enemy)

        my_team_gold = 0
        enemy_team_gold = 0
        for p in participants:
            fs = base.frame_summary(pframes.get(str(p.get("participantId"))))
            if not fs:
                continue
            if p.get("teamId") == my_team:
                my_team_gold += fs.get("gold") or 0
            elif p.get("teamId") == enemy_team:
                enemy_team_gold += fs.get("gold") or 0

        my_kills = 0
        enemy_kills = 0
        for event in kill_events:
            if (event.get("timestamp") or 0) > timestamp:
                continue
            killer_team = pid_team.get(event.get("killerId"))
            if killer_team == my_team:
                my_kills += 1
            elif killer_team == enemy_team:
                enemy_kills += 1

        my_lane = roles.get(my_role) if my_role in ROLES else None
        my_lane_gold_diff = my_lane.get("goldDiff") if my_lane else None
        team_gold_diff = my_team_gold - enemy_team_gold
        other_lanes_gold_diff = team_gold_diff - my_lane_gold_diff if isinstance(my_lane_gold_diff, (int, float)) else None

        bot_gold_diff = None
        bottom = roles.get("BOTTOM")
        support = roles.get("UTILITY")
        if bottom and support:
            bot_gold_diff = (bottom.get("goldDiff") or 0) + (support.get("goldDiff") or 0)

        snapshots.append({
            "minute": minute,
            "timestamp": timestamp,
            "teamGoldDiff": team_gold_diff,
            "myLaneGoldDiff": my_lane_gold_diff,
            "otherLanesGoldDiff": other_lanes_gold_diff,
            "myTeamKills": my_kills,
            "enemyTeamKills": enemy_kills,
            "killDiff": my_kills - enemy_kills,
            "botDuoGoldDiff": bot_gold_diff,
            "roles": roles,
        })

    final_roles = {role: final_role(participants, my_team, enemy_team, role) for role in ROLES}
    final_my_kills = sum(p.get("kills", 0) or 0 for p in participants if p.get("teamId") == my_team)
    final_enemy_kills = sum(p.get("kills", 0) or 0 for p in participants if p.get("teamId") == enemy_team)

    return {
        "matchId": (match.get("metadata") or {}).get("matchId"),
        "gameCreation": info.get("gameCreation"),
        "gameDuration": game_duration,
        "queueId": info.get("queueId"),
        "gameMode": info.get("gameMode"),
        "championName": me.get("championName"),
        "position": my_role,
        "opponent": opponent.get("championName") if opponent else None,
        "win": bool(me.get("win")),
        "snapshots": snapshots,
        "final": {
            "myTeamKills": final_my_kills,
            "enemyTeamKills": final_enemy_kills,
            "killDiff": final_my_kills - final_enemy_kills,
            "roles": final_roles,
        },
    }


def metric_payload(matches, champion, position, available_count):
    out = {
        "champion": champion,
        "position": position,
        "availableCount": available_count,
        "sampleCount": len(matches),
        "wins": sum(1 for m in matches if m.get("win")),
        "losses": sum(1 for m in matches if not m.get("win")),
        "snapshots": {},
    }
    for minute in SNAPSHOT_MINUTES:
        rows = []
        for m in matches:
            s = next((x for x in m.get("snapshots") or [] if x.get("minute") == minute), None)
            if s:
                rows.append(s)
        out["snapshots"][str(minute)] = {
            "sampleCount": len(rows),
            "avgTeamGoldDiff": avg([r.get("teamGoldDiff") for r in rows]),
            "avgMyLaneGoldDiff": avg([r.get("myLaneGoldDiff") for r in rows]),
            "avgOtherLanesGoldDiff": avg([r.get("otherLanesGoldDiff") for r in rows]),
            "avgKillDiff": avg([r.get("killDiff") for r in rows]),
            "avgTopGoldDiff": avg([(r.get("roles") or {}).get("TOP", {}).get("goldDiff") if (r.get("roles") or {}).get("TOP") else None for r in rows]),
            "avgJungleGoldDiff": avg([(r.get("roles") or {}).get("JUNGLE", {}).get("goldDiff") if (r.get("roles") or {}).get("JUNGLE") else None for r in rows]),
            "avgMidGoldDiff": avg([(r.get("roles") or {}).get("MIDDLE", {}).get("goldDiff") if (r.get("roles") or {}).get("MIDDLE") else None for r in rows]),
            "avgBotDuoGoldDiff": avg([r.get("botDuoGoldDiff") for r in rows]),
            "myLaneBehindTeamAhead": sum(1 for r in rows if isinstance(r.get("myLaneGoldDiff"), (int, float)) and r.get("myLaneGoldDiff") < 0 and r.get("teamGoldDiff", 0) > 0),
            "myLaneAheadTeamBehind": sum(1 for r in rows if isinstance(r.get("myLaneGoldDiff"), (int, float)) and r.get("myLaneGoldDiff") > 0 and r.get("teamGoldDiff", 0) < 0),
        }

    out["matches"] = []
    for m in matches:
        compact_snaps = []
        for s in m.get("snapshots") or []:
            roles = s.get("roles") or {}
            compact_snaps.append({
                "minute": s.get("minute"),
                "teamGoldDiff": s.get("teamGoldDiff"),
                "myLaneGoldDiff": s.get("myLaneGoldDiff"),
                "otherLanesGoldDiff": s.get("otherLanesGoldDiff"),
                "killDiff": s.get("killDiff"),
                "topGoldDiff": (roles.get("TOP") or {}).get("goldDiff"),
                "jungleGoldDiff": (roles.get("JUNGLE") or {}).get("goldDiff"),
                "midGoldDiff": (roles.get("MIDDLE") or {}).get("goldDiff"),
                "botDuoGoldDiff": s.get("botDuoGoldDiff"),
            })
        out["matches"].append({
            "matchId": m.get("matchId"),
            "opponent": m.get("opponent"),
            "win": m.get("win"),
            "durationMin": round((m.get("gameDuration") or 0) / 60, 1),
            "snapshots": compact_snaps,
        })
    return out


def main():
    found = base.find_archive()
    if not found:
        print("Could not find the local Riot archive for team-context generation.")
        return 2

    _, _, archive, matches_dir, timelines_dir = found
    puuid = None
    account_file = archive / "data" / "meta" / "account.json"
    if account_file.exists():
        try:
            puuid = base.read_json(account_file).get("puuid")
        except Exception:
            pass

    for path in (OUT_MATCHES, OUT_RECENT, OUT_METRICS):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    groups = defaultdict(list)
    built = 0
    files = sorted(matches_dir.glob("KR_*.json"))
    for idx, match_path in enumerate(files, 1):
        timeline_path = timelines_dir / match_path.name
        if not timeline_path.exists():
            continue
        try:
            match = base.read_json(match_path)
            timeline = base.read_json(timeline_path)
            context = build_match_context(match, timeline, puuid)
        except Exception:
            continue
        if not context:
            continue
        base.write_json(OUT_MATCHES / match_path.name, context)
        built += 1
        champ_slug = base.slugify(context.get("championName"))
        pos_slug = base.POSITION_SLUGS.get(context.get("position"), base.slugify(context.get("position") or "unknown"))
        groups[(champ_slug, "all")].append(context)
        groups[(champ_slug, pos_slug)].append(context)
        if idx % 50 == 0 or idx == len(files):
            print(f"Team context processed {idx}/{len(files)}")

    index = []
    for (champ, pos), rows in sorted(groups.items()):
        rows.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)
        recent = rows[:RECENT_LIMIT]
        name = f"{champ}_{pos}.json"
        base.write_json(OUT_RECENT / name, {
            "champion": champ,
            "position": pos,
            "availableCount": len(rows),
            "sampleCount": len(recent),
            "matches": recent,
        })
        base.write_json(OUT_METRICS / name, metric_payload(recent, champ, pos, len(rows)))
        index.append({"champion": champ, "position": pos, "file": name, "count": len(rows)})

    base.write_json(OUT_RECENT / "index.json", index)
    base.write_json(OUT_METRICS / "index.json", index)
    print(f"Team-context match files: {built}")
    print(f"Team-context analysis groups: {len(index)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
