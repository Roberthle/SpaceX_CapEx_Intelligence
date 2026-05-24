"""
SpaceX CapEx Intelligence — Flask API Server

Routes:
  GET  /              → Serves the terminal UI (index.html)
  POST /api/run       → Starts background pipeline (filter → geocode → score)
  GET  /api/leads     → Returns scored leads (from cache if available)
  GET  /api/status    → Returns pipeline run status and progress
  GET  /api/stats     → Returns aggregate statistics

The pipeline runs in a background thread. First run may take several minutes
(geocoding ~400-800 city/state pairs at 1 req/sec via Nominatim).
All subsequent runs are instant via the 24-hour disk cache.
"""

import json
import logging
import os
import sqlite3
import threading
import time
import re
import random
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup
import stripe
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from engine.geocoder import geocode_batch
from engine.score_engine import score_lead
from engine.spacex_filter import run_filters, DB_PATH

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Stripe & DB Setup ────────────────────────────────────────────────────────
# Load local .env if it exists
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            if line.strip() and not line.strip().startswith("#") and "=" in line:
                key, val = line.strip().split("=", 1)
                os.environ[key.strip()] = val.strip()

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

def init_db():
    conn = sqlite3.connect("purchases.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lead_purchases (
            lead_id TEXT PRIMARY KEY,
            tier TEXT,
            price_cents INTEGER,
            stripe_session_id TEXT,
            status TEXT,
            buyer_email TEXT,
            stripe_payment_intent TEXT,
            unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            email TEXT PRIMARY KEY,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def clean_company_name(name: str) -> str:
    """Cleans common corporate suffixes, punctuation, and extra spaces from the company name."""
    name_clean = name.lower()
    suffixes = [
        r'\bllc\b', r'\bl\.l\.c\.\b', r'\binc\b', r'\binc\.\b', 
        r'\bcorp\b', r'\bcorporation\b', r'\bco\b', r'\bco\.\b', 
        r'\bltd\b', r'\blimited\b', r'\bpc\b', r'\bp\.c\.\b',
        r'\bgroup\b', r'\bsolutions\b', r'\bservices\b'
    ]
    for suffix in suffixes:
        name_clean = re.sub(suffix, '', name_clean)
    name_clean = re.sub(r'[^\w\s]', ' ', name_clean)
    return " ".join(name_clean.split())

def extract_real_url(url: str) -> str:
    """Decodes DuckDuckGo search redirect URLs to extract the actual target job listing URL."""
    if not url:
        return ""
    if "uddg=" in url:
        try:
            parsed = urlparse(url)
            queries = parse_qs(parsed.query)
            if "uddg" in queries:
                return unquote(queries["uddg"][0])
        except Exception:
            pass
    if url.startswith("//"):
        return "https:" + url
    return url

def get_job_signals(company_name: str) -> list:
    """Searches for active job postings for a given company name using DuckDuckGo X-Ray."""
    if not company_name:
        return []
    
    cleaned_company = clean_company_name(company_name)
    words = [w for w in cleaned_company.split() if len(w) > 2 and w not in ["and", "the", "for", "with", "our"]]
    if not words:
        words = cleaned_company.split()
        
    query = f'"{cleaned_company}" (welder OR welding OR fabricator OR fabrication OR CNC OR machinist OR "heavy machinery" OR "machine operator" OR operator) (hiring OR jobs OR career OR careers OR job)'
    url = "https://html.duckduckgo.com/html/"
    data = {'q': query}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    
    response_text = ""
    for attempt in range(3):
        try:
            response = requests.post(url, data=data, headers=headers, timeout=5)
            response.raise_for_status()
            response_text = response.text
            break
        except Exception:
            if attempt == 2:
                return []
            time.sleep(random.uniform(0.5, 1.5))
            
    if not response_text:
        return []
    
    soup = BeautifulSoup(response_text, 'html.parser')
    raw_results = []
    containers = soup.select(".result")
    
    if containers:
        for r in containers:
            title_elem = r.select_one(".result__a") or r.select_one(".result__title")
            snippet_elem = r.select_one(".result__snippet")
            if title_elem and title_elem.has_attr("href"):
                raw_results.append({
                    "title": title_elem.get_text(strip=True),
                    "url": title_elem["href"],
                    "snippet": snippet_elem.get_text(strip=True) if snippet_elem else ""
                })
            
    CATEGORIES = {
        "Welder": ["welder", "welding", "mig", "tig", "stick", "flux", "gmaw", "smaw", "fitter-welder"],
        "Fabricator": ["fabricator", "fabrication", "fitter", "fit-up", "structural fabricator", "metal fabricator"],
        "CNC Machinist": ["cnc", "machinist", "lathe", "mill", "machining", "machinist operator", "cnc operator"],
        "Heavy Machinery Operator": ["heavy machinery", "heavy equipment", "forklift", "crane", "loader", "excavator", "backhoe", "bulldozer", "machine operator", "machinery operator", "equipment operator", "rigging", "material handler", "forklift operator"]
    }
    
    hiring_keywords = [
        "hiring", "job", "jobs", "career", "careers", "vacancy", "employment", 
        "apply", "salary", "wages", "shift", "opening", "openings", "recruiting", 
        "recruit", "work", "position", "positions"
    ]
    
    job_boards = [
        "indeed.com", "ziprecruiter.com", "linkedin.com/jobs", "simplyhired.com", 
        "glassdoor.com", "jora.com", "talent.com", "careerbuilder.com", 
        "monster.com", "snagajob.com", "jooble.org", "lever.co", "greenhouse.io", 
        "ashbyhq.com", "workdayjobs.com", "bamboohr.com", "paycomonline.net", 
        "paylocity.com", "recruitee.com"
    ]
    
    signals = []
    seen_urls = set()
    
    for res in raw_results:
        title = res["title"]
        snippet = res["snippet"]
        raw_url = res["url"]
        
        real_url = extract_real_url(raw_url)
        if not real_url or real_url in seen_urls:
            continue
            
        combined_text = f"{title} {snippet} {real_url}".lower()
        name_match = (cleaned_company in combined_text)
        if not name_match:
            matching_words = sum(1 for w in words if w in combined_text)
            required_matches = min(2, len(words))
            if matching_words >= required_matches:
                name_match = True
                
        if not name_match:
            continue
            
        is_job_board = any(board in real_url.lower() for board in job_boards)
        has_hiring_keyword = any(k in combined_text for k in hiring_keywords)
        if not (is_job_board or has_hiring_keyword):
            continue
            
        matched_category = None
        for category, keywords in CATEGORIES.items():
            if any(keyword in combined_text for keyword in keywords):
                matched_category = category
                break
                
        if not matched_category:
            continue
            
        seen_urls.add(real_url)
        signals.append({
            "job_title": title,
            "category": matched_category,
            "source_url": real_url,
            "snippet": snippet[:140] + "..." if len(snippet) > 140 else snippet
        })
        
    return signals


init_db()

def _is_purchased(lead_id) -> bool:
    """Check if a lead has been unlocked in purchases.db"""
    try:
        conn = sqlite3.connect("purchases.db")
        row = conn.execute(
            "SELECT lead_id FROM lead_purchases WHERE lead_id=? AND status='completed'",
            [str(lead_id)]
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        logger.warning(f"Error checking purchase status for {lead_id}: {e}")
        return False

# ── Company name privacy gate ────────────────────────────────────────────────
def _mask_name(name):
    """Obfuscate company name — show first letter + bullets per word."""
    if not name:
        return 'Confidential Business'
    SUFFIXES = {'LLC','INC','CORP','LTD','LP','DBA','L.L.C.','INC.','CORP.','L.P.','CO.','CO'}
    parts = name.split()
    out = []
    for p in parts:
        if p.upper().rstrip('.') in SUFFIXES or len(p) <= 2:
            out.append(p)
        else:
            out.append(p[0] + '\u2022' * min(len(p) - 1, 8))
    return ' '.join(out)

def _apply_mask(lead: dict) -> dict:
    """Mask private details of a lead unless purchased."""
    lead_id = lead.get("id")
    if _is_purchased(lead_id):
        lead_copy = lead.copy()
        lead_copy["locked"] = False
        return lead_copy
        
    masked = lead.copy()
    masked["company_name"] = _mask_name(lead.get("company_name", ""))
    masked["address"] = "••••••••••••••••"
    masked["phone"] = None
    masked["email"] = None
    masked["contact_name"] = None
    masked["company_website"] = None
    masked["website"] = None
    masked["locked"] = True
    return masked

TIERS = {
    "priority": {"price": 9900, "label": "Priority", "desc": "Exclusive high-probability heavy machinery lease target."},
    "hot": {"price": 7900, "label": "Hot", "desc": "Accelerated CapEx growth signal with strong proximity."},
    "monitor": {"price": 4900, "label": "Monitor", "desc": "Mid-tier potential for continuous monitoring and future pipeline mapping."},
    "low": {"price": 2900, "label": "Low", "desc": "Low-probability monitoring lead with baseline activity."},
}

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# ── Cache ─────────────────────────────────────────────────────────────────────

_CACHE_FILE = os.path.join(os.path.dirname(__file__), "cache", "scored_leads.json")
_CACHE_TTL_HOURS = 24

# ── Pipeline State ────────────────────────────────────────────────────────────
_pipeline_lock = threading.Lock()
_pipeline_state = {
    "running": False,
    "stage": "idle",
    "progress": 0,
    "total": 0,
    "last_run_at": None,
    "last_run_seconds": None,
    "error": None,
    "result": None,  # Latest scored result dict
}


# ── Cache Helpers ─────────────────────────────────────────────────────────────

def _load_cache() -> Optional[dict]:
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE) as f:
            data = json.load(f)
        generated_at = datetime.fromisoformat(data.get("generated_at", "2000-01-01T00:00:00"))
        # Make timezone-aware comparison
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - generated_at).total_seconds() / 3600
        if age_hours < _CACHE_TTL_HOURS or not os.path.exists(DB_PATH):
            if age_hours >= _CACHE_TTL_HOURS:
                logger.info(f"Cache expired ({age_hours:.1f}h old), but database not found. Serving cache anyway.")
            return data
        logger.info(f"Cache expired ({age_hours:.1f}h old)")
        return None
    except Exception as e:
        logger.warning(f"Cache load error: {e}")
        return None


def _save_cache(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(data, f)
        logger.info(f"Cache saved: {len(data.get('leads', []))} leads")
    except Exception as e:
        logger.warning(f"Cache save error: {e}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _run_pipeline(force_refresh: bool = False) -> dict:
    """
    Full pipeline: filter → geocode → score → cache.
    Runs synchronously; call from a background thread.
    """
    global _pipeline_state

    # Check cache first
    if not force_refresh:
        cached = _load_cache()
        if cached:
            logger.info(f"Serving {len(cached.get('leads', []))} leads from cache")
            with _pipeline_lock:
                _pipeline_state["result"] = cached
            return cached

    t_start = time.time()

    # Stage 1: Filter
    with _pipeline_lock:
        _pipeline_state.update({"running": True, "stage": "filtering", "progress": 0, "error": None})

    leads = run_filters()

    # Stage 2: Geocode
    with _pipeline_lock:
        _pipeline_state.update({"stage": "geocoding", "total": len(leads), "progress": 0})

    def _progress(done, total):
        with _pipeline_lock:
            _pipeline_state["progress"] = done
        if done % 25 == 0 or done == total:
            logger.info(f"Geocoding: {done}/{total}")

    geocode_batch(leads, progress_callback=_progress)

    # Stage 3: Score
    with _pipeline_lock:
        _pipeline_state["stage"] = "scoring"

    scored = [score_lead(lead) for lead in leads]
    scored.sort(key=lambda x: x.get("propensity_score", 0), reverse=True)

    # Build result
    priority = [l for l in scored if l.get("score_tier") == "priority"]
    hot = [l for l in scored if l.get("score_tier") == "hot"]
    monitor = [l for l in scored if l.get("score_tier") == "monitor"]
    low = [l for l in scored if l.get("score_tier") == "low"]

    runtime = round(time.time() - t_start, 1)
    now_utc = datetime.now(timezone.utc).isoformat()

    result = {
        "generated_at": now_utc,
        "runtime_seconds": runtime,
        "total_leads": len(scored),
        "priority_count": len(priority),
        "hot_count": len(hot),
        "monitor_count": len(monitor),
        "low_count": len(low),
        "w2_active": False,  # Phase 1: no job board API
        "data_sources": ["tomcat_capex.db (CO, CT, GA, CA, ID, MT, NJ, NY, OH, FL)"],
        "leads": scored,
    }

    _save_cache(result)

    with _pipeline_lock:
        _pipeline_state.update(
            {
                "running": False,
                "stage": "complete",
                "last_run_at": now_utc,
                "last_run_seconds": runtime,
                "result": result,
            }
        )

    logger.info(
        f"Pipeline complete in {runtime}s | "
        f"{len(scored)} leads | "
        f"⚡{len(priority)} priority | 🔴{len(hot)} hot | 🟡{len(monitor)} monitor"
    )

    return result


def _start_pipeline_thread(force_refresh: bool = False) -> bool:
    """Starts the pipeline in a background thread. Returns False if already running."""
    with _pipeline_lock:
        if _pipeline_state["running"]:
            return False
        _pipeline_state["running"] = True

    def _bg():
        try:
            _run_pipeline(force_refresh=force_refresh)
        except Exception as e:
            logger.exception("Pipeline thread error")
            with _pipeline_lock:
                _pipeline_state.update(
                    {"running": False, "stage": "error", "error": str(e)}
                )

    t = threading.Thread(target=_bg, daemon=True)
    t.start()
    return True


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/run", methods=["POST"])
def api_run():
    """Kick off the pipeline in background. Returns immediately."""
    body = request.get_json(silent=True) or {}
    force_refresh = body.get("force_refresh", False)

    started = _start_pipeline_thread(force_refresh=force_refresh)
    if not started:
        return jsonify({"status": "already_running"})
    return jsonify({"status": "started"})


@app.route("/api/status")
def api_status():
    """Returns current pipeline state and progress."""
    with _pipeline_lock:
        state = {k: v for k, v in _pipeline_state.items() if k != "result"}
    return jsonify(state)


@app.route("/api/leads")
def api_leads():
    """
    Returns scored leads. Applies optional query filters:
      ?min_score=40       — minimum propensity score
      ?state=GA           — filter by state code
      ?node=Memphis       — filter by nearest node (substring)
      ?tier=hot           — filter by tier (priority|hot|monitor|low)
      ?q=company_name     — text search on company name
    """
    # Serve from in-memory result or cache
    with _pipeline_lock:
        result = _pipeline_state.get("result")

    if result is None:
        result = _load_cache()

    if result is None:
        # Auto-start pipeline and return 202
        _start_pipeline_thread()
        return (
            jsonify(
                {
                    "status": "pipeline_starting",
                    "message": "Data pipeline is initializing. Check /api/status for progress.",
                }
            ),
            202,
        )

    leads = result.get("leads", [])

    # Apply filters
    min_score = float(request.args.get("min_score", 0))
    state_filter = request.args.get("state", "").upper()
    node_filter = request.args.get("node", "").lower()
    tier_filter = request.args.get("tier", "").lower()
    text_search = request.args.get("q", "").upper()

    if min_score > 0:
        leads = [l for l in leads if l.get("propensity_score", 0) >= min_score]
    if state_filter:
        leads = [l for l in leads if (l.get("state") or "").upper() == state_filter]
    if node_filter:
        leads = [l for l in leads if node_filter in (l.get("nearest_node") or "").lower()]
    if tier_filter:
        leads = [l for l in leads if l.get("score_tier", "") == tier_filter]
    if text_search:
        leads = [l for l in leads if text_search in (l.get("company_name") or "").upper()]

    masked_leads = [_apply_mask(l) for l in leads]
    return jsonify(
        {
            **{k: v for k, v in result.items() if k != "leads"},
            "filtered_count": len(masked_leads),
            "leads": masked_leads,
        }
    )



@app.route("/api/stats")
def api_stats():
    """Aggregate statistics for dashboard cards."""
    with _pipeline_lock:
        result = _pipeline_state.get("result")

    if result is None:
        result = _load_cache()
    if result is None:
        return jsonify({"ready": False})

    leads = result.get("leads", [])

    state_counts = {}
    node_counts = {}
    tier_counts = {"priority": 0, "hot": 0, "monitor": 0, "low": 0}

    for l in leads:
        s = l.get("state") or "Unknown"
        state_counts[s] = state_counts.get(s, 0) + 1
        n = l.get("nearest_node") or "Unknown"
        node_counts[n] = node_counts.get(n, 0) + 1
        tier = l.get("score_tier", "low")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    return jsonify(
        {
            "ready": True,
            "total": len(leads),
            "by_tier": tier_counts,
            "by_state": state_counts,
            "by_node": node_counts,
            "generated_at": result.get("generated_at"),
            "w2_active": result.get("w2_active", False),
        }
    )


@app.route("/api/leads/<lead_id>/jobs")
def api_lead_jobs(lead_id):
    """
    Scrapes and returns active job signals for a lead.
    Only accessible if the lead has been purchased/unlocked.
    """
    if not _is_purchased(lead_id):
        return jsonify({"error": "Lead is locked. Purchase to unlock hiring signal intelligence.", "locked": True}), 402

    # Get the unmasked lead info from pipeline state/cache
    with _pipeline_lock:
        result = _pipeline_state.get("result")
    if result is None:
        result = _load_cache()
    
    if not result:
        return jsonify({"error": "Data not initialized"}), 500

    leads = result.get("leads", [])
    lead = next((l for l in leads if str(l.get("id")) == str(lead_id)), None)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    company_name = lead.get("company_name")
    if not company_name:
        return jsonify([])

    try:
        jobs = get_job_signals(company_name)
        return jsonify(jobs)
    except Exception as e:
        logger.error(f"Error fetching jobs for {company_name}: {e}")
        return jsonify({"error": "Failed to scan job signals", "details": str(e)}), 500


# ── Stripe & Unlock Endpoints ──────────────────────────────────────────────────

@app.route("/api/leads/<lead_id>/pricing")
def api_lead_pricing(lead_id):
    """Returns pricing metadata for a lead."""
    with _pipeline_lock:
        result = _pipeline_state.get("result")
    if result is None:
        result = _load_cache()

    if not result:
        return jsonify({"error": "Data not ready"}), 503

    lead = None
    for l in result.get("leads", []):
        if l.get("id") == lead_id:
            lead = l
            break

    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    tier_key = lead.get("score_tier", "low")
    tier_info = TIERS.get(tier_key, TIERS["low"])

    is_demo = not bool(os.environ.get("STRIPE_SECRET_KEY"))

    return jsonify({
        "lead_id": lead_id,
        "tier": tier_key,
        "price": tier_info["price"] / 100.0,
        "price_cents": tier_info["price"],
        "label": tier_info["label"],
        "description": tier_info["desc"],
        "purchased": _is_purchased(lead_id),
        "demo_mode": is_demo
    })


@app.route("/api/leads/<lead_id>/checkout", methods=["POST"])
def api_lead_checkout(lead_id):
    """Creates a Stripe checkout session, or triggers Demo Mode unlock if no Stripe key is configured."""
    with _pipeline_lock:
        result = _pipeline_state.get("result")
    if result is None:
        result = _load_cache()

    if not result:
        return jsonify({"error": "Data not ready"}), 503

    lead = None
    for l in result.get("leads", []):
        if l.get("id") == lead_id:
            lead = l
            break

    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    if _is_purchased(lead_id):
        return jsonify({"error": "Lead already unlocked", "already_unlocked": True}), 400

    tier_key = lead.get("score_tier", "low")
    tier_info = TIERS.get(tier_key, TIERS["low"])

    # If STRIPE_SECRET_KEY is absent from environment variables, we do Demo Mode!
    is_demo = not bool(os.environ.get("STRIPE_SECRET_KEY"))

    if is_demo:
        # In Demo Mode, instantly mark as completed in SQLite
        conn = sqlite3.connect("purchases.db")
        conn.execute(
            "INSERT OR REPLACE INTO lead_purchases (lead_id, tier, price_cents, status) VALUES (?, ?, ?, 'completed')",
            [lead_id, tier_key, tier_info["price"]]
        )
        conn.commit()
        conn.close()
        logger.info(f"Demo unlocked lead {lead_id} successfully")
        return jsonify({
            "demo_unlock": True,
            "lead_id": lead_id,
            "message": "Demo Mode: Lead unlocked successfully!"
        })

    # Otherwise, create a real Stripe Checkout Session
    host = request.host_url.rstrip("/")
    company = lead.get("company_name", "Unknown Company")
    masked_company = _mask_name(company)
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": tier_info["price"],
                    "product_data": {
                        "name": f"SpaceX CapEx — {tier_info['label']} Lead",
                        "description": f"{masked_company} | Lead ID: {lead_id} | Propensity Score: {lead.get('propensity_score', 0):.1f}",
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{host}/purchase-success?session_id={{CHECKOUT_SESSION_ID}}&lead_id={lead_id}",
            cancel_url=f"{host}/#data-section",
            metadata={
                "lead_id": lead_id,
                "tier": tier_key,
                "company": masked_company,
            }
        )

        # Record pending purchase
        conn = sqlite3.connect("purchases.db")
        conn.execute(
            "INSERT OR REPLACE INTO lead_purchases (lead_id, tier, price_cents, stripe_session_id, status) VALUES (?, ?, ?, ?, 'pending')",
            [lead_id, tier_key, tier_info["price"], session.id]
        )
        conn.commit()
        conn.close()

        return jsonify({"checkout_url": session.url, "session_id": session.id})

    except Exception as e:
        logger.error(f"Stripe session creation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/leads/<lead_id>/unlock")
def api_unlock_lead(lead_id):
    """Returns the unmasked lead details if purchased."""
    if not _is_purchased(lead_id):
        return jsonify({"error": "Purchase required", "locked": True}), 402

    with _pipeline_lock:
        result = _pipeline_state.get("result")
    if result is None:
        result = _load_cache()

    if not result:
        return jsonify({"error": "Data not ready"}), 503

    lead = None
    for l in result.get("leads", []):
        if l.get("id") == lead_id:
            lead = l
            break

    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    lead_copy = lead.copy()
    lead_copy["locked"] = False
    return jsonify(lead_copy)


@app.route("/api/purchase/verify")
def verify_purchase():
    """Verify a completed Stripe purchase and unlock the lead."""
    session_id = request.args.get("session_id", "")
    lead_id = request.args.get("lead_id", "")
    if not session_id or not lead_id:
        return jsonify({"error": "Missing parameters"}), 400

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            conn = sqlite3.connect("purchases.db")
            conn.execute(
                "UPDATE lead_purchases SET status = 'completed', buyer_email = ?, stripe_payment_intent = ? WHERE stripe_session_id = ?",
                [session.customer_details.email if session.customer_details else "", session.payment_intent, session_id]
            )
            conn.commit()
            conn.close()
            return jsonify({"status": "completed", "lead_id": lead_id})
        else:
            return jsonify({"status": session.payment_status})
    except Exception as e:
        logger.error(f"Purchase verification error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/purchase-success")
def purchase_success():
    return send_from_directory(".", "index.html")


@app.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe Webhook events."""
    endpoint_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        if endpoint_secret and sig_header:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        else:
            # Fallback for local testing without webhook secret verification
            event = json.loads(payload)
    except ValueError as e:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError as e:
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")
        payment_intent = session.get("payment_intent")
        customer_details = session.get("customer_details")
        customer_email = customer_details.get("email", "") if customer_details else ""
        
        lead_id = session.get("metadata", {}).get("lead_id")
        
        conn = sqlite3.connect("purchases.db")
        try:
            if lead_id:
                # Update existing pending purchase or insert if not present
                conn.execute(
                    "UPDATE lead_purchases SET status = 'completed', buyer_email = ?, stripe_payment_intent = ? WHERE stripe_session_id = ? OR (lead_id = ? AND status = 'pending')",
                    [customer_email, payment_intent, session_id, lead_id]
                )
                # Check if row was updated, if not insert it
                cursor = conn.cursor()
                cursor.execute("SELECT changes()")
                changes = cursor.fetchone()[0]
                if changes == 0:
                    tier = session.get("metadata", {}).get("tier", "unknown")
                    price = session.get("amount_total", 0)
                    conn.execute(
                        "INSERT OR REPLACE INTO lead_purchases (lead_id, tier, price_cents, stripe_session_id, stripe_payment_intent, buyer_email, status) VALUES (?, ?, ?, ?, ?, ?, 'completed')",
                        [lead_id, tier, price, session_id, payment_intent, customer_email]
                    )
            else:
                conn.execute(
                    "UPDATE lead_purchases SET status = 'completed', buyer_email = ?, stripe_payment_intent = ? WHERE stripe_session_id = ?",
                    [customer_email, payment_intent, session_id]
                )
            conn.commit()
            logger.info(f"Webhook successfully updated purchase status to completed for session {session_id}")
        except Exception as e:
            logger.error(f"Webhook DB error: {e}")
        finally:
            conn.close()

    return jsonify({"status": "success"}), 200


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    """Saves a user's business email in the subscribers database table."""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    
    if not email or "@" not in email:
        return jsonify({"error": "Invalid email address"}), 400
        
    try:
        conn = sqlite3.connect("purchases.db")
        conn.execute(
            "INSERT OR IGNORE INTO subscribers (email) VALUES (?)",
            [email]
        )
        conn.commit()
        conn.close()
        logger.info(f"New newsletter subscriber registered: {email}")
        return jsonify({"success": True, "message": "Subscribed successfully!"}), 200
    except Exception as e:
        logger.error(f"Subscription database error: {e}")
        return jsonify({"error": "Failed to subscribe"}), 500


if __name__ == "__main__":
    # Auto-start pipeline on first launch (serves from cache if fresh)
    logger.info("⚡ SpaceX CapEx Intelligence starting...")
    _start_pipeline_thread(force_refresh=False)
    port = int(os.environ.get("PORT", 5052))
    app.run(host="0.0.0.0", port=port, debug=False)
