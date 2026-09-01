const state = { profile: null, matches: [], filtered: [], details: new Map() };

const els = {
  accountLine: document.querySelector('#accountLine'),
  syncBadge: document.querySelector('#syncBadge'),
  matchCount: document.querySelector('#matchCount'),
  winRate: document.querySelector('#winRate'),
  championCount: document.querySelector('#championCount'),
  searchInput: document.querySelector('#searchInput'),
  championFilter: document.querySelector('#championFilter'),
  positionFilter: document.querySelector('#positionFilter'),
  resultFilter: document.querySelector('#resultFilter'),
  matchList: document.querySelector('#matchList'),
  resultCount: document.querySelector('#resultCount'),
  emptyState: document.querySelector('#emptyState')
};

const fmtDate = (ms) => {
  if (!ms) return '-';
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  }).format(new Date(ms));
};

const fmtDuration = (sec) => {
  if (!Number.isFinite(sec)) return '-';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
};

const fmtDiff = (value) => {
  if (!Number.isFinite(value)) return '-';
  return value > 0 ? `+${value}` : String(value);
};

async function loadJson(path, fallback = null) {
  try {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) throw new Error(`${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`Failed to load ${path}`, err);
    return fallback;
  }
}

function normalizeMatch(m) {
  return {
    matchId: m.matchId ?? '',
    gameCreation: m.gameCreation ?? null,
    gameDuration: m.gameDuration ?? null,
    queueId: m.queueId ?? null,
    gameMode: m.gameMode ?? '',
    championName: m.championName ?? 'Unknown',
    position: m.position ?? '',
    opponent: m.opponent ?? m.laneOpponent?.championName ?? '',
    kills: m.kills ?? 0,
    deaths: m.deaths ?? 0,
    assists: m.assists ?? 0,
    cs: m.cs ?? 0,
    gold: m.gold ?? 0,
    damage: m.damage ?? 0,
    win: Boolean(m.win),
    detailPath: m.detailPath ?? `matches/${m.matchId}.json`
  };
}

function renderStats() {
  const ms = state.matches;
  els.matchCount.textContent = ms.length.toLocaleString('ko-KR');
  if (ms.length) {
    const wins = ms.filter(m => m.win).length;
    els.winRate.textContent = `${((wins / ms.length) * 100).toFixed(1)}%`;
    els.championCount.textContent = new Set(ms.map(m => m.championName)).size;
  } else {
    els.winRate.textContent = '-';
    els.championCount.textContent = '0';
  }
}

function fillChampionFilter() {
  const names = [...new Set(state.matches.map(m => m.championName))].sort((a, b) => a.localeCompare(b));
  for (const name of names) {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    els.championFilter.appendChild(opt);
  }
}

function applyFilters() {
  const q = els.searchInput.value.trim().toLowerCase();
  const champ = els.championFilter.value;
  const pos = els.positionFilter.value;
  const result = els.resultFilter.value;

  state.filtered = state.matches.filter(m => {
    const haystack = `${m.matchId} ${m.championName} ${m.position} ${m.opponent}`.toLowerCase();
    if (q && !haystack.includes(q)) return false;
    if (champ && m.championName !== champ) return false;
    if (pos && m.position !== pos) return false;
    if (result === 'win' && !m.win) return false;
    if (result === 'loss' && m.win) return false;
    return true;
  });
  renderMatches();
}

function renderMatches() {
  els.matchList.innerHTML = '';
  els.resultCount.textContent = `${state.filtered.length.toLocaleString('ko-KR')}경기`;
  els.emptyState.hidden = state.matches.length !== 0;

  const frag = document.createDocumentFragment();
  for (const m of state.filtered.slice(0, 200)) {
    const card = document.createElement('article');
    card.className = `match ${m.win ? 'win' : 'loss'}`;
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-expanded', 'false');
    card.dataset.matchId = m.matchId;
    card.innerHTML = `
      <div>
        <div class="result">${m.win ? '승리' : '패배'}</div>
        <div class="meta">${fmtDuration(m.gameDuration)}</div>
      </div>
      <div>
        <div class="champ">${escapeHtml(m.championName)}</div>
        <div class="meta">${escapeHtml(m.position || '-')} · ${fmtDate(m.gameCreation)}</div>
      </div>
      <div>
        <div class="kda">${m.kills} / ${m.deaths} / ${m.assists}</div>
        <div class="meta">CS ${Number(m.cs || 0).toLocaleString('ko-KR')} · Gold ${Number(m.gold || 0).toLocaleString('ko-KR')}</div>
      </div>
      <div>
        <div>${Number(m.damage || 0).toLocaleString('ko-KR')}</div>
        <div class="meta">챔피언 피해량</div>
      </div>
      <div>
        <div class="enemy-list">라인 상대: ${escapeHtml(m.opponent || '-')}</div>
        <div class="match-id">${escapeHtml(m.matchId)}</div>
        <div class="meta detail-hint">클릭하면 상세 요약 불러오기</div>
      </div>`;

    const toggle = () => toggleDetail(card, m);
    card.addEventListener('click', toggle);
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggle();
      }
    });
    frag.appendChild(card);
  }
  els.matchList.appendChild(frag);
}

async function toggleDetail(card, match) {
  const existing = card.querySelector('.match-detail');
  if (existing) {
    const hidden = existing.hidden;
    existing.hidden = !hidden;
    card.setAttribute('aria-expanded', String(hidden));
    return;
  }

  card.setAttribute('aria-expanded', 'true');
  const panel = document.createElement('div');
  panel.className = 'match-detail';
  panel.innerHTML = '<p class="muted">상세 데이터를 불러오는 중…</p>';
  card.appendChild(panel);

  let detail = state.details.get(match.matchId);
  if (!detail) {
    detail = await loadJson(`./data/${match.detailPath}`, null);
    if (detail) state.details.set(match.matchId, detail);
  }

  if (!detail) {
    panel.innerHTML = '<p class="muted">상세 JSON을 불러오지 못했습니다. 데이터 갱신 후 다시 시도해주세요.</p>';
    return;
  }
  panel.innerHTML = renderDetail(detail);
}

function renderDetail(detail) {
  const opponent = detail.laneOpponent;
  const timeline = detail.timeline || {};
  const snapshots = timeline.snapshots || [];
  const team = [detail.me, ...(detail.teammates || [])].filter(Boolean);
  const enemies = detail.enemies || [];
  const meId = detail.me?.participantId;

  const participantName = new Map(
    [...team, ...enemies].filter(Boolean).map(p => [p.participantId, p.championName || `P${p.participantId}`])
  );

  const snapshotRows = snapshots.map(s => `
    <tr>
      <td>${s.minute}분</td>
      <td>${Number(s.me?.gold || 0).toLocaleString('ko-KR')}</td>
      <td>${fmtDiff(s.goldDiff)}</td>
      <td>${s.me?.cs ?? '-'}</td>
      <td>${fmtDiff(s.csDiff)}</td>
      <td>${s.me?.level ?? '-'}</td>
      <td>${fmtDiff(s.levelDiff)}</td>
    </tr>`).join('');

  const championEvents = (timeline.events || []).filter(e => e.type === 'CHAMPION_KILL');
  const myFirstKill = championEvents.find(e => e.killerId === meId);
  const myFirstDeath = championEvents.find(e => e.victimId === meId);
  const myFirstAssist = championEvents.find(e => (e.assistingParticipantIds || []).includes(meId));

  const eventTime = (e) => e ? fmtDuration((e.timestamp || 0) / 1000) : '-';
  const comp = (rows) => rows.map(p => escapeHtml(p.championName || '?')).join(' · ') || '-';

  const recentFightEvents = championEvents.slice(0, 8).map(e => {
    const killer = participantName.get(e.killerId) || `P${e.killerId ?? '?'}`;
    const victim = participantName.get(e.victimId) || `P${e.victimId ?? '?'}`;
    const mine = e.killerId === meId || e.victimId === meId || (e.assistingParticipantIds || []).includes(meId);
    return `<li class="${mine ? 'mine' : ''}"><strong>${fmtDuration((e.timestamp || 0) / 1000)}</strong> ${escapeHtml(killer)} → ${escapeHtml(victim)}</li>`;
  }).join('');

  return `
    <div class="detail-grid">
      <div class="detail-block">
        <h3>라인 매치업</h3>
        <p><strong>${escapeHtml(detail.championName || '-')}</strong> vs <strong>${escapeHtml(opponent?.championName || '확인 불가')}</strong></p>
        <p class="meta">내 최종: ${detail.kills}/${detail.deaths}/${detail.assists} · CS ${detail.cs} · Gold ${Number(detail.gold || 0).toLocaleString('ko-KR')}</p>
        ${opponent ? `<p class="meta">상대 최종: ${opponent.kills}/${opponent.deaths}/${opponent.assists} · CS ${(opponent.totalMinionsKilled || 0) + (opponent.neutralMinionsKilled || 0)} · Gold ${Number(opponent.goldEarned || 0).toLocaleString('ko-KR')}</p>` : ''}
      </div>
      <div class="detail-block">
        <h3>첫 관여 시점</h3>
        <p class="meta">첫 킬 ${eventTime(myFirstKill)} · 첫 데스 ${eventTime(myFirstDeath)} · 첫 어시스트 ${eventTime(myFirstAssist)}</p>
        <p class="meta">아군: ${comp(team)}</p>
        <p class="meta">적군: ${comp(enemies)}</p>
      </div>
    </div>
    ${snapshotRows ? `
      <div class="detail-block">
        <h3>라인 스냅샷</h3>
        <div class="table-scroll">
          <table class="snapshot-table">
            <thead><tr><th>시점</th><th>Gold</th><th>골드차</th><th>CS</th><th>CS차</th><th>Lv</th><th>Lv차</th></tr></thead>
            <tbody>${snapshotRows}</tbody>
          </table>
        </div>
      </div>` : '<p class="muted">이 경기에는 타임라인 스냅샷이 없습니다.</p>'}
    ${recentFightEvents ? `
      <details class="event-details">
        <summary>내가 관여한 킬 이벤트 보기</summary>
        <ul>${recentFightEvents}</ul>
      </details>` : ''}
    <a class="json-link" href="./data/matches/${encodeURIComponent(detail.matchId)}.json" target="_blank" rel="noopener">이 경기 상세 JSON 열기</a>`;
}

function escapeHtml(v) {
  return String(v ?? '').replace(/[&<>'"]/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[ch]));
}

async function init() {
  const profilePromise = loadJson('./data/profile.json', {});
  let rawCatalog = await loadJson('./data/catalog.json', null);
  if (!Array.isArray(rawCatalog)) {
    rawCatalog = await loadJson('./data/matches.json', []);
  }
  const profile = await profilePromise;

  state.profile = profile;
  state.matches = (Array.isArray(rawCatalog) ? rawCatalog : []).map(normalizeMatch)
    .sort((a, b) => (b.gameCreation ?? 0) - (a.gameCreation ?? 0));
  state.filtered = [...state.matches];

  els.accountLine.textContent = profile.riotId ?? '발린이#극악무도';
  els.syncBadge.textContent = profile.updatedAt ? `업데이트 ${fmtDate(profile.updatedAt)}` : '데이터 준비 중';
  renderStats();
  fillChampionFilter();
  renderMatches();

  [els.searchInput, els.championFilter, els.positionFilter, els.resultFilter]
    .forEach(el => el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', applyFilters));
}

init();
