/* ════════════════════════════════════════════
   SESSION TITLE
════════════════════════════════════════════ */
document.title = 'AML Intelligence Platform';

/* ════════════════════════════════════════════
   AUTHENTICATION
════════════════════════════════════════════ */
let authUser = null;

function authStep1() {
  const companyId = document.getElementById('auth-company-id').value.trim();
  const name      = document.getElementById('auth-name').value.trim();
  const password  = document.getElementById('auth-password').value;

  if (!companyId || !name || !password) {
    showAuthError('auth-error', 'All fields are required');
    return;
  }
  if (password.length < 4) {
    showAuthError('auth-error', 'Invalid credentials');
    return;
  }

  authUser = { companyId, name };
  document.getElementById('auth-step1').style.display = 'none';
  document.getElementById('auth-step2').style.display = 'flex';
  document.querySelector('.auth-code-digit').focus();
}

function authStep2() {
  const digits = [...document.querySelectorAll('.auth-code-digit')].map(d => d.value);
  const code = digits.join('');

  if (code.length !== 6) {
    showAuthError('auth-error2', 'Enter all 6 digits');
    return;
  }

  // Accept any 6-digit code for demo
  completeAuth();
}

function authBack() {
  document.getElementById('auth-step2').style.display = 'none';
  document.getElementById('auth-step1').style.display = 'flex';
  document.getElementById('auth-error2').style.display = 'none';
  document.querySelectorAll('.auth-code-digit').forEach(d => d.value = '');
}

function showAuthError(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 3000);
}

// Auto-advance code digit inputs
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.auth-code-digit').forEach(inp => {
    inp.addEventListener('input', e => {
      const v = e.target.value.replace(/\D/g, '');
      e.target.value = v;
      if (v && e.target.dataset.idx < 5) {
        const next = document.querySelector(`.auth-code-digit[data-idx="${+e.target.dataset.idx + 1}"]`);
        if (next) next.focus();
      }
    });
    inp.addEventListener('keydown', e => {
      if (e.key === 'Backspace' && !e.target.value && e.target.dataset.idx > 0) {
        const prev = document.querySelector(`.auth-code-digit[data-idx="${+e.target.dataset.idx - 1}"]`);
        if (prev) { prev.focus(); prev.value = ''; }
      }
    });
  });
});

function completeAuth() {
  const screen = document.getElementById('auth-screen');
  screen.style.transition = 'opacity .5s ease';
  screen.style.opacity = '0';
  setTimeout(() => {
    screen.style.display = 'none';
    playCinematicIntro();
  }, 500);
}

/* ════════════════════════════════════════════
   CINEMATIC INTRO — movie-studio logo reveal
════════════════════════════════════════════ */
function playCinematicIntro() {
  const intro = document.getElementById('cinematic-intro');
  intro.style.display = 'flex';

  // Particle background
  const canvas = document.getElementById('cine-canvas');
  const ctx = canvas.getContext('2d');
  let w = canvas.width = window.innerWidth;
  let h = canvas.height = window.innerHeight;

  const particles = [];
  for (let i = 0; i < 80; i++) {
    particles.push({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.3, vy: (Math.random() - 0.5) * 0.3,
      r: Math.random() * 1.5 + 0.5, alpha: Math.random() * 0.3 + 0.1,
    });
  }

  let cineFrame;
  function drawParticles() {
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      // Connections
      for (let j = i + 1; j < particles.length; j++) {
        const q = particles[j];
        const dx = p.x - q.x, dy = p.y - q.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          ctx.beginPath();
          ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y);
          ctx.strokeStyle = `rgba(0, 87, 156, ${(1 - dist / 120) * 0.08})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
      // Dot
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0, 87, 156, ${p.alpha})`;
      ctx.fill();
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
    }
    cineFrame = requestAnimationFrame(drawParticles);
  }
  drawParticles();

  // Animate elements in sequence
  const content = document.getElementById('cine-content');
  const shield  = content.querySelector('.cine-shield');
  const line    = document.getElementById('cine-line');
  const name    = document.getElementById('cine-name');
  const sub     = document.getElementById('cine-sub');
  const tagline = document.getElementById('cine-tagline');

  // Fade in content container
  setTimeout(() => { content.style.transition = 'opacity .4s ease'; content.style.opacity = '1'; }, 100);

  // Shield scales in
  setTimeout(() => {
    shield.style.transition = 'opacity .4s ease, transform .4s ease';
    shield.style.opacity = '1'; shield.style.transform = 'scale(1)';
  }, 150);

  // Red-blue line extends
  setTimeout(() => { line.style.width = '280px'; }, 400);

  // Bank name types in
  setTimeout(() => {
    name.style.transition = 'opacity .3s ease, transform .3s ease';
    name.style.opacity = '1'; name.style.transform = 'translateY(0)';
  }, 500);

  // Sub text
  setTimeout(() => {
    sub.style.transition = 'opacity .3s ease, transform .3s ease';
    sub.style.opacity = '1'; sub.style.transform = 'translateY(0)';
  }, 700);

  // Tagline
  setTimeout(() => {
    tagline.style.transition = 'opacity .3s ease';
    tagline.style.opacity = '1';
  }, 900);

  // Hold for a beat, then fade out → loading screen
  setTimeout(() => {
    cancelAnimationFrame(cineFrame);
    intro.style.transition = 'opacity .4s ease';
    intro.style.opacity = '0';
    setTimeout(() => {
      intro.style.display = 'none';
      document.getElementById('loading-overlay').style.display = 'flex';
      startLoadingAnimation();
      init();
    }, 400);
  }, 1500);
}

/* ════════════════════════════════════════════
   LOADING SCREEN — particle network animation
════════════════════════════════════════════ */
let loadAnimFrame = null;

function startLoadingAnimation() {
  const canvas = document.getElementById('load-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w = canvas.width = window.innerWidth;
  let h = canvas.height = window.innerHeight;

  const particles = [];
  const PARTICLE_COUNT = 60;
  const CONNECTION_DIST = 150;

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    particles.push({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.6,
      vy: (Math.random() - 0.5) * 0.6,
      r: Math.random() * 2 + 1,
    });
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);

    // Draw connections
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONNECTION_DIST) {
          const alpha = (1 - dist / CONNECTION_DIST) * 0.15;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(0, 87, 156, ${alpha})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }

    // Draw particles
    for (const p of particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0, 87, 156, 0.4)';
      ctx.fill();

      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;
    }

    loadAnimFrame = requestAnimationFrame(draw);
  }

  draw();

  // Show session info
  const infoEl = document.getElementById('load-session-info');
  if (infoEl && authUser) {
    const now = new Date();
    infoEl.textContent = `SESSION ${authUser.companyId} · ${authUser.name.toUpperCase()} · ${now.toISOString().replace('T',' ').slice(0,19)} UTC`;
  }
}

function stopLoadingAnimation() {
  if (loadAnimFrame) {
    cancelAnimationFrame(loadAnimFrame);
    loadAnimFrame = null;
  }
}

/* ════════════════════════════════════════════
   CONFIG
════════════════════════════════════════════ */
const API_BASE = (window.location.protocol === 'file:')
  ? 'http://localhost:8000'
  : '';

/* ── Pattern formatting ── */
function formatPatternName(pt) {
  const map = {
    fanOut:'FAN-OUT', fanIn:'FAN-IN',
    scatterGather:'SCATTER-GATHER', gatherScatter:'GATHER-SCATTER',
    cycle:'CYCLE', bipartite:'BIPARTITE', stack:'STACK', random:'RANDOM',
  };
  return map[pt] || pt.toUpperCase();
}
const PATTERN_ICONS = {
  fanOut:'📤', fanIn:'📥', cycle:'🔄', scatterGather:'🔀',
  gatherScatter:'⚖️', bipartite:'⚖️', stack:'📚', random:'❓'
};

const SIGNAL_ICONS = {
  'Rapid Fan-Out':'⚡', 'Round-Trip':'🔁', 'Structuring':'💰',
  'Layering Velocity':'🌊', 'Dormant Activation':'😴',
  'Currency Mismatch':'💱', 'Smurfing':'🐚',
};

const SEV_BADGE = { HIGH:'badge-red', MEDIUM:'badge-amber', LOW:'badge-green' };
const SEV_COLOR = { HIGH:'var(--red)', MEDIUM:'var(--amber)', LOW:'var(--green)' };
const SRC_BADGE = { labelled:'badge-blue', unlabelled:'badge-purple', both:'badge-amber' };
const SRC_LABEL = { labelled:'LABELLED', unlabelled:'UNLABELLED', both:'BOTH' };

/* ── State ── */
let allAlerts    = [];
let alertDetails = {};
let decisions    = {};
let currentAlert = null;
let cy           = null;
let currentStep  = -1;
let playTimer    = null;
let srcFilter    = 'all';
let sevFilter    = 'all';
let caseFilter   = 'all';
let dbCharts     = {};

/* ════════════════════════════════════════════
   INIT — loading stages
════════════════════════════════════════════ */
const STAGES = ['ls-0','ls-1','ls-2','ls-3','ls-4'];
const BAR_PCTS = [10, 30, 60, 85, 100];
const STAGE_DELAYS = [0, 300, 600, 900, 1200];

function setStage(idx) {
  STAGES.forEach((id, i) => {
    const el = document.getElementById(id);
    const dot = el.querySelector('.load-stage-dot');
    el.classList.remove('active','done');
    dot.classList.remove('active','done');
    if (i < idx)      { el.classList.add('done'); dot.classList.add('done'); }
    else if (i === idx){ el.classList.add('active'); dot.classList.add('active'); }
  });
  document.getElementById('load-bar').style.width = BAR_PCTS[Math.min(idx,4)] + '%';
}

async function init() {
  const t0 = Date.now();
  setStage(0);
  await pollUntilReady();

  const minWait = s => Math.max(0, STAGE_DELAYS[s] - (Date.now() - t0));
  await sleep(minWait(1)); setStage(1);
  await sleep(minWait(2)); setStage(2);
  await sleep(minWait(3)); setStage(3);
  await loadAllAlerts();
  await sleep(minWait(4)); setStage(4);
  await sleep(400);
  stopLoadingAnimation();
  // Reveal nav/main hidden by inline style to prevent dashboard flash
  const hideStyle = document.querySelector('style');
  if (hideStyle && hideStyle.textContent.includes('display: none !important')) hideStyle.remove();
  const ov = document.getElementById('loading-overlay');
  ov.style.transition = 'opacity .6s ease';
  ov.style.opacity = '0';
  setTimeout(() => ov.style.display = 'none', 600);
  // Show user in navbar
  const navUser = document.getElementById('nav-user');
  if (navUser && authUser) {
    navUser.textContent = authUser.name;
    navUser.style.display = '';
  }
  renderDashboard();
  renderSidebar();
  toast(`Welcome, ${authUser?.name || 'Analyst'}`, 'success');
}

async function pollUntilReady() {
  let lastCount = 0;
  const statusDot = document.getElementById('status-dot');
  const statusLabel = document.getElementById('status-label');
  while (true) {
    try {
      const r = await fetch(`${API_BASE}/status`).catch(() => null);
      if (r && r.ok) {
        const d = await r.json();
        setStage(d.alert_count > 0 ? (d.alert_count !== lastCount ? 2 : 1) : 1);
        lastCount = d.alert_count;
        if (d.status === 'error') {
          if (statusDot) { statusDot.className = 'status-dot'; statusDot.style.background = 'var(--red)'; }
          if (statusLabel) statusLabel.textContent = 'Pipeline error';
          document.querySelector('.load-sub').textContent = d.error || 'Pipeline failed to start.';
          document.querySelector('.load-sub').style.color = 'var(--red)';
          return d;
        }
        if (d.status === 'ready') {
          if (statusDot) statusDot.className = 'status-dot ready';
          if (statusLabel) statusLabel.textContent =
            `Live · ${d.alert_count} alerts | L:${d.labelled_count} U:${d.unlabelled_count} ∩:${d.overlap_count}`;
          return d;
        }
      }
    } catch(e) {}
    await sleep(1000);
  }
}

async function loadAllAlerts() {
  const r = await fetch(`${API_BASE}/alerts`);
  allAlerts = await r.json();
  await loadDecisions();
}

// Hydrate analyst decisions from the persistent audit log so they survive restarts.
async function loadDecisions() {
  try {
    const r = await fetch(`${API_BASE}/decisions`);
    if (r.ok) decisions = await r.json();
  } catch (e) { /* non-fatal — decisions stay empty */ }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/* ════════════════════════════════════════════
   VIEW SWITCHING
════════════════════════════════════════════ */
function toggleDark() {
  const dark = document.body.classList.toggle('dark');
  document.getElementById('dark-toggle').textContent = dark ? '🌙' : '☀️';
  localStorage.setItem('aml-dark', dark ? '1' : '');
}
(function(){if(localStorage.getItem('aml-dark')){document.body.classList.add('dark');const b=document.getElementById('dark-toggle');if(b)b.textContent='🌙';}})();

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`view-${name}`).classList.add('active');
  [...document.querySelectorAll('.nav-tab')].find(t =>
    t.textContent.toLowerCase().includes(name.replace('_',' ').split(' ')[0])
  )?.classList.add('active');

  if (name === 'dashboard')   renderDashboard();
  if (name === 'investigate') { renderSidebar(); if (!currentAlert && allAlerts.length) loadAlertById(allAlerts[0].id); }
  if (name === 'cases')       renderCaseManager();
  if (name === 'search')      runSearch('', 'all');
  if (name === 'validation')  loadValidation();
  if (name === 'whitelist')   loadWhitelist();
}

/* ════════════════════════════════════════════
   DASHBOARD
════════════════════════════════════════════ */
function renderDashboard() {
  document.getElementById('st-total').textContent = allAlerts.length;
  const total = allAlerts.reduce((s,a) => s + parseMoney(a.totalMoved), 0);
  document.getElementById('st-money').textContent = fmtMoney(total);
  document.getElementById('st-high').textContent  = allAlerts.filter(a=>a.severity==='HIGH').length;
  document.getElementById('st-dec').textContent   = Object.keys(decisions).length;

  if (!allAlerts.length) {
    document.getElementById('db-recent').innerHTML =
      '<div style="text-align:center;color:var(--muted);padding:var(--sp-4);font-family:var(--sans)">' +
      'No alerts detected. Model may need retraining or threshold adjustment.</div>';
    return;
  }

  // Pattern donut
  const ptMap = {};
  allAlerts.forEach(a => { ptMap[formatPatternName(a.patternType)] = (ptMap[formatPatternName(a.patternType)]||0)+1; });
  const colors = ['#00579C','#7C3AED','#059669','#D97706','#DC2626','#0891B2','#475569','#94A3B8'];
  if (dbCharts.donut) dbCharts.donut.destroy();
  dbCharts.donut = new Chart(document.getElementById('chart-donut').getContext('2d'), {
    type:'doughnut',
    data:{ labels:Object.keys(ptMap), datasets:[{ data:Object.values(ptMap),
      backgroundColor:colors, borderColor:document.body.classList.contains('dark')?'#1E293B':'#fff', borderWidth:2 }]},
    options:{ plugins:{ legend:{ position:'right', labels:{ color:document.body.classList.contains('dark')?'#94A3B8':'#475569', font:{size:10}, boxWidth:12 } } },
      cutout:'62%', maintainAspectRatio:false }
  });

  // Banks bar
  const bankMap = {};
  allAlerts.forEach(a => {
    const det = alertDetails[a.id];
    if (det) det.nodes.forEach(n => {
      const b = (n.bank||'').replace('Bank-','').trim();
      if (b) bankMap[b] = (bankMap[b]||0)+1;
    });
  });
  const sortedB = Object.entries(bankMap).sort((a,b)=>b[1]-a[1]).slice(0,8);
  if (dbCharts.banks) dbCharts.banks.destroy();
  const bCtx = document.getElementById('chart-banks').getContext('2d');
  if (sortedB.length) {
    dbCharts.banks = new Chart(bCtx, {
      type:'bar',
      data:{ labels:sortedB.map(x=>getBankName(x[0])), datasets:[{ data:sortedB.map(x=>x[1]),
        backgroundColor:'#00579C', borderRadius:2 }]},
      options:{ indexAxis:'y', plugins:{legend:{display:false}},
        scales:{ x:{ticks:{color:document.body.classList.contains('dark')?'#94A3B8':'#475569',font:{family:'DM Mono'}}},
                 y:{ticks:{color:document.body.classList.contains('dark')?'#94A3B8':'#475569',font:{family:'DM Mono',size:10}}} },
        maintainAspectRatio:false }
    });
  }

  // Timeline
  const bins = new Array(48).fill(0), binsU = new Array(48).fill(0);
  const WIN = new Date('2022-09-01T00:00:00');
  allAlerts.forEach(a => {
    const det = alertDetails[a.id];
    if (det?.transactions?.length) {
      const ts = det.transactions[0].ts;
      if (ts) {
        const h = Math.floor((new Date(ts.replace(' ','T')) - WIN) / 3600000);
        if (h >= 0 && h < 48) {
          (a.source === 'unlabelled' ? binsU : bins)[h]++;
          return;
        }
      }
    }
    const idx = allAlerts.indexOf(a);
    const h = idx % 48;
    (a.source === 'unlabelled' ? binsU : bins)[h]++;
  });
  if (dbCharts.tl) dbCharts.tl.destroy();
  const isDark = document.body.classList.contains('dark');
  const axisColor = isDark ? '#94A3B8' : '#475569';
  dbCharts.tl = new Chart(document.getElementById('chart-tl').getContext('2d'), {
    type:'line',
    data:{ labels:Array.from({length:48},(_,i)=>`${i}h`),
      datasets:[
        { label:'Alerts', data:bins, borderColor:'#00579C', backgroundColor:'rgba(0,87,156,.08)', tension:.3, fill:true, pointRadius:2 }
      ]},
    options:{ plugins:{legend:{labels:{color:axisColor,font:{size:10}}}},
      scales:{ x:{ticks:{color:axisColor,maxTicksLimit:12,font:{size:10}}},
               y:{ticks:{color:axisColor,font:{size:10}}} },
      maintainAspectRatio:false }
  });

  // Recent
  document.getElementById('db-recent').innerHTML = allAlerts.slice(0,5).map(a => `
    <div class="mini-card" onclick="jumpInvestigate('${a.id}')" role="button" tabindex="0"
         onkeydown="if(event.key==='Enter')jumpInvestigate('${a.id}')">
      <div><div class="mini-card-name">${PATTERN_ICONS[a.patternType]||'?'} ${formatPatternName(a.patternType)}</div>
      <div class="mini-card-sub">${a.sub}</div></div>
      <span class="badge ${SEV_BADGE[a.severity]||'badge-light'}">${a.severity}</span>
    </div>`).join('');

  const cnt = {confirm:0,review:0,dismiss:0};
  Object.values(decisions).forEach(d => { if(cnt[d.decision]!==undefined) cnt[d.decision]++; });
  document.getElementById('dc-confirm').textContent = cnt.confirm;
  document.getElementById('dc-review').textContent  = cnt.review;
  document.getElementById('dc-dismiss').textContent = cnt.dismiss;
  document.getElementById('dc-pending').textContent = allAlerts.length - Object.keys(decisions).length;
}

function jumpInvestigate(id) { showView('investigate'); loadAlertById(id); }

function parseMoney(s) { return parseFloat((s||'').replace(/[$,]/g,''))||0; }
function fmtMoney(n) {
  if (n>=1e9) return `$${(n/1e9).toFixed(1)}B`;
  if (n>=1e6) return `$${(n/1e6).toFixed(1)}M`;
  if (n>=1e3) return `$${(n/1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

/* ════════════════════════════════════════════
   INVESTIGATE SIDEBAR
════════════════════════════════════════════ */
function setSrc(v,el) {
  srcFilter=v;
  document.querySelectorAll('#src-pills .filter-pill').forEach(p=>p.classList.remove('active'));
  el.classList.add('active'); renderSidebar();
}
function setSev(v,el) {
  sevFilter=v;
  document.querySelectorAll('#sev-pills .filter-pill').forEach(p=>p.classList.remove('active'));
  el.classList.add('active'); renderSidebar();
}

function renderSidebar() {
  const q = (document.getElementById('inv-search')?.value||'').toLowerCase();
  const filtered = allAlerts.filter(a => {
    if (srcFilter!=='all' && a.source!==srcFilter) return false;
    if (sevFilter!=='all' && a.severity!==sevFilter) return false;
    if (q && !formatPatternName(a.patternType).toLowerCase().includes(q) &&
             !a.id.toLowerCase().includes(q) && !a.sub.toLowerCase().includes(q)) return false;
    return true;
  });
  const el = document.getElementById('alert-list');
  if (!el) return;
  el.innerHTML = filtered.map(a => {
    const dec  = decisions[a.id];
    const active = (currentAlert?.id === a.id) ? 'active' : '';
    const sevCls = `sev-${a.severity}`;
    const decDot = dec ? `<div class="dec-indicator ${dec.decision}"></div>` : '';
    const conf   = Math.round((a.confidence||0)*100);
    const mlPct  = a.mlScore != null ? Math.round(a.mlScore*100) : null;
    const mlBg  = mlPct>=70 ? 'var(--red-bg)'   : mlPct>=40 ? 'var(--amber-bg)'  : 'var(--green-bg)';
    const mlClr = mlPct>=70 ? 'var(--red)'      : mlPct>=40 ? 'var(--amber)'     : 'var(--green)';
    const mlBd  = mlPct>=70 ? 'var(--red-bd)'   : mlPct>=40 ? 'var(--amber-bd)'  : 'var(--green-bd)';
    const mlBadge = mlPct != null ? `<span class="badge" style="background:${mlBg};color:${mlClr};border:1px solid ${mlBd}">ML ${mlPct}%</span>` : '';
    return `<div class="ac ${active} ${sevCls}" id="ac_${a.id}" onclick="loadAlertById('${a.id}')"
                role="button" tabindex="0" aria-label="${formatPatternName(a.patternType)} alert, ${a.severity} severity"
                onkeydown="if(event.key==='Enter')loadAlertById('${a.id}')">
      ${decDot}
      <div class="ac-name">${formatPatternName(a.patternType)}</div>
      <div class="ac-badges">
        <span class="badge ${SEV_BADGE[a.severity]||'badge-light'}">${a.severity}</span>
        <span class="badge ${SRC_BADGE[a.source]||'badge-blue'}">${SRC_LABEL[a.source]||''}</span>
        ${mlBadge}
      </div>
      <div class="conf-bar-bg"><div class="conf-bar" style="width:${conf}%"></div></div>
      <div class="ac-meta">${a.totalMoved} · ${a.timeSpan} · ${a.node_count}n · ${a.txn_count}tx</div>
    </div>`;
  }).join('');
}

/* ════════════════════════════════════════════
   LOAD ALERT DETAIL
════════════════════════════════════════════ */
async function loadAlertById(id) {
  if (!alertDetails[id]) {
    try {
      const r = await fetch(`${API_BASE}/alerts/${id}`);
      if (!r.ok) return;
      alertDetails[id] = await r.json();
      renderDashboard();
    } catch(e) { toast('Error loading alert','error'); return; }
  }
  currentAlert = alertDetails[id];
  currentStep  = -1;
  if (playTimer) { clearInterval(playTimer); playTimer=null; }
  document.getElementById('play-btn').textContent = '▶ Play';

  document.querySelectorAll('.ac').forEach(c=>c.classList.remove('active'));
  const card = document.getElementById('ac_'+id);
  if (card) { card.classList.add('active'); card.scrollIntoView({block:'nearest'}); }

  // Route bar
  const route = currentAlert.routeNodes||[];
  document.getElementById('route-bar').innerHTML = route.map((n,i) =>
    `<span class="route-pill" onclick="highlightNode('${n}')" role="button" tabindex="0"
           onkeydown="if(event.key==='Enter')highlightNode('${n}')">${n}</span>${i<route.length-1?'<span class="route-arrow">→</span>':''}`
  ).join('');

  // Stats strip
  document.getElementById('is-moved').textContent = currentAlert.totalMoved||'—';
  document.getElementById('is-span').textContent  = currentAlert.timeSpan||'—';
  document.getElementById('is-hops').textContent  = currentAlert.hops??'—';
  document.getElementById('is-conf').textContent  = `${Math.round((currentAlert.confidence||0)*100)}%`;
  document.getElementById('is-pat').textContent   = formatPatternName(currentAlert.patternType||'');

  renderGraph();
  renderRightPanel();
  renderTimeline();
  toast(`Loaded: ${formatPatternName(currentAlert.patternType)}`, 'info');
}

/* ════════════════════════════════════════════
   GRAPH
════════════════════════════════════════════ */
const SEV_NODE = {
  high:   { bg:'#FEF2F2', border:'#DC2626' },
  medium: { bg:'#FFFBEB', border:'#D97706' },
  low:    { bg:'#ECFDF5', border:'#059669' },
};
const FMT_EDGE = { RTGS:'#00579C', NEFT:'#059669', Cheque:'#D97706', 'Credit Card':'#7C3AED' };

function getImportanceColor(importance) {
  // Map GNNExplainer importance (0-1) to color: light gray → orange → red
  // Low (0.0): #E5E7EB, Medium (0.5): #F97316, High (1.0): #DC2626
  const imp = Math.max(0, Math.min(1, importance || 0.5));
  if (imp < 0.5) {
    // Interpolate from gray to orange
    const t = imp * 2; // 0 to 1
    return interpolateHex('#E5E7EB', '#F97316', t);
  } else {
    // Interpolate from orange to red
    const t = (imp - 0.5) * 2; // 0 to 1
    return interpolateHex('#F97316', '#DC2626', t);
  }
}

function interpolateHex(hex1, hex2, t) {
  const c1 = parseInt(hex1.slice(1), 16);
  const c2 = parseInt(hex2.slice(1), 16);
  const r1 = (c1 >> 16) & 255, g1 = (c1 >> 8) & 255, b1 = c1 & 255;
  const r2 = (c2 >> 16) & 255, g2 = (c2 >> 8) & 255, b2 = c2 & 255;
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('').toUpperCase();
}

const BANK_NAMES = [
  'Apex National Bank','Meridian Trust Co.','Pinnacle Savings Bank',
  'Harbor Commercial Bank','Summit Finance Corp','Central Mutual Bank',
  'Pacific Trade Bank','Atlantic Financial Group','Inland Credit Union',
  'Horizon Cooperative Bank','Unity Savings Bank','Frontier Banking Corp',
  'Capital Fidelity Bank','Westpoint Savings','Northern Mutual Bank',
  'Eastern Finance Group','Global Commerce Bank','Premier Credit Bank',
  'Allied Banking Corp','First National Trust',
];
function getBankName(raw) {
  if (!raw) return raw;
  const id = String(raw).replace('Bank-','').trim();
  const n  = parseInt(id, 10);
  if (isNaN(n)) return id;
  return BANK_NAMES[n % BANK_NAMES.length];
}

function getLayout(alert) {
  if (!alert) return { name:'cose', padding:30, animate:false };
  const pt    = alert.patternType;
  const nodes = alert.nodes || [];

  if (pt === 'fanOut') {
    const dist = nodes.find(n => n.role === 'Distributor') || nodes[0];
    return {
      name: 'breadthfirst', directed: true,
      roots: dist ? [`#${dist.id}`] : undefined,
      padding: 40, spacingFactor: 2.0, avoidOverlap: true
    };
  }

  if (pt === 'fanIn') {
    return {
      name: 'breadthfirst', directed: false,
      padding: 40, spacingFactor: 2.0, avoidOverlap: true
    };
  }

  if (pt === 'cycle') {
    return { name: 'circle', padding: 30, spacingFactor: 1.3, avoidOverlap: true };
  }

  if (pt === 'bipartite') {
    const coords  = nodes.filter(n => n.role === 'Coordinator');
    const root = coords.length ? coords.map(n => `#${n.id}`) : undefined;
    return {
      name: 'breadthfirst', directed: true,
      roots: root,
      padding: 40, spacingFactor: 1.8, avoidOverlap: true
    };
  }

  if (pt === 'scatterGather' || pt === 'gatherScatter') {
    return { name: 'breadthfirst', directed: true, padding: 30, spacingFactor: 1.8, avoidOverlap: true };
  }

  if (pt === 'stack') {
    return { name: 'breadthfirst', directed: true, padding: 30, spacingFactor: 1.5, avoidOverlap: true };
  }

  return { name: 'cose', padding: 30, animate: false, nodeRepulsion: 4500 };
}
function renderGraph() {
  if (!currentAlert) return;
  if (cy) cy.destroy();

  const elements = [];
  // Build role-based short labels: S=source, D=destination, I/I1/I2...=intermediary
  let intermediaryIdx = 0;
  const intermediaryNodes = currentAlert.nodes.filter(n => {
    const r = (n.role||'').toLowerCase();
    return r !== 'source' && r !== 'destination';
  });
  const needsNumbering = intermediaryNodes.length > 1;

  currentAlert.nodes.forEach(n => {
    const c = SEV_NODE[n.sev]||SEV_NODE.low;
    const r = (n.role||'').toLowerCase();
    let shortLabel;
    if (r === 'source') {
      shortLabel = 'S';
    } else if (r === 'destination') {
      shortLabel = 'D';
    } else {
      // intermediary, distributor, coordinator, hub, etc.
      shortLabel = needsNumbering ? `I${intermediaryIdx}` : 'I';
      intermediaryIdx++;
    }
    elements.push({ data:{ id:n.id, label:shortLabel, sev:n.sev, role:n.role,
      bank:n.bank, vol:n.vol, txn:n.txn }, style:{
      'background-color':c.bg, 'border-color':c.border,
    }});
  });
  currentAlert.edges.forEach(e => {
    const fmt = (currentAlert.transactions[e.txIdx]||{}).fmt||'';
    const importance = e.importance || 0.5;
    elements.push({ data:{ id:e.id, source:e.source, target:e.target,
      label:e.label, txIdx:e.txIdx, fmt, importance } });
  });

  cy = cytoscape({
    container: document.getElementById('cy'),
    elements,
    style:[
      { selector:'node', style:{
        'background-color':'data(background-color)',
        'border-color':'data(border-color)',
        'border-width':2, 'color':'#0F172A',
        'font-size':9, 'font-family':'Poppins, sans-serif',
        'label':'data(label)', 'text-valign':'center', 'width':38, 'height':38,
      }},
      { selector:'edge', style:{
        'line-color': e => getImportanceColor(e.data('importance')),
        'target-arrow-color': e => getImportanceColor(e.data('importance')),
        'target-arrow-shape':'triangle', 'curve-style':'bezier',
        'width': e => 1.5 + (e.data('importance')||0.5) * 2,
        'font-size':8, 'color':'#475569',
        'text-background-color': document.body.classList.contains('dark') ? '#1E293B' : '#fff',
        'text-background-opacity':.9,
        'text-background-padding':2,
      }},
      { selector:'node', style:{
        'background-color': ele => (SEV_NODE[ele.data('sev')]||SEV_NODE.low).bg,
        'border-color':     ele => (SEV_NODE[ele.data('sev')]||SEV_NODE.low).border,
      }},
      { selector:'.hl-edge', style:{ 'line-color':'#00579C','target-arrow-color':'#00579C','width':3 } },
      { selector:'.dim', style:{ opacity:0.15 } },
    ],
    layout: getLayout(currentAlert),
    userZoomingEnabled:true, userPanningEnabled:true,
  });

  cy.on('mouseover','node', e => {
    const n = e.target.data();
    const pos = e.renderedPosition;
    const box = document.getElementById('cy').getBoundingClientRect();
    const tt  = document.getElementById('tooltip');
    tt.style.left = (box.left+pos.x+16)+'px';
    tt.style.top  = (box.top+pos.y-20)+'px';
    tt.style.display='block';
    document.getElementById('tt-id').textContent   = n.id;
    document.getElementById('tt-bank').textContent = getBankName(n.bank)||'—';
    document.getElementById('tt-role').textContent = n.role||'—';
    document.getElementById('tt-vol').textContent  = n.vol||'—';
    document.getElementById('tt-txn').textContent  = n.txn||'—';
  });
  cy.on('mouseout','node', () => document.getElementById('tooltip').style.display='none');
  cy.on('mouseover','edge', e => {
    const edgeData = e.target.data();
    const pos = e.renderedPosition;
    const box = document.getElementById('cy').getBoundingClientRect();
    const tt  = document.getElementById('tooltip');
    tt.style.left = (box.left+pos.x+16)+'px';
    tt.style.top  = (box.top+pos.y-20)+'px';
    tt.style.display='block';
    document.getElementById('tt-id').textContent   = `${edgeData.source} → ${edgeData.target}`;
    document.getElementById('tt-bank').textContent = edgeData.label||'—';
    document.getElementById('tt-role').textContent = `Importance: ${Math.round(edgeData.importance * 100)}%`;
    document.getElementById('tt-vol').textContent  = '—';
    document.getElementById('tt-txn').textContent  = '—';
  });
  cy.on('mouseout','edge', () => document.getElementById('tooltip').style.display='none');
  cy.on('tap','node', e => highlightNode(e.target.id()));
}

function highlightNode(id) {
  if (!cy) return;
  resetHighlight();
  cy.nodes(`[id="${id}"]`).style({'border-width':4});
  cy.elements().not(`[id="${id}"]`).not(cy.nodes(`[id="${id}"]`).connectedEdges()).addClass('dim');
  document.querySelectorAll('.route-pill').forEach(p=>p.classList.toggle('active-node', p.textContent===id));
}
function resetHighlight() {
  if (!cy) return;
  cy.elements().removeClass('dim hl-edge');
  cy.nodes().style({'border-width':2});
  document.querySelectorAll('.route-pill').forEach(p=>p.classList.remove('active-node'));
}
function downloadPNG() {
  if (!cy) return;
  const a = document.createElement('a');
  a.href = cy.png({scale:2, bg: document.body.classList.contains('dark') ? '#0D1B2A' : '#F8FAFC'});
  a.download = `aml-${currentAlert?.id||'graph'}.png`; a.click();
}

/* ════════════════════════════════════════════
   TIMELINE
════════════════════════════════════════════ */
function renderTimeline() {
  updateCounter(); renderDots();
  if (currentAlert?.transactions?.length) applyStep(0);
}
function applyStep(idx) {
  if (!currentAlert) return;
  const txns = currentAlert.transactions;
  if (idx<0||idx>=txns.length) return;
  currentStep = idx;
  const tx = txns[idx];
  const edge = currentAlert.edges[idx];
  const imp = edge?.importance || 0.5;
  const impColor = getImportanceColor(imp);
  document.getElementById('tl-card').innerHTML = `
    <div class="tl-route">
      <span style="color:var(--blue)">${tx.from}</span>
      <span style="color:var(--light)">→</span>
      <span style="color:var(--green)">${tx.to}</span>
      <span class="badge badge-teal">${tx.fmt||'—'}</span>
    </div>
    <div class="tl-details">
      <span>Paid: <strong>${tx.paid}</strong></span>
      <span>Recv: <strong>${tx.recv}</strong></span>
      <span>${tx.fromBank} → ${tx.toBank}</span>
      <span>${tx.ts||'—'}</span>
      <span style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);color:${impColor};font-weight:500">🔍 ML Importance: ${Math.round(imp*100)}%</span>
    </div>`;
  if (cy) {
    cy.edges().removeClass('hl-edge');
    const me = currentAlert.edges.find(e=>e.txIdx===idx);
    if (me) cy.edges(`[id="${me.id}"]`).addClass('hl-edge');
  }
  updateCounter(); renderDots();
}
function stepBy(d) {
  if (!currentAlert) return;
  const n = currentStep+d;
  if (n>=0&&n<currentAlert.transactions.length) applyStep(n);
}
function tlPlay() {
  if (!currentAlert) return;
  if (playTimer) {
    clearInterval(playTimer); playTimer=null;
    document.getElementById('play-btn').textContent='▶ Play';
  } else {
    document.getElementById('play-btn').textContent='⏸ Pause';
    playTimer = setInterval(()=>{
      if (currentStep<currentAlert.transactions.length-1) { currentStep++; applyStep(currentStep); }
      else { clearInterval(playTimer); playTimer=null; document.getElementById('play-btn').textContent='▶ Play'; }
    },1500);
  }
}
function updateCounter() {
  const t = currentAlert ? currentAlert.transactions.length : 0;
  document.getElementById('tl-counter').textContent = t ? `${currentStep<0?'—':currentStep+1} / ${t}` : '— / —';
}
function renderDots() {
  const t = currentAlert ? currentAlert.transactions.length : 0;
  document.getElementById('tl-dots').innerHTML = Array.from({length:t},(_,i)=>{
    const edge = currentAlert?.edges[i];
    const imp = edge?.importance || 0.5;
    const isImportant = imp >= 0.7;
    return `<div class="tl-dot ${i<currentStep?'visited':''} ${i===currentStep?'current':''} ${isImportant?'important':''}"
          onclick="applyStep(${i})" role="button" tabindex="0" aria-label="Transaction ${i+1}"
          onkeydown="if(event.key==='Enter')applyStep(${i})" style="box-shadow:${isImportant?`0 0 8px ${getImportanceColor(imp)}`:'none'}"></div>`
  }).join('');
}

/* ════════════════════════════════════════════
   RIGHT PANEL
════════════════════════════════════════════ */
function renderRightPanel() {
  if (!currentAlert) return;
  const a = currentAlert;
  const sevColor = SEV_COLOR[a.severity]||'var(--muted)';

  document.getElementById('ir-pattern-sec').innerHTML = `
    <div class="ir-pattern-name" style="color:${sevColor}">${PATTERN_ICONS[a.patternType]||'?'} ${formatPatternName(a.patternType)}</div>
    <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:var(--sp-2)">
      <span class="badge ${SEV_BADGE[a.severity]||'badge-light'}">${a.severity}</span>
      <span class="badge ${SRC_BADGE[a.source]||'badge-blue'}">${SRC_LABEL[a.source]||''}</span>
      <span class="badge badge-light">${Math.round((a.confidence||0)*100)}% CONF</span>
      ${a.mlScore != null ? `<span class="badge" style="background:${a.mlScore>=0.7?'var(--red-bg)':a.mlScore>=0.4?'var(--amber-bg)':'var(--green-bg)'};color:${a.mlScore>=0.7?'var(--red)':a.mlScore>=0.4?'var(--amber)':'var(--green)'};border:1px solid ${a.mlScore>=0.7?'var(--red-bd)':a.mlScore>=0.4?'var(--amber-bd)':'var(--green-bd)'}">🤖 ML ${Math.round(a.mlScore*100)}%</span>` : ''}
    </div>
    <div class="ir-desc">${a.description||''}</div>`;

  // Source / signals
  const srcEl = document.getElementById('ir-source-sec');
  srcEl.style.display='block';
  const sigs = a.signalsTriggered||[];
  let srcHtml = `<span class="label-up">Detection Source</span>`;
  if (a.source==='labelled') {
    srcHtml += `<div class="signal-chip blue">🏷 Is Laundering label filter</div>`;
  } else if (a.source==='both') {
    srcHtml += `<div class="signal-chip" style="background:var(--amber-bg);border-color:var(--amber-bd);color:var(--amber)">⭐ Cross-validated by both modes</div>`;
  } else {
    srcHtml += sigs.map(s=>`<div class="signal-chip">${SIGNAL_ICONS[s]||'•'} ${s}</div>`).join('') ||
      `<span style="color:var(--light);font-size:var(--text-sm);font-family:var(--mono)">No signals recorded</span>`;
  }
  srcEl.innerHTML = srcHtml;

  // Roles
  const roleEl = document.getElementById('ir-roles-sec');
  roleEl.style.display='block';
  const roleCnt = {};
  (a.nodes||[]).forEach(n=>{ roleCnt[n.role]=(roleCnt[n.role]||{count:0,sev:n.sev}); roleCnt[n.role].count++; });
  const roleColors = {high:'var(--red)',medium:'var(--amber)',low:'var(--green)'};
  roleEl.innerHTML = `<span class="label-up">Node Roles</span>` +
    Object.entries(roleCnt).map(([role,{count,sev}])=>
      `<div class="role-row"><div class="role-dot" style="background:${roleColors[sev]||'#94A3B8'}"></div>
       <span>${role}</span><span style="color:var(--muted);margin-left:auto">×${count}</span></div>`
    ).join('');

  renderDecStatus();
}

function renderDecStatus() {
  if (!currentAlert) return;
  const dec = decisions[currentAlert.id];
  const el  = document.getElementById('dec-status-box');
  if (dec) {
    el.style.display='block';
    el.className = `dec-status-box ${dec.decision}`;
    el.textContent = {confirm:'✓ Confirmed',review:'⚠ Needs Review',dismiss:'✗ Dismissed'}[dec.decision]||dec.decision;
  } else { el.style.display='none'; }
}

/* ════════════════════════════════════════════
   DECISIONS
════════════════════════════════════════════ */
async function postDecision(decision) {
  if (!currentAlert) return;
  const reason = document.getElementById('dec-reason').value||'';
  try {
    const r = await fetch(`${API_BASE}/alerts/${currentAlert.id}/decision`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({decision,reason})
    });
    const d = await r.json();
    if (d.status==='saved') {
      decisions[currentAlert.id]={decision,reason};
      renderSidebar(); renderDecStatus(); renderDashboard();
      document.querySelectorAll('.ac').forEach(c=>c.classList.remove('active'));
      document.getElementById('ac_'+currentAlert.id)?.classList.add('active');
      toast(`Decision saved: ${decision} ✓`,'success');
    }
  } catch(e){ toast('Error saving decision','error'); }
}

/* ════════════════════════════════════════════
   CASE MANAGER
════════════════════════════════════════════ */
function setCaseFilter(v,el) {
  caseFilter=v;
  document.querySelectorAll('#case-filters .filter-pill').forEach(p=>p.classList.remove('active'));
  el.classList.add('active'); renderCaseManager();
}
function renderCaseManager() {
  const rows = allAlerts.filter(a=>{
    const dec=decisions[a.id]; if(!dec) return false;
    return caseFilter==='all'||dec.decision===caseFilter;
  });
  const tbody = document.getElementById('cases-tbody');
  const empty = document.getElementById('cases-empty');
  if (!rows.length) { tbody.innerHTML=''; empty.style.display='block'; return; }
  empty.style.display='none';
  tbody.innerHTML = rows.map(a=>{
    const dec=decisions[a.id];
    const decColors={confirm:'var(--green)',review:'var(--amber)',dismiss:'var(--red)'};
    return `<tr>
      <td style="font-size:var(--text-xs);color:var(--muted);font-family:var(--mono)">${a.id}</td>
      <td style="font-family:var(--sans);font-weight:600">${formatPatternName(a.patternType)}</td>
      <td><span class="badge ${SEV_BADGE[a.severity]||'badge-light'}">${a.severity}</span></td>
      <td>${Math.round((a.confidence||0)*100)}%</td>
      <td>${a.totalMoved}</td>
      <td><span class="badge ${SRC_BADGE[a.source]||'badge-blue'}">${SRC_LABEL[a.source]||''}</span></td>
      <td style="color:${decColors[dec.decision]};font-weight:600;font-family:var(--sans)">${dec.decision.toUpperCase()}</td>
      <td style="color:var(--muted);font-size:var(--text-sm)">${dec.reason||'—'}</td>
      <td><button class="btn btn-ghost" style="font-size:var(--text-xs);padding:var(--sp-1) var(--sp-2)" onclick="jumpInvestigate('${a.id}')">Re-open</button></td>
    </tr>`;
  }).join('');
}
function exportCSV() {
  const rows = allAlerts.filter(a=>decisions[a.id]);
  if (!rows.length) { toast('No decisions to export','warning'); return; }
  const hdr = 'Alert ID,Pattern,Severity,Confidence,Total Moved,Source,Decision,Reason';
  const lines = rows.map(a=>{
    const d=decisions[a.id];
    return [a.id,formatPatternName(a.patternType),a.severity,`${Math.round((a.confidence||0)*100)}%`,
      a.totalMoved,a.source||'',d.decision,(d.reason||'').replace(/,/g,' ')].join(',');
  });
  const blob=new Blob([[hdr,...lines].join('\n')],{type:'text/csv'});
  const url=URL.createObjectURL(blob);
  const l=document.createElement('a'); l.href=url; l.download='aml-cases.csv';
  l.click(); URL.revokeObjectURL(url);
  toast('Export ready','success');
}

/* ════════════════════════════════════════════
   SEARCH
════════════════════════════════════════════ */
function doSearch() {
  const q = (document.getElementById('search-inp').value||'').trim();
  document.querySelectorAll('.quick-filters .filter-pill').forEach(p => p.classList.remove('active'));
  runSearch(q, 'auto');
}

function qFilter(val, type='pat') {
  const patDisplayMap = {
    fanOut:'FAN-OUT', fanIn:'FAN-IN', scatterGather:'SCATTER-GATHER',
    gatherScatter:'GATHER-SCATTER', cycle:'CYCLE', bipartite:'BIPARTITE', stack:'STACK',
  };
  document.querySelectorAll('.quick-filters .filter-pill').forEach(p => p.classList.remove('active'));
  event.currentTarget.classList.add('active');
  document.getElementById('search-inp').value = (type==='pat' && patDisplayMap[val]) ? patDisplayMap[val] : '';
  runSearch(val, type);
}

function normStr(s) { return String(s).replace(/[-_\s]/g,'').toLowerCase(); }

function runSearch(q, type='auto') {
  const container = document.getElementById('search-results');

  let res;
  if (type === 'all' || (!q && type !== 'sev' && type !== 'src' && type !== 'pat')) {
    res = allAlerts.slice();
  } else {
    const lq = q.toLowerCase().trim();
    res = allAlerts.filter(a => {
      if (type === 'sev') return a.severity === lq.toUpperCase();
      if (type === 'src') return a.source === lq;
      if (type === 'pat') {
        return normStr(a.patternType) === normStr(lq);
      }
      const nq = normStr(lq);
      const det = alertDetails[a.id];
      const nodes = (det ? det.nodes.map(n => n.id).join(' ') : '') || '';
      const banks = (det ? det.nodes.map(n => getBankName(n.bank||'')).join(' ') : '') || '';
      return normStr(formatPatternName(a.patternType)).includes(nq) ||
        normStr(a.name||'').includes(nq) ||
        a.id.toLowerCase().includes(lq) ||
        (a.sub||'').toLowerCase().includes(lq) ||
        nodes.toLowerCase().includes(lq) ||
        banks.toLowerCase().includes(lq);
    });
  }

  if (!res.length) {
    container.innerHTML = `<div class="search-empty">No alerts match "${q}"</div>`;
    return;
  }

  const header = `<div style="grid-column:1/-1;font-family:var(--mono);font-size:var(--text-sm);
    color:var(--muted);margin-bottom:var(--sp-1)">${res.length} alert${res.length!==1?'s':''} found</div>`;

  const cards = res.map(a => {
    const patLabel = a.name || formatPatternName(a.patternType);
    const mlPct = a.mlScore != null ? Math.round(a.mlScore * 100) : null;
    const mlBg  = mlPct != null ? (mlPct>=70?'var(--red-bg)':mlPct>=40?'var(--amber-bg)':'var(--green-bg)') : '';
    const mlClr = mlPct != null ? (mlPct>=70?'var(--red)':mlPct>=40?'var(--amber)':'var(--green)') : '';
    const mlBd  = mlPct != null ? (mlPct>=70?'var(--red-bd)':mlPct>=40?'var(--amber-bd)':'var(--green-bd)') : '';
    return `
    <div class="search-card sev-${a.severity}" style="border-left-color:${SEV_COLOR[a.severity]||'var(--border)'}"
         onclick="jumpInvestigate('${a.id}')" role="button" tabindex="0"
         aria-label="${patLabel}, ${a.severity} severity"
         onkeydown="if(event.key==='Enter')jumpInvestigate('${a.id}')">
      <div style="font-family:var(--sans);font-weight:700;font-size:var(--text-base);margin-bottom:var(--sp-2);color:var(--text)">
        ${PATTERN_ICONS[a.patternType]||'?'} ${patLabel}
      </div>
      <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:var(--sp-2)">
        <span class="badge ${SEV_BADGE[a.severity]||'badge-light'}">${a.severity}</span>
        <span class="badge ${SRC_BADGE[a.source]||'badge-blue'}">${SRC_LABEL[a.source]||''}</span>
        ${mlPct!=null?`<span class="badge" style="background:${mlBg};color:${mlClr};border:1px solid ${mlBd}">ML ${mlPct}%</span>`:''}
      </div>
      <div style="font-size:var(--text-sm);color:var(--muted);font-family:var(--mono);margin-bottom:var(--sp-1)">${a.sub||''}</div>
      <div style="font-size:var(--text-sm);color:var(--text);font-family:var(--mono)">${a.totalMoved} · ${a.timeSpan} · ${a.node_count}n</div>
    </div>`;
  }).join('');

  container.innerHTML = header + cards;
}

/* ════════════════════════════════════════════
   VALIDATION
════════════════════════════════════════════ */
async function loadValidation() {
  try {
    const r=await fetch(`${API_BASE}/validation`);
    if (!r.ok) {
      document.getElementById('val-compare-body').innerHTML=
        `<tr><td colspan="5" style="color:var(--red);padding:var(--sp-4)">Run validator.py first to generate validation data.</td></tr>`;
      return;
    }
    renderValidation(await r.json());
  } catch(e) {
    document.getElementById('val-compare-body').innerHTML=
      `<tr><td colspan="5" style="color:var(--red);padding:var(--sp-4)">Error: ${e.message}</td></tr>`;
  }
}
function setRing(circleId,pctId,val,color) {
  const pct=Math.min(1,Math.max(0,val));
  const el=document.getElementById(circleId);
  if(el) el.setAttribute('stroke-dashoffset',(276*(1-pct)).toFixed(1));
  const pe=document.getElementById(pctId);
  if(pe) pe.textContent=`${Math.round(pct*100)}%`;
}
function renderValidation(data) {
  const lab=data.labelled||{}, unlab=data.unlabelled||{};
  setRing('ring-lab','ring-lab-pct',lab.overall_precision||0,'#00579C');
  setRing('ring-unlab','ring-unlab-pct',unlab.overall_precision||0,'#7C3AED');
  document.getElementById('val-compare-body').innerHTML=`
    <tr><td style="font-family:var(--sans);font-weight:600">Labelled</td>
        <td>${lab.total_alerts||0}</td><td>${lab.matched||0}</td>
        <td>${pct(lab.overall_precision)}</td><td>${pct(lab.overall_recall)}</td></tr>
    <tr><td style="font-family:var(--sans);font-weight:600">Unlabelled</td>
        <td>${unlab.total_alerts||0}</td><td>${unlab.matched||0}</td>
        <td>${pct(unlab.overall_precision)}</td><td>${pct(unlab.overall_recall)}</td></tr>
    <tr style="border-top:2px solid var(--border)">
        <td style="color:var(--amber);font-weight:600">Overlap</td>
        <td style="color:var(--amber)">${data.overlap_count||0}</td>
        <td>—</td><td>—</td><td>—</td></tr>`;
  const prec=lab.per_pattern_precision||{}, rec=lab.per_pattern_recall||{};
  const recs=lab.records||[];
  const det={}, corr={};
  recs.forEach(r=>{ det[r.detected_type]=(det[r.detected_type]||0)+1; if(r.status==='correct') corr[r.detected_type]=(corr[r.detected_type]||0)+1; });
  document.getElementById('val-prec-body').innerHTML=Object.entries(prec).map(([pt,p])=>`
    <tr><td>${pt}</td><td>${det[pt]||0}</td><td>${corr[pt]||0}</td>
    <td><div style="display:flex;align-items:center;gap:var(--sp-2)">
      <div class="prec-bar-bg" style="width:80px"><div class="prec-bar-fill" style="width:${(p*100).toFixed(0)}%"></div></div>${pct(p)}
    </div></td></tr>`).join('')||'<tr><td colspan="4" style="color:var(--muted)">No data</td></tr>';
  document.getElementById('val-recall-body').innerHTML=Object.entries(rec).map(([pt,r])=>`
    <tr><td>${pt}</td><td>?</td><td>${Math.round(r*10)}</td>
    <td><div style="display:flex;align-items:center;gap:var(--sp-2)">
      <div class="prec-bar-bg" style="width:80px"><div class="prec-bar-fill" style="width:${(r*100).toFixed(0)}%;background:var(--purple)"></div></div>${pct(r)}
    </div></td></tr>`).join('')||'<tr><td colspan="4" style="color:var(--muted)">No data</td></tr>';
}
function pct(v){ return v!=null?`${Math.round((v||0)*100)}%`:'—'; }

/* ════════════════════════════════════════════
   WHITELIST
════════════════════════════════════════════ */
async function loadWhitelist() {
  const [wlRes, suppRes] = await Promise.all([
    fetch(`${API_BASE}/whitelist`).then(r=>r.json()).catch(()=>null),
    fetch(`${API_BASE}/alerts/suppressed`).then(r=>r.json()).catch(()=>[]),
  ]);
  if (wlRes) renderWhitelistPanel(wlRes);
  renderSuppressed(Array.isArray(suppRes) ? suppRes : []);
}

function renderWhitelistPanel(wl) {
  const accs = wl.exempt_accounts||[];
  document.getElementById('wl-accounts-list').innerHTML = accs.length
    ? accs.map(a=>`<div class="wl-account-item">${a}
        <button class="wl-remove-btn" onclick="removeWhitelistAccount('${a}')" aria-label="Remove ${a} from whitelist">×</button></div>`).join('')
    : `<span style="color:var(--light);font-size:var(--text-sm);font-family:var(--mono)">No accounts explicitly whitelisted</span>`;

  document.getElementById('wl-banks-list').innerHTML = (wl.exempt_banks||[])
    .map(b=>`<span class="badge badge-teal">${b}</span>`).join('');

  const rules = wl.exemption_rules||{};
  document.getElementById('wl-rules-list').innerHTML = Object.entries(rules).map(([pat,rule])=>`
    <div class="wl-rule-item">
      <div class="wl-rule-pattern">${pat}</div>
      <div class="wl-rule-reason">${rule.reason}</div>
      <div style="margin-top:var(--sp-1);display:flex;gap:var(--sp-1);flex-wrap:wrap">
        ${(rule.exempt_if||[]).map(c=>`<span class="badge badge-light">${c}</span>`).join('')}
      </div>
    </div>`).join('');
}

function renderSuppressed(suppressed) {
  const tbody=document.getElementById('suppressed-tbody');
  const empty=document.getElementById('suppressed-empty');
  document.getElementById('suppressed-count').textContent=`${suppressed.length} alert${suppressed.length!==1?'s':''}`;
  if (!suppressed.length) { tbody.innerHTML=''; empty.style.display='block'; return; }
  empty.style.display='none';
  tbody.innerHTML=suppressed.map(a=>`<tr>
    <td style="font-size:var(--text-xs);color:var(--muted);font-family:var(--mono)">${a.id}</td>
    <td style="font-family:var(--sans);font-weight:600">${formatPatternName(a.patternType||'')}</td>
    <td><span class="badge ${SEV_BADGE[a.severity]||'badge-light'}">${a.severity||'—'}</span></td>
    <td style="font-size:var(--text-sm);color:var(--muted)">${a.exemption_reason||'—'}</td>
    <td style="font-size:var(--text-sm);color:var(--muted)">${(a.exempt_accounts||[]).join(', ')||'—'}</td>
    <td><button class="btn btn-ghost" style="font-size:var(--text-xs);padding:var(--sp-1) var(--sp-2)" onclick="jumpInvestigate('${a.id}')">View</button></td>
  </tr>`).join('');
}

async function addWhitelistAccount() {
  const id=(document.getElementById('wl-account-inp').value||'').trim();
  if (!id) { toast('Enter an account ID','warning'); return; }
  const reason=(document.getElementById('wl-reason-inp').value||'').trim();
  try {
    const r=await fetch(`${API_BASE}/whitelist/account`,{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({account_id:id,reason})
    });
    const d=await r.json();
    document.getElementById('wl-account-inp').value='';
    document.getElementById('wl-reason-inp').value='';
    renderWhitelistPanel(d.whitelist);
    toast(`Added ${id} to whitelist`,'success');
  } catch(e){ toast('Error adding to whitelist','error'); }
}

async function removeWhitelistAccount(id) {
  try {
    await fetch(`${API_BASE}/whitelist/account/${encodeURIComponent(id)}`,{method:'DELETE'});
    await loadWhitelist();
    toast(`Removed ${id} from whitelist`,'success');
  } catch(e){ toast('Error removing from whitelist','error'); }
}

/* ════════════════════════════════════════════
   TOAST
════════════════════════════════════════════ */
function toast(msg, type='info') {
  const container=document.getElementById('toasts');
  const el=document.createElement('div');
  el.className=`toast ${type}`;
  el.textContent=msg;
  el.setAttribute('role','alert');
  el.setAttribute('aria-live','polite');
  container.appendChild(el);
  const all=container.querySelectorAll('.toast');
  if (all.length>3) all[0].remove();
  requestAnimationFrame(()=>el.classList.add('show'));
  setTimeout(()=>{ el.classList.remove('show'); setTimeout(()=>el.remove(),300); },3000);
}

/* ════════════════════════════════════════════
   KEYBOARD SHORTCUTS (Investigate view)
════════════════════════════════════════════ */
document.addEventListener('keydown', e => {
  // Don't fire shortcuts when typing in inputs
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

  const investigateActive = document.getElementById('view-investigate')?.classList.contains('active');

  if (investigateActive && currentAlert) {
    switch(e.key.toLowerCase()) {
      case 'j': // Next alert
        e.preventDefault();
        navigateAlert(1);
        break;
      case 'k': // Previous alert
        e.preventDefault();
        navigateAlert(-1);
        break;
      case 'c': // Confirm
        e.preventDefault();
        postDecision('confirm');
        break;
      case 'r': // Review
        e.preventDefault();
        postDecision('review');
        break;
      case 'd': // Dismiss
        e.preventDefault();
        postDecision('dismiss');
        break;
      case 'arrowleft': // Prev transaction
        e.preventDefault();
        stepBy(-1);
        break;
      case 'arrowright': // Next transaction
        e.preventDefault();
        stepBy(1);
        break;
      case ' ': // Play/pause timeline
        e.preventDefault();
        tlPlay();
        break;
    }
  }
});

function navigateAlert(direction) {
  if (!currentAlert || !allAlerts.length) return;
  const currentIdx = allAlerts.findIndex(a => a.id === currentAlert.id);
  if (currentIdx === -1) return;
  const newIdx = currentIdx + direction;
  if (newIdx >= 0 && newIdx < allAlerts.length) {
    loadAlertById(allAlerts[newIdx].id);
  }
}

/* ═══ BOOT ═══ */
// Auth screen handles init() — no auto-start
