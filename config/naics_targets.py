"""
NAICS code targeting table for supply-chain intelligence.
Used for OpenCorporates, SAM.gov, and job board filtering.
"""

NAICS_TARGETS = {
    "237130": "Power/Communication Line Construction",
    "333249": "Other Industrial Machinery Manufacturing",
    "484122": "General Freight Trucking, Long-Distance LTL",
    "238210": "Electrical Contractors and Other Wiring Installation",
    "532490": "Other Commercial and Industrial Machinery Rental",
    "236220": "Commercial and Institutional Building Construction",
    "238220": "Plumbing, Heating, and Air-Conditioning Contractors",
    "332710": "Machine Shops",
    "488510": "Freight Transportation Arrangement",
    "541330": "Engineering Services",
}

# High-priority subset for SpaceX-specific targeting
PRIORITY_NAICS = ["333249", "238210", "238220", "332710", "237130"]
