from __future__ import annotations

from datetime import datetime, timezone


STANDARD_POSITION_MODES = {
    "normal_draft",
    "normal_blind",
    "quickplay",
    "ranked_solo",
    "ranked_flex",
    "swiftplay",
    "clash",
}

STANDARD_RIFT_RULE_MODES = {
    "normal_draft",
    "normal_blind",
    "quickplay",
    "ranked_solo",
    "ranked_flex",
    "clash",
}


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _game_year(game_creation):
    value = _as_int(game_creation)
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).year
    except (OSError, OverflowError, ValueError):
        return None


def _version_major(game_version):
    if not game_version:
        return None
    first = str(game_version).split(".", 1)[0]
    return int(first) if first.isdigit() else None


def _result(
    key,
    name_ko,
    family,
    *,
    queue_id,
    game_mode,
    ruleset_key=None,
    ruleset_name_ko=None,
    is_standard_rift=False,
    has_standard_positions=False,
    confidence="high",
):
    return {
        "modeKey": key,
        "modeNameKo": name_ko,
        "modeFamily": family,
        "rulesetKey": ruleset_key or key,
        "rulesetNameKo": ruleset_name_ko or name_ko,
        "isStandardRift": bool(is_standard_rift),
        "hasStandardPositions": bool(has_standard_positions),
        "modeConfidence": confidence,
        "queueSignature": f"{queue_id if queue_id is not None else 'null'}|{game_mode or 'UNKNOWN'}",
    }


def classify_mode(*, queue_id=None, game_mode=None, map_id=None, game_version=None, game_creation=None):
    """Normalize Riot queue/gameMode values into stable archive-facing mode labels.

    queueId is not treated as globally timeless. gameMode is checked first for
    known reused/alternate IDs (notably observed Swiftplay queue 890).
    """
    q = _as_int(queue_id)
    gm = str(game_mode or "").strip().upper()
    major = _version_major(game_version)
    year = _game_year(game_creation)

    if gm == "SWIFTPLAY":
        modern = (major is not None and major >= 16) or (major is None and year is not None and year >= 2026)
        return _result(
            "swiftplay",
            "신속 대전",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            ruleset_key="swiftplay_2026" if modern else "swiftplay_2025",
            ruleset_name_ko="신속 대전 (2026 규칙)" if modern else "신속 대전 (기존 규칙)",
            has_standard_positions=True,
            confidence="high" if q in (480, 890) else "medium",
        )

    if gm == "CHERRY" or q in (1700, 1710, 1750):
        if q == 1750:
            ruleset_key = "arena_1750"
            ruleset_name = "아레나 (3인 팀 규칙)"
        elif q == 1710:
            ruleset_key = "arena_1710"
            ruleset_name = "아레나 (확장 규칙)"
        else:
            ruleset_key = "arena_1700"
            ruleset_name = "아레나 (기존 규칙)"
        return _result(
            "arena",
            "아레나",
            "arena",
            queue_id=q,
            game_mode=gm,
            ruleset_key=ruleset_key,
            ruleset_name_ko=ruleset_name,
            has_standard_positions=False,
        )

    if q == 2400:
        return _result(
            "aram_mayhem",
            "증강 칼바람",
            "aram",
            queue_id=q,
            game_mode=gm,
            has_standard_positions=False,
        )

    if q == 450 or gm == "ARAM":
        return _result(
            "aram",
            "칼바람 나락",
            "aram",
            queue_id=q,
            game_mode=gm,
            has_standard_positions=False,
            confidence="high" if q == 450 else "medium",
        )

    if gm == "URF" or q in (900, 1900):
        if q == 900:
            key, name = "arurf", "무작위 우르프"
        elif q == 1900:
            key, name = "pick_urf", "우르프 (선택)"
        else:
            key, name = "urf", "우르프"
        return _result(
            key,
            name,
            "urf",
            queue_id=q,
            game_mode=gm,
            has_standard_positions=False,
            confidence="high" if q in (900, 1900) else "medium",
        )

    if q == 400:
        return _result(
            "normal_draft",
            "일반 · 교차 선택",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            is_standard_rift=True,
            has_standard_positions=True,
        )

    if q == 420:
        return _result(
            "ranked_solo",
            "솔로/듀오 랭크",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            is_standard_rift=True,
            has_standard_positions=True,
        )

    if q == 440:
        return _result(
            "ranked_flex",
            "자유 랭크",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            is_standard_rift=True,
            has_standard_positions=True,
        )

    if q == 490:
        return _result(
            "quickplay",
            "빠른 대전 (Quickplay)",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            ruleset_key="quickplay_legacy",
            ruleset_name_ko="빠른 대전 (구 규칙)",
            is_standard_rift=True,
            has_standard_positions=True,
        )

    if q == 430:
        return _result(
            "normal_blind",
            "일반 · 블라인드 픽",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            is_standard_rift=True,
            has_standard_positions=True,
        )

    if q == 700:
        return _result(
            "clash",
            "격전",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            is_standard_rift=True,
            has_standard_positions=True,
        )

    if q in (830, 840, 850, 870, 880, 890):
        return _result(
            "bot",
            "AI 상대 대전",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            ruleset_key=f"bot_{q}",
            ruleset_name_ko=f"AI 상대 대전 ({q})",
            has_standard_positions=False,
            confidence="medium",
        )

    if gm == "CLASSIC" and _as_int(map_id) == 11:
        return _result(
            "rift_other",
            "소환사의 협곡 · 기타",
            "summoners_rift",
            queue_id=q,
            game_mode=gm,
            has_standard_positions=True,
            confidence="low",
        )

    key = f"unknown_{q}" if q is not None else "unknown"
    return _result(
        key,
        f"기타 모드 ({q if q is not None else gm or 'UNKNOWN'})",
        "other",
        queue_id=q,
        game_mode=gm,
        has_standard_positions=False,
        confidence="low",
    )


def classify_detail(detail):
    return classify_mode(
        queue_id=detail.get("queueId"),
        game_mode=detail.get("gameMode"),
        map_id=detail.get("mapId"),
        game_version=detail.get("gameVersion"),
        game_creation=detail.get("gameCreation"),
    )
