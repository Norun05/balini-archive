import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERGED = ROOT / "data" / "_merged_archive"
MERGED_MATCHES = MERGED / "data" / "raw" / "matches"
MERGED_TIMELINES = MERGED / "data" / "raw" / "timelines"
MERGED_META = MERGED / "data" / "meta"
INDEX_PATH = MERGED_META / "merge-index.json"


def version_number(path: Path) -> int:
    m = re.search(r"-v(\d+)$", path.name, flags=re.I)
    return int(m.group(1)) if m else 0


def discover_archives():
    found = []
    seen = set()
    for base in [ROOT, *ROOT.parents]:
        try:
            dirs = list(base.glob("balini-lol-archive-v*")) + list(base.glob("balini-lol-archive"))
        except OSError:
            continue
        for archive in dirs:
            matches = archive / "data" / "raw" / "matches"
            timelines = archive / "data" / "raw" / "timelines"
            if not matches.is_dir():
                continue
            key = str(matches.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append({
                "archive": archive,
                "matches": matches,
                "timelines": timelines,
                "version": version_number(archive),
            })
    return found


def candidate_score(match_path: Path, timeline_path: Path, version: int):
    timeline_exists = timeline_path.exists()
    timeline_size = timeline_path.stat().st_size if timeline_exists else 0
    match_size = match_path.stat().st_size if match_path.exists() else 0
    return (1 if timeline_exists else 0, timeline_size, match_size, version)


def copy_if_needed(src: Path, dst: Path):
    if dst.exists():
        try:
            if dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime_ns == src.stat().st_mtime_ns:
                return False
        except OSError:
            pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def remove_stale(directory: Path, keep_names: set[str]):
    if not directory.exists():
        return 0
    removed = 0
    for path in directory.glob("KR_*.json"):
        if path.name not in keep_names:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def main():
    archives = discover_archives()
    if not archives:
        print("No local balini-lol-archive-v* archives found.")
        return 2

    MERGED_MATCHES.mkdir(parents=True, exist_ok=True)
    MERGED_TIMELINES.mkdir(parents=True, exist_ok=True)
    MERGED_META.mkdir(parents=True, exist_ok=True)

    best = {}
    source_counts = {}
    for info in archives:
        archive = info["archive"]
        matches = info["matches"]
        timelines = info["timelines"]
        version = info["version"]
        source_counts[archive.name] = 0
        for match_path in matches.glob("KR_*.json"):
            timeline_path = timelines / match_path.name
            score = candidate_score(match_path, timeline_path, version)
            current = best.get(match_path.name)
            if current is None or score > current["score"]:
                best[match_path.name] = {
                    "match": match_path,
                    "timeline": timeline_path if timeline_path.exists() else None,
                    "archive": archive,
                    "score": score,
                }

    keep = set(best)
    removed_matches = remove_stale(MERGED_MATCHES, keep)
    keep_timelines = {name for name, row in best.items() if row["timeline"] is not None}
    removed_timelines = remove_stale(MERGED_TIMELINES, keep_timelines)

    copied_matches = 0
    copied_timelines = 0
    timeline_count = 0
    for name, row in best.items():
        if copy_if_needed(row["match"], MERGED_MATCHES / name):
            copied_matches += 1
        if row["timeline"] is not None:
            timeline_count += 1
            if copy_if_needed(row["timeline"], MERGED_TIMELINES / name):
                copied_timelines += 1
        source_counts[row["archive"].name] = source_counts.get(row["archive"].name, 0) + 1

    # Use account metadata from the highest-version archive that has it.
    account_candidates = []
    for info in archives:
        account = info["archive"] / "data" / "meta" / "account.json"
        if account.exists():
            account_candidates.append((info["version"], account))
    if account_candidates:
        account_candidates.sort(reverse=True, key=lambda x: x[0])
        copy_if_needed(account_candidates[0][1], MERGED_META / "account.json")

    index = {
        "schemaVersion": 1,
        "archiveCount": len(archives),
        "matchCount": len(best),
        "timelineCount": timeline_count,
        "sources": [
            {
                "name": info["archive"].name,
                "version": info["version"],
                "matchCount": sum(1 for _ in info["matches"].glob("KR_*.json")),
                "selectedCount": source_counts.get(info["archive"].name, 0),
            }
            for info in sorted(archives, key=lambda x: (x["version"], x["archive"].name))
        ],
        "selectionRule": "Prefer duplicate source with timeline; then larger timeline JSON; then larger match JSON; then higher archive version.",
        "generatedPath": "data/_merged_archive/data/raw",
    }
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Archives merged: {len(archives)}")
    print(f"Unique matches: {len(best)}")
    print(f"Matches with timelines: {timeline_count}")
    print(f"Copied/updated matches: {copied_matches}")
    print(f"Copied/updated timelines: {copied_timelines}")
    print(f"Removed stale files: {removed_matches + removed_timelines}")
    print(f"Merged archive: {MERGED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
