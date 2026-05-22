"""
Lender allowlist and blocklist for UCC-1 data purification.
Matched via substring against the secured_party field (case-insensitive).

INDUSTRIAL_LENDER_KEYWORDS: Pass — these are real heavy asset / commercial equipment funders.
SOFT_ASSET_LENDER_KEYWORDS: Drop — these are tech/consumer/soft-asset lenders (IT gear, copiers, etc.)
"""

# ✅ PASS: Industrial asset banks and commercial equipment funders
# Sourced from actual records in tomcat_capex.db + plan allowlist
INDUSTRIAL_LENDER_KEYWORDS = [
    "DE LAGE LANDEN",           # DLL — major industrial lessor
    "DLL FINANCE",
    "CATERPILLAR FINANCIAL",    # CAT Financial — heavy construction
    "CAT FINANCIAL",
    "JOHN DEERE",               # Deere — ag / heavy equipment
    "DEERE FINANCIAL",
    "KOMATSU FINANCIAL",        # Heavy construction
    "STEARNS BANK",             # Equipment finance bank
    "KEY EQUIPMENT FINANCE",    # KeyBank equipment division
    "WESTERN EQUIPMENT FINANCE",
    "LEAF CAPITAL",             # Commercial equipment
    "TAKEUCHI FINANCIAL",       # Compact construction equipment
    "BANK OF THE WEST",         # Takeuchi program bank
    "SUMITOMO MITSUI",          # Industrial/manufacturing
    "BLACKRIVER BUSINESS CAPITAL",
    "KEYSTONE EQUIPMENT FINANCE",
    "OAKMONT CAPITAL",
    "NORTH STAR LEASING",
    "SACHEM CAPITAL",
    "SACHEMS CAPITAL",
    "FLATIRON REALTY CAPITAL",
    "MARLIN BUSINESS",
    "MARLIN LEASING",
    "EVERBANK COMMERCIAL",
    "TRUIST EQUIPMENT",
    "BMO HARRIS EQUIPMENT",
    "FIRST WESTERN EQUIPMENT",
    "MITSUBISHI HC CAPITAL",
    "GREATAMERICA FINANCIAL",
    "GREATAMERICA",
    "HUNTINGTON EQUIPMENT",
    "FIRST HOPE BANK",
    "GENEVA CAPITAL",
    "REYNA CAPITAL",
    "TCF EQUIPMENT",
    "CITIZENS BANK",            # Present in confirmed equipment records
    "BYLINE BANK",
    "CRESTMARK",
    "HITACHI CAPITAL",
    "SIEMENS FINANCIAL",        # Industrial equipment programs
    "VOLVO FINANCIAL",          # Heavy trucking/construction
    "NAVISTAR FINANCIAL",       # Commercial trucks
    "PACCAR FINANCIAL",         # Kenworth/Peterbilt — heavy freight
    "DAIMLER TRUCK FINANCIAL",
    "TRINITY CAPITAL",
    "AMUR EQUIPMENT FINANCE",
    "NAVITAS CREDIT",
    "MERIDIAN EQUIPMENT FINANCE",
    "FORUM FINANCIAL",
    "EQUILEASE TRUST",
    "BALBOA CAPITAL",
]

# ❌ DROP: Tech, consumer, and soft-asset lenders
SOFT_ASSET_LENDER_KEYWORDS = [
    "DELL FINANCIAL",
    "CISCO SYSTEMS CAPITAL",
    "RICOH",
    "KONICA MINOLTA",
    "XEROX FINANCIAL",
    "XEROX",
    "CANON FINANCIAL",
    "IBM CREDIT",
    "HEWLETT-PACKARD FINANCIAL",
    "HEWLETT PACKARD FINANCIAL",
    "HP FINANCIAL",
    "YAMAHA MOTOR FINANCE",
    "DE LAGE LANDEN PUBLIC FINANCE",    # Government/public sector — not target
    "APPLE FINANCIAL",
    "MICROSOFT FINANCING",
    "SAP FINANCIAL",
    "ORACLE CREDIT",
    "PITNEY BOWES",
    "NEOPOST",
]
