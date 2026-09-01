const state = { profile: null, matches: [], filtered: [] };

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
    timeZone: 'Asia/Seoul', year:'numeric', month:'2-digit', day:'2-digit',
    hour:'2-digit', minute:'2-digit'
  }).format(new Date(ms));
};

const fmtDuration = (sec) => {
  if (!Number.isFinite(sec)) return '-';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2,'0')}`;
};

async function loadJson(path, fallback) {
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
    championName: m.championName ?? m.me?.championName ?? 'Unknown',
    position: m.position ?? m.me?.teamPosition ?? m.me?.individualPosition ?? '',
    kills: m.kills ?? m.me?.kills ?? 0,
    deaths: m.deaths ?? m.me?.deaths ?? 0,
    assists: m.assists ?? m.me?.assists ?? 0,
    cs: m.cs ?? ((m.me?.totalMinionsKilled ?? 0) + (m.me?.neutralMinionsKilled ?? 0)),
    gold: m.gold ?? m.me?.goldEarned ?? 0,
    damage: m.damage ?? m.me?.totalDamageDealtToChampions ?? 0,
    win: typeof m.win === 'boolean' ? m.win : Boolean(m.me?.win),
    enemies: Array.isArray(m.enemies) ? m.enemies : []
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
  const names = [...new Set(state.matches.map(m => m.championName))].sort((a,b) => a.localeCompare(b));
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
    const enemyText = m.enemies.map(e => e.championName ?? '').join(' ');
    const haystack = `${m.matchId} ${m.championName} ${m.position} ${enemyText}`.toLowerCase();
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
    const enemies = m.enemies.map(e => e.championName).filter(Boolean).join(' · ') || '-';
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
        <div class="enemy-list">상대: ${escapeHtml(enemies)}</div>
        <div class="match-id">${escapeHtml(m.matchId)}</div>
      </div>`;
    frag.appendChild(card);
  }
  els.matchList.appendChild(frag);
}

function escapeHtml(v) {
  return String(v).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

async function init() {
  const [profile, rawMatches] = await Promise.all([
    loadJson('./data/profile.json', {}),
    loadJson('./data/matches.json', [])
  ]);
  state.profile = profile;
  state.matches = (Array.isArray(rawMatches) ? rawMatches : rawMatches.matches ?? []).map(normalizeMatch)
    .sort((a,b) => (b.gameCreation ?? 0) - (a.gameCreation ?? 0));
  state.filtered = [...state.matches];

  els.accountLine.textContent = profile.riotId ?? '발린이#극악무도';
  els.syncBadge.textContent = profile.updatedAt ? `업데이트 ${fmtDate(profile.updatedAt)}` : '1차 뼈대';
  renderStats();
  fillChampionFilter();
  renderMatches();

  [els.searchInput, els.championFilter, els.positionFilter, els.resultFilter]
    .forEach(el => el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', applyFilters));
}

init();
