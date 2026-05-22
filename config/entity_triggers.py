"""
Musk entity string triggers and known prime contractors.
Any match in company_name, secured_party, or collateral fields
adds bonus points to the propensity score.
"""

# +3 pts: Musk entity directly named in filing
MUSK_ENTITY_TRIGGERS = [
    # SpaceX family
    "SPACE EXPLORATION TECHNOLOGIES",
    "SPACEX",
    "STARLINK INTERNET SERVICES",
    "STARLINK",
    "LONE STAR MINERAL DEVELOPMENT",
    # xAI / X Corp (acquired by SpaceX Feb 2026)
    "XAI CORP",
    "X.AI",
    "X HOLDINGS",
    "X CORP",
    # Tesla / Terafab (independent but joint-venture partner)
    "TESLA",
    "TERAFAB",
    # Neuralink
    "NEURALINK",
    # The Boring Company
    "BORING COMPANY",
    # Macrohard (early stage JV)
    "MACROHARD",
]

# +4 pts: Named prime contractor confirmed on a Musk project
KNOWN_CONTRACTORS = [
    # Giga Texas / Terafab confirmed contractors
    "AUSTIN COMMERCIAL",
    "RANGER EXCAVATION",
    "CORBINS ELECTRIC",
    "CEC FACILITIES GROUP",
    "CLAYCO",
    "POLK MECHANICAL",
    "GARZA EMC",
    "S'N'S ERECTORS",
    "SNS ERECTORS",
    "WG YATES",
    "W.G. YATES",
    "KEYSTONE CONCRETE",
    # Terafab equipment suppliers
    "APPLIED MATERIALS",
    "TOKYO ELECTRON",
    "LAM RESEARCH",
    # xAI Colossus known hardware partners
    "SUPERMICRO",
]
