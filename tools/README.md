# 발린이 아카이브 데이터 파이프라인

`update_site_data.bat`이 현재의 정식 진입점입니다. 새 기능은 가능한 한 이 배치 파일에 연결된 범용 생성기에서 관리합니다.

## 현재 정식 실행 순서

1. `merge_local_archives.py` — 로컬 `balini-lol-archive-v*` 원본 병합
2. `build_site_data.py` — 기본 경기 상세/카탈로그/챔피언 페이지 생성
3. `enrich_full_events.py` — Riot ID, 소환사 주문, 전체 킬/아이템/스킬업 이벤트 보존
4. `enrich_early_laning.py` — 2/3/4/5/6/8/10/15/20분 라인전 스냅샷
5. `add_movement_snapshots.py` — 전 포지션 약 1분 위치 스냅샷/큰 이동 표시
6. `add_item_names_ko.py` — 한국어 아이템명 보강
7. `build_item_economy.py` — 10인 아이템 구매 흐름/코어 완성 추정
8. `build_team_context.py` — 팀/라인별 골드 및 킬 맥락
9. `build_stats.py` — 범용 챔피언/포지션/매치업/소환사 주문 통계
10. `build_item_stats.py` — 1/2코어 완성 시각 통계
11. `build_player_stats.py` — 함께한 플레이어/듀오 조합 상세 통계
12. `build_search_index.py` — AI용 초소형 검색 라우터
13. `build_kennen_skill_order.py` — 케넨 스킬 오더 특화 분석(범용 통계로 대체되지 않는 보조 분석)
14. `validate_generated_data.py` — 생성 결과 정합성 검증

## 구형/비정식 스크립트

아래 파일들은 과거 실험·전용 분석용으로 남아 있을 수 있지만 `update_site_data.bat`의 정식 파이프라인에는 포함하지 않습니다.

- `build_ai_indexes.py`
- `build_ai_compact.py`
- `build_recent20_indexes.py`
- `build_metrics20.py`
- `build_role_matchup_index.py`
- `build_kennen_build_stats.py`
- `build_kennen_firstcore_profile.py`

새 기능을 추가할 때는 위 구형 파일에 기능을 덧붙이기보다 `build_stats.py`, `build_search_index.py`, 또는 별도의 범용 후처리기를 우선 사용합니다.

## 검증 결과

정상 실행이 끝나면 `data/validation.json`이 생성됩니다.

- `ok: true` — 치명적인 정합성 오류 없음
- `errors` — 배치를 실패시키는 문제
- `warnings` — 데이터 특성상 발생할 수 있어 빌드를 멈추지는 않는 문제

검증기는 경기 수 일치, 최신 경기의 Riot ID/소환사 주문/전체 이벤트/초반 스냅샷/동선/아이템 경제, 그리고 검색 라우트가 실제 파일을 가리키는지 일부 샘플을 확인합니다.

## 데이터 해석 원칙

- Match-V5에 직접 있는 값은 사실로 저장합니다.
- 위치 스냅샷 사이의 큰 이동은 `largeDisplacement` 휴리스틱일 뿐 텔레포트/쉔 궁으로 확정하지 않습니다.
- 1/2코어는 아이템 트리와 가격을 이용한 추정치입니다.
- Riot이 제공하지 않는 임의 스킬/소환사 주문의 정확한 시전 시각은 만들어내지 않습니다.
