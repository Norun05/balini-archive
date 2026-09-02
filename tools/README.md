# 발린이 아카이브 데이터 파이프라인

`update_site_data.bat`이 현재의 정식 진입점입니다. 새 기능은 가능한 한 이 배치 파일에 연결된 범용 생성기에서 관리합니다.

## 현재 정식 실행 순서

1. `merge_local_archives.py` — 로컬 `balini-lol-archive-v*` 원본 병합
2. `build_site_data_incremental.py` — 변경된 경기만 기본 상세 처리하고 카탈로그/챔피언 페이지 재생성
3. `build_mode_data.py` — `queueId + gameMode + gameVersion + 날짜`를 이용해 역사형 게임 모드/규칙 세대 분류
4. `enrich_timeline_incremental.py` — Riot ID, 전체 이벤트, 초반 스냅샷, 동선 등 타임라인 증분 보강
5. `add_item_names_ko.py` — 한국어 아이템명 보강
6. `build_item_economy.py` — 10인 아이템 구매 흐름/코어 완성 추정
7. `build_team_context_incremental.py` — 팀/라인별 골드 및 킬 맥락 증분 보강
8. `build_stats.py` — 전체 모드 범용 챔피언/포지션/매치업/소환사 주문 통계(명시적인 '전체 모드' 조회용)
9. `build_item_stats.py` — 전체 모드 1/2코어 완성 시각 통계(명시적인 '전체 모드' 조회용)
10. `build_player_stats.py` — 함께한 플레이어/듀오 조합 상세 통계
11. `build_search_index.py` — AI용 기본 검색 라우터
12. `build_mode_stats.py` — 모드별/규칙 세대별 통계와 AI 모드 라우터 생성
13. `build_kennen_skill_order.py` — 케넨 스킬 오더 특화 분석(범용 통계로 대체되지 않는 보조 분석)
14. `validate_generated_data.py` — 생성 결과 정합성 검증

## 게임 모드 분리 원칙

`queueId` 하나만 현재 이름표에 대입하지 않습니다. Riot 큐 ID는 시대에 따라 재사용되거나 의미가 바뀔 수 있으므로 `gameMode`, `gameVersion`, 경기 날짜와 함께 해석합니다.

주요 생성 필드:

- `modeKey` / `modeNameKo` — 사람이 고르는 큰 게임 모드
- `rulesetKey` / `rulesetNameKo` — 같은 이름의 모드 안에서 규칙이 크게 달라진 세대
- `isStandardRift` — 일반적인 소환사의 협곡 규칙인지
- `hasStandardPositions` — 탑/정글/미드/바텀/서포터 포지션 통계를 적용할 수 있는지
- `queueSignature` — 원본 `queueId|gameMode` 확인용

예를 들어 신속 대전은 UI에서는 하나의 모드로 묶을 수 있지만, 경제/오브젝트 규칙이 크게 달라진 `swiftplay_2025`와 `swiftplay_2026`은 AI 분석용 통계에서 별도 ruleset으로도 생성합니다. 아레나도 1700/1710/1750 세대를 분리할 수 있습니다.

`gameMode: CLASSIC`은 Riot Match-V5의 오래된 일반 게임모드 값이며 2026년에 출시된 제품 모드 'League Classic'을 뜻하지 않습니다.

## AI가 통계를 읽는 순서

챔피언, 라인, 매치업, 1코어/2코어, 소환사 주문 같은 분석을 할 때는 **모드를 먼저 결정한 뒤** 통계를 엽니다.

1. `data/search/modes.json`에서 요청한 모드/규칙 세대를 찾습니다.
2. 사용자가 모드를 말하지 않은 일반적인 협곡 분석은 `defaultAnalysisMode`인 `standard_rift`를 우선합니다.
3. 해당 라우트가 가리키는 `data/stats/by-mode/...` 파일을 읽습니다.
4. '2025 신속', '3인 아레나'처럼 규칙 세대를 구분한 질문이면 `rulesetRoutes`와 `data/stats/by-ruleset/...`을 사용합니다.
5. 사용자가 명시적으로 '전체 모드'라고 요청한 경우에만 기존 `data/stats/*.json` 전체 합산 통계를 우선합니다.
6. 더 깊은 경기 검토가 필요할 때만 선택된 Match ID의 `data/matches/{matchId}.json`을 엽니다.

특히 일반 협곡 챔피언/아이템 분석에 아레나·칼바람·우르프·신속 데이터를 섞지 않습니다. 특수 모드에서 표준 라인이 없는 경우 `Invalid`를 라인으로 해석하지 않습니다.

## 구형/비정식 스크립트

아래 파일들은 과거 실험·전용 분석용으로 남아 있을 수 있지만 `update_site_data.bat`의 정식 파이프라인에는 포함하지 않습니다.

- `build_ai_indexes.py`
- `build_ai_compact.py`
- `build_recent20_indexes.py`
- `build_metrics20.py`
- `build_role_matchup_index.py`
- `build_kennen_build_stats.py`
- `build_kennen_firstcore_profile.py`

**AI는 위 구형 스크립트가 만든 전용/과거 결과물을 현재 통계의 우선 출처로 사용하지 않습니다.** 새 기능을 추가할 때도 위 구형 파일에 기능을 덧붙이기보다 `build_stats.py`, `build_search_index.py`, `build_mode_stats.py`, 또는 별도의 범용 후처리기를 우선 사용합니다.

## 검증 결과

정상 실행이 끝나면 `data/validation.json`이 생성됩니다.

- `ok: true` — 치명적인 정합성 오류 없음
- `errors` — 배치를 실패시키는 문제
- `warnings` — 데이터 특성상 발생할 수 있어 빌드를 멈추지는 않는 문제

검증기는 경기 수 일치, 모드 분류 누락, 모드 통계/검색 라우트, 최신 경기의 Riot ID/소환사 주문/전체 이벤트/초반 스냅샷/동선/아이템 경제, 그리고 검색 라우트가 실제 파일을 가리키는지 일부 샘플을 확인합니다.

## 데이터 해석 원칙

- Match-V5에 직접 있는 값은 사실로 저장합니다.
- 위치 스냅샷 사이의 큰 이동은 `largeDisplacement` 휴리스틱일 뿐 텔레포트/쉔 궁/귀환으로 확정하지 않습니다.
- Riot이 제공하는 Q/W/E/R 및 소환사 주문의 총 사용 횟수와 개별 사용 시각은 구분합니다. 총 횟수 필드가 있어도 시각을 임의 생성하지 않습니다.
- 1/2코어는 아이템 트리와 가격을 이용한 추정치이며, 모드/규칙 세대가 다른 경기를 섞어 비교하지 않습니다.
- Riot이 제공하지 않는 임의 스킬/소환사 주문의 정확한 시전 시각은 만들어내지 않습니다.
