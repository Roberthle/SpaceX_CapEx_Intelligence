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
import threading
import time
from datetime import datetime, timezone

from typing import Optional

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

    return jsonify(
        {
            **{k: v for k, v in result.items() if k != "leads"},
            "filtered_count": len(leads),
            "leads": leads,
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


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Auto-start pipeline on first launch (serves from cache if fresh)
    logger.info("⚡ SpaceX CapEx Intelligence starting...")
    _start_pipeline_thread(force_refresh=False)
    app.run(host="0.0.0.0", port=5050, debug=False)
