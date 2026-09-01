import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "data" / ".incremental"


def read_json(path: Path, default=None):
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {} if default is None else default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_signature(path: Path | None):
    if path is None or not path.exists():
        return None
    stat = path.stat()
    return {"size": stat.st_size, "mtimeNs": stat.st_mtime_ns}


def source_signature(match_path: Path | None, timeline_path: Path | None = None):
    return {
        "match": file_signature(match_path),
        "timeline": file_signature(timeline_path),
    }


def cache_path(stage: str):
    return STATE_DIR / f"{stage}.json"


def load_stage(stage: str):
    payload = read_json(cache_path(stage), {})
    return payload if isinstance(payload, dict) else {}


def save_stage(stage: str, signatures: dict):
    write_json(cache_path(stage), {
        "schemaVersion": 1,
        "stage": stage,
        "signatures": signatures,
    })


def cached_signatures(stage: str):
    payload = load_stage(stage)
    rows = payload.get("signatures") or {}
    return rows if isinstance(rows, dict) else {}


def output_is_newer(output_path: Path, *source_paths: Path | None):
    if not output_path.exists():
        return False
    try:
        output_mtime = output_path.stat().st_mtime_ns
        source_mtimes = [p.stat().st_mtime_ns for p in source_paths if p is not None and p.exists()]
    except OSError:
        return False
    return bool(source_mtimes) and output_mtime >= max(source_mtimes)


def unchanged(stage: str, key: str, signature: dict, output_path: Path | None = None, bootstrap_ok=False):
    old = cached_signatures(stage).get(key)
    if old == signature:
        return output_path is None or output_path.exists()
    if old is None and bootstrap_ok and output_path is not None:
        return output_is_newer(output_path)
    return False
