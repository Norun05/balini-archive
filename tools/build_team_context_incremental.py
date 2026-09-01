import shutil
from collections import defaultdict

import build_site_data as base
import build_team_context as team
import incremental_state as inc

STAGE = "team_context"


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

    team.OUT_MATCHES.mkdir(parents=True, exist_ok=True)
    old_signatures = inc.cached_signatures(STAGE)
    new_signatures = {}
    processed = 0
    skipped = 0
    missing = 0

    files = sorted(matches_dir.glob("KR_*.json"))
    source_names = set()
    total = len(files)
    for idx, match_path in enumerate(files, 1):
        timeline_path = timelines_dir / match_path.name
        if not timeline_path.exists():
            missing += 1
            continue
        source_names.add(match_path.name)
        output_path = team.OUT_MATCHES / match_path.name
        sig = inc.source_signature(match_path, timeline_path)
        new_signatures[match_path.stem] = sig

        can_skip = old_signatures.get(match_path.stem) == sig and output_path.exists()
        if not can_skip and match_path.stem not in old_signatures and output_path.exists():
            can_skip = inc.output_is_newer(output_path, match_path, timeline_path)

        if can_skip:
            skipped += 1
        else:
            try:
                match = base.read_json(match_path)
                timeline = base.read_json(timeline_path)
                context = team.build_match_context(match, timeline, puuid)
            except Exception as exc:
                print(f"  WARN {match_path.stem}: {type(exc).__name__}")
                missing += 1
                continue
            if not context:
                missing += 1
                continue
            base.write_json(output_path, context)
            processed += 1

        if idx % 100 == 0 or idx == total:
            print(f"Team context checked {idx}/{total} (processed {processed}, skipped {skipped})")

    removed = 0
    for path in team.OUT_MATCHES.glob("KR_*.json"):
        if path.name not in source_names:
            path.unlink(missing_ok=True)
            removed += 1

    for path in (team.OUT_RECENT, team.OUT_METRICS):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    groups = defaultdict(list)
    built = 0
    for path in sorted(team.OUT_MATCHES.glob("KR_*.json")):
        try:
            context = base.read_json(path)
        except Exception:
            continue
        built += 1
        champ_slug = base.slugify(context.get("championName"))
        pos_slug = base.POSITION_SLUGS.get(context.get("position"), base.slugify(context.get("position") or "unknown"))
        groups[(champ_slug, "all")].append(context)
        groups[(champ_slug, pos_slug)].append(context)

    index = []
    for (champ, pos), rows in sorted(groups.items()):
        rows.sort(key=lambda x: x.get("gameCreation") or 0, reverse=True)
        recent = rows[:team.RECENT_LIMIT]
        name = f"{champ}_{pos}.json"
        base.write_json(team.OUT_RECENT / name, {
            "champion": champ,
            "position": pos,
            "availableCount": len(rows),
            "sampleCount": len(recent),
            "matches": recent,
        })
        base.write_json(team.OUT_METRICS / name, team.metric_payload(recent, champ, pos, len(rows)))
        index.append({"champion": champ, "position": pos, "file": name, "count": len(rows)})

    base.write_json(team.OUT_RECENT / "index.json", index)
    base.write_json(team.OUT_METRICS / "index.json", index)
    inc.save_stage(STAGE, new_signatures)

    print(f"Team-context processed: {processed}")
    print(f"Team-context skipped: {skipped}")
    print(f"Team-context total reusable files: {built}")
    print(f"Team-context missing/unreadable: {missing}")
    print(f"Stale team-context files removed: {removed}")
    print(f"Analysis groups rebuilt: {len(index)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
