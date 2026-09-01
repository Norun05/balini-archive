# 발린이 아카이브 갱신 방법

1. GitHub Desktop에서 이 저장소를 열고 **Fetch origin / Pull origin**으로 최신 파일을 받습니다.
2. 저장소 폴더의 `update_site_data.bat`을 더블클릭합니다.
3. 프로그램이 근처의 `balini-lol-archive-v* / data/raw/matches`와 `timelines`를 자동으로 찾아 현재까지 저장된 Riot 경기 JSON을 읽습니다.
4. 완료되면 사이트용 데이터가 아래 구조로 다시 생성됩니다.

```text
data/
├─ profile.json
├─ manifest.json
├─ catalog.json
├─ champions/
│  ├─ index.json
│  └─ kennen/
│     ├─ all/
│     │  ├─ recent.json
│     │  └─ page-001.json ...
│     └─ top/
│        ├─ recent.json
│        └─ page-001.json ...
└─ matches/
   ├─ KR_xxxxxxxxxx.json
   └─ ...
```

- `catalog.json` — 사이트 첫 화면과 빠른 전체 검색용. 경기당 최소 정보만 들어갑니다.
- `champions/index.json` — 챔피언/포지션별 분석 파일 위치와 경기 수를 알려주는 색인입니다.
- `champions/<champion>/<position>/recent.json` — 해당 챔피언/포지션의 최근 최대 50경기 분석용 요약입니다. 예: `champions/kennen/top/recent.json`.
- `champions/<champion>/<position>/page-001.json` — 오래된 경기까지 볼 때 쓰는 50경기 단위 페이지입니다.
- `matches/KR_....json` — 한 경기의 팀 조합, 라인 상대, 5/10/15/20분 스냅샷, 사용자 관여 킬/아이템/오브젝트 이벤트를 담은 상세 요약입니다.
- 정글 포지션이거나 강타를 든 경기의 `matches/KR_....json`에는 `timeline.movementSnapshots`도 추가됩니다. Riot Timeline의 약 1분 간격 참가자 프레임에서 `timestamp`, `minute`, `x`, `y`, `jungleCs`, `laneCs`, `level`, `xp`만 추려 이동 경로 분석용으로 저장합니다. 원본 Timeline 전체를 GitHub에 올리지는 않습니다.
- 아이템 이벤트에는 Riot Data Dragon의 한국어 이름이 `itemNameKo`로 함께 저장됩니다. `ITEM_UNDO`처럼 이전/이후 아이템 ID가 있는 이벤트는 `beforeItemNameKo`, `afterItemNameKo`도 추가됩니다. 참가자의 최종 아이템 배열에도 같은 순서의 `itemNamesKo`가 붙습니다. 숫자 `itemId`는 원본 대조와 통계를 위해 그대로 유지합니다.
- 아이템 이름은 각 경기의 `gameVersion`에 맞는 Data Dragon 버전을 우선 사용합니다. 처음 한 번 받은 한국어 아이템 사전은 로컬 원본 아카이브의 `data/meta/ddragon-items-ko`에 캐시하므로 GitHub에는 무거운 사전 파일을 올리지 않습니다.
- `profile.json` — 마지막 갱신 시각과 경기 수입니다.
- `manifest.json` — 데이터 구조 버전과 변환 오류 개수입니다. 이동 경로와 한국어 아이템 이름을 만든 뒤에는 관련 생성 건수와 알 수 없는 아이템 ID 수도 함께 기록됩니다.

기존의 거대한 `data/matches.json`은 새 구조에서는 사용하지 않으며, 변환기가 자동으로 삭제합니다.

5. GitHub Desktop에서 생성/수정/삭제된 파일을 모두 Commit한 뒤 **Push origin**을 누릅니다.
6. GitHub Pages가 자동으로 다시 배포합니다.

## 사이트는 어떻게 읽나요?

사이트는 처음에 `catalog.json`만 읽습니다. 경기 카드를 클릭했을 때만 해당 `matches/KR_....json`을 추가로 불러옵니다. 그래서 전체 타임라인 요약을 한 번에 내려받지 않습니다.

## AI가 분석할 때는?

예를 들어 "최근 케넨 탑 20판"은 먼저 `data/champions/kennen/top/recent.json` 하나만 읽으면 됩니다. 특정 한 판을 더 깊게 볼 필요가 있을 때만 그 경기의 `data/matches/KR_....json`을 읽습니다.

정글 동선을 분석할 때는 해당 경기의 `data/matches/KR_....json` 안 `timeline.movementSnapshots`를 킬/어시/오브젝트 이벤트와 함께 보면 됩니다. 챔피언별 50경기 묶음에는 이동 스냅샷을 중복 저장하지 않아 파일 크기 증가를 줄입니다.

아이템 구매 기록을 읽을 때는 `itemId` 대신 함께 저장된 `itemNameKo`를 우선 표시하면 됩니다. 예: `3067`과 `itemNameKo: "점화석"`이 함께 있으면 분석 문장에는 "점화석 구매"라고 적습니다.

## 원본은 어디에 있나요?

무거운 Match/Timeline 원본 JSON은 로컬의 `balini-lol-archive-v*` 폴더에만 남깁니다. GitHub에는 가공된 요약 데이터만 올립니다.

## 새 게임을 한 뒤에는?

먼저 Riot 수집기를 실행해 새 원본 경기를 받은 뒤 `update_site_data.bat`을 실행하고 Push하면 됩니다.
