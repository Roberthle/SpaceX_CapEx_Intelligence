"""
SpaceX CapEx Filter Engine.
Reads directly from the Tomcat CapEx SQLite database and applies
four sequential gates to isolate SpaceX-relevant leads.

Gate 1: lien_type = 'equipment' (drops blanket/tech/soft-asset)
Gate 2: secured_party must be an industrial lender (allowlist match)
Gate 3: filing_date in the 24-48 month maturity window
Gate 4: company_name must be present (no individual consumers)
"""

import logging
import os
import sqlite3
from datetime import date, timedelta

from config.lender_allowlist import INDUSTRIAL_LENDER_KEYWORDS, SOFT_ASSET_LENDER_KEYWORDS

logger = logging.getLogger(__name__)

# Path to Tomcat CapEx database — can be overridden via environment variable
DB_PATH = os.environ.get(
    "TOMCAT_DB_PATH",
    "/Users/robertle/tomcat_capex/leads/tomcat_capex.db",
)

# Maturity window: filings between 24 and 48 months ago
WINDOW_MIN_MONTHS = 24
WINDOW_MAX_MONTHS = 48


def get_maturity_window():
    """Returns (oldest_date, newest_date) ISO strings for the maturity window."""
    today = date.today()
    oldest = today - timedelta(days=WINDOW_MAX_MONTHS * 30)
    newest = today - timedelta(days=WINDOW_MIN_MONTHS * 30)
    return oldest.isoformat(), newest.isoformat()


def is_industrial_lender(secured_party: str) -> bool:
    """Gate 2: Returns True if secured_party is an industrial asset lender."""
    if not secured_party:
        return False

    sp = secured_party.upper()

    # First: hard-drop soft-asset lenders
    for kw in SOFT_ASSET_LENDER_KEYWORDS:
        if kw.upper() in sp:
            return False

    # Then: check industrial allowlist
    for kw in INDUSTRIAL_LENDER_KEYWORDS:
        if kw.upper() in sp:
            return True

    return False


def predict_asset_type(secured_party: str, collateral: str) -> str:
    """
    Derives a human-readable predicted asset type from lender and collateral context.
    Since most records have generic collateral descriptions, we use lender as primary signal.
    """
    combined = f"{secured_party or ''} {collateral or ''}".upper()

    mapping = [
        (["CATERPILLAR", "CAT FINANCIAL"], "Heavy Construction Equipment"),
        (["JOHN DEERE", "DEERE FINANCIAL"], "Agricultural / Heavy Equipment"),
        (["TAKEUCHI"], "Compact Construction Equipment"),
        (["KOMATSU"], "Heavy Construction Equipment"),
        (["VOLVO FINANCIAL"], "Heavy Trucking / Construction"),
        (["PACCAR", "NAVISTAR", "DAIMLER TRUCK"], "Commercial Freight Equipment"),
        (["SUMITOMO MITSUI", "HITACHI CAPITAL"], "Industrial / Manufacturing Equipment"),
        (["SIEMENS FINANCIAL"], "Industrial Machinery"),
        (["DE LAGE LANDEN", "DLL FINANCE"], "Industrial Equipment"),
        (["WESTERN EQUIPMENT", "KEYSTONE EQUIPMENT", "FLATIRON"], "Heavy Equipment"),
        (["STEARNS BANK", "HUNTINGTON EQUIPMENT"], "Commercial Equipment"),
    ]

    for keywords, asset_type in mapping:
        if any(kw in combined for kw in keywords):
            return asset_type

    return "Industrial Equipment"


def run_filters() -> list[dict]:
    """
    Execute all four gates against tomcat_capex.db.
    Returns a list of qualifying lead dicts, ready for geocoding and scoring.
    """
    oldest_date, newest_date = get_maturity_window()

    logger.info(
        f"SpaceX Filter | DB: {DB_PATH} | "
        f"Maturity window: {oldest_date} → {newest_date}"
    )

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Tomcat CapEx database not found at: {DB_PATH}\n"
            f"Set TOMCAT_DB_PATH environment variable to override."
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Gates 1, 3, 4 in SQL — Gate 2 (lender) applied in Python
    query = """
        SELECT
            id, source_state, file_id,
            company_name, address, city, state, zipcode,
            secured_party, collateral, filing_date,
            lapse_date, days_to_lapse, lien_type,
            phone, email, company_website, contact_name
        FROM ucc_leads
        WHERE
            lien_type = 'equipment'
            AND filing_date IS NOT NULL
            AND filing_date >= ?
            AND filing_date <= ?
            AND company_name IS NOT NULL
            AND company_name != ''
            AND company_name NOT LIKE '%INDIVIDUAL%'
        ORDER BY filing_date DESC
    """

    cursor.execute(query, (oldest_date, newest_date))
    rows = cursor.fetchall()
    conn.close()

    logger.info(f"Gate 1+3+4: {len(rows)} records after SQL filter")

    qualified = []
    dropped_soft = 0
    dropped_unknown = 0

    for row in rows:
        lead = dict(row)
        sp = lead.get("secured_party") or ""

        # Gate 2: industrial lender check
        if not is_industrial_lender(sp):
            if any(kw.upper() in sp.upper() for kw in SOFT_ASSET_LENDER_KEYWORDS):
                dropped_soft += 1
            else:
                dropped_unknown += 1
            continue

        # Enrich with derived fields
        lead["predicted_asset"] = predict_asset_type(sp, lead.get("collateral", ""))
        lead["lat"] = None
        lead["lon"] = None
        lead["trigger_hits"] = 0  # Phase 2: populated by job_signal.py

        qualified.append(lead)

    logger.info(
        f"Gate 2: {len(qualified)} qualified | "
        f"{dropped_soft} soft-asset dropped | "
        f"{dropped_unknown} unknown lender dropped"
    )

    return qualified
