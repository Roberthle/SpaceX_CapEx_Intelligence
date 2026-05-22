"""
Job board keyword intent triggers for Phase 2 (Indeed/Adzuna API).
Organized by entity and signal type.
"""

JOB_BOARD_KEYWORDS = {
    "primary": [
        "Cleanroom CNC",
        "Heavy Riggers",
        "Data Center Cooling",
        "Megawatt Generator",
        "Aerospace Quality Inspector",
    ],
    "spacex_xai": [
        "liquid nitrogen",
        "cryogenic",
        "friction stir weld",
        "gantry crane operator",
        "high-bay assembly",
        "propellant handling",
        "launch site technician",
        "composite structures",
    ],
    "tesla_terafab": [
        "2nm fab",
        "semiconductor equipment",
        "EUV lithography",
        "Optimus assembly",
        "gigacasting",
        "dry electrode",
        "4680 cell",
        "chip fabrication",
    ],
    "neuralink": [
        "cleanroom technician",
        "MEMS fabrication",
        "neural device assembly",
        "Class 10 cleanroom",
        "microfabrication",
        "electrode array",
    ],
    "boring_company": [
        "tunnel boring",
        "TBM operator",
        "shotcrete",
        "segment erector",
        "underground construction",
    ],
    "shared_high_value": [
        "AS9100",
        "ITAR",
        "FAA repair station",
        "TWIC card",
        "prevailing wage TX",
        "per diem Bastrop",
        "per diem Memphis",
        "per diem Del Valle",
        "per diem Boca Chica",
        "per diem Austin",
        "aerospace inspector",
        "NADCAP",
    ],
}

# Flat list of all triggers for quick iteration
ALL_KEYWORDS = [kw for group in JOB_BOARD_KEYWORDS.values() for kw in group]
