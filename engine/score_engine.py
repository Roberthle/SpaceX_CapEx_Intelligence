"""
Propensity Score Engine for SpaceX CapEx Intelligence.

Scoring formula (three equal weights, max 100 with bonuses):
  W1 — UCC Maturity Score (0-33.3 pts): peaks at 36 months since filing
  W2 — Job Board Intensity (0-33.3 pts): Phase 2, currently returns 0
  W3 — Proximity Score (0-33.3 pts): haversine distance to nearest Musk node

Phase 1 normalization: when W2=0, W1+W3 are scaled to fill the 0-100 range
so scores are meaningful from day one.

Bonuses (stacking, hard cap at 100):
  +3: Musk entity trigger found in filing
  +4: Known prime contractor found in filing
  +3: Captive lender maxed + job board expansion signal (Phase 2)
"""

import math
from datetime import date, datetime
from typing import Optional, Tuple

from config.epicenters import EPICENTERS
from config.entity_triggers import KNOWN_CONTRACTORS, MUSK_ENTITY_TRIGGERS


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + (
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(min(1.0, a)))


def score_maturity(filing_date_str: str) -> Tuple[float, float]:
    """
    W1: UCC Maturity Score.
    Peak at month 36 (center of 24-48 window). Zero at months 24 and 48.
    Returns (score, filing_age_months).
    """
    if not filing_date_str:
        return 0.0, 0.0
    try:
        if "T" in filing_date_str:
            filing_date = datetime.fromisoformat(filing_date_str).date()
        else:
            filing_date = date.fromisoformat(filing_date_str[:10])
        today = date.today()
        filing_age_months = (today - filing_date).days / 30.44
        score = max(0.0, 33.3 * (1.0 - abs(filing_age_months - 36.0) / 12.0))
        return round(score, 2), round(filing_age_months, 1)
    except (ValueError, TypeError):
        return 0.0, 0.0


def score_proximity(lat, lon) -> Tuple[float, Optional[str], Optional[float]]:
    """
    W3: Proximity to nearest confirmed Musk infrastructure node.
    Max 33.3 pts at 0 km, zero at 800 km.
    Returns (score, nearest_node_name, distance_km).
    """
    if lat is None or lon is None:
        return 0.0, None, None

    best_dist = float("inf")
    best_node = None

    for node_name, node in EPICENTERS.items():
        d = haversine_km(lat, lon, node["lat"], node["lon"])
        if d < best_dist:
            best_dist = d
            best_node = node_name

    score = max(0.0, 33.3 * (1.0 - best_dist / 800.0))
    return round(score, 2), best_node, round(best_dist, 1)


def score_job_board(trigger_hits: int = 0) -> float:
    """
    W2: Job Board Intensity Score.
    Phase 1: Returns 0 (no API keys configured yet).
    Phase 2: log-scale, 8+ hits = full 33.3 pts.
    """
    if trigger_hits <= 0:
        return 0.0
    return round(33.3 * min(1.0, math.log(1 + trigger_hits) / math.log(8)), 2)


def calculate_bonuses(company_name: str, secured_party: str, collateral: str, w2: float) -> Tuple[float, list]:
    """
    Bonus points for high-confidence SpaceX signals.
    Returns (bonus_pts, list_of_matched_signals).
    """
    bonus = 0.0
    matches = []

    combined = f"{company_name} {secured_party} {collateral}".upper()

    # Musk entity match +3
    for trigger in MUSK_ENTITY_TRIGGERS:
        if trigger.upper() in combined:
            bonus += 3.0
            matches.append(f"Entity: {trigger.title()}")
            break  # Only award once

    # Known prime contractor match +4
    for contractor in KNOWN_CONTRACTORS:
        if contractor.upper() in combined:
            bonus += 4.0
            matches.append(f"Contractor: {contractor.title()}")
            break  # Only award once

    # Phase 2: Captive lender saturated + active job signal = +3
    if w2 > 20.0:
        bonus += 3.0
        matches.append("Job board expansion signal")

    return round(bonus, 2), matches


def estimate_financing_volume(score: float) -> str:
    """Map propensity score to an estimated financing volume range."""
    if score >= 85:
        return "$500k – $1M+"
    elif score >= 65:
        return "$250k – $500k"
    elif score >= 40:
        return "$100k – $250k"
    else:
        return "< $100k"


def score_lead(lead: dict) -> dict:
    """
    Score a single lead dict. Adds scoring fields in-place and returns it.

    Input fields used: filing_date, lat, lon, company_name, secured_party,
                       collateral, trigger_hits (optional)
    Output fields added: score_w1, score_w2, score_w3, score_bonus,
                         filing_age_months, propensity_score, score_tier,
                         nearest_node, nearest_node_dist_km,
                         est_financing_volume, entity_matches
    """
    w1, filing_age_months = score_maturity(lead.get("filing_date", ""))
    w2 = score_job_board(lead.get("trigger_hits", 0))
    w3, nearest_node, nearest_dist_km = score_proximity(lead.get("lat"), lead.get("lon"))

    bonus, entity_matches = calculate_bonuses(
        lead.get("company_name", ""),
        lead.get("secured_party", ""),
        lead.get("collateral", ""),
        w2,
    )

    # Phase 1 normalization: W2=0, scale W1+W3 up to fill 0-100 range
    # W1 max 33.3 + W3 max 33.3 = 66.6 → multiply by 1.5015 to reach 100
    if w2 == 0:
        base_score = (w1 + w3) * 1.5015
    else:
        base_score = w1 + w2 + w3

    raw = min(100.0, base_score + bonus)
    propensity_score = round(raw, 1)

    # Determine tier
    if propensity_score >= 85:
        score_tier = "priority"
        score_tier_label = "Priority"
    elif propensity_score >= 65:
        score_tier = "hot"
        score_tier_label = "Hot"
    elif propensity_score >= 40:
        score_tier = "monitor"
        score_tier_label = "Monitor"
    else:
        score_tier = "low"
        score_tier_label = "Low"

    lead.update(
        {
            "score_w1": w1,
            "score_w2": w2,
            "score_w3": w3,
            "score_bonus": bonus,
            "filing_age_months": filing_age_months,
            "propensity_score": propensity_score,
            "score_tier": score_tier,
            "score_tier_label": score_tier_label,
            "nearest_node": nearest_node,
            "nearest_node_dist_km": nearest_dist_km,
            "est_financing_volume": estimate_financing_volume(propensity_score),
            "entity_matches": entity_matches,
            "w2_active": w2 > 0,
        }
    )

    return lead
