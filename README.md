# SpaceX CapEx Predictive Terminal

Automated, predictive lead-generation engine targeting ground-level contractors,
transport carriers, and precision fabricators forced to lease heavy machinery
due to the 2026 SpaceX/Musk infrastructure expansion.

## Quick Start

```bash
cd /Users/robertle/SpaceX_CapEx_Intelligence
pip install -r requirements.txt
python app.py
```

Then open: **http://localhost:5050**

---

## Architecture

```
tomcat_capex.db (40,835 real UCC records)
        ↓
spacex_filter.py  (4 gates: equipment lien → industrial lender → maturity window → company name)
        ↓
geocoder.py       (city+state → lat/lon via Nominatim, cached to cache/geocode_cache.json)
        ↓
score_engine.py   (W1 maturity + W3 proximity + bonuses → propensity score 0-100)
        ↓
Flask /api/leads  → index.html terminal UI
```

## Scoring Formula

| Component | Weight | Logic |
|---|---|---|
| W1 — UCC Maturity | 0–33.3 pts | Peak at 36 months since filing |
| W2 — Job Board Signal | 0–33.3 pts | **Phase 2** — configure API keys below |
| W3 — Proximity | 0–33.3 pts | Haversine distance to nearest Musk node |
| Entity Bonus | +3 pts | Musk entity named in filing |
| Contractor Bonus | +4 pts | Known prime contractor named |

**Phase 1 normalization:** While W2=0, W1+W3 are scaled to 0–100 so scores are meaningful from day one.

## Score Tiers

| Tier | Score | Action |
|---|---|---|
| ⚡ Priority | 85–100 | Same-day contact |
| 🔴 Hot | 65–84 | Immediate outreach |
| 🟡 Monitor | 40–64 | Revisit in 60 days |
| ⬛ Low | 0–39 | Do not contact |

## Adding Phase 2: Job Board APIs

Register for free API keys:
- **Indeed Publisher API**: https://ads.indeed.com/jobroll/xmlfeed
- **Adzuna Developer API**: https://developer.adzuna.com

Then set environment variables:
```bash
export INDEED_API_KEY=your_key_here
export ADZUNA_APP_ID=your_app_id
export ADZUNA_API_KEY=your_key_here
```

The `engine/job_signal.py` module will activate automatically.

## Texas & Tennessee FOIA Requests

Send to these addresses to fill the critical data gap:

**Texas SOS:** `ucc@sos.texas.gov`  
Request: Bulk UCC-1 equipment filing export, May 2022–May 2024, CSV format.  
Authority: Texas Public Information Act (Tex. Gov't Code Ch. 552)

**Tennessee SOS:** `sos.business@tn.gov`  
Request: Same parameters.  
Authority: Tennessee Public Records Act (T.C.A. § 10-7-503)

When data arrives, drop CSV files into `data/foia_imports/` and run:
```bash
# (import handler — Phase 4)
python engine/import_foia.py data/foia_imports/texas_ucc.csv
```

## Data Source

Reads from: `/Users/robertle/tomcat_capex/leads/tomcat_capex.db`  
Override: `export TOMCAT_DB_PATH=/path/to/other.db`

## Infrastructure Nodes Targeted

| Node | Entity | Location |
|---|---|---|
| Giga Texas / Terafab | Tesla/SpaceX/xAI | Del Valle, TX |
| Neuralink ATX1 | Neuralink | Del Valle, TX |
| Starbase | SpaceX | Boca Chica, TX |
| Bastrop Facility | SpaceX/TBC | Bastrop, TX |
| Grimes County Terafab | Terafab | Grimes County, TX |
| Colossus Memphis | xAI | Memphis, TN |
| Colossus Phase 2 | xAI | Southaven, MS |
| Cape Canaveral LC-39A | SpaceX | Cape Canaveral, FL |
| Vegas Loop Phase 3 | The Boring Company | Las Vegas, NV |
| Hawthorne HQ | SpaceX | Hawthorne, CA |
