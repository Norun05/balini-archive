const state = { profile: null, matches: [], filtered: [], details: new Map(), stats: {} };

const $ = (s) => document.querySelector(s);
const els = {
  accountLine: $('#accountLine'), syncBadge: $('#syncBadge'), matchCount: $('#matchCount'), winRate: $('#winRate'), championCount: $('#championCount'),
  searchInput: $('#searchInput'), modeFilter: $('#modeFilter'), championFilter: $('#championFilter'), positionFilter: $('#positionFilter'), resultFilter: $('#resultFilter'),
  matchList: $('#matchList'), resultCount: $('#resultCount'), emptyState: $('#emptyState'),
  statsModeFilter: $('#statsModeFilter'), championModeFilter: $('#championModeFilter'), statsModeHint: $('#statsModeHint'),
  statsOverview: $('#statsOverview'), positionStats: $('#positionStats'), summonerStats: $('#summonerStats'),
  championStats: $('#championStats'), championStatsSearch: $('#championStatsSearch'), teammateStats: $('#teammateStats'), teammateSearch: $('#teammateSearch')
};

const MODE_ORDER = ['standard_rift','normal_draft','ranked_solo','ranked_flex','quickplay','normal_blind','swiftplay','aram','aram_mayhem','arena','arurf','pick_urf','urf','clash','bot'];

const fmtDate = (ms) => !ms ? '-' : new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(ms));
const fmtDuration = (sec) => Number.isFinite(sec) ? `${Math.floor(sec/60)}:${String(Math.floor(sec%60)).padStart(2,'0')}` : '-';
const fmtDiff = (v) => Number.isFinite(v) ? (v > 0 ? `+${v}` : String(v)) : '-';
const fmtPct = (v) => Number.isFinite(v) ? `${v.toFixed(1)}%` : '-';
const n = (v) => Number(v || 0).toLocaleString('ko-KR');

async function loadJson(path, fallback=null) {
  try { const r = await fetch(path,{cache:'no-store'}); if(!r.ok) throw new Error(r.status); return await r.json(); }
  catch(err) { console.warn(`Failed to load ${path}`,err); return fallback; }
}

function escapeHtml(v) { return String(v ?? '').replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch])); }

function fallbackModeMeta(m) {
  const q = Number(m.queueId);
  const gm = String(m.gameMode || '').toUpperCase();
  const year = m.gameCreation ? new Date(m.gameCreation).getUTCFullYear() : null;

  if (gm === 'SWIFTPLAY') return {
    modeKey:'swiftplay', modeNameKo:'신속 대전', modeFamily:'summoners_rift',
    rulesetKey:year && year >= 2026 ? 'swiftplay_2026' : 'swiftplay_2025',
    rulesetNameKo:year && year >= 2026 ? '신속 대전 (2026 규칙)' : '신속 대전 (기존 규칙)',
    isStandardRift:false, hasStandardPositions:true
  };
  if (gm === 'CHERRY' || [1700,1710,1750].includes(q)) return {
    modeKey:'arena', modeNameKo:'아레나', modeFamily:'arena',
    rulesetKey:q === 1750 ? 'arena_1750' : q === 1710 ? 'arena_1710' : 'arena_1700',
    rulesetNameKo:q === 1750 ? '아레나 (3인 팀 규칙)' : q === 1710 ? '아레나 (확장 규칙)' : '아레나 (기존 규칙)',
    isStandardRift:false, hasStandardPositions:false
  };
  if (q === 2400) return {modeKey:'aram_mayhem',modeNameKo:'증강 칼바람',modeFamily:'aram',rulesetKey:'aram_mayhem',rulesetNameKo:'증강 칼바람',isStandardRift:false,hasStandardPositions:false};
  if (q === 450 || gm === 'ARAM') return {modeKey:'aram',modeNameKo:'칼바람 나락',modeFamily:'aram',rulesetKey:'aram',rulesetNameKo:'칼바람 나락',isStandardRift:false,hasStandardPositions:false};
  if (gm === 'URF' || q === 900 || q === 1900) {
    if (q === 900) return {modeKey:'arurf',modeNameKo:'무작위 우르프',modeFamily:'urf',rulesetKey:'arurf',rulesetNameKo:'무작위 우르프',isStandardRift:false,hasStandardPositions:false};
    if (q === 1900) return {modeKey:'pick_urf',modeNameKo:'우르프 (선택)',modeFamily:'urf',rulesetKey:'pick_urf',rulesetNameKo:'우르프 (선택)',isStandardRift:false,hasStandardPositions:false};
    return {modeKey:'urf',modeNameKo:'우르프',modeFamily:'urf',rulesetKey:'urf',rulesetNameKo:'우르프',isStandardRift:false,hasStandardPositions:false};
  }

  const known = {
    400:['normal_draft','일반 · 교차 선택'],
    420:['ranked_solo','솔로/듀오 랭크'],
    440:['ranked_flex','자유 랭크'],
    490:['quickplay','빠른 대전 (Quickplay)'],
    430:['normal_blind','일반 · 블라인드 픽'],
    700:['clash','격전']
  };
  if (known[q]) return {
    modeKey:known[q][0], modeNameKo:known[q][1], modeFamily:'summoners_rift',
    rulesetKey:known[q][0], rulesetNameKo:known[q][1],
    isStandardRift:true, hasStandardPositions:true
  };
  if ([830,840,850,870,880,890].includes(q)) return {modeKey:'bot',modeNameKo:'AI 상대 대전',modeFamily:'summoners_rift',rulesetKey:`bot_${q}`,rulesetNameKo:`AI 상대 대전 (${q})`,isStandardRift:false,hasStandardPositions:false};
  return {modeKey:`unknown_${Number.isFinite(q)?q:'x'}`,modeNameKo:`기타 모드 (${Number.isFinite(q)?q:gm||'UNKNOWN'})`,modeFamily:'other',rulesetKey:'unknown',rulesetNameKo:'기타',isStandardRift:false,hasStandardPositions:false};
}

function normalizeMatch(m) {
  const fallback = fallbackModeMeta(m);
  return {
    matchId:m.matchId??'', gameCreation:m.gameCreation??null, gameDuration:m.gameDuration??null,
    queueId:m.queueId??null, gameMode:m.gameMode??'', championName:m.championName??'Unknown',
    position:m.position??'', opponent:m.opponent??m.laneOpponent?.championName??'',
    kills:m.kills??0, deaths:m.deaths??0, assists:m.assists??0, cs:m.cs??0,
    gold:m.gold??0, damage:m.damage??0, win:Boolean(m.win), detailPath:m.detailPath??`matches/${m.matchId}.json`,
    modeKey:m.modeKey??fallback.modeKey, modeNameKo:m.modeNameKo??fallback.modeNameKo,
    modeFamily:m.modeFamily??fallback.modeFamily, rulesetKey:m.rulesetKey??fallback.rulesetKey,
    rulesetNameKo:m.rulesetNameKo??fallback.rulesetNameKo,
    isStandardRift:m.isStandardRift??fallback.isStandardRift,
    hasStandardPositions:m.hasStandardPositions??fallback.hasStandardPositions
  };
}

function renderHero() {
  const ms=state.matches;
  els.matchCount.textContent=n(ms.length);
  els.winRate.textContent=ms.length?fmtPct(ms.filter(m=>m.win).length*100/ms.length):'-';
  els.championCount.textContent=new Set(ms.map(m=>m.championName)).size;
}

function modeCandidates() {
  const selected = els.modeFilter?.value || '';
  return selected ? state.matches.filter(m=>m.modeKey===selected) : state.matches;
}

function fillModeFilter() {
  if (!els.modeFilter) return;
  const current = els.modeFilter.value;
  const modes = new Map();
  for (const m of state.matches) {
    const entry = modes.get(m.modeKey) || {key:m.modeKey,name:m.modeNameKo,games:0};
    entry.games += 1;
    modes.set(m.modeKey,entry);
  }
  const list = [...modes.values()].sort((a,b)=>{
    const ai=MODE_ORDER.indexOf(a.key), bi=MODE_ORDER.indexOf(b.key);
    if(ai!==-1||bi!==-1) return (ai===-1?999:ai)-(bi===-1?999:bi);
    return a.name.localeCompare(b.name,'ko');
  });
  els.modeFilter.innerHTML='<option value="">전체 모드</option>';
  for(const mode of list){
    const o=document.createElement('option');
    o.value=mode.key;
    o.textContent=`${mode.name} (${n(mode.games)})`;
    els.modeFilter.appendChild(o);
  }
  if ([...modes.keys()].includes(current)) els.modeFilter.value=current;
}

function fillChampionFilter() {
  const current=els.championFilter.value;
  const names=[...new Set(modeCandidates().map(m=>m.championName))].sort((a,b)=>a.localeCompare(b));
  els.championFilter.innerHTML='<option value="">전체</option>';
  for(const name of names){
    const o=document.createElement('option');o.value=name;o.textContent=name;els.championFilter.appendChild(o);
  }
  if(names.includes(current)) els.championFilter.value=current;
}

function fillPositionFilter() {
  const current=els.positionFilter.value;
  const allowed=['TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY'];
  const positions=[...new Set(modeCandidates().filter(m=>m.hasStandardPositions).map(m=>m.position).filter(p=>allowed.includes(p)))];
  els.positionFilter.innerHTML='<option value="">전체</option>';
  for(const p of allowed.filter(x=>positions.includes(x))){
    const o=document.createElement('option');o.value=p;o.textContent=p==='UTILITY'?'SUPPORT':p;els.positionFilter.appendChild(o);
  }
  if(positions.includes(current)) els.positionFilter.value=current;
}

function applyFilters() {
  const q=els.searchInput.value.trim().toLowerCase(), mode=els.modeFilter?.value||'', c=els.championFilter.value, p=els.positionFilter.value, r=els.resultFilter.value;
  state.filtered=state.matches.filter(m=>{
    const h=`${m.matchId} ${m.championName} ${m.position} ${m.opponent} ${m.modeNameKo} ${m.rulesetNameKo}`.toLowerCase();
    return (!q||h.includes(q))&&(!mode||m.modeKey===mode)&&(!c||m.championName===c)&&(!p||m.position===p)&&(!r||(r==='win'?m.win:!m.win));
  });
  renderMatches();
}

function renderMatches() {
  els.matchList.innerHTML='';
  els.resultCount.textContent=`${n(state.filtered.length)}경기`;
  els.emptyState.hidden=state.matches.length!==0;
  const f=document.createDocumentFragment();
  for(const m of state.filtered.slice(0,200)){
    const card=document.createElement('article');
    card.className=`match ${m.win?'win':'loss'}`;
    card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-expanded','false');
    const posMeta=m.hasStandardPositions&&m.position?` · ${escapeHtml(m.position)}`:'';
    card.innerHTML=`<div><div class="result">${m.win?'승리':'패배'}</div><div class="meta">${fmtDuration(m.gameDuration)}</div></div><div><div class="champ">${escapeHtml(m.championName)}</div><div class="meta">${escapeHtml(m.modeNameKo)}${posMeta} · ${fmtDate(m.gameCreation)}</div></div><div><div class="kda">${m.kills} / ${m.deaths} / ${m.assists}</div><div class="meta">CS ${n(m.cs)} · Gold ${n(m.gold)}</div></div><div><div>${n(m.damage)}</div><div class="meta">챔피언 피해량</div></div><div><div class="enemy-list">${m.hasStandardPositions?'라인 상대':'상대'}: ${escapeHtml(m.opponent||'-')}</div><div class="match-id">${escapeHtml(m.matchId)}</div><div class="meta detail-hint">클릭하면 상세 요약 불러오기</div></div>`;
    const t=()=>toggleDetail(card,m);
    card.addEventListener('click',t);
    card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();t();}});
    f.appendChild(card);
  }
  els.matchList.appendChild(f);
}

async function toggleDetail(card,match){
  const old=card.querySelector('.match-detail');
  if(old){old.hidden=!old.hidden;card.setAttribute('aria-expanded',String(!old.hidden));return;}
  const panel=document.createElement('div');panel.className='match-detail';panel.innerHTML='<p class="muted">상세 데이터를 불러오는 중…</p>';card.appendChild(panel);
  let d=state.details.get(match.matchId);
  if(!d){d=await loadJson(`./data/${match.detailPath}`,null);if(d)state.details.set(match.matchId,d);}
  panel.innerHTML=d?renderDetail(d):'<p class="muted">상세 JSON을 불러오지 못했습니다.</p>';
}

function renderDetail(d){
  const mode=fallbackModeMeta(d),opp=d.laneOpponent,t=d.timeline||{},snaps=t.earlySnapshots||t.snapshots||[],team=[d.me,...(d.teammates||[])].filter(Boolean),enemies=d.enemies||[],meId=d.me?.participantId,all=[...team,...enemies],nameMap=new Map(all.map(p=>[p.participantId,p.riotId||p.championName||`P${p.participantId}`]));
  const rows=snaps.map(s=>`<tr><td>${s.minute}분</td><td>${n(s.me?.gold)}</td><td>${fmtDiff(s.goldDiff)}</td><td>${s.me?.cs??'-'}</td><td>${fmtDiff(s.csDiff)}</td><td>${s.me?.level??'-'}</td><td>${fmtDiff(s.levelDiff)}</td><td>${fmtDiff(s.xpDiff)}</td></tr>`).join('');
  const kills=(t.events||[]).filter(e=>e.type==='CHAMPION_KILL');
  const fights=kills.slice(0,12).map(e=>`<li class="${e.killerId===meId||e.victimId===meId||(e.assistingParticipantIds||[]).includes(meId)?'mine':''}"><strong>${fmtDuration((e.timestamp||0)/1000)}</strong> ${escapeHtml(nameMap.get(e.killerId)||e.killerChampion||'?')} → ${escapeHtml(nameMap.get(e.victimId)||e.victimChampion||'?')}</li>`).join('');
  const spells=(p)=>(p?.summonerSpells||[]).map(s=>s.nameKo||s.id).join(' + ')||'-';
  return `<div class="detail-grid"><div class="detail-block"><h3>라인 매치업</h3><p><strong>${escapeHtml(d.championName||'-')}</strong> vs <strong>${escapeHtml(opp?.championName||'확인 불가')}</strong></p><p class="meta">${escapeHtml(mode.modeNameKo)} · 내 Riot ID: ${escapeHtml(d.me?.riotId||'-')} · ${escapeHtml(spells(d.me))}</p><p class="meta">상대 Riot ID: ${escapeHtml(opp?.riotId||'-')} · ${escapeHtml(spells(opp))}</p></div><div class="detail-block"><h3>팀</h3><p class="meta">아군: ${team.map(p=>escapeHtml(p.riotId||p.championName)).join(' · ')}</p><p class="meta">적군: ${enemies.map(p=>escapeHtml(p.riotId||p.championName)).join(' · ')}</p></div></div>${rows?`<div class="detail-block"><h3>라인 스냅샷</h3><div class="table-scroll"><table class="snapshot-table"><thead><tr><th>시점</th><th>Gold</th><th>골드차</th><th>CS</th><th>CS차</th><th>Lv</th><th>Lv차</th><th>XP차</th></tr></thead><tbody>${rows}</tbody></table></div></div>`:''}${fights?`<details class="event-details"><summary>전체 킬 이벤트 보기</summary><ul>${fights}</ul></details>`:''}<a class="json-link" href="./data/matches/${encodeURIComponent(d.matchId)}.json" target="_blank" rel="noopener">이 경기 상세 JSON 열기</a>`;
}

function statCard(label,value,sub=''){return `<article class="metric-card card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>${sub?`<small>${escapeHtml(sub)}</small>`:''}</article>`;}
function statsTable(headers,rows){return `<table class="stats-table"><thead><tr>${headers.map(h=>`<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;}

function modeBundlesForStats() {
  const bundles=state.stats.modeIndex?.modes||[];
  return [...bundles].sort((a,b)=>{
    const ai=MODE_ORDER.indexOf(a.modeKey), bi=MODE_ORDER.indexOf(b.modeKey);
    if(ai!==-1||bi!==-1) return (ai===-1?999:ai)-(bi===-1?999:bi);
    return String(a.modeNameKo||a.modeKey).localeCompare(String(b.modeNameKo||b.modeKey),'ko');
  });
}

function fillStatsModeFilters() {
  const bundles=modeBundlesForStats();
  for(const select of [els.statsModeFilter,els.championModeFilter]){
    if(!select) continue;
    select.innerHTML='<option value="">전체 모드</option>';
    for(const bundle of bundles){
      const o=document.createElement('option');
      o.value=bundle.modeKey;
      o.textContent=`${bundle.modeNameKo||bundle.modeKey} (${n(bundle.games)})`;
      select.appendChild(o);
    }
  }
}

async function loadModeStats(modeKey) {
  if(!modeKey) return state.stats.global;
  if(state.stats.modeCache.has(modeKey)) return state.stats.modeCache.get(modeKey);
  const bundle=(state.stats.modeIndex?.modes||[]).find(x=>x.modeKey===modeKey);
  if(!bundle?.files) return state.stats.global;
  const f=bundle.files;
  const [overview,positions,champions,summoners]=await Promise.all([
    loadJson(`./data/${f.overview}`,null),
    loadJson(`./data/${f.positions}`,[]),
    loadJson(`./data/${f.champions}`,[]),
    loadJson(`./data/${f.summoners}`,[])
  ]);
  const result={overview,positions,champions,summoners,modeNameKo:bundle.modeNameKo||modeKey,modeKey};
  state.stats.modeCache.set(modeKey,result);
  return result;
}

async function setStatsMode(modeKey) {
  if(!state.stats.loaded) return;
  state.stats.activeMode=modeKey||'';
  if(els.statsModeFilter) els.statsModeFilter.value=state.stats.activeMode;
  if(els.championModeFilter) els.championModeFilter.value=state.stats.activeMode;
  state.stats.current=await loadModeStats(state.stats.activeMode);
  if(els.statsModeHint){
    const label=state.stats.activeMode ? (state.stats.current.modeNameKo||state.stats.activeMode) : '전체 모드';
    els.statsModeHint.textContent=state.stats.activeMode==='standard_rift'
      ? `${label} — 신속·아레나·칼바람·우르프를 제외한 일반 규칙 협곡 통계입니다.`
      : `${label} 기준 통계`;
  }
  renderOverview();
  renderChampions();
}

async function loadStats(){
  if(state.stats.loaded)return;
  const [overview,positions,champions,teammates,summoners,modeIndex]=await Promise.all([
    loadJson('./data/stats/overview.json',null),
    loadJson('./data/stats/positions.json',[]),
    loadJson('./data/stats/champions.json',[]),
    loadJson('./data/stats/teammates.json',[]),
    loadJson('./data/stats/summoners.json',[]),
    loadJson('./data/stats/modes.json',null)
  ]);
  const global={overview,positions,champions,summoners,modeNameKo:'전체 모드',modeKey:''};
  state.stats={loaded:true,global,current:global,teammates,modeIndex,modeCache:new Map(),activeMode:''};
  fillStatsModeFilters();
  const preferred=modeIndex?.defaultAnalysisMode||'';
  await setStatsMode(preferred);
  renderTeammates();
}

function renderOverview(){
  const data=state.stats.current||state.stats.global||{};
  const o=data.overview;
  if(!o){els.statsOverview.innerHTML='<p class="muted">통계 데이터가 아직 없습니다. update_site_data.bat을 실행해주세요.</p>';return;}
  els.statsOverview.innerHTML=statCard('경기',n(o.games||o.matchCount))+statCard('승률',fmtPct(o.winRate))+statCard('평균 KDA',String(o.kdaRatio??'-'))+statCard('평균 CS',String(o.avgCs??'-'))+statCard('평균 골드',n(o.avgGold))+statCard('평균 피해량',n(o.avgDamage));
  const posRows=(data.positions||[]).map(p=>`<tr><td>${escapeHtml(p.position)}</td><td>${n(p.games)}</td><td>${fmtPct(p.winRate)}</td><td>${p.avgKills??'-'} / ${p.avgDeaths??'-'} / ${p.avgAssists??'-'}</td><td>${p.lane?.['10']?.avgGoldDiff??'-'}</td><td>${p.lane?.['10']?.avgCsDiff??'-'}</td></tr>`);
  els.positionStats.innerHTML=posRows.length?statsTable(['포지션','경기','승률','평균 K/D/A','10분 골드차','10분 CS차'],posRows):'<p class="muted">이 모드에는 표준 라인 포지션 통계가 없습니다.</p>';
  const sRows=(data.summoners||[]).slice(0,30).map(s=>`<tr><td>${escapeHtml(s.champion)}</td><td>${escapeHtml(s.position||'해당 없음')}</td><td>${escapeHtml(s.summoners)}</td><td>${n(s.games)}</td><td>${fmtPct(s.winRate)}</td></tr>`);
  els.summonerStats.innerHTML=sRows.length?statsTable(['챔피언','포지션','주문','경기','승률'],sRows):'<p class="muted">이 모드의 소환사 주문 통계가 없습니다.</p>';
}

function renderChampions(){
  const data=state.stats.current||state.stats.global||{};
  const q=(els.championStatsSearch?.value||'').trim().toLowerCase();
  const list=(data.champions||[]).filter(c=>!q||String(c.champion).toLowerCase().includes(q));
  els.championStats.innerHTML=list.map(c=>`<article class="stats-card card"><div class="stats-card-head"><div><p class="section-kicker">${n(c.games)} GAMES</p><h3>${escapeHtml(c.champion)}</h3></div><strong>${fmtPct(c.winRate)}</strong></div><div class="mini-metrics"><span>KDA ${c.kdaRatio??'-'}</span><span>평균 CS ${c.avgCs??'-'}</span><span>평균 피해 ${n(c.avgDamage)}</span></div>${c.positions&&Object.keys(c.positions).length?`<div class="chip-row">${Object.entries(c.positions).map(([p,v])=>`<span class="stat-chip">${escapeHtml(p)} ${n(v.games)}판 · ${fmtPct(v.winRate)}</span>`).join('')}</div>`:''}</article>`).join('')||'<p class="muted">검색 결과가 없습니다.</p>';
}

function renderTeammates(){
  const q=(els.teammateSearch?.value||'').trim().toLowerCase();
  const list=(state.stats.teammates||[]).filter(p=>!q||String(p.riotId).toLowerCase().includes(q));
  els.teammateStats.innerHTML=list.slice(0,200).map(p=>`<article class="stats-card card"><div class="stats-card-head"><div><p class="section-kicker">${n(p.games)} GAMES TOGETHER</p><h3>${escapeHtml(p.riotId)}</h3></div><strong>${fmtPct(p.winRate)}</strong></div><div class="mini-metrics"><span>${n(p.wins)}승 ${n(p.losses)}패</span><span>내 평균 KDA ${p.kdaRatio??'-'}</span></div>${(p.myChampionPositionPairs||[]).length?`<div class="chip-row">${p.myChampionPositionPairs.slice(0,8).map(x=>`<span class="stat-chip">${escapeHtml(x.champion)} ${escapeHtml(x.position)} · ${n(x.games)}판</span>`).join('')}</div>`:''}</article>`).join('')||'<p class="muted">검색 결과가 없습니다.</p>';
}

async function switchTab(name){
  document.querySelectorAll('.tab-button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
  document.querySelectorAll('.tab-panel').forEach(p=>{const on=p.dataset.panel===name;p.hidden=!on;p.classList.toggle('active',on);});
  if(name!=='matches')await loadStats();
}

async function init(){
  const profileP=loadJson('./data/profile.json',{});
  let raw=await loadJson('./data/catalog.json',null);
  if(!Array.isArray(raw))raw=await loadJson('./data/matches.json',[]);
  state.profile=await profileP;
  state.matches=(Array.isArray(raw)?raw:[]).map(normalizeMatch).sort((a,b)=>(b.gameCreation??0)-(a.gameCreation??0));
  state.filtered=[...state.matches];
  els.accountLine.textContent=state.profile.riotId??'발린이#극악무도';
  els.syncBadge.textContent=state.profile.updatedAt?`업데이트 ${fmtDate(state.profile.updatedAt)}`:'데이터 준비 중';
  renderHero();fillModeFilter();fillChampionFilter();fillPositionFilter();renderMatches();

  els.searchInput.addEventListener('input',applyFilters);
  els.modeFilter?.addEventListener('change',()=>{fillChampionFilter();fillPositionFilter();applyFilters();});
  [els.championFilter,els.positionFilter,els.resultFilter].forEach(el=>el.addEventListener('change',applyFilters));
  document.querySelectorAll('.tab-button').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.tab)));
  els.statsModeFilter?.addEventListener('change',e=>setStatsMode(e.target.value));
  els.championModeFilter?.addEventListener('change',e=>setStatsMode(e.target.value));
  els.championStatsSearch?.addEventListener('input',renderChampions);
  els.teammateSearch?.addEventListener('input',renderTeammates);
}

init();
