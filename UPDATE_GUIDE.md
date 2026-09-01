# 발린이 아카이브 갱신 방법

1. GitHub Desktop에서 이 저장소를 열고 **Fetch origin / Pull origin**으로 최신 파일을 받습니다.
2. 저장소 폴더의 `update_site_data.bat`을 더블클릭합니다.
3. 프로그램이 근처의 `balini-lol-archive-v* / data/raw/matches`를 자동으로 찾아 현재까지 저장된 Riot 경기 JSON을 읽습니다.
4. 완료되면 아래 파일이 갱신됩니다.
   - `data/matches.json` — 웹/AI용 경기 요약
   - `data/profile.json` — 마지막 갱신 시각과 경기 수
   - `data/manifest.json` — 변환 결과/오류 개수
5. GitHub Desktop에서 변경된 파일을 Commit한 뒤 **Push origin**을 누릅니다.
6. GitHub Pages가 자동으로 다시 배포합니다.

## 원본은 어디에 있나요?

무거운 Match/Timeline 원본 JSON은 로컬의 `balini-lol-archive-v*` 폴더에만 남깁니다. GitHub에는 가공된 작은 데이터만 올립니다.

## 새 게임을 한 뒤에는?

먼저 Riot 수집기를 실행해 새 원본 경기를 받은 뒤 `update_site_data.bat`을 실행하고 Push하면 됩니다.
