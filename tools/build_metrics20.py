import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "ai" / "summary20"
OUT = ROOT / "data" / "ai" / "metrics20"


def avg(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def med(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.median(values), 2) if values else None


def snap(match, minute):
    for s in match.get("snapshots") or []:
        if s.get("minute") == minute:
            return s
    return {}


def mins(ms):
    return round(ms / 60000, 2) if isinstance(ms, (int, float)) else None


def build_metrics(payload):
    matches = payload.get("matches") or []
    wins = [m for m in matches if m.get("win")]
    losses = [m for m in matches if not m.get("win")]
    out = {
        "champion": payload.get("champion"),
        "position": payload.get("position"),
        "availableCount": payload.get("availableCount"),
        "sampleCount": len(matches),
        "wins": len(wins),
        "losses": len(losses),
        "winRate": round(len(wins) / len(matches), 4) if matches else None,
        "snapshots": {},
    }
    for minute in (5, 10, 15, 20):
        rows = [snap(m, minute) for m in matches]
        gold = [r.get("goldDiff") for r in rows if r]
        cs = [r.get("csDiff") for r in rows if r]
        lvl = [r.get("levelDiff") for r in rows if r]
        out["snapshots"][str(minute)] = {
            "sampleCount": len(gold),
            "avgGoldDiff": avg(gold),
            "medianGoldDiff": med(gold),
            "goldAhead": sum(1 for v in gold if v > 0),
            "goldBehind": sum(1 for v in gold if v < 0),
            "avgCsDiff": avg(cs),
            "medianCsDiff": med(cs),
            "csAhead": sum(1 for v in cs if v > 0),
            "csBehind": sum(1 for v in cs if v < 0),
            "avgLevelDiff": avg(lvl),
        }

    def split_stats(group):
        return {
            "count": len(group),
            "avg10GoldDiff": avg([snap(m, 10).get("goldDiff") for m in group]),
            "avg15GoldDiff": avg([snap(m, 15).get("goldDiff") for m in group]),
            "avg20GoldDiff": avg([snap(m, 20).get("goldDiff") for m in group]),
            "avg10CsDiff": avg([snap(m, 10).get("csDiff") for m in group]),
            "avg15CsDiff": avg([snap(m, 15).get("csDiff") for m in group]),
            "avg20CsDiff": avg([snap(m, 20).get("csDiff") for m in group]),
            "avgFirstDeathMin": avg([mins(m.get("firstDeathTimestamp")) for m in group]),
            "avgFirstKillMin": avg([mins(m.get("firstKillTimestamp")) for m in group]),
        }
    out["winsStats"] = split_stats(wins)
    out["lossesStats"] = split_stats(losses)

    death_minutes = [mins(m.get("firstDeathTimestamp")) for m in matches]
    death_minutes = [v for v in death_minutes if v is not None]
    out["firstDeath"] = {
        "noDeath": sum(1 for m in matches if m.get("firstDeathTimestamp") is None),
        "avgMinute": avg(death_minutes),
        "before5": sum(1 for v in death_minutes if v < 5),
        "before8": sum(1 for v in death_minutes if v < 8),
        "before10": sum(1 for v in death_minutes if v < 10),
        "before15": sum(1 for v in death_minutes if v < 15),
    }

    transitions = {
        "ahead10_to_behind15": 0,
        "behind10_to_ahead15": 0,
        "ahead15_but_loss": 0,
        "behind15_but_win": 0,
        "ahead10_by300_plus": 0,
        "behind10_by300_plus": 0,
        "ahead15_by500_plus": 0,
        "behind15_by500_plus": 0,
    }
    rows = []
    for m in matches:
        s10 = snap(m, 10)
        s15 = snap(m, 15)
        s20 = snap(m, 20)
        g10 = s10.get("goldDiff")
        g15 = s15.get("goldDiff")
        if isinstance(g10, (int, float)) and isinstance(g15, (int, float)):
            if g10 > 0 and g15 < 0:
                transitions["ahead10_to_behind15"] += 1
            if g10 < 0 and g15 > 0:
                transitions["behind10_to_ahead15"] += 1
            if g10 >= 300:
                transitions["ahead10_by300_plus"] += 1
            if g10 <= -300:
                transitions["behind10_by300_plus"] += 1
            if g15 >= 500:
                transitions["ahead15_by500_plus"] += 1
            if g15 <= -500:
                transitions["behind15_by500_plus"] += 1
        if isinstance(g15, (int, float)):
            if g15 > 0 and not m.get("win"):
                transitions["ahead15_but_loss"] += 1
            if g15 < 0 and m.get("win"):
                transitions["behind15_but_win"] += 1
        rows.append({
            "matchId": m.get("matchId"),
            "opponent": m.get("opponent"),
            "win": m.get("win"),
            "kda": [m.get("kills"), m.get("deaths"), m.get("assists")],
            "durationMin": round((m.get("gameDuration") or 0) / 60, 1),
            "firstDeathMin": mins(m.get("firstDeathTimestamp")),
            "firstKillMin": mins(m.get("firstKillTimestamp")),
            "g5": snap(m, 5).get("goldDiff"),
            "cs5": snap(m, 5).get("csDiff"),
            "g10": g10,
            "cs10": s10.get("csDiff"),
            "g15": g15,
            "cs15": s15.get("csDiff"),
            "g20": s20.get("goldDiff"),
            "cs20": s20.get("csDiff"),
            "soloKills": m.get("soloKills"),
            "teamDamagePercentage": m.get("teamDamagePercentage"),
        })
    out["transitions"] = transitions
    out["matches"] = rows
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    built = 0
    for path in sorted(SRC.glob("*.json")):
        if path.name == "index.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        metrics = build_metrics(payload)
        (OUT / path.name).write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        built += 1
    print(f"Metrics-20 indexes ready: {built} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
