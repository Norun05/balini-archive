# 발린이 아카이브

`발린이#극악무도`의 League of Legends 개인 전적 아카이브입니다.

## 구조

- `index.html` : 사이트 첫 화면
- `style.css` : 화면 스타일
- `app.js` : 검색/필터/렌더링
- `data/profile.json` : 계정 정보
- `data/matches.json` : AI와 사이트가 공통으로 읽는 가벼운 경기 요약

무거운 Riot 원본 Match/Timeline JSON과 API Key는 이 저장소에 올리지 않습니다.

## 다음 단계

로컬 수집기 폴더의 `data/raw/matches/*.json`을 읽어 `data/matches.json`을 자동 생성하는 변환기를 연결합니다.
