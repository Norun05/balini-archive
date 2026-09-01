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
- `profile.json` — 마지막 갱신 시각과 경기 수입니다.
- `manifest.json` — 데이터 구조 버전과 변환 오류 개수입니다.

기존의 거대한 `data/matches.json`은 새 구조에서는 사용하지 않으며, 변환기가 자동으로 삭제합니다.

5. GitHub Desktop에서 생성/수정/삭제된 파일을 모두 Commit한 뒤 **Push origin**을 누릅니다.
6. GitHub Pages가 자동으로 다시 배포합니다.

## 사이트는 어떻게 읽나요?

사이트는 처음에 `catalog.json`만 읽습니다. 경기 카드를 클릭했을 때만 해당 `matches/KR_....json`을 추가로 불러옵니다. 그래서 전체 타임라인 요약을 한 번에 내려받지 않습니다.

## AI가 분석할 때는?

예를 들어 "최근 케넨 탑 20판"은 먼저 `data/champions/kennen/top/recent.json` 하나만 읽으면 됩니다. 특정 한 판을 더 깊게 볼 필요가 있을 때만 그 경기의 `data/matches/KR_....json`을 읽습니다.

## 원본은 어디에 있나요?

무거운 Match/Timeline 원본 JSON은 로컬의 `balini-lol-archive-v*` 폴더에만 남깁니다. GitHub에는 가공된 요약 데이터만 올립니다.

## 새 게임을 한 뒤에는?

먼저 Riot 수집기를 실행해 새 원본 경기를 받은 뒤 `update_site_data.bat`을 실행하고 Push하면 됩니다.
