'use strict';

// ── Scroll-aware nav ──────────────────────────────────────────────────────────
(function () {
  const nav = document.getElementById('main-nav');
  const indicator = document.getElementById('scroll-indicator');
  let ticking = false;
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        const scrolled = window.scrollY > 60;
        nav.classList.toggle('scrolled', scrolled);
        if (indicator) indicator.style.opacity = scrolled ? '0' : '';
        ticking = false;
      });
      ticking = true;
    }
  }, { passive: true });
})();

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  allLeads:   [],
  filtered:   [],
  sortCol:    'propensity_score',
  sortDir:    'desc',
  pollTimer:  null,
  initialized: false,
  openLeadId: null,
};

// ── DOM ───────────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const dom = {
  tbody:        $('leads-tbody'),
  resultN:      $('results-n'),
  sortInfo:     $('sort-info'),
  statTotal:    $('stat-total'),
  statPriority: $('stat-priority'),
  statHot:      $('stat-hot'),
  statMonitor:  $('stat-monitor'),
  navTimestamp: $('nav-timestamp'),
  banner:       $('pipeline-banner'),
  bannerLabel:  $('pipeline-label'),
  bannerFill:   $('pipeline-fill'),
  bannerPct:    $('pipeline-pct'),
  ctrlScore:    $('ctrl-min-score'),
  ctrlScoreVal: $('ctrl-score-display'),
  ctrlTier:     $('ctrl-tier'),
  ctrlState:    $('ctrl-state'),
  ctrlNode:     $('ctrl-node'),
  ctrlSearch:   $('ctrl-search'),
  btnRefresh:   $('btn-refresh'),
  btnExport:    $('btn-export'),
  toast:        $('toast'),
  panel:        $('detail-panel'),
  overlay:      $('detail-overlay'),
};

// ── Right-side Detail Panel ───────────────────────────────────────────────────
function openPanel(lead) {
  if (!lead) return;
  state.openLeadId = lead.id;
  dom.panel.innerHTML = buildPanelHTML(lead);
  dom.panel.classList.add('open');
  dom.overlay.style.display = 'block';
  document.body.style.overflow = 'hidden';
}

window.closePanel = function () {
  dom.panel.classList.remove('open');
  dom.overlay.style.display = 'none';
  document.body.style.overflow = '';
  state.openLeadId = null;
  dom.tbody.querySelectorAll('tr.data-row.row-open').forEach(r => {
    r.classList.remove('row-open');
    r.setAttribute('aria-expanded', 'false');
  });
};

function buildPanelHTML(lead) {
  const esc = s => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const fmt = s => { try { return new Date(s+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}); } catch { return s || '—'; } };

  const score      = (lead.propensity_score || 0).toFixed(1);
  const tier       = lead.score_tier || 'low';
  const tierLabel  = { priority:'PRIORITY', hot:'HOT', monitor:'MONITOR', low:'LOW' }[tier] || 'LOW';
  const dtl        = lead.days_to_lapse;
  const lender     = lead.secured_party || 'Unknown Lender';
  const collateral = lead.collateral || lead.predicted_asset || '—';
  const ageMo      = lead.filing_age_months ? lead.filing_age_months.toFixed(1) : '—';

  // ── Urgency ──────────────────────────────────────────────────────────────
  let accentClass = 'ok';
  let urgencyLabel = dtl != null ? `${dtl} Days Remaining` : 'Unknown';
  let urgencyColor = '#34c759';
  let urgencyContext = '';
  if (dtl != null) {
    if (dtl < 0)   { accentClass='urgent';  urgencyColor='#ff3b3b'; urgencyLabel=`Lapsed ${Math.abs(dtl)} Days Ago`; urgencyContext='Lender relationship expired. Competitor may have already made contact.'; }
    else if (dtl===0){ accentClass='urgent'; urgencyColor='#ff3b3b'; urgencyLabel='Expires TODAY'; urgencyContext='Maximum urgency — decision is being made right now.'; }
    else if (dtl<=7) { accentClass='urgent'; urgencyColor='#ff3b3b'; urgencyLabel=`${dtl} Days Remaining`; urgencyContext='Critical window — very high likelihood of active vendor evaluation.'; }
    else if (dtl<=30){ accentClass='warning';urgencyColor='#ff8c00'; urgencyLabel=`${dtl} Days Remaining`; urgencyContext='30-day window — early mover advantage. Position before competitors reach out.'; }
    else if (dtl<=90){ accentClass='warm';   urgencyColor='#f5a623'; urgencyLabel=`${dtl} Days Remaining`; urgencyContext='Warm window — company beginning to evaluate renewal options.'; }
    else             { accentClass='ok';     urgencyColor='#6b7280'; urgencyLabel=`${dtl} Days Remaining`; urgencyContext='Monitor. Schedule outreach 60 days before lapse.'; }
  }

  // ── Lender Intel ─────────────────────────────────────────────────────────
  const lu = lender.toUpperCase();
  let lenderType = 'Independent / Specialty Lender';
  let lenderIntel = 'Approach with a competitive rate comparison — emphasize speed of close, flexible term structures, and multi-brand capability at renewal.';
  if (lu.includes('CATERPILLAR') || lu.includes('CAT FINANCIAL')) {
    lenderType = '◼ Caterpillar Financial (Captive)';
    lenderIntel = '<strong>Captive lien — CAT-branded equipment only.</strong> FMV lease residuals inflated 20-30% above market. At lapse, CAT pushes fleet management programs with 5-year lock-ins. Counter with multi-brand capability and $1 buyout or EFA structures CAT cannot match.';
  } else if (lu.includes('WELLS FARGO')) {
    lenderType = '◻ Wells Fargo Equipment Finance';
    lenderIntel = '<strong>WF exited small-ticket equipment lending (&lt;$250K) in 2021.</strong> This lapse will NOT be renewed by WF — the client already needs a new lender. No incumbent fighting for the renewal. Warm introduction — they know they need to refinance.';
  } else if (lu.includes('MARLIN')) {
    lenderType = '▹ Marlin Business Services';
    lenderIntel = '<strong>Acquired by HPS Investment Partners (2022).</strong> Post-acquisition underwriting tightened ~20%. Existing clients seeing renewal offers 50-100bps above original rate. Beat their renewal rate and you win — they\'re not negotiating aggressively during integration.';
  } else if (lu.includes('JOHN DEERE') || lu.includes('DEERE')) {
    lenderType = '◼ John Deere Financial (Captive)';
    lenderIntel = '<strong>Captive — Deere-branded equipment only.</strong> At lapse, Deere pushes 5-year fleet programs. Multi-brand flexibility and EFA structures are a strong counter. No penalty at natural lapse — clean displacement window.';
  } else if (lu.includes('KOMATSU')) {
    lenderType = '◼ Komatsu Financial (Captive)';
    lenderIntel = '<strong>Single-brand lock.</strong> At natural lapse, zero penalty — clean displacement window. Position with competitive rate and multi-brand used equipment options.';
  } else if (lu.includes('VOLVO')) {
    lenderType = '◼ Volvo Financial Services';
    lenderIntel = '<strong>FMV leases with residuals 15-25% above market.</strong> Volvo construction and truck divisions share the same financial arm. Clean buyout option is a strong counter. Confirm equipment type (construction vs. truck).';
  } else if (lu.includes('BANK OF AMERICA') || lu.includes('BANC OF AMERICA') || lu.includes('BANC OF AMER')) {
    lenderType = '◻ Banc of America Leasing';
    lenderIntel = '<strong>Major banks rarely renew equipment-specific deals</strong> — they push clients toward generic commercial lines. Position as a dedicated equipment finance specialist with faster approvals and better equipment-specific terms.';
  } else if (lu.includes('SIEMENS')) {
    lenderType = '▸ Siemens Financial Services';
    lenderIntel = '<strong>At lapse, Siemens pushes digital service bundles at 15-20% premium.</strong> Clients who want equipment — not managed services — are easily displaced. Clean separation is your angle.';
  } else if (lu.includes('DLL') || lu.includes('DE LAGE LANDEN')) {
    lenderType = '▹ DLL / De Lage Landen';
    lenderIntel = '<strong>White-label lessor behind many OEM financing programs.</strong> Client may not know DLL holds the lien. Auto-renewals at 110% of original rate are standard. Window opens 60 days before lapse — time outreach precisely.';
  }

  // ── Score ring ────────────────────────────────────────────────────────────
  const pct     = Math.min(100, parseFloat(score));
  const r       = 30;
  const circ    = 2 * Math.PI * r;
  const offset  = circ - (pct / 100) * circ;
  const ringColor = { priority:'#111827', hot:'#374151', monitor:'#6b7280', low:'#9ca3af' }[tier] || '#9ca3af';

  // ── Node ──────────────────────────────────────────────────────────────────
  const node = lead.nearest_node || '—';
  const dist = lead.nearest_node_dist_km != null ? `${Math.round(lead.nearest_node_dist_km).toLocaleString()} km` : '—';

  // ── Entity badges ─────────────────────────────────────────────────────────
  const matches = (lead.entity_matches || []);
  const matchHTML = matches.length
    ? matches.map(m => `<span class="dp-badge">${esc(m)}</span>`).join('')
    : '<span class="dp-empty-note">No SpaceX entity matches detected</span>';

  const priceObj = TIER_PRICES[tier] || TIER_PRICES.low;
  const priceStr = `$${priceObj.price.toFixed(2)}`;

  let contactCardHTML = '';
  if (lead.locked) {
    contactCardHTML = `
    <!-- GLASSMORPHIC PAYWALL CARD -->
    <div class="sx-paywall-card">
      <div class="sx-paywall-icon">🔒</div>
      <div class="sx-paywall-title">Lead Locked (Tier: ${tierLabel})</div>
      <div class="sx-paywall-price">${priceStr}</div>
      <div class="sx-paywall-desc">Unlock full company name, location, and verified contact details instantly. Ready for immediate outreach and CRM import.</div>
      <button class="sx-paywall-btn" onclick="unlockLead('${esc(lead.id)}')">Unlock Lead</button>
    </div>`;
  } else {
    contactCardHTML = `
    <!-- COMPANY & CONTACT -->
    <div class="dp-card">
      <div class="dp-card-header">🏢 Company & Contact</div>
      ${lead.address || lead.phone || lead.email || lead.company_website ? `
      <table class="dp-table">
        ${lead.address ? `<tr><td>Address</td><td>${esc(lead.address)}</td></tr>` : ''}
        ${lead.phone   ? `<tr><td>Phone</td><td><a href="tel:${esc(lead.phone)}">${esc(lead.phone)}</a></td></tr>` : ''}
        ${lead.email   ? `<tr><td>Email</td><td><a href="mailto:${esc(lead.email)}">${esc(lead.email)}</a></td></tr>` : ''}
        ${lead.company_website ? `<tr><td>Website</td><td><a href="${esc(lead.company_website)}" target="_blank" rel="noopener">${esc(lead.company_website)}</a></td></tr>` : ''}
      </table>` : '<div class="dp-empty-note">Contact data pending — FOIA enrichment in queue for TX/TN filings</div>'}
    </div>`;
  }

  const primaryActionHTML = lead.locked
    ? `<button class="dp-action-primary" onclick="unlockLead('${esc(lead.id)}')">🔓 Unlock Lead — ${priceStr}</button>`
    : `<button class="dp-action-primary" onclick="exportSingleLead('${esc(lead.id)}')">↓ Export This Lead</button>`;

  return `
  <div class="dp-accent-bar ${accentClass}"></div>

  <div class="dp-header">
    <div class="dp-header-info">
      <div class="dp-company">${esc(lead.company_name || '—')}</div>
      <div class="dp-location">${esc(lead.city || '')}${lead.city && lead.state ? ', ' : ''}${esc(lead.state || '')} · UCC-1 Filing</div>
    </div>
    <button class="dp-close" onclick="closePanel()" aria-label="Close">✕</button>
  </div>

  <div class="dp-body">

    <!-- URGENCY -->
    <div class="dp-urgency-block">
      <div class="dp-urgency-label">Lapse Urgency</div>
      <div class="dp-urgency-days" style="color:${urgencyColor}">${urgencyLabel}</div>
      ${urgencyContext ? `<div class="dp-urgency-ctx">${urgencyContext}</div>` : ''}
      <div class="dp-filing-meta">
        <div class="dp-meta-item"><span class="dp-meta-label">Filed</span><span class="dp-meta-val">${fmt(lead.filing_date)}</span></div>
        <div class="dp-meta-item"><span class="dp-meta-label">Lapses</span><span class="dp-meta-val">${fmt(lead.lapse_date)}</span></div>
        <div class="dp-meta-item"><span class="dp-meta-label">Age</span><span class="dp-meta-val">${ageMo} mo</span></div>
      </div>
    </div>

    <!-- SCORE RING -->
    <div class="dp-score-block">
      <div class="dp-score-ring-wrap">
        <svg viewBox="0 0 72 72">
          <circle class="dp-score-ring-bg" cx="36" cy="36" r="${r}"/>
          <circle class="dp-score-ring-fill" cx="36" cy="36" r="${r}"
            stroke="${ringColor}"
            stroke-dasharray="${circ.toFixed(2)}"
            stroke-dashoffset="${offset.toFixed(2)}"/>
        </svg>
        <div class="dp-score-ring-label">
          <span class="dp-score-ring-num">${score}</span>
          <span class="dp-score-ring-tier">${tierLabel}</span>
        </div>
      </div>
      <div class="dp-score-narrative">
        <div class="dp-score-section-label">⚡ Propensity Score</div>
        <div class="dp-score-text">
          ${tier==='priority' ? 'Top-tier lead. High UCC maturity + strong proximity to Musk infrastructure node. Outreach recommended immediately.' :
            tier==='hot'     ? 'High-probability target. UCC filing is maturing into the ideal replacement window.' :
            tier==='monitor' ? 'Mid-tier signal. Monitor and initiate outreach 60 days before lapse.' :
                               'Early-stage signal. Low proximity or early filing age. Add to long-horizon pipeline.'}
        </div>
        <div class="dp-score-rows">
          <div class="dp-score-row">
            <span class="dp-score-row-label">UCC Maturity</span>
            <div class="dp-mini-bar-track"><div class="dp-mini-bar-fill" style="width:${Math.min(100,(lead.score_w1||0)/33.3*100).toFixed(0)}%"></div></div>
            <span class="dp-score-row-val">${(lead.score_w1||0).toFixed(1)}</span>
          </div>
          <div class="dp-score-row dp-score-row--pending">
            <span class="dp-score-row-label">Job Board</span>
            <span class="dp-score-row-pending">Phase 2 — API key needed</span>
          </div>
          <div class="dp-score-row">
            <span class="dp-score-row-label">Node Proximity</span>
            <div class="dp-mini-bar-track"><div class="dp-mini-bar-fill" style="width:${Math.min(100,(lead.score_w3||0)/33.3*100).toFixed(0)}%"></div></div>
            <span class="dp-score-row-val">${(lead.score_w3||0).toFixed(1)}</span>
          </div>
          ${(lead.score_bonus||0) > 0 ? `
          <div class="dp-score-row">
            <span class="dp-score-row-label">Entity Bonus</span>
            <div class="dp-mini-bar-track"><div class="dp-mini-bar-fill" style="width:${Math.min(100,(lead.score_bonus||0)/7*100).toFixed(0)}%"></div></div>
            <span class="dp-score-row-val">+${lead.score_bonus}</span>
          </div>` : ''}
        </div>
      </div>
    </div>

    <!-- EST. FINANCING VOLUME -->
    <div class="dp-card">
      <div class="dp-card-header">📊 Est. Financing Volume</div>
      <div class="dp-volume-block">
        <div>
          <div class="dp-volume-num">${esc(lead.est_financing_volume || '—')}</div>
          <div class="dp-volume-sub">Signal-based estimate</div>
        </div>
        <div class="dp-volume-note">Based on collateral type and lender profile. Use as conversation anchor — actual deal size varies.</div>
      </div>
    </div>

    <!-- FILING INTELLIGENCE -->
    <div class="dp-card">
      <div class="dp-card-header">📄 Filing Intelligence</div>
      <table class="dp-table">
        <tr><td>Current Lender</td><td>${esc(lender)}</td></tr>
        <tr><td>Lender Type</td><td>${esc(lenderType)}</td></tr>
        <tr><td>Collateral</td><td>${esc(collateral)}</td></tr>
        <tr><td>Predicted Asset</td><td>${esc(lead.predicted_asset || '—')}</td></tr>
        <tr><td>Filed</td><td>${fmt(lead.filing_date)}</td></tr>
        <tr><td>Lapses</td><td>${fmt(lead.lapse_date)}</td></tr>
        ${lead.id ? `<tr><td>Filing ID</td><td><span style="font-family:monospace;font-size:0.6875rem;color:#6b7280">${esc(lead.id)}</span></td></tr>` : ''}
      </table>
    </div>

    <!-- LENDER COMPETITIVE INTEL -->
    <div class="dp-card">
      <div class="dp-card-header">🎯 Competitive Approach</div>
      <div class="dp-lender-text">${lenderIntel}</div>
    </div>

    <!-- MUSK NODE PROXIMITY -->
    <div class="dp-card">
      <div class="dp-card-header">🚀 Musk Infrastructure Proximity</div>
      <table class="dp-table">
        <tr><td>Nearest Node</td><td>${esc(node)}</td></tr>
        <tr><td>Distance</td><td>${dist}</td></tr>
      </table>
    </div>

    ${contactCardHTML}

    <!-- ENTITY MATCHES -->
    <div class="dp-card">
      <div class="dp-card-header">⚡ SpaceX Entity Matches</div>
      <div class="dp-badges">${matchHTML}</div>
    </div>

  </div>

  <div class="dp-actions">
    ${primaryActionHTML}
    <button class="dp-action-secondary" onclick="closePanel()">Close</button>
  </div>`;
}

const TIER_PRICES = {
  priority: { price: 99.00, cents: 9900, label: 'Priority' },
  hot: { price: 79.00, cents: 7900, label: 'Hot' },
  monitor: { price: 49.00, cents: 4900, label: 'Monitor' },
  low: { price: 29.00, cents: 2900, label: 'Low' }
};

window.unlockLead = async function(leadId) {
  const btn = document.querySelector(`.sx-paywall-btn`) || document.querySelector(`.dp-action-primary`);
  const originalText = btn ? btn.textContent : 'Unlock Lead';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'SECURE CHECKOUT CONFIGURED...';
  }
  
  try {
    const response = await fetch(`/api/leads/${leadId}/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    
    if (!response.ok) {
      const errData = await response.json();
      throw new Error(errData.error || `HTTP ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data.demo_unlock) {
      showToast('Demo Mode: Lead unlocked successfully!');
      const unlockRes = await fetch(`/api/leads/${leadId}/unlock`);
      if (!unlockRes.ok) throw new Error('Failed to fetch unlocked lead');
      const unmaskedLead = await unlockRes.json();
      
      const idxAll = state.allLeads.findIndex(l => l.id === leadId);
      if (idxAll !== -1) {
        state.allLeads[idxAll] = unmaskedLead;
      }
      
      const idxFiltered = state.filtered.findIndex(l => l.id === leadId);
      if (idxFiltered !== -1) {
        state.filtered[idxFiltered] = unmaskedLead;
      }
      
      const tableRow = dom.tbody.querySelector(`tr[data-idx="${idxFiltered}"]`);
      if (tableRow) {
        const companyNameEl = tableRow.querySelector('.sx-company-name');
        if (companyNameEl) {
          companyNameEl.textContent = unmaskedLead.company_name;
        }
        const companyLocEl = tableRow.querySelector('.sx-company-loc');
        if (companyLocEl) {
          const city = unmaskedLead.city || '';
          const st = unmaskedLead.state || '';
          companyLocEl.textContent = `${city}${city && st ? ', ' : ''}${st}`;
        }
      }
      
      openPanel(unmaskedLead);
    } else if (data.checkout_url) {
      showToast('Redirecting to secure Stripe Checkout...');
      window.location.href = data.checkout_url;
    }
  } catch (e) {
    console.error('Unlock error:', e);
    showToast(`Unlock failed: ${e.message}`);
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
};

// ── Export single lead ────────────────────────────────────────────────────────
window.exportSingleLead = function(id) {
  const lead = state.filtered.find(l => l.id === id) || state.allLeads.find(l => l.id === id);
  if (!lead) return;
  const cols = [
    ['company_name','Company'],['city','City'],['state','State'],['address','Address'],
    ['phone','Phone'],['email','Email'],['company_website','Website'],
    ['secured_party','Lender'],['collateral','Collateral'],['predicted_asset','Asset'],
    ['filing_date','Filing Date'],['lapse_date','Lapse Date'],['days_to_lapse','Days to Lapse'],
    ['filing_age_months','Age (Mo)'],['propensity_score','Score'],['score_tier','Tier'],
    ['score_w1','W1'],['score_w3','W3'],['score_bonus','Bonus'],
    ['est_financing_volume','Est. Volume'],['nearest_node','Nearest Node'],
    ['nearest_node_dist_km','Dist (km)'],
  ];
  const q = v => { const s=String(v??''); return (s.includes(',')||s.includes('"')) ? '"'+s.replace(/"/g,'""')+'"' : s; };
  const csv = [cols.map(c=>c[1]).join(','), cols.map(([k])=>q(lead[k])).join(',')].join('\n');
  const a = Object.assign(document.createElement('a'),{
    href: URL.createObjectURL(new Blob([csv],{type:'text/csv'})),
    download: `${(lead.company_name||'lead').replace(/[^a-z0-9]/gi,'-').toLowerCase()}.csv`
  });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  showToast('Lead exported.');
};

// ── Utilities ─────────────────────────────────────────────────────────────────
function fmtDate(str) {
  if (!str) return '—';
  try { return new Date(str.slice(0,10)+'T00:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}); } catch { return str; }
}
function truncate(str, n) { return str && str.length > n ? str.slice(0,n)+'…' : (str||'—'); }
function escHtml(str) { return String(str||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function showToast(msg, d=3000) {
  dom.toast.textContent = msg; dom.toast.classList.add('show');
  setTimeout(() => dom.toast.classList.remove('show'), d);
}
function animateCounter(el, target, dur=800) {
  if (!el) return;
  const start = performance.now();
  const from = parseInt(el.textContent.replace(/\D/g,''),10)||0;
  function tick(now) {
    const t = Math.min((now-start)/dur,1);
    const ease = 1-Math.pow(1-t,3);
    el.textContent = Math.round(from+(target-from)*ease).toLocaleString();
    if (t<1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ── Banner ────────────────────────────────────────────────────────────────────
function showBanner(label, pct) {
  dom.banner.classList.add('visible');
  dom.bannerLabel.textContent = label;
  dom.bannerFill.style.width = pct+'%';
  dom.bannerPct.textContent = Math.round(pct)+'%';
}
function hideBanner() { dom.banner.classList.remove('visible'); }

// ── Polling ───────────────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const s = await (await fetch('/api/status')).json();
    if (s.error) { clearInterval(state.pollTimer); hideBanner(); showToast('Pipeline error.'); return; }
    if (s.running) {
      const stage = (s.stage||'RUNNING').toUpperCase().replace('_',' ');
      const pct = s.stage==='geocoding'&&s.total>0 ? (s.progress/s.total)*100 : 0;
      showBanner(s.stage==='geocoding' ? `${stage} — ${s.progress.toLocaleString()} / ${s.total.toLocaleString()} LOCATIONS` : stage, pct);
    } else {
      clearInterval(state.pollTimer); state.pollTimer=null; hideBanner(); await loadLeads();
    }
  } catch(e) { console.error('Poll error',e); }
}
function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(pollStatus, 2500);
  pollStatus();
}

// ── Data ──────────────────────────────────────────────────────────────────────
async function init() {
  bindControls();
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session_id');
    const leadId = urlParams.get('lead_id');
    
    let purchaseVerified = false;
    if (sessionId && leadId) {
      showToast('Verifying secure payment transaction...');
      try {
        const verifyRes = await fetch(`/api/purchase/verify?session_id=${sessionId}&lead_id=${leadId}`);
        if (verifyRes.ok) {
          const verifyData = await verifyRes.json();
          if (verifyData.status === 'completed' || verifyData.status === 'paid' || verifyData.status === 'success') {
            showToast('Payment verified! Lead unlocked successfully.');
            purchaseVerified = true;
            const newUrl = window.location.origin + '/';
            window.history.replaceState({ path: newUrl }, '', newUrl);
          }
        }
      } catch (e) {
        console.error('Verify error:', e);
      }
    }

    const statsRes = await fetch('/api/stats');
    if (statsRes.status===202) { showBanner('INITIALIZING INTELLIGENCE PIPELINE',0); startPolling(); return; }
    const stats = await statsRes.json();
    if (!stats.ready) {
      showBanner('STARTING PIPELINE',0);
      await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force_refresh:false})});
      startPolling();
    } else {
      await loadLeads();
      if (purchaseVerified && leadId) {
        const lead = state.allLeads.find(l => l.id === leadId);
        if (lead) {
          const idxFiltered = state.filtered.findIndex(l => l.id === leadId);
          if (idxFiltered !== -1) {
            const row = dom.tbody.querySelector(`tr[data-idx="${idxFiltered}"]`);
            if (row) {
              row.classList.add('row-open');
              row.setAttribute('aria-expanded', 'true');
            }
          }
          openPanel(lead);
        }
      }
    }
  } catch(e) { console.error('Init error',e); showBanner('CONNECTION ERROR — IS THE SERVER RUNNING?',0); }
}

async function loadLeads(forceRefresh=false) {
  try {
    const res = await fetch(forceRefresh?'/api/leads?refresh=true':'/api/leads');
    if (res.status===202) { startPolling(); return; }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.allLeads = data.leads||[];
    state.initialized = true;
    animateCounter(dom.statTotal,    data.total_leads||0);
    animateCounter(dom.statPriority, data.priority_count||0);
    animateCounter(dom.statHot,      data.hot_count||0);
    animateCounter(dom.statMonitor,  data.monitor_count||0);
    if (data.generated_at) {
      dom.navTimestamp.textContent = new Date(data.generated_at).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
    }
    populateDropdowns();
    applyFiltersAndRender();
  } catch(e) { console.error('Load error',e); showToast('Failed to load leads.'); }
}

function populateDropdowns() {
  const states = [...new Set(state.allLeads.map(l=>l.state).filter(Boolean))].sort();
  dom.ctrlState.innerHTML = '<option value="">All States</option>';
  states.forEach(s => { const o=document.createElement('option'); o.value=s; o.textContent=s; dom.ctrlState.appendChild(o); });
  const nodes = [...new Set(state.allLeads.map(l=>l.nearest_node).filter(Boolean))].sort();
  dom.ctrlNode.innerHTML = '<option value="">All Nodes</option>';
  nodes.forEach(n => { const o=document.createElement('option'); o.value=n; o.textContent=n; dom.ctrlNode.appendChild(o); });
}

// ── Filter & Sort ─────────────────────────────────────────────────────────────
function getFilters() {
  return {
    minScore: parseInt(dom.ctrlScore.value,10)||0,
    tier:     dom.ctrlTier.value,
    state:    dom.ctrlState.value.toUpperCase(),
    node:     dom.ctrlNode.value.toLowerCase(),
    query:    dom.ctrlSearch.value.trim().toUpperCase(),
  };
}

function applyFiltersAndRender() {
  if (!state.initialized) return;
  const f = getFilters();
  let leads = state.allLeads;
  if (f.minScore>0)  leads = leads.filter(l=>(l.propensity_score||0)>=f.minScore);
  if (f.tier)        leads = leads.filter(l=>l.score_tier===f.tier);
  if (f.state)       leads = leads.filter(l=>(l.state||'').toUpperCase()===f.state);
  if (f.node)        leads = leads.filter(l=>(l.nearest_node||'').toLowerCase().includes(f.node));
  if (f.query)       leads = leads.filter(l=>(l.company_name||'').toUpperCase().includes(f.query));
  leads = [...leads].sort((a,b) => {
    const va=a[state.sortCol]??'', vb=b[state.sortCol]??'';
    const cmp = typeof va==='number' ? va-vb : String(va).localeCompare(String(vb));
    return state.sortDir==='asc' ? cmp : -cmp;
  });
  state.filtered = leads;
  dom.resultN.textContent = leads.length.toLocaleString();
  renderTable(leads);
}

// ── Table ─────────────────────────────────────────────────────────────────────
function tierClass(tier) {
  return {priority:'tier-priority',hot:'tier-hot',monitor:'tier-monitor',low:'tier-low'}[tier]||'tier-low';
}

function renderTable(leads) {
  if (!leads.length) {
    dom.tbody.innerHTML = `<tr><td colspan="9"><div class="sx-empty"><span class="sx-empty-label">No leads match current filters.</span></div></td></tr>`;
    return;
  }
  dom.tbody.innerHTML = leads.map((lead, idx) => {
    const tier  = lead.score_tier||'low';
    const tc    = tierClass(tier);
    const score = (lead.propensity_score||0).toFixed(1);
    const name  = escHtml(lead.company_name||'—');
    const city  = escHtml(lead.city||'');
    const st    = escHtml(lead.state||'');
    const asset = escHtml(truncate(lead.predicted_asset||'—',28));
    const lender= escHtml(truncate(lead.secured_party||'—',32));
    const ageMo = lead.filing_age_months ? lead.filing_age_months.toFixed(1) : '—';
    const lapseCls = (lead.days_to_lapse!=null&&lead.days_to_lapse<180)?'lapse-urgent':'lapse-normal';
    const volume= escHtml(lead.est_financing_volume||'—');
    const nodeName=truncate(escHtml(lead.nearest_node||'—'),30);
    const nodeDist=lead.nearest_node_dist_km!=null?lead.nearest_node_dist_km.toLocaleString()+' km':'';
    const matches=(lead.entity_matches||[]).map(m=>`<span class="sx-match-badge">${escHtml(truncate(m,18))}</span>`).join(' ');

    return `<tr class="data-row" data-idx="${idx}" aria-expanded="false">
      <td>
        <div class="sx-score-wrap">
          <div class="sx-score-bar-track"><div class="sx-score-bar-fill ${tc}" style="width:0" data-pct="${score}"></div></div>
          <span class="sx-score-num ${tc}">${score}</span>
        </div>
      </td>
      <td><div class="sx-company-name">${name}</div><div class="sx-company-loc">${city}${city&&st?', ':''}${st}</div></td>
      <td>${asset}</td>
      <td>${lender}</td>
      <td>${ageMo}</td>
      <td class="${lapseCls}">${fmtDate(lead.lapse_date)}</td>
      <td class="sx-volume">${volume}</td>
      <td><div class="sx-node-name">${nodeName}</div>${nodeDist?`<div class="sx-node-dist">${nodeDist}</div>`:''}</td>
      <td>${matches}</td>
    </tr>`;
  }).join('');

  // Animate score bars
  dom.tbody.querySelectorAll('.sx-score-bar-fill[data-pct]').forEach((el,i) => {
    setTimeout(() => { el.style.width = el.dataset.pct+'%'; }, i*5);
  });

  // Row click → open right panel
  dom.tbody.querySelectorAll('tr.data-row').forEach(row => {
    row.addEventListener('click', () => {
      const idx = parseInt(row.dataset.idx, 10);
      const lead = state.filtered[idx];
      dom.tbody.querySelectorAll('tr.data-row.row-open').forEach(r => {
        r.classList.remove('row-open'); r.setAttribute('aria-expanded','false');
      });
      row.classList.add('row-open');
      row.setAttribute('aria-expanded','true');
      openPanel(lead);
    });
  });
}

// ── Sort ──────────────────────────────────────────────────────────────────────
function bindSortHeaders() {
  document.querySelectorAll('thead th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      state.sortDir = state.sortCol===col ? (state.sortDir==='asc'?'desc':'asc') : (th.dataset.dir||'desc');
      state.sortCol = col;
      document.querySelectorAll('thead th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
      th.classList.add(state.sortDir==='asc'?'sort-asc':'sort-desc');
      dom.sortInfo.textContent = `Sorted by ${th.textContent.replace(/[↑↓]/g,'').trim()} ${state.sortDir==='asc'?'↑':'↓'}`;
      applyFiltersAndRender();
    });
  });
  const defTh = document.querySelector('thead th[data-col="propensity_score"]');
  if (defTh) defTh.classList.add('sort-desc');
}

// ── Controls ──────────────────────────────────────────────────────────────────
function bindControls() {
  dom.ctrlScore.addEventListener('input', () => { dom.ctrlScoreVal.textContent=dom.ctrlScore.value; applyFiltersAndRender(); });
  [dom.ctrlTier,dom.ctrlState,dom.ctrlNode].forEach(el => el.addEventListener('change',applyFiltersAndRender));
  dom.ctrlSearch.addEventListener('input', applyFiltersAndRender);
  dom.btnRefresh.addEventListener('click', async () => {
    dom.btnRefresh.textContent='↺  REFRESHING…'; dom.btnRefresh.disabled=true;
    try {
      await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({force_refresh:true})});
      startPolling();
    } catch(e) { showToast('Refresh failed.'); }
    finally { dom.btnRefresh.textContent='↺  Refresh'; dom.btnRefresh.disabled=false; }
  });
  dom.btnExport.addEventListener('click', exportCsv);
  if (dom.overlay) dom.overlay.addEventListener('click', closePanel);
  bindSortHeaders();
}

// ── CSV ───────────────────────────────────────────────────────────────────────
function exportCsv() {
  if (!state.filtered.length) { showToast('No leads to export.'); return; }
  const cols = [
    ['company_name','Company'],['city','City'],['state','State'],['address','Address'],
    ['phone','Phone'],['email','Email'],['company_website','Website'],
    ['secured_party','Lender'],['collateral','Collateral'],['predicted_asset','Asset'],
    ['filing_date','Filing Date'],['lapse_date','Lapse Date'],['days_to_lapse','Days to Lapse'],
    ['filing_age_months','Age (Mo)'],['propensity_score','Score'],['score_tier','Tier'],
    ['score_w1','W1'],['score_w3','W3'],['score_bonus','Bonus'],
    ['est_financing_volume','Est. Volume'],['nearest_node','Nearest Node'],['nearest_node_dist_km','Dist (km)'],
  ];
  const q = v => { const s=String(v??''); return (s.includes(',')||s.includes('"')||s.includes('\n')) ? '"'+s.replace(/"/g,'""')+'"' : s; };
  const csv = [cols.map(c=>c[1]).join(','), ...state.filtered.map(l=>cols.map(([k])=>q(l[k])).join(','))].join('\n');
  const a = Object.assign(document.createElement('a'),{href:URL.createObjectURL(new Blob([csv],{type:'text/csv'})),download:`spacex-capex-${new Date().toISOString().slice(0,10)}.csv`});
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  showToast(`Exported ${state.filtered.length.toLocaleString()} leads.`);
}

document.addEventListener('DOMContentLoaded', init);
