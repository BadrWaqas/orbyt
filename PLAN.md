# Orbyt Earth: build plan

Owner: Badr Waqas. Plan version 1.0, 12 November 2026.

Orbyt Earth (orbytearth.com) fact-checks the world from space. Each module puts what was officially reported next to what a satellite measured, and shows the gap on a 3D globe. Module 1 is Pollution Hunter.

Every data source, free tier and library version in this plan was checked on 12 November 2026. Items marked (verify) could not be confirmed and need a quick check before you rely on them. Links are in Appendix C.

## Contents

0. The plan on one page
1. Feasibility check
2. Architecture
3. Tech stack
4. The core method
5. Repo structure
6. Milestones
7. Risks
8. What needs a top model
9. Design system
- Appendix A: reference implementation (tested)
- Appendix B: data contract examples
- Appendix C: sources
- Appendix D: glossary

---

## 0. The plan on one page

### Decisions

| Question | Decision | Why |
|---|---|---|
| Pollutant | NO2, published as NOx. Methane comes later as a map layer built from published plume catalogues. | NO2 plumes show up daily at about 5 km resolution and fade within hours, so they stay attached to their source. Sentinel-5P cannot see methane from European facilities (section 1.2). |
| Region | Europe is the product. The United States is the test bench. | Europe has a public register with facility coordinates and annual NOx up to 2024. The US has hourly stack monitors, the closest thing to ground truth. |
| Years | Satellite data from July 2022 onward. Compare calendar years 2023 and 2024. | One processor generation (v2.4 and later), and both years exist in the register. |
| Method | Wind-aligned stacking on a travel-time axis, EMG curve fit, bootstrap interval, literature corrections. A verdict only when the gap beats the validated uncertainty. | Published, explainable, testable. A tested reference implementation is in Appendix A. |
| Satellite data access | Google Earth Engine, Community tier. | Small cloud-filtered patches straight into NumPy. No terabyte downloads. |
| Pipeline | Python, DuckDB and Parquet. Runs on your laptop, later on GitHub Actions. | Free, fast, and standard data engineering. |
| Serving | Static files only. Cloudflare Pages for the app and JSON, Cloudflare R2 for map tiles. No server, no online database. | Nothing sleeps, nothing bills, and a traffic spike costs nothing. |
| Frontend | Vite, React, TypeScript, Tailwind, MapLibre GL JS v5 with globe projection. deck.gl added later for glow. | One map engine from orbit to street level, no API key, works on phones. |
| Budget | Zero until launch, then the domain only. | Every service above has a free tier that fits. |

### What the MVP is

- A live public URL with a dark 3D globe and a monthly NO2 layer from July 2022 to the latest month.
- At least 25 European facilities or clusters with a verdict for 2023 and 2024: reported tonnes, satellite estimate with interval, ratio, confidence grade.
- A validation page: the same method against hourly stack monitors at 25 or more US power plants.
- A page per facility with a share card, a leaderboard, a method page and a corrections page.
- It works on a phone.

### Three things to accept up front

1. Most European results will come out "consistent with reported". Large EU plants have stack monitors and the best published satellite catalogue agrees with the German register within about 20% on average. The product is the check itself, shown beautifully. A scandal is not required for it to be good.
2. Only large, isolated sources can be measured. The practical floor is about 2,000 to 3,500 tonnes of NOx a year. Facilities inside cities or dense industrial clusters cannot be separated.
3. A single facility estimate carries roughly 40% uncertainty until your own validation tightens it. With that, a gap has to be about 2.5 times before the site is allowed to flag it.

### Timeline

About 11 weeks at 8 to 10 hours a week. Internship hiring runs through the winter, so the order is built to give you a shareable live link after week 2, with real paired numbers on it, and to improve what is behind that link every week after.

| Milestone | Weeks | What you can show |
|---|---|---|
| M0 Skeleton live | 0 | A dark spinning globe on a public URL |
| M1 The globe glows | 1 | Global NO2 on the globe, Europe's largest reporters as dots |
| M2 First paired numbers | 2 | Reported vs published satellite estimates, leaderboard v0 |
| M3 Your own estimate | 3 to 4 | One facility measured end to end by your code |
| M4 Validation | 5 to 6 | Scatter plot against US stack monitors |
| M5 Europe at scale | 7 | 25 or more verdicts |
| M6 Product UI | 8 to 9 | Side panel, time slider, share pages, mobile |
| M7 Visual polish | 10 | Glow, cinematic intro, scroll story |
| M8 Trust and launch | 11 | Domain, method page, launch clip |

---

## 1. Feasibility check

### 1.1 Verdict

Feasible at zero cost, with the scope cuts in section 0. The satellite data, the wind data, the European register and the US monitor data are all live and free today. The method is established in peer-reviewed work, and I ran a reference implementation against synthetic plumes for this plan (Appendix A). The original brief needs three changes:

- Start with NO2 only. Do not try to detect methane yourself with Sentinel-5P.
- Do not expect a leaderboard of scandals. Expect a leaderboard of checks, with a few open questions.
- Treat "trace plumes to facilities" as a test you run on known facilities, not as free-form detective work. Blind discovery of unknown sources is a later feature.

### 1.2 NO2 or methane

| | NO2 | Methane (CH4) |
|---|---|---|
| TROPOMI pixel | 5.5 x 3.5 km | 7 x 5.5 km |
| Signal | Strong against a low background | A few parts per billion on top of roughly 1,900 |
| Atmospheric lifetime | Hours. The plume stays near its source and you can fit its decay. | About a decade. Plumes sit on a huge shared background. |
| Smallest source you can quantify | About 0.11 kg/s of NOx, which is 3,500 t/yr. Down to 0.03 kg/s (950 t/yr) over bright desert. (Beirle et al. 2023) | About 5 t/h in favourable conditions. Automated detections in 2021 ranged from 8 to 122 t/h (5th to 95th percentile). (Schuit et al. 2023) |
| Coverage over Europe | Daily, clouds permitting | Sparse: cloud, dark surfaces, snow and water all block it |
| Attribution | One facility or a tight cluster | One detection can cover up to 10 facilities |
| Official number to compare with | EU: annual NOx per facility, often from continuous monitors. US: hourly stack data. | EU: annual CH4 above 100 t/yr, mostly calculated. US: the federal programme is in limbo. |
| Published method to follow | Yes, several | Needs higher resolution satellites |

The methane numbers settle it. A source emitting 5 t/h around the clock releases 43,800 t a year. The EU reporting threshold is 100 t a year. Almost everything in the European register is far below what TROPOMI can see, and the few global super-emitters it does see are mostly oil and gas fields outside Europe.

Methane still belongs on the globe, because the plumes are dramatic. Use detections that specialist teams already publish instead of making your own:

- UNEP IMEO Eye on Methane: open, no registration, CSV, GeoJSON and API. Detections go public 30 days after they are made.
- Carbon Mapper: free for non-commercial use, API with a free account. The licence is non-commercial and share-alike, so display with attribution and do not rehost bulk copies.
- SRON publishes weekly TROPOMI super-emitter detections.

Show these as a second layer after launch. Do not build a "reported vs observed" verdict for methane yet. A plume is a snapshot and a register entry is an annual total, and turning one into the other needs care you do not have time for in the MVP.

### 1.3 Region

Europe for the product:

- The EEA Industrial Reporting database (the successor to the standalone E-PRTR download) is at version 16, published 20 February 2026, covering reporting years 2007 to 2024. It has facility names, operators, coordinates and annual releases to air, plus more detailed data for large combustion plants.
- Facilities report NOx when they exceed 100 t/yr, and each reported value is flagged as measured, calculated or estimated. Show that flag.
- There is published precedent for exactly this comparison in Europe, which is good news. It means the idea is accepted science and you have numbers to compare against (van der A et al. 2024, Beirle et al. 2023).
- Good first candidates are large lignite and coal plants in open country: Bełchatów in Poland (about 30,000 t of NOx in 2018 according to a published power plant catalogue, roughly nine times the detection floor), the big German lignite sites, Maritsa East in Bulgaria, the Nikola Tesla plants in Serbia, and the Greek lignite region. Check each against the 2023 and 2024 register values, because European coal output is falling fast.

The United States for validation:

- EPA's Clean Air Markets Program Data (CAMPD) publishes hourly NOx mass for power plant units, measured by continuous emission monitors. Data for 2025 was already available in February 2026. Access is free through bulk files or an API with a free key. The PUDL project republishes the hourly data in a cleaned form.
- This lets you compare your satellite estimate with measured emissions for the same hours on the same days. Nothing in Europe gives you that.

Other registers can be added later through the same adapter interface: Canada (NPRI) and Australia (NPI) both publish facility NOx (verify access details when you get there).

### 1.4 What will not work with free data

- Detecting methane leaks at European facilities with Sentinel-5P.
- A number for one facility on one day. Estimates need a stack of at least 40 clear, windy days. Annual and rolling 12-month numbers are realistic. Monthly numbers are not.
- Facilities below about 2,000 t/yr of NOx, facilities inside cities, and dense clusters such as the Ruhr, Rotterdam or the Po valley. Report clusters as clusters or leave them out.
- Coastal and mountain sites without a warning flag. Winds are less reliable and surface brightness contrasts cause artefacts.
- Winter. With the usual sun-angle filter (solar zenith below 65 degrees), a site at 50 to 55 degrees north only contributes observations from about late February to late October. Your "annual" estimate is really a spring to autumn estimate.
- Trends that cross July 2022 using Earth Engine. The NO2 processor changed several times before then, and each change shifted the columns by 10 to 40%. A consistent full-mission reprocessing exists at the Copernicus Data Space, but Earth Engine does not document any reprocessing of its collection. Check the PROCESSOR_VERSION property on images before using anything earlier.
- Real-time figures. Earth Engine's offline NO2 runs about two weeks behind. The register runs about a year behind: 2024 data first appeared in December 2025.
- Any statement about legal compliance. A satellite estimate cannot show that a permit limit was broken.
- A US methane comparison built on EPA's Greenhouse Gas Reporting Program. EPA proposed in September 2025 to end most of that reporting, has twice postponed the 2025 deadline (now 10 March 2027), and has not issued a final rule.

### 1.5 Data sources, checked 12 November 2026

| Source | Used for | Status today | Access and cost | Watch out for |
|---|---|---|---|---|
| Sentinel-5P TROPOMI NO2, Earth Engine collection `COPERNICUS/S5P/OFFL/L3_NO2` | Plumes | Live. Data runs to 31 Oct 2026. The satellite is past its 7 year design life and in extended operation. CEOS lists a planned end of life of September 2027. | Earth Engine, free | Gridded at 1.1 km from 5.5 x 3.5 km pixels. Quality filter (qa 0.75) already applied to the tropospheric band. Mixed processor versions before mid 2022. |
| ERA5 hourly winds, `ECMWF/ERA5/HOURLY` | Wind at overpass time | Live. Data runs to 5 Nov 2026. | Earth Engine, free | About 28 km grid. Has 10 m and 100 m wind bands and surface pressure. Pressure level winds are in a separate collection. |
| EEA Industrial Reporting database v16 | Reported NOx, EU | Published 20 Feb 2026, covers 2007 to 2024 | Direct download, CSV or Excel, plus GeoPackage | Check each country's 2024 completeness. Table names change between versions, so inspect before coding. Reuse terms: attribution (verify on the dataset page). |
| EPA CAMPD hourly emissions | Validation, US | Live. 2025 data available. | Bulk files or API with free key. PUDL has cleaned Parquet. | Large files. Pull only the plants and years you need. |
| Beirle et al. NOx point source catalogue v2 | Early demo and sanity check | Published 2023. 1,139 sources worldwide, May 2018 to Nov 2021. CC BY 4.0. | Download, CSV and NetCDF | Different years from your own estimates. Label it as third-party. |
| Climate TRACE | Optional third opinion per facility | Live, monthly releases, CC BY 4.0, includes NOx | CSV downloads and API | Modelled, not measured. Never present it as a second measurement. |
| Earth Engine quota | Extraction | Since 27 April 2026 noncommercial projects get a monthly quota: Community tier 150 EECU-hours, Contributor tier 1,000 (needs a billing account on file, Earth Engine use is not charged). | Free | Batch and interactive use both count. Over quota you are slowed down, not cut off. Noncommercial status must be re-verified yearly. |
| Copernicus Data Space | Fallback, and the science upgrade path | Live. Free tier: 12 TB of downloads a month, 10,000 Sentinel Hub processing units and 10,000 openEO credits a month. | Free account | Original orbit files are hundreds of MB each. Only worth it if you need averaging kernels. |
| UNEP IMEO Eye on Methane | Methane layer, later | Live, open | CSV, GeoJSON, API | Read the terms of use before publishing. |
| Carbon Mapper | Methane layer, later | Live | Free account, API | Non-commercial, share-alike licence |
| EPA Greenhouse Gas Reporting Program | Not used | Uncertain future, see 1.4 | | Do not build on it |
| Sentinel-4 (hourly NO2 over Europe) | Future upgrade | In orbit since July 2025. EUMETSAT took over operations in August 2026 and published user guides for operational Level 2 products in October 2026. | EUMETSAT (verify NO2 product availability) | Would allow hourly animations over Europe. Not for the MVP. |

### 1.6 What the results will probably look like

- For large EU power plants, satellite and register will mostly agree within the uncertainty. The best published catalogue (Beirle et al. 2023) found its estimates within about 20% of the German register on average, and about 20% low overall for isolated sources.
- "Satellite lower than reported" will be common. The standard NO2 product is known to read low near strong sources, the satellite passes at about 13:30 when solar power pushes fossil plants below their daily average, and clear days are not random days.
- A few sites may come out well above reported. Published work on large European point sources has seen satellite-based estimates above register values for several of them. Each one needs a manual review before it goes public, because the usual explanation is a neighbour, a city or bad wind data.
- The 2025 and 2026 estimates have no official counterpart yet. That is a feature: "the register for 2025 is not published yet, here is what the satellite saw". When the next register version lands, the site compares the two automatically.

### 1.7 Go or no-go gate (end of milestone 2)

Count the facilities and clusters in the EEA data that reported at least 2,000 t of NOx in 2023 or 2024 and that pass the isolation rule in section 4.5.

- 20 or more: proceed as planned.
- Fewer than 20: keep going, but lower the bar to clusters (compare the satellite estimate with the summed reported emissions inside a 20 km footprint), and bring the US plants onto the public map as well as the validation page.

---

## 2. Architecture

### 2.1 Principles

1. Static first. Everything the site needs is a file built ahead of time. There is no server to keep awake and no database to query at page load.
2. One contract, many modules. Every module ends in the same object, a Finding: what was claimed, what was observed, the gap, and the evidence.
3. Reproducible numbers. Every published figure carries a data version, a method version and a git commit.
4. Raw data stays out of git. Small test fixtures go in.

### 2.2 The system at a glance

```
 LAPTOP, later GITHUB ACTIONS (Python)                          CLOUDFLARE (static)        BROWSER
+----------+   +-----------+   +-----------+   +----------+   +-------------------+   +------------------+
| ingest   |-->| extract   |-->| observe   |-->| publish  |-->| Pages: app + JSON |-->| React app        |
| EEA,     |   | daily NO2 |   | rotate,   |   | JSON,    |   | R2: tiles, images |   | MapLibre globe   |
| CAMPD,   |   | patches + |   | stack,    |   | tiles,   |   +-------------------+   | deck.gl layers   |
| GEE,ERA5 |   | wind      |   | fit,      |   | images,  |                           +------------------+
+----------+   +-----------+   | compare   |   | schemas  |
     |              |          +-----------+   +----------+
     v              v               v               v
 data/raw      data/interim    data/warehouse     dist/
 (cache)       (npz stacks)    (Parquet+DuckDB)   (what gets deployed)
```

### 2.3 Pipeline stages for Pollution Hunter

| Stage | Input | What it does | Output |
|---|---|---|---|
| ingest | EEA download, CAMPD, Beirle catalogue | Download and cache. No logic. | `data/raw/` |
| candidates | facilities, reported NOx | Keep sources at or above 2,000 t/yr, score isolation, merge neighbours into clusters | `candidates.parquet` |
| extract | Earth Engine | For each candidate: list usable overpasses, download NO2 patches, get wind at overpass time | `data/interim/<id>/*.npz` |
| observe | patches, wind | Rotate, convert to travel time, stack, fit, bootstrap, apply gates (section 4) | `estimates.parquet`, `observations_daily.parquet` |
| compare | estimates, reported footprint sums | Ratio, interval, verdict, grade | `findings.parquet` |
| validate | US estimates, hourly CEMS | Bias and scatter against stack monitors | `validation.parquet` |
| layers | monthly NO2 means, stacks | Colourise and tile the global layer, render plume images, flipbooks and share cards | `dist/tiles/`, `dist/img/` |
| publish | everything above | Write JSON per the contract, validate against schemas, write the manifest | `dist/data/v1/` |

Every stage is a CLI command, reads files and writes files, and can be rerun alone:

```
orbyt ingest eea
orbyt ph candidates --region eu
orbyt ph extract --id <facility> --from 2022-07 --to 2026-10
orbyt ph observe --id <facility> --window 2024
orbyt ph compare
orbyt ph validate --region us
orbyt ph layers
orbyt publish
```

### 2.4 Storage

| Where | What | In git |
|---|---|---|
| `data/raw/` | Downloads exactly as received, keyed by request hash | No |
| `data/interim/` | Per facility NO2 patches as compressed float32 NPZ. Expect 1 to 3 GB in total. | No |
| `data/warehouse/` | Parquet tables, plus `orbyt.duckdb` holding views over them | No |
| `dist/` | The deployable output: JSON, tiles, images | No, built by the pipeline |
| `pipeline/tests/fixtures/` | A few tiny real patches and CSV extracts for tests | Yes |

Warehouse tables:

| Table | Key columns |
|---|---|
| `facilities` | facility_id, register, register_id, name, operator, sector, country, lat, lon |
| `reported` | facility_id, year, pollutant, value_kg, basis (measured, calculated, estimated), source_version |
| `subjects` | subject_id, kind (facility or cluster), member_facility_ids, lat, lon, footprint_radius_km, isolation flags |
| `observations_daily` | subject_id, date, wind_u, wind_v, valid_frac, solar_zenith, plume_z, detected |
| `estimates` | subject_id, window_start, window_end, q_mol_s, nox_t_yr, ci_lo, ci_hi, tau_h, t0_h, r2, n_days, gates_failed, method_version |
| `findings` | finding_id, subject_id, period, claimed_t, observed_t, lo, hi, ratio, ratio_lo, ratio_hi, verdict, grade |
| `validation` | plant_id, year, cems_matched_t_yr, cems_annual_t, estimate_t_yr, ci_lo, ci_hi |

### 2.5 The API is a set of versioned files

The frontend only ever fetches these. Changing a field means bumping `v1` to `v2`.

| Path | Contents |
|---|---|
| `/data/v1/manifest.json` | Build time, data version, method versions, git commit, list of modules |
| `/data/v1/pollution-hunter/findings.json` | Compact list for the map and leaderboard: one row per subject and period |
| `/data/v1/pollution-hunter/finding/<id>.json` | Full detail for the panel: rolling estimates, fit profile, gates, daily detections, sources |
| `/data/v1/pollution-hunter/layers.json` | Tile URLs per month, colour ramp, units, legend stops |
| `/data/v1/pollution-hunter/validation.json` | US plants: estimate, monitor value, interval |
| `/data/v1/pollution-hunter/findings.csv` and `.parquet` | Downloads for anyone who wants to check your work |

Appendix B has example payloads. If you later need a dynamic endpoint (search, a corrections form), add a Cloudflare Worker. The free plan allows 100,000 requests a day.

### 2.6 How modules plug in

A module is one Python package and one frontend folder. Both implement a small contract and register themselves. Nothing in the core changes when you add one.

Pipeline side:

```python
from typing import Literal, Protocol
from pydantic import BaseModel

class Claimed(BaseModel):
    value: float
    unit: str
    source: str        # for example "EEA Industrial Reporting database v16"
    basis: Literal["measured", "calculated", "estimated", "stated", "unknown"]

class Observed(BaseModel):
    value: float
    lo: float          # 95% interval
    hi: float
    unit: str
    method: str        # for example "ph-emg-1.0"

class Finding(BaseModel):
    id: str
    module: str
    subject: "Subject"         # name, operator, kind, country, lat, lon, register_id
    period: "Period"
    claimed: Claimed | None    # None when nothing official exists yet
    observed: Observed | None
    ratio: "Interval | None"
    verdict: Literal["higher", "consistent", "lower", "inconclusive", "unpaired"]
    grade: Literal["A", "B", "C"] | None
    evidence: dict             # image paths, profiles, anything the panel draws
    versions: "Versions"

class Module(Protocol):
    id: str
    def ingest(self, ctx) -> None: ...          # fetch raw inputs
    def claims(self, ctx): ...                  # what was reported or promised
    def observe(self, ctx): ...                 # what the satellite shows, with uncertainty
    def compare(self, ctx) -> list[Finding]: ...
    def layers(self, ctx) -> list["Layer"]: ... # tiles and images for the map
```

Frontend side:

```ts
export interface ModuleDescriptor {
  id: string;                  // "pollution-hunter"
  title: string;
  hue: HueName;                // one of the six module hues in section 9
  dataBase: string;            // "/data/v1/pollution-hunter"
  layers: LayerSpec[];         // what to draw on the globe, and at which zooms
  Panel: React.ComponentType<{ finding: Finding }>;
  Legend: React.ComponentType;
  formatValue(v: number): string;
}
```

Shared by every module and written once: the globe, camera, time rail, leaderboard table, gap bar, share cards, verdict logic and the publish step.

How the future modules map onto the same contract:

| Module | Claimed (the record) | Observed (the instrument) | Free data | Notes |
|---|---|---|---|---|
| Gas flaring tracker | Reported flared volumes | Night-time thermal detections converted to flared gas | VIIRS Nightfire (verify licence), World Bank flaring data | Easiest next module. Detections are already published as points. |
| Deforestation promise checker | Supplier lists and zero-deforestation pledges | Tree cover loss inside concession boundaries | Hansen Global Forest Change and forest alerts in Earth Engine | Attribution is by polygon. Highest legal risk, because you name brands. |
| Irrigation ban watch | Dates and areas of official irrigation bans | Fields that stay green during a ban while neighbours brown | Sentinel-2 in Earth Engine | False positives from legal exemptions and local rain. Never name a farm. |
| Ghost developments | Completion and occupancy claims | Night light radiance over new building footprints | NASA Black Marble (500 m pixels), open building footprints | Only works for large estates. |

Naming note: "Drought water thieves" accuses people of a crime in the title. Use something like "Irrigation ban watch". Same logic for every module name and headline.

### 2.7 Frontend architecture

- One page, one map. A single MapLibre instance lives for the whole session. The intro, the story and the explore view all drive the same camera, so nothing reloads between them.
- The URL is the state: `/explore?m=pollution-hunter&f=<id>&t=2024-06`. Every view is a shareable link. Zustand holds only short-lived UI state.
- Routes: `/` (intro, story, globe), `/explore`, `/leaderboard`, `/method`, `/validation`, `/data`, `/corrections`, `/about`.
- Share pages: a small build script writes `/f/<slug>/index.html` for every finding. Each is a copy of the app shell with that facility's title, description and share image in the meta tags, so links unfurl properly on LinkedIn.
- First paint: the HTML shell contains the hero text and a poster image of the globe. They appear immediately. The map loads behind and cross-fades in when ready. deck.gl is a separate chunk loaded when idle.
- Modules register a descriptor (2.6). The app reads `manifest.json`, shows the modules it finds, and loads a module's code on demand.

### 2.8 Keeping it updated

- MVP: run the pipeline on your laptop once a month, upload tiles to R2, push JSON, Pages redeploys.
- After launch: a scheduled GitHub Actions workflow does the same with an Earth Engine service account key stored as a secret.
- When a new register version appears, `orbyt ingest eea` picks it up and every "unpaired" satellite estimate for that year becomes a paired finding.

---

## 3. Tech stack

### 3.1 Choices and reasons

| Layer | Choice | Why | Fallback |
|---|---|---|---|
| Dev machine | WSL2 Ubuntu on the Vivobook, repo inside the Linux filesystem | Same environment as GitHub Actions, painless geospatial installs, CLI tools work as documented | Native Windows also works: NumPy, SciPy and rasterio ship Windows wheels |
| Python | 3.12 with uv | Fast installs, lockfile | pip and venv |
| Satellite and wind data | Earth Engine Python API, `ee.data.computePixels` returning NumPy arrays | The official call for small pixel grabs | `xee`. Its 0.1 release changed the API, so pin a version if you use it |
| Numerics | NumPy, SciPy | The whole method is about 150 lines of array math | |
| Tables | DuckDB over Parquet, with Polars or pandas | No setup, SQL for joins, the files are the database | SQLite |
| Contracts | Pydantic models exported to JSON Schema, TypeScript types generated from the schema | One source of truth for pipeline and web | Hand-written zod schemas |
| CLI and quality | Typer, pytest, ruff | Standard | |
| Raster tiles | rasterio and rio-tiler to cut tiles, the `pmtiles` CLI to pack them | Installable with pip, no GDAL command line needed | gdal2tiles |
| Site hosting | Cloudflare Pages | Free plan: unlimited static bandwidth, 500 builds a month, up to 20,000 files of at most 25 MiB each | GitHub Pages |
| Tiles and images | Cloudflare R2 | 10 GB free, no egress fees, supports the range requests PMTiles needs. Set a CORS rule that allows GET with the Range header. | Small tile sets can sit in the Pages bundle as plain files |
| Automation | GitHub Actions | Free on public repositories with standard runners | `make publish` on the laptop |
| App | Vite, React, TypeScript | This is a WebGL app, not a content site. No server rendering means no hydration bugs around the map, and lighter models are reliable with this stack. | Astro with one React island |
| Styling | Tailwind CSS v4 reading CSS variables from `tokens.css` | Tokens live in one file | CSS modules |
| Globe | MapLibre GL JS v5, globe projection | See 3.2 | |
| Glow and data layers | deck.gl 9.x through `MapboxOverlay`, added in M7 | Additive blending, bitmap layers, custom shaders. Works with the MapLibre globe since 9.1. | MapLibre layers only |
| Basemap | OpenFreeMap vector tiles with your own dark style, plus NASA Black Marble night lights as a low zoom raster | Free with no key. City lights under glowing plumes is the look. | Protomaps |
| State | URL parameters, Zustand for UI state | Shareable views | |
| Charts | Hand-built SVG with d3-scale and d3-shape | Four small charts, full control of the look | Observable Plot |
| Motion | Motion for UI, MapLibre camera for the globe, scrollama for the story | Small and well known | GSAP |
| Tests | Vitest, Playwright (which also renders the share cards) | | |
| Analytics | Cloudflare Web Analytics | Free and cookieless (verify current terms) | None |
| Domain | Buy orbytearth.com at launch | Use the free pages.dev address until then | |

### 3.2 Globe library

| Option | For | Against | Verdict |
|---|---|---|---|
| MapLibre GL JS v5 | Globe projection with atmosphere since v5.0 (January 2025). One engine from orbit to street level. Built-in fly-to. Free, no key. Works with deck.gl. Runs well on phones. | Less cinematic out of the box than a custom scene | Use this |
| CesiumJS | True 3D globe, terrain, time-dynamic data | Heavy, its own ecosystem, hard to make it look designed, more than flat data on a sphere needs | No |
| deck.gl GlobeView alone | Excellent data layers | No basemap or labels by itself | Use deck.gl as an overlay on MapLibre |
| Three.js or globe.gl | Total visual control | You rebuild tiles, labels, picking and deep zoom yourself | Not needed |
| Mapbox GL JS | The prettiest atmosphere | Proprietary, needs a token, capped free tier. A viral day could cost money. | No |

Version warning that matters when lighter models write the code: MapLibre GL JS v6 came out on 22 July 2026. It is ESM-only, requires WebGL2, and removed the default export and `map.transform`. Most models still write v5 code, and v5 has everything this project needs. Pin `"maplibre-gl": "^5"` and upgrade after launch using the official migration guide. deck.gl 9.4 (September 2026) added an `@deck.gl/maplibre` module that supports MapLibre v4 to v6, which is the path to take when you do upgrade.

### 3.3 Earth Engine or Copernicus Data Space

| | Earth Engine | Copernicus Data Space |
|---|---|---|
| What you get | Gridded per-orbit images, cloud filtered, cut to any box on request | Original orbit files with every variable, including averaging kernels |
| Effort | Low | High: regridding, quality filtering and big downloads are on you |
| Laptop load | A few GB of small patches | Roughly a terabyte or more for four years over Europe (my estimate) |
| Limits | 150 EECU-hours a month on the Community tier | 12 TB of transfer a month |
| Science ceiling | Cannot recompute the air mass factor. Older years carry older processor versions. | Full control, and the reprocessed v2.4 record for the whole mission |

Decision: Earth Engine for the MVP. Treat Copernicus Data Space as the version 2 science upgrade. Measure quota before scaling: log EECU use for one facility and one year, multiply, and if the full backfill would pass about 100 EECU-hours, split it across two calendar months.

### 3.4 Why there is no backend and no online database

Free always-on Python hosting either sleeps or has cold starts, and both ruin the first three seconds. A map of a few hundred facilities with precomputed numbers has no query that needs a server. Static files on a CDN are faster, free and cannot go down under load. To show SQL skills, add a `/data` page after launch that runs DuckDB-WASM in the browser against the published Parquet file.

---

## 4. The core method

### 4.1 The 60 second version

Say this in an interview:

> The TROPOMI instrument gives a daily map of NO2 at about 5 km resolution. A big plant makes a plume that the wind carries away and that fades within a few hours. On any single day the plume is faint and half hidden by cloud, so I use every clear day in a year. I rotate each day's image around the plant so the wind always points the same way, and I convert distance from the stack into travel time using that day's wind speed. Averaged together, the noise cancels and one clean curve is left: it jumps at the plant and decays downwind. I fit that curve. Its height is the emission rate and its decay is the chemical lifetime. I convert NO2 to NOx, correct for the satellite's known low bias near point sources, and bootstrap over days to get an interval. Only then do I compare with the reported number, and I only flag a gap that is bigger than the error I measured against US plants with hourly stack monitors.

### 4.2 What the satellite measures

- TROPOMI records sunlight reflected by the Earth and measures how much blue light NO2 absorbed on the way. The product is a tropospheric column: moles of NO2 above each square metre of ground (mol/m2). Typical clean air is 10 to 30 micromol/m2. A strong plume adds 50 to 300.
- One pass a day at about 13:30 local solar time. Pixel 5.5 x 3.5 km.
- Useful conversion: 1 micromol/m2 = 6.022e13 molecules/cm2.
- Plants emit mostly NO, which turns into NO2 within minutes. NO plus NO2 is NOx, and registers report NOx expressed as NO2 mass. Your estimate uses the same convention, so the units match.

### 4.3 From images to an emission rate

Step 1. Choose subjects. Facilities with at least 2,000 t/yr of reported NOx. Merge facilities closer than 20 km into one cluster subject.

Step 2. Extract. For each subject and each overpass from July 2022 onward, download the tropospheric NO2 column on a 0.03 degree grid covering 180 km in every direction. Before downloading, filter on the server so you only pull usable overpasses:

- at least 50% valid pixels within 50 km of the source
- solar zenith angle below 65 degrees and sensor zenith angle below 56 degrees at the source (both are bands in the collection)

Sketch of the download call (not tested, check it against the `ee.data.computePixels` documentation):

```python
BAND = "tropospheric_NO2_column_number_density"

def fetch_patch(image, lats, lons, step=0.03):
    """One overpass as a 2D float32 array [lat ascending, lon ascending], NaN = no data."""
    request = {
        "expression": image.select(BAND).unmask(-9999),
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": len(lons), "height": len(lats)},
            "affineTransform": {
                "scaleX": step, "shearX": 0, "translateX": float(lons[0] - step / 2),
                "shearY": 0, "scaleY": -step, "translateY": float(lats[-1] + step / 2),
            },
            "crsCode": "EPSG:4326",
        },
    }
    arr = ee.data.computePixels(request)[BAND].astype("float32")
    arr[arr == -9999] = np.nan
    return arr[::-1, :]          # flip rows so latitude ascends
```

Step 3. Wind. Take the ERA5 100 m wind (u and v) at the source for the hour nearest the overpass. Overpass time in UTC is about 13.5 minus longitude divided by 15, so about 12:15 UTC at 19 degrees east. Drop days with wind below 2 m/s: in calm air the gas pools and has no direction. The published catalogue uses wind at about 500 m above ground. Test that level too (the pressure level collection, at surface pressure minus about 55 hPa) and keep whichever validates better. The emission scales directly with wind speed, so this choice matters.

Step 4. Rotate and convert to travel time. For each day:

1. Subtract that day's background: the median column in a box 20 to 70 km upwind.
2. Resample the image onto a grid whose x axis points downwind. Sample it at distances x = wind speed x t, for travel times t from minus 2 to plus 6 hours. Now every day shares one clock, whatever its wind speed.
3. Multiply by wind speed. Column times speed is a flux: moles per second crossing each metre of a line across the wind.

Step 5. Stack and integrate. Average all days cell by cell (cloud gaps are simply skipped), then sum across the wind inside a fan that is 20 km wide at the source and widens downwind. You now have one curve F(t): the flux of NO2 through a gate at each travel time, in mol/s.

Step 6. Fit. If a source emits q moles per second and NO2 decays with lifetime tau, then F(t) is zero upwind, jumps to q at the source and decays as exp(-t / tau). Pixel size and wind error blur the jump. A decay blurred by a Gaussian is called an exponentially modified Gaussian (EMG):

```
F(t) = q * exp( sigma^2 / (2 tau^2) - (t - t0) / tau ) * Phi( (t - t0) / sigma - sigma / tau ) + b

q      emission of NO2 in mol/s        (what you want)
tau    lifetime in hours               (comes for free, typically 2 to 8)
sigma  blur in hours
t0     where the plume starts          (should be 0 if the source is where you think it is)
b      leftover background
Phi    standard normal cumulative distribution
```

Step 7. Convert q to tonnes of NOx per year (4.6).

Step 8. Bootstrap. Resample the days with replacement 200 times, refit each time, and take the 2.5th and 97.5th percentiles. This interval covers sampling noise only.

Step 9. Apply the quality gates (4.5). Anything that fails is published as "inconclusive", never as a number.

Why travel time and not distance: the classic version of this method stacks in distance and multiplies by the mean wind speed afterwards. On synthetic plumes that overestimates by about 30%, because slow days hold more gas near the source and dominate the average. Stacking in travel time removes that bias. This is a small design decision of your own that you can explain and show a test for, which interviewers like.

### 4.4 Plume detection on a single day

Used for the flipbook, for "plume visible on 61 of 96 clear days", and as a sanity check. On the wind-aligned image for one day:

```
down  = mean enhancement in the box 0 to min(2 h of travel, 60 km) downwind, inside the fan
up    = mean enhancement in the same box mirrored upwind
noise = 1.4826 * MAD(background cells) / sqrt(n_independent)
z     = (down - up) / noise

plume detected if z >= 3 and the box is at least 60% valid
```

`n_independent` is roughly the box area divided by the real pixel area (about 19 km2), because the download grid is finer than the real pixels.

### 4.5 Attribution: is it really this facility?

The rotation is the test. If you rotate around the true source, the curve jumps at t0 = 0. If the gas comes from somewhere else, the jump is offset and the decay looks wrong. Synthetic tests for this plan show what that looks like: an empty site with a 20,000 t/yr source 44 km away produced a fake estimate of about 3,800 t/yr with a good-looking fit (r2 around 0.9). The plume start was pinned at the edge of its allowed range and the lifetime ran past 8 hours, so the gates rejected it every time.

Quality gates:

| Gate | Pass when | Why |
|---|---|---|
| Days | at least 40 valid days in the window | Noise |
| Wind | every day at least 2 m/s | Calm days have no direction |
| Fit quality | r2 at least 0.85 | Pure noise gave at most 0.5 in tests |
| Plume start | abs(t0) at most 0.5 h, and not at a bound | Catches neighbours |
| Lifetime | tau between 1 and 8 h, and not at a bound | Published range is about 2 to 8 h |
| Signal to noise | estimate at least 3 times its bootstrap standard error | |
| Isolation | no other register source above 25% of this one between 20 and 60 km away, no city above 200,000 people within 30 km | Otherwise treat as a cluster or flag it |
| Terrain and coast | flag (do not fail) if elevation varies by more than 300 m within 30 km or the sea is within 15 km | Wind and brightness artefacts |

Footprint accounting. The satellite cannot tell two stacks 5 km apart from one. So the comparison is always: satellite estimate for the subject against the sum of reported NOx from every register facility within 20 km. Show the list of facilities in that sum.

Blind discovery (after launch). The Beirle catalogue lists satellite-detected point sources without using any register. Match it against the EEA facilities. Sources in the catalogue with no register facility within 20 km are candidates for "the satellite sees a source here and nobody reports one". Most will be cities, ports or airports. Review by hand.

### 4.6 From NO2 flux to NOx tonnes

```
NOx (t/yr) = q (mol/s) * 0.0460055 kg/mol * f * c * 31,557,600 s/yr / 1000

f = 1.38   NOx to NO2 ratio at midday (Beirle et al. 2023 give 1.38 +/- 0.10; older papers use 1.32)
c = 1.61   air mass factor correction (Beirle et al. 2023 give 1.61 +/- 0.32)
```

Worked example: q = 10 mol/s gives 20,035 t/yr before the correction and 32,257 t/yr with it.

About c. The standard retrieval assumes NO2 is spread through the lower atmosphere the way a coarse global model says. A fresh plume sits low, where the satellite is less sensitive, so the product reads low near strong sources. Recomputing this per pixel needs variables Earth Engine does not carry, so you apply a published average factor. This is the largest simplification in the project. Say so on the method page. The US validation tells you whether 1.61 is right for your pipeline. If your estimates come out 15% high against stack monitors, change c, document why, and never tune it on European data.

### 4.7 Uncertainty

| Term | Size (one sigma) | Where it comes from |
|---|---|---|
| Sampling noise | 2% at 20,000 t/yr, 7% at 4,000, 15% at 2,000 (120 days) | Bootstrap. Numbers from the synthetic tests. |
| Wind speed and height | 15 to 20% | Reanalysis against reality, 100 m against plume height |
| Air mass factor correction | 20% | 1.61 +/- 0.32 |
| NOx to NO2 ratio | 7% | 1.38 +/- 0.10 |
| Time sampling | 15 to 25% | Midday, clear, spring to autumn days standing in for a calendar year |
| Method bias | 5 to 10% | Synthetic tests with wind errors |
| Total | about 35 to 40% | Added in quadrature |

Treat the total as a placeholder. After milestone 4, replace it with the scatter you measure against US stack monitors.

### 4.8 Verdict rules

```
u_sys   = 0.35                                  # relative, replace after validation
s_boot  = (ln(ci_hi) - ln(ci_lo)) / 3.92
s_total = sqrt(s_boot^2 + u_sys^2)
R       = observed / reported_in_footprint
R_lo    = R * exp(-1.96 * s_total)
R_hi    = R * exp(+1.96 * s_total)

higher than reported   if R_lo > 1.25 in two separate periods
lower than reported    if R_hi < 0.80 in two separate periods
consistent             otherwise, when all gates pass
inconclusive           if any gate fails
unpaired               if there is no reported value for the period yet
```

With s_total near 0.36 the interval spans a factor of about 2 either way, so a site is only flagged "higher" when the satellite estimate is roughly 2.5 times the reported figure. If validation brings the scatter down to 0.25, the bar drops to about 2 times. Tightening the uncertainty is what makes the product sharper, and it is the best use of your time after launch.

Confidence grade: A when all gates pass, there are 80 or more days and there are no flags. B when it passes with one flag or with 40 to 79 days. C for clusters.

Leaderboard order: sort by R_lo, the most cautious reading of the gap, not by R.

### 4.9 Validation plan

| Step | What | Pass mark |
|---|---|---|
| V0 Synthetic | Plumes with a known emission, noise, cloud gaps and wrong winds (Appendix A). Done for this plan, rerun it as your first unit test. | Recovers 20,000 t/yr within 5%, 4,000 within 10%. Rejects empty sites. |
| V1 US, like for like | 30 to 40 isolated power plants, 2023 and 2024. Compare with monitor NOx averaged over the 3 hours before each overpass, on the same days. | Mean bias within 20%, correlation above 0.7. For reference, Beirle et al. got a ratio of 0.78 and r of 0.64 for 41 US plants. |
| V2 US, annual | Same estimates against the full calendar-year monitor totals. This includes the time sampling error. | Use this scatter as u_sys in 4.8. |
| V3 Null sites | Run the pipeline at 20 places with no source within 60 km. | No site passes the gates. |
| V4 Sensitivity | Rerun with the other wind level, a narrower and wider fan, and 4 instead of 6 hours. | Estimates move less than 15%. |
| V5 Europe sanity | Rank correlation between your estimates and reported values. Compare a few sites with published numbers. | Same ordering for the biggest sources. |

### 4.10 Limitations to state openly

- One look a day at about 13:30. Plants that ramp down at midday look smaller than their daily average.
- Clear, windy, spring to autumn days only.
- NO takes minutes to become NO2, so the first few kilometres of the plume are under-counted. The blur term absorbs part of this.
- One average correction for satellite sensitivity instead of a per-pixel one.
- Wind comes from a 28 km reanalysis grid.
- Clusters cannot be split into facilities.
- Reported values follow facility boundaries drawn on paper. The satellite follows air.

### 4.11 Questions you should be able to answer

| Question | Short answer |
|---|---|
| Why not use machine learning to find plumes? | There is no labelled data, and a physical model gives a number with units and an uncertainty. A classifier would be a good later add-on for single-day detection. |
| How do you know the plume belongs to that plant? | The curve has to start at the plant after rotation (t0 near 0), the lifetime has to be physical, and there must be no comparable source nearby. I tested the failure case with a synthetic neighbour. |
| Why is your number different from the reported one? | Different quantities. Mine is a midday, clear-sky, footprint estimate with about 40% uncertainty. Theirs is an annual stack total. I only call it a gap beyond 2.5 times. |
| What is the biggest weakness? | The single air mass factor correction, followed by wind. Both are checked against US stack monitors. |
| Why bootstrap over days? | Days are the independent samples. Resampling them shows how much the answer depends on which days happened to be clear. |
| Why DuckDB and static files? | The data is small and read-only. Files on a CDN are faster and free, and DuckDB gives SQL without a server. |
| What would you do with more time? | Recompute the air mass factor from the original orbit files, use hourly generation data to correct for midday output, and add Sentinel-4 for hourly coverage over Europe. |

---

## 5. Repo structure

```
orbyt-earth/
  PLAN.md                     this file
  README.md                   what it is, screenshot, live link, how to run
  METHODS.md                  the method with every constant and its source
  DATA_LICENSES.md            each data source, licence, required attribution
  CORRECTIONS.md              log of corrections, newest first
  AGENTS.md                   rules for AI coding assistants (section 8.4)
  LICENSE                     MIT, covers the code only
  Makefile                    setup, test, pipeline, publish, dev

  pipeline/
    pyproject.toml            uv project, pinned versions
    orbyt/
      cli.py                  Typer entry point: orbyt <command>
      core/
        contracts.py          Finding, Claimed, Observed, Layer (Pydantic)
        module.py             Module protocol and registry
        verdict.py            ratio, interval and verdict rules (4.8)
        publish.py            write JSON, validate against schemas, manifest
        geo.py                distances, footprints, isolation scoring
        store.py              Parquet and DuckDB helpers
      sources/
        gee.py                Earth Engine session, patch download, monthly means
        era5.py               wind at overpass time
        eea.py                Industrial Reporting database loader
        campd.py              US hourly stack data
        beirle.py             published point source catalogue
        cities.py             populated places for the isolation rule
      modules/
        pollution_hunter/
          config.yaml         thresholds, constants, method version
          candidates.py
          extract.py
          core_math.py        Appendix A, do not edit without the tests passing
          detect.py           single-day plume test (4.4)
          observe.py          runs core_math per subject and window
          compare.py
          validate.py
          layers.py           tiles, plume images, flipbooks
          module.py           implements the Module protocol
        _template/            copy this to start a new module
    tests/
      test_core_math.py       Appendix A synthetic tests
      test_verdict.py
      test_contracts.py
      fixtures/
    notebooks/                exploration only, never imported

  web/
    package.json              pinned: maplibre-gl ^5, deck.gl ^9
    index.html                static hero and poster for instant first paint
    src/
      app/                    shell, routes, providers
      globe/                  map setup, base style, camera choreography
      modules/
        registry.ts
        pollution-hunter/     descriptor, layers, Panel, Legend
      panels/                 VerdictPanel, MethodDrawer, Leaderboard, TimeRail, MobileSheet
      charts/                 GapBar, EstimateSeries, PlumeProfile, Flipbook
      story/                  chapters.json and the scroll driver
      data/                   fetch helpers, generated types
      design/                 tokens.css, fonts, primitives
    scripts/
      make-share-pages.ts     writes /f/<slug>/index.html with meta tags
      make-share-cards.ts     Playwright renders 1200x630 cards
    public/

  schemas/                    JSON Schema exported from contracts.py
  data/                       gitignored
  dist/                       gitignored, built output
  docs/                       diagrams, screenshots, decision log
  .github/workflows/
    ci.yml                    lint, tests, typecheck, build
    pipeline.yml              monthly run (after launch)
```

Conventions:

- Units in names: `column_mol_m2`, `wind_ms`, `half_width_km`, `nox_t_yr`.
- One task from section 6 per pull request.
- Commits are authored by you only. No AI co-author trailers and no AI credit anywhere in the repo.
- Constants live in `config.yaml` with a comment naming their source. No magic numbers in code.
- The code is MIT. The data is not yours to relicense: list every source in `DATA_LICENSES.md` and show attributions on the site.

---

## 6. Milestones

Sizes: S is up to 2 hours, M is about half a day, L is one to two days. Tier: [L] a lighter model can do it from this plan, [T] worth a top model, [H] your own judgement. Every milestone ends with something deployed.

### M0. Skeleton live (week 0)

Demo: a dark globe you can spin on a public URL.

| ID | Task | Size | Tier |
|---|---|---|---|
| M0.1 | Create the public repo `orbyt-earth` with this file, `AGENTS.md` (8.4), MIT licence and the folder skeleton from section 5 | S | L |
| M0.2 | Set up WSL2 Ubuntu, git, uv, Node LTS and pnpm. Clone inside the Linux filesystem. | S | H |
| M0.3 | `web/`: Vite, React, TypeScript, Tailwind v4. Add `tokens.css` and fonts from section 9. | M | L |
| M0.4 | Globe: MapLibre v5 with globe projection, the atmosphere settings from 9.7, a minimal dark style on OpenFreeMap tiles, slow auto-rotation that stops on touch | M | L |
| M0.5 | Connect the repo to Cloudflare Pages. Preview deployments on pull requests. | S | L |
| M0.6 | CI: ruff, pytest, tsc, vite build | S | L |

Exit: the pages.dev URL loads in under 3 seconds on your phone and the globe spins and zooms.

### M1. The globe glows (week 1)

Demo: real satellite NO2 on the globe and Europe's biggest reporters as dots.

| ID | Task | Size | Tier |
|---|---|---|---|
| M1.1 | Register a noncommercial Earth Engine project on the Community tier and authenticate | S | H |
| M1.2 | `sources/gee.py`: 2024 annual mean tropospheric NO2 at 0.1 degrees, downloaded in chunks with `computePixels`, saved as GeoTIFF | M | L |
| M1.3 | `layers.py`: colour with the plume ramp (9.2), cut PNG tiles for zoom 0 to 4 (341 tiles), copy into `web/public/tiles/no2-2024/` | M | L |
| M1.4 | Raster layer on the globe, plus the legend | S | L |
| M1.5 | `sources/eea.py`: download v16, inspect the tables, load to DuckDB, build `facilities` and `reported` for NOx to air. Export the 300 largest 2024 reporters as `findings.json` with reported values only. | M | L |
| M1.6 | Facility markers, click to fly, a first panel showing the reported series and its measured, calculated or estimated flag | M | L |

Exit: a screenshot you would post. Put the link on your CV now.

### M2. First paired numbers and the feasibility gate (week 2)

Demo: reported against a published satellite estimate for dozens of European sources.

| ID | Task | Size | Tier |
|---|---|---|---|
| M2.1 | `sources/beirle.py`: load catalogue v2 and match to EEA facilities by distance, summing reported NOx within 20 km | M | L |
| M2.2 | Notebook: scatter of reported (2018 to 2021 mean) against the catalogue, and a ratio table | M | L |
| M2.3 | Show both numbers in the panel. Label the satellite figure "Beirle et al. 2023, 2018 to 2021". | S | L |
| M2.4 | Run the gate in 1.7 and write the count and decision into `docs/decisions.md` | S | H |
| M2.5 | Leaderboard v0: sortable table page | M | L |

Exit: real paired numbers on the live site, clearly attributed. This already supports the sentence "I built a platform that compares satellite-derived emissions with official registers".

### M3. Your own estimate for one facility (weeks 3 to 4)

Demo: one facility measured end to end by your code, with the plume picture.

| ID | Task | Size | Tier |
|---|---|---|---|
| M3.1 | Copy Appendix A into `core_math.py` and `test_core_math.py`. All five tests pass. | S | L |
| M3.2 | `extract.py` for one subject: list usable overpasses with the server-side filter, download patches, cache as NPZ. Log the EECU cost of one facility-year. | L | L |
| M3.3 | `era5.py`: 100 m wind at the overpass hour for each day | M | L |
| M3.4 | `observe.py`: daily flux densities, estimate, gates, JSON, and a diagnostic figure (stack image, curve, fit) | M | L |
| M3.5 | Review the first real result: does the curve start at zero, is the lifetime sensible, how does the number sit against reported and published values. Adjust gates if needed. | M | T |
| M3.6 | `detect.py` and flipbook: per-day test, export clear-day frames as a sprite sheet | M | L |
| M3.7 | Panel: wind-aligned plume image, curve with fit, flipbook player | M | L |

Exit: the largest reporter that passes the isolation rule has an estimate with an interval from your own pipeline.

### M4. Validation against US stack monitors (weeks 5 to 6)

Demo: a scatter plot of your estimates against measured emissions.

| ID | Task | Size | Tier |
|---|---|---|---|
| M4.1 | `sources/campd.py`: facility list and hourly NOx for chosen plants, 2023 and 2024 | M | L |
| M4.2 | Choose 30 to 40 isolated plants. Start from the US power plants in the Beirle catalogue and drop any near a city. | S | H |
| M4.3 | Run extract and observe for each. Compute the like-for-like and annual comparisons (4.9). | M | L |
| M4.4 | Interpret: bias, scatter, which wind level, whether c stays at 1.61. Fix the constants and write `METHODS.md`. | M | T |
| M4.5 | Null test at 20 empty sites | M | L |
| M4.6 | `/validation` page: scatter with intervals, table view, one paragraph of plain explanation | M | L |

Exit: you can say "across N US plants my estimates correlate at r = X with stack monitors, with a bias of Y%". Put the real numbers on your CV.

### M5. Europe at scale (week 7)

Demo: 25 or more verdicts on the map.

| ID | Task | Size | Tier |
|---|---|---|---|
| M5.1 | `candidates.py`: thresholds, isolation scoring, cluster merging | M | L |
| M5.2 | Batch run for 2023, 2024 and rolling 12-month windows stepped monthly up to the latest data | L | L |
| M5.3 | `compare.py` and `verdict.py` with unit tests on the rules in 4.8 | M | L |
| M5.4 | Review every "higher" flag by hand against the checklist in 7.2 | M | H |
| M5.5 | Export schemas, generate TypeScript types, publish data contract v1 | M | L |

Exit: `findings.json` validates against its schema and has at least 25 European subjects with a verdict.

### M6. Product UI (weeks 8 to 9)

Demo: the real product flow on desktop and phone.

| ID | Task | Size | Tier |
|---|---|---|---|
| M6.1 | VerdictPanel with the two-voice number pair and GapBar (9.6) | M | L |
| M6.2 | Monthly NO2 tiles, July 2022 to latest, zoom 0 to 5, one PMTiles file per month on R2 with the CORS rule | L | L |
| M6.3 | TimeRail: scrub and autoplay with a cross-fade between two raster layers | M | L |
| M6.4 | Leaderboard with filters, sorted by R_lo | M | L |
| M6.5 | Share pages and share cards for every finding | M | L |
| M6.6 | MobileSheet with three snap points, touch targets at least 44 px | M | L |
| M6.7 | MethodDrawer ("How we know") inside the panel, and the `/method` page | M | L |
| M6.8 | `/data` page with downloads and field descriptions | S | L |

Exit: a stranger can open a shared facility link on a phone and understand what they are looking at in 10 seconds.

### M7. Visual polish (week 10)

Demo: the 20 second recording in 9.11.

| ID | Task | Size | Tier |
|---|---|---|---|
| M7.1 | deck.gl overlay: plume layers with additive blending and a soft halo | L | T |
| M7.2 | Black Marble night lights as the low zoom base layer, self-hosted as one PMTiles file | M | L |
| M7.3 | Cinematic intro (9.7), skippable, once per session, respects reduced motion | M | T |
| M7.4 | Scroll story from `chapters.json`: five chapters that fly the same globe | M | L |
| M7.5 | Performance pass against the budgets in 9.10, on a mid-range Android phone | M | L |

Exit: someone who has never seen it says some version of "wait, what is this" inside 3 seconds.

### M8. Trust and launch (week 11)

| ID | Task | Size | Tier |
|---|---|---|---|
| M8.1 | Read every public sentence against the wording rules in 7.2 | M | T |
| M8.2 | Email the operators of any site flagged "higher" with your figures and method, two weeks before launch. Publish replies. | S | H |
| M8.3 | `/corrections`, `/about`, attributions footer, `DATA_LICENSES.md` | S | L |
| M8.4 | Buy the domain, point it at Pages, put R2 behind a subdomain | S | H |
| M8.5 | README with a screenshot, architecture diagram and the validation result | S | L |
| M8.6 | Record the launch clip, write the LinkedIn post in your own voice, post it | S | H |

### After launch

- Monthly pipeline on GitHub Actions.
- Methane layer from IMEO and Carbon Mapper detections.
- Hourly generation data from ENTSO-E to correct for midday output at European power plants (verify API access).
- Module 2: gas flaring.
- Sentinel-4 hourly NO2 over Europe.
- Recompute the air mass factor from original orbit files.

---

## 7. Risks

### 7.1 Risk register

| Risk | How likely | What it costs | Handling |
|---|---|---|---|
| False positive: a facility is flagged because of a neighbour, a city or bad wind | High without gates | Credibility, and legal exposure | Gates in 4.5, footprint accounting, two separate periods before any "higher" verdict, manual review of every flag, null-site test |
| Systematic bias: estimates are off by a constant factor | Medium | Every verdict shifts | US validation sets the constants. Never tune on European data. Publish the validation plot. |
| Nothing to flag: everything comes out consistent | Likely | The "exposé" angle is weaker | Lead with the check, not the accusation. "We checked Europe's 40 largest NOx sources from orbit" is a strong line either way. The unpaired 2025 and 2026 estimates give a forward-looking hook. |
| Too few measurable facilities in Europe | Medium | Thin leaderboard | Gate at M2. Fall back to clusters and add US plants to the public map. |
| Data gaps: cloud, winter, missing overpasses | Certain | Fewer days, wider intervals | Minimum 40 days per window, rolling 12-month windows, show day counts, grey out months with no data on the time rail |
| Sentinel-5P ends | Possible from 2027 | No new data | The source adapter isolates the satellite. Sentinel-5 has been delivering data since late 2025 and Sentinel-4 covers Europe hourly. |
| Earth Engine quota or policy changes | Medium | Extraction stalls | Cache every patch, measure EECU early, keep the Copernicus Data Space route documented |
| Register format changes between versions | Likely | Loader breaks | Pin the version in config, keep a fixture test, inspect tables before each upgrade |
| Free tier limits | Low | Site or tiles unavailable | Static files only. Pages has no bandwidth cap. Keep tiles under 10 GB on R2. |
| Legal: an operator objects to being named | Low, but serious | Stress, takedown demand | Section 7.2 |
| Licence breach on third-party data | Low | Takedown | Section 7.3 |
| AI-written code uses an API that no longer exists | High | Lost evenings | Pinned versions, `AGENTS.md`, tests first, one task per session |
| Scope creep | High | No launch | The MVP list in section 0 is the definition of done. Everything else goes under "After launch". |
| Phone performance | Medium | Bad first impression | Poster first, lazy deck.gl, budgets in 9.10, test on a real mid-range phone |

### 7.2 Naming companies: wording rules

I am not a lawyer and this is not legal advice. Before launch, ask someone who is: your college, or a free legal advice clinic. Context you should know: Ireland's Defamation (Amendment) Act 2026 took effect for the most part on 1 March 2026. Companies now have to show serious harm, meaning serious financial loss, to sue. The anti-SLAPP part of the Act had not been commenced as of early November 2026. Operators abroad can also act under their own country's law. None of this makes careless claims safe. Accuracy, fairness and transparency are what protect you.

Rules for every public sentence:

1. State two facts and a caveat, never a conclusion about conduct. Reported value with source and year. Your estimate with its interval. What could explain a difference.
2. Fixed verdict labels only: "Higher than reported", "Consistent with reported", "Lower than reported", "Inconclusive".
3. Banned words about any named operator: lying, hiding, cheating, fraud, illegal, caught, exposed, thieves, cover-up. Also banned: any claim about permits or compliance.
4. Say "satellite-based estimate", never "actual emissions". The interval appears wherever the number appears.
5. Name facilities and operators exactly as the register does. Never name individuals.
6. Every figure links to its method, data version and the date it was computed.
7. Offer a right of reply before publishing any "higher" verdict, and publish what you get back.
8. Keep a public corrections log and fix errors fast. Put a contact address on every page.
9. A standing line in the footer: "Orbyt Earth is an independent student research project. Estimates are uncertain and are not findings of non-compliance."

Template for a flagged site:

> For 2024, [operator] reported 4,200 t of NOx for [facility] to the EU register (basis: measured). Our satellite-based estimate for the area within 20 km of the site is 11,500 t (95% interval 5,700 to 23,200), based on 88 clear days. One other reporting facility lies inside that area and is included in the reported total. Differences can come from sources that do not report, from the satellite seeing midday rather than average output, and from uncertainty in our method. This is an estimate, not a finding of non-compliance. [Operator] was contacted on [date]. Their reply: [reply or "no reply yet"].

Review checklist before any "higher" verdict goes live:

- All gates pass in two separate periods.
- You have looked at the stacked image yourself and the plume starts at the site.
- You have checked satellite imagery and the map for unlisted sources within 30 km: towns, motorways, ports, other industry.
- The reported total includes every register facility in the footprint.
- The site is not coastal or mountainous, or the flag is shown.
- The reported value is not a known data error. Compare with the previous and next year.

### 7.3 Data licences and attribution

| Source | What to do |
|---|---|
| Copernicus Sentinel-5P | Free and open. Credit "Contains modified Copernicus Sentinel data [year]". |
| ERA5 | Credit the Copernicus Climate Change Service. |
| EEA Industrial Reporting database | Reuse with attribution (verify the exact wording on the dataset page). |
| EPA CAMPD | US government data, credit EPA. |
| Beirle et al. catalogue, Climate TRACE | CC BY 4.0. Cite them. |
| OpenFreeMap and OpenStreetMap | Show "OpenStreetMap contributors" and OpenMapTiles attribution on the map. |
| NASA Black Marble via GIBS | Free and open. NASA asks for an acknowledgement. |
| Sentinel-2 cloudless by EOX | Only the 2016 edition is CC BY 4.0. Later editions are non-commercial. |
| Carbon Mapper | Non-commercial and share-alike. Display with attribution, do not rehost bulk data, do not mix into your MIT-licensed downloads. |
| IMEO Eye on Methane | Open. Read and follow the terms of use. |

---

## 8. What needs a top model

### 8.1 Already settled in this plan

These were the parts most likely to go wrong with a lighter model, so they are done here and you should not reopen them without a reason:

- Pollutant, region, years and data sources, checked against live documentation.
- The method, including the travel-time stacking decision, the gates and the verdict rules.
- The core numerics, written and tested on synthetic plumes (Appendix A).
- The architecture and data contract.
- The design system, with colours checked for contrast and colour-blind separation.

### 8.2 Split by kind of work

| Work | Tier | Why |
|---|---|---|
| Repo scaffolding, CI, deploy config | Lighter | Standard patterns |
| Data loaders: EEA, CAMPD, Beirle | Lighter | Tabular work with clear inputs and outputs. Have the model inspect real files first. |
| Earth Engine extraction | Lighter, with care | Give it the sketch in 4.3 and the documentation link. Test on one facility before any batch. |
| Wiring `core_math.py` into `observe.py` | Lighter | The math exists. Do not let the model rewrite it. |
| Changing anything inside `core_math.py` | Top | Small numerical changes cause silent bias. The synthetic tests must pass after any edit. |
| Reading the first real results and the US validation | Top | Needs scientific judgement: why is it biased, which constant is responsible, is the fit trustworthy |
| Verdict logic and its tests | Lighter | Rules are written out in 4.8 |
| React components from the design system | Lighter | Tokens and specs are in section 9 |
| Tiles, PMTiles, R2 upload | Lighter | Documented tooling |
| deck.gl glow layer and any shader | Top | Blending and shader work is easy to get almost right |
| Intro choreography and motion timing | Top for the first pass, lighter for tweaks | Taste and timing |
| Share cards, leaderboard, forms, docs | Lighter | |
| Review of every public sentence and every flagged finding before launch | Top, then a human | The cost of a mistake is highest here |

### 8.3 Three sessions worth saving top-model access for

1. After M4.3. Paste the validation table and three diagnostic figures. Ask: is the bias a wind problem or a correction-factor problem, which constants should change, and what should `METHODS.md` say.
2. M7. Build the deck.gl plume layer and the intro in one sitting, with screenshots of the current state.
3. Before launch. Paste every finding marked "higher" with its evidence, and all site copy. Ask it to attack each claim and to check the wording against 7.2.

### 8.4 AGENTS.md (copy into the repo)

```
# Rules for AI coding assistants in this repo

1. Read PLAN.md before any task. Work on one task ID from section 6 at a time.
2. Never add AI attribution: no Co-Authored-By trailers, no "generated with" lines,
   no AI names in commits, pull requests, README, comments or docs. Commits are authored by Badr only.
3. Never use em dashes in docs, UI copy or comments.
4. Pinned stack: Python 3.12, maplibre-gl ^5 (not 6), deck.gl ^9 via MapboxOverlay, React, Vite,
   Tailwind 4. Do not upgrade a major version without being asked.
5. Static only. No server code, no API routes, no database connections in web/.
6. Never invent data. No placeholder numbers in anything under dist/. Fixtures live in tests/ only.
7. pipeline/orbyt/modules/pollution_hunter/core_math.py changes only when the task says so,
   and tests/test_core_math.py must pass afterwards.
8. Constants live in config.yaml with their source. Units go in variable names.
9. UI text follows PLAN.md section 9.9. Verdict labels are fixed strings.
10. If you are unsure an API exists in the pinned version, say so and link the docs. Do not guess.
11. Write or update a test with every pipeline change.
```

### 8.5 Task prompt template for lighter models

```
Task: <ID and title from PLAN.md section 6>
Read first: PLAN.md sections <numbers>, AGENTS.md, and these files: <paths>
Change only: <paths>
Inputs: <files, schemas, example rows>
Output: <files to create or edit>, with tests
Done when: <the exit line from the task, plus "CI passes">
If something in the plan looks wrong or an API is uncertain, stop and tell me before writing code.
```

---

## 9. Design system

### 9.1 Concept: the record and the instrument

Every module compares two things, so the whole interface speaks in two voices.

- The record is what was reported or promised. It is set in a serif, in a warm paper tone, and always carries its year and source. It should feel like a line from a filed document.
- The instrument is what the satellite measured. It is set in a wide sans, in the module's glowing signal colour, and always carries its interval. It should feel like a readout.

Wherever a reader sees the serif, they are reading a claim. Wherever they see the glow, they are reading a measurement. This holds for every future module, and it means the comparison is never carried by colour alone.

Everything else stays quiet. Space is true black. Panels are dark glass with a hairline edge. There are no gradients on the interface, no card grids, no drop shadows and no capitalised labels. The two loud things are the plumes and the number pair.

Principles:

1. The globe is the page. Interface floats at the edges and never covers the centre.
2. Black is black. `#000000` for space, so the Earth floats and OLED phones look their best.
3. Nothing moves unless the data or the user moved it. One exception: the intro.
4. Every number shows its uncertainty and its source one tap away.

### 9.2 Colour

Surfaces and text (contrast measured against the panel colour):

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--void` | `#000000` | Page and space | |
| `--panel` | `rgba(13, 18, 24, 0.84)` with a 20 px backdrop blur. Solid fallback `#0D1218`. | Side panel, sheets, time rail | |
| `--raised` | `#161D26` | Hovered rows, inputs | |
| `--hairline` | `rgba(255, 255, 255, 0.10)` | Panel edges, dividers | |
| `--text` | `#F2F4F7` | Primary text | 17.1 |
| `--text-2` | `#AAB2BD` | Secondary text | 8.8 |
| `--text-3` | `#7D8794` | Small labels, axis text | 5.2 |
| `--ledger` | `#E9E1D0` | The record voice: reported numbers and their sources | 14.5 |
| `--focus` | `#7CC4FF` | 2 px focus ring with 2 px offset | 10.0 |

Night-side Earth (basemap style): ocean `#04070B`, land `#0C1219`, borders `#2A3440`, place labels `#8A94A3`. A thin blue atmosphere at the limb. Night lights at low zoom.

Module hues. Each module owns one hue with two steps: a mark step for chart marks, chips and markers, and a glow step for map layers and large numerals. The order is fixed.

| Slot | Module | Mark | Glow |
|---|---|---|---|
| 1 | Pollution Hunter (NO2) | `#C98500` | `#FFB02E` |
| 2 | Ghost developments | `#D55181` | `#FEACC4` |
| 3 | Deforestation | `#008300` | `#80E379` |
| 4 | Methane | `#9085E9` | `#C3BFFE` |
| 5 | Flaring | `#D95926` | `#FFB297` |
| 6 | Irrigation ban watch | `#199E70` | `#2EE9A7` |

The mark steps were run through a palette validator on the panel colour. In this order every neighbouring pair is distinguishable for red-green colour blindness and each has at least 3:1 contrast. Not every non-neighbouring pair is, so a module chip always shows an icon and a name next to its colour. Amber was chosen for NO2 because the gas itself is amber-brown: it absorbs blue light, which is how the satellite detects it.

NO2 plume ramp, low to high. One warm family, lightness rising at every step so it reads correctly in greyscale and for colour-blind viewers:

| Position | Colour | Opacity |
|---|---|---|
| 0.00 | `#4F1C00` | 0 |
| 0.15 | `#7D3501` | 0.35 |
| 0.35 | `#AF5504` | 0.60 |
| 0.55 | `#D97A05` | 0.80 |
| 0.75 | `#F5A420` | 0.90 |
| 0.90 | `#FCD583` | 0.95 |
| 1.00 | `#FDF6D8` | 1 |

Map the global layer on a square-root scale from 20 to 250 micromol/m2. In facility view, show enhancement above background from 0 to 100. Other modules get the same construction in their own hue.

The gap (diverging pair, used by the GapBar and verdict icons only):

| Meaning | Colour | Icon |
|---|---|---|
| Satellite higher than reported | `#E66767` | Arrow up |
| Consistent | `#8A94A3` | Equals |
| Satellite lower than reported | `#3987E5` | Arrow down |
| Inconclusive | Dashed outline in `--text-3` | Question mark |

Red and amber sit close together for colour-blind viewers, so a verdict is never shown as colour alone: icon and label always.

### 9.3 Typography

Two families with fixed jobs.

| Family | Voice | Licence |
|---|---|---|
| Mona Sans, variable, weight 200 to 900, width 75 to 125 | The instrument and the interface | Open source (verify the licence file in the GitHub repo). Fallback: Archivo, which also has a width axis. |
| Source Serif 4, variable | The record | Open Font License |

Width follows altitude. Wide type for statements made from orbit, normal for reading, narrow for dense ground-level data.

| Role | Family and settings | Size / line height |
|---|---|---|
| Hero line, record half | Source Serif 4, 400 | 72 / 76 desktop, 40 / 44 phone |
| Hero line, instrument half | Mona Sans, width 125, weight 600, tracking -0.02em | Same |
| Page title | Mona Sans, width 110, weight 600 | 36 / 40 |
| Section title | Mona Sans, width 100, weight 600 | 24 / 30 |
| Body | Mona Sans, width 100, weight 400 | 16 / 24 |
| Small | Mona Sans, width 100, weight 400 | 14 / 20 |
| Table and axis | Mona Sans, width 85, weight 500, tabular figures | 12 / 16 |
| Observed number | Mona Sans, width 112, weight 600, tabular figures, glow colour | 48 / 48 |
| Reported number | Source Serif 4, 400, lining tabular figures, ledger colour | 48 / 48 |
| Source line under a reported number | Source Serif 4, 400 | 14 / 20 |

Scale: 12, 14, 16, 18, 21, 24, 36, 48, 72. Story text is at most 68 characters wide. Sentence case everywhere. No all-capitals labels, no monospace. Self-host both fonts as WOFF2 with `font-display: swap`.

### 9.4 Space, shape, depth

- Spacing steps: 4, 8, 12, 16, 24, 32, 48, 64, 96 px.
- Radius: 2 px for bars and chips, 10 px for panels, full for markers.
- One kind of depth: the glass panel (blur plus hairline). No shadows.
- Panel width 420 px on desktop. Outer margin 24 px, 12 px on phones.

### 9.5 Layout

Desktop, explore view (all numbers are placeholders):

```
+----------------------------------------------------------------------------------+
| Orbyt Earth                                               ( Pollution Hunter v ) |
|                                                                                  |
|                                                    +---------------------------+ |
|                 .  -  ~  ~  -  .                   | Facility name             | |
|             .'   night-side Earth  '.              | Operator, country         | |
|            /    with glowing plumes   \            |                           | |
|           |                            |           | Reported 2024   Satellite | |
|           |              *             |           | 12,300 t        14,100 t  | |
|            \                          /            | EEA v16,        7,000 to  | |
|             '.                      .'             | measured        28,500    | |
|                ' -  .  _  _  .  - '                | [----|=o=====|--]  1.1x   | |
|                                                    | = Consistent      Grade A | |
|  Leaderboard   Story   Method                      | (plume) (curve) (flipbook)| |
|                                                    | How we know     Sources   | |
|  2022 |------|------|------o------|------| 2026 >  +---------------------------+ |
+----------------------------------------------------------------------------------+
```

Phone:

```
+------------------------+
| Orbyt Earth     (NO2 v)|
|                        |
|        (globe)         |
|                        |
| 2022 |-----o-----| 2026|
+------------------------+
|          ----          |  sheet: peek 96 px, half, full
| Facility name          |
| Reported     Satellite |
| 12,300 t     14,100 t  |
| [---|=o===|--]   1.1x  |
+------------------------+
```

Story view: text column 440 px wide on the left over the globe, one chapter per screen height. The globe flies when a chapter crosses the middle of the screen. On phones the text sits in the bottom third.

Text is left aligned everywhere. Only the hero is centred.

### 9.6 Components

| Component | Spec |
|---|---|
| GlobeCanvas | Full bleed. Star field as a CSS background behind the map (verify the area around the globe is transparent). Auto-rotates at 2 degrees per second until first touch. |
| PlumeLayer | M1: pre-coloured raster tiles. M6: monthly PMTiles with a 400 ms cross-fade between two layers. M7: deck.gl with additive blending, plus a blurred copy underneath at 40% opacity as the halo. |
| FacilityMarker | Circle, radius from the square root of reported tonnes (4 to 18 px), 1.5 px stroke in the verdict colour, fill `--panel`. Selected: a single expanding ring, 1.6 s loop. Minimum touch target 44 px. |
| VerdictPanel | Top: name, operator, sector, country. Then the number pair side by side: reported on the left in the record voice with source and basis underneath, satellite on the right in the instrument voice with its interval underneath. Then GapBar, verdict with icon, grade. Then evidence tabs: plume image, curve, flipbook. Then "How we know" and sources. |
| GapBar | Horizontal log axis from 0.25x to 4x with ticks at 0.5, 1 and 2. Shaded neutral band from 0.8 to 1.25. A dot at the ratio and a whisker for the 95% interval. Coloured only when the whole whisker clears the band. Text beside it: "1.1x reported (0.6 to 2.3)". |
| EstimateSeries | Rolling 12-month satellite estimates as a 2 px line with a 20% opacity interval band, reported annual values as steps in the ledger colour. One y axis, starting at zero. Legend above, hover crosshair with a tooltip, toggle to a table. |
| PlumeProfile | The stacked curve F(t) as dots and the EMG fit as a line. Vertical rule at t = 0 labelled "source". Annotations for the two things the fit yields: emission and lifetime. |
| Flipbook | Clear-day frames from a sprite sheet with date, wind arrow and a detected or not mark. Play, pause, scrub. |
| TimeRail | Month scrubber from July 2022. Tick per month, label per year. Months without data are hatched. Play button advances 2 months a second. Arrow keys step. |
| Leaderboard | Table: rank, name, country, reported, satellite, ratio with mini GapBar, verdict, grade. Default sort is the cautious lower bound of the ratio. Filters for country, sector, verdict. Rows are links. |
| ModuleSwitcher | Chips with icon, name and hue dot. Future modules appear greyed with "soon". |
| Legend | Colour ramp with three labelled values and units, and one line: "Monthly mean NO2 in the lower atmosphere". |
| MethodDrawer | Five steps with small diagrams built from this facility's own data. A sequence, so it is numbered. |
| ConfidenceBadge | A, B or C with a tooltip listing which gates passed and which flags apply. |
| ShareCard | 1200 x 630. Black, the facility's plume image on the right, the number pair on the left, verdict, URL. Rendered by Playwright from a hidden route. |
| MobileSheet | Three snap points, drag handle, the globe stays interactive above it. |
| States | Loading: skeleton lines in `--raised`, no spinners. Empty: say what to do ("Pick a facility on the globe"). Error: say what failed and how to retry. |
| Footer | Attributions, the standing disclaimer, link to corrections. |

### 9.7 Motion and the intro

MapLibre globe and atmosphere, to check against the official "globe with an atmosphere" example:

```js
map.on("style.load", () => map.setProjection({ type: "globe" }));
// in the style JSON
"sky":   { "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7, 0] },
"light": { "anchor": "map", "position": [1.5, 90, 80] }
```

The intro is the one orchestrated moment. About 6 seconds, skippable with any input, shown once per session:

| Time | What happens |
|---|---|
| 0.0 s | Black. The poster image of the globe is already there from the HTML. |
| 0.0 to 0.6 s | Stars fade in. Live map cross-fades over the poster when ready. |
| 0.6 to 3.0 s | Slow rotation. NO2 layer fades in from 0 to full. |
| 1.2 s | Hero line 1 appears in the record voice: "Reported on paper." |
| 2.0 s | Hero line 2 appears in the instrument voice: "Measured from orbit." |
| 3.5 s | Two quiet buttons: "Explore the globe" and "See how it works". |
| On scroll or Explore | Fly to the first story facility: 4.5 s, zoom 7.5, pitch 50. The panel slides in 300 ms before arrival. |

Other motion:

- Fly-to on select: 1.8 to 3.5 s depending on distance, ease-out, pitch 45 on arrival.
- Panel: 240 ms slide and fade. Numbers do not count up.
- Time change: 400 ms cross-fade.
- Reduced motion: no rotation, `jumpTo` instead of `flyTo`, no intro sequence, cross-fades become cuts.

### 9.8 Charts

- One y axis per chart. Never two scales on one chart.
- Thin marks: 2 px lines, dots at least 8 px, 4 px rounded bar ends.
- Text in charts uses the text tokens. Colour belongs to the marks.
- A legend whenever there are two series. Direct labels on the last point.
- Every chart has hover values and a table view.
- Grid lines in `--hairline`. Axis text in `--text-3`.

### 9.9 Voice and copy

- Plain verbs, sentence case, no hype. The site describes. It does not accuse.
- Labels: "Reported", "Satellite estimate", "Gap", "How we know", "Sources".
- Buttons say what they do: "Explore the globe", "Download the data", "Copy link".
- Numbers: tonnes with thousands separators and no decimals, ratios with one decimal and a multiplication sign, intervals as "7,000 to 28,500".
- Verdict strings are fixed (7.2).
- Tagline: "Fact-checking the world from space."
- Explainer line under the hero: "We compare what facilities report with what satellites measure, and show our working."

### 9.10 Accessibility and performance budgets

- Text contrast at least 4.5:1, which every token in 9.2 meets on the panel.
- Full keyboard path: tab through markers in leaderboard order, Enter opens the panel, Escape closes it, arrow keys move the time rail. Visible focus ring.
- Every finding is also reachable through the leaderboard table, so the site works without the map.
- First paint under 1.5 s on a 4G phone, live globe under 3 s.
- Initial JavaScript under 350 KB compressed. deck.gl loads later.
- Device pixel ratio capped at 2. Pause rendering when the tab is hidden.
- 50 frames per second or better while flying on a mid-range Android phone. If not, drop the halo layer first.

### 9.11 The 20 second recording

| Seconds | Shot |
|---|---|
| 0 to 3 | The night globe turning, plumes glowing, the two hero lines |
| 3 to 8 | One scroll. The camera dives to a plume in Europe. |
| 8 to 13 | The panel slides in. Reported number, satellite number, gap bar. Flipbook plays the plume swinging with the wind. |
| 13 to 17 | Drag the time rail. The plumes breathe through four years. |
| 17 to 20 | Leaderboard, then the URL |

Record at 1080 x 1350 for LinkedIn, 60 frames per second, with the cursor visible.

---

## Appendix A: reference implementation (tested)

This is the numerical core of Pollution Hunter. It was written for this plan and run against synthetic plumes with a known emission, added noise, cloud gaps, a neighbouring source and deliberately wrong winds. It needs only NumPy and SciPy. The noise levels in the generator are assumptions, so real data will be harder. Treat these results as proof that the math is right, not as proof of real-world accuracy. That is what milestone 4 is for.

Results, 12 random runs per row, 120 valid days unless stated:

| Scenario | Estimate / truth (mean) | Spread (sd) | Runs passing all gates |
|---|---|---|---|
| 20,000 t/yr source with a 5,000 t/yr neighbour 44 km away | 1.02 | 0.02 | 12 of 12 |
| 4,000 t/yr source | 1.05 | 0.07 | 12 of 12 |
| 2,000 t/yr source | 1.11 | 0.15 | 4 of 12 |
| 1,000 t/yr source | 1.50 | 0.81 | 0 of 12 |
| 20,000 t/yr, wind wrong by 25 degrees and 25% | 1.05 | 0.04 | 12 of 12 |
| 20,000 t/yr, only 60 days | 1.03 | 0.04 | 12 of 12 |
| 20,000 t/yr, true lifetime 2 h | 1.01 | 0.03 | 12 of 12 |
| 20,000 t/yr, true lifetime 6 h | 1.03 | 0.02 | 12 of 12 |
| Empty site, noise only | median 950 t/yr reported by the fit | | 0 of 12 |
| Empty site, 5,000 t/yr neighbour | median 1,040 t/yr | | 0 of 12 |
| Empty site, 20,000 t/yr neighbour | median 3,790 t/yr | | 0 of 12 |

What this shows:

- The floor is between 2,000 and 4,000 t/yr, which matches the published detection limit of about 3,500.
- Without gates, an empty site next to a big neighbour would be published as a 3,800 t/yr source. The gates stop it.
- For comparison, the classic distance-domain stack with the mean wind speed gave 1.31 on the first row. Travel-time stacking with the widening fan is what brings it to 1.02.

`pipeline/orbyt/modules/pollution_hunter/core_math.py`

```python
"""Orbyt Earth, Pollution Hunter: core plume math (reference implementation).

Units: columns in mol/m2, distances in km, wind in m/s, time in hours.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import curve_fit
from scipy.special import ndtr  # standard normal CDF

M_NO2 = 0.0460055                 # kg per mol
SEC_PER_YEAR = 365.25 * 24 * 3600
EARTH_R_KM = 6371.0088


def rotate_scene(field, lats, lons, lat0, lon0, u, v, xr, yr):
    """Resample one daily scene onto a wind-aligned grid centred on the source.

    field: 2D array [lat, lon], NaN = no data. lats and lons are ascending 1D arrays.
    u, v: wind components in m/s (the direction the wind blows TO).
    xr: 1D downwind distances in km (negative = upwind). yr: 1D crosswind km.
    Returns an array shaped [len(yr), len(xr)].
    """
    theta = np.arctan2(v, u)
    c, s = np.cos(theta), np.sin(theta)
    XR, YR = np.meshgrid(xr, yr)
    east, north = c * XR - s * YR, s * XR + c * YR      # back to east/north offsets
    lat = lat0 + np.degrees(north / EARTH_R_KM)
    lon = lon0 + np.degrees(east / (EARTH_R_KM * np.cos(np.radians(lat0))))
    interp = RegularGridInterpolator((lats, lons), field, method="linear",
                                     bounds_error=False, fill_value=np.nan)
    return interp(np.stack([lat.ravel(), lon.ravel()], axis=-1)).reshape(XR.shape)


def daily_flux_density(field, lats, lons, lat0, lon0, u, v, t_hours, yr,
                       upwind_km=(-70.0, -20.0)):
    """One day's plume on a travel-time axis, as flux density in mol per m per s.

    Step 1: subtract that day's background (median of an upwind box).
    Step 2: sample the scene at downwind distance x = wind * t, so every day
            shares one clock whatever its wind speed.
    Step 3: multiply by wind speed (column * speed = flux through a 1 m wide gate).
    """
    speed = float(np.hypot(u, v))
    up = rotate_scene(field, lats, lons, lat0, lon0, u, v,
                      np.arange(upwind_km[0], upwind_km[1] + 1, 2.0), yr)
    if np.isfinite(up).mean() < 0.3:
        return np.full((len(yr), len(t_hours)), np.nan)
    x_at_t = speed * np.asarray(t_hours) * 3.6               # km travelled after t hours
    scene = rotate_scene(field, lats, lons, lat0, lon0, u, v, x_at_t, yr)
    return (scene - np.nanmedian(up)) * speed


def fan_half_width(t_hours, mean_wind_ms, base_km=20.0, growth=0.3, cap_km=76.0):
    """Crosswind half-width that widens downwind, so wind-direction error loses no mass.

    20 km at the source plus 0.3 km per km travelled (at the mean wind), capped.
    """
    return np.clip(base_km + growth * np.abs(mean_wind_ms * np.asarray(t_hours) * 3.6),
                   base_km, cap_km)


def stack_profile(daily, yr, half_width_km, min_days_frac=0.3, min_cover=0.8):
    """Average days cell by cell, then integrate across the wind.

    daily: [n_days, len(yr), n_x]. half_width_km: scalar or one value per column.
    Returns a 1D profile (input units times metres).
    """
    hw = np.broadcast_to(np.asarray(half_width_km, dtype=float), (daily.shape[2],))
    inside = np.abs(yr)[:, None] <= hw[None, :]
    n_in = inside.sum(axis=0)
    dy_m = (yr[1] - yr[0]) * 1000.0
    with warnings.catch_warnings():                    # all-NaN cells are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        cover = np.isfinite(daily).mean(axis=0)
        mean = np.where(cover >= min_days_frac, np.nanmean(daily, axis=0), np.nan)
        band = np.where(inside, mean, np.nan)
        prof = np.nanmean(band, axis=0) * n_in * dy_m  # mean of valid cells times full width
    prof[np.isfinite(band).sum(axis=0) / n_in < min_cover] = np.nan
    return prof


def emg(t, q, tau, sigma, t0, b):
    """Exponentially modified Gaussian: an exponential decay blurred by a Gaussian.

    q: value at the source before blurring. tau: e-folding scale. sigma: blur.
    t0: source offset. b: residual background. In the flux form q is the emission.
    """
    z = t - t0
    return q * np.exp(sigma**2 / (2 * tau**2) - z / tau) * ndtr(z / sigma - sigma / tau) + b


def fit_emg(t, y, tau_bounds=(0.5, 12.0), sigma_bounds=(0.05, 3.0), t0_bounds=(-1.5, 1.5)):
    """Least-squares EMG fit. Returns a dict of parameters, or None if it fails."""
    ok = np.isfinite(y)
    if ok.sum() < 12:
        return None
    t, y = t[ok], y[ok]
    q0 = max(float(np.max(y)), 1e-9)
    p0 = [q0, float(np.mean(tau_bounds)) / 2, float(np.mean(sigma_bounds)) / 2, 0.0, 0.0]
    lo = [0.0, tau_bounds[0], sigma_bounds[0], t0_bounds[0], -q0]
    hi = [10 * q0, tau_bounds[1], sigma_bounds[1], t0_bounds[1], q0]
    try:
        p, _ = curve_fit(emg, t, y, p0=p0, bounds=(lo, hi), maxfev=20000)
    except (RuntimeError, ValueError):
        return None
    resid = y - emg(t, *p)
    r2 = 1 - float(np.sum(resid**2) / np.sum((y - y.mean())**2))
    return dict(q=float(p[0]), tau=float(p[1]), sigma=float(p[2]), t0=float(p[3]),
                b=float(p[4]), r2=r2)


def nox_tonnes_per_year(q_no2_mol_s, nox_to_no2=1.38, amf_correction=1.0):
    """NO2 flux in mol/s to NOx in tonnes per year, expressed as NO2 mass."""
    return q_no2_mol_s * M_NO2 * nox_to_no2 * amf_correction * SEC_PER_YEAR / 1000.0


def estimate_emission(daily_flux, t_hours, yr, wind_speeds, n_boot=200, seed=0, **conv):
    """Stack daily flux densities, fit the EMG, bootstrap over days for a 95% interval.

    daily_flux: [n_days, len(yr), len(t_hours)] from daily_flux_density().
    wind_speeds: one speed per day (m/s), used only to size the integration fan.
    conv: nox_to_no2 and amf_correction passed to nox_tonnes_per_year().
    The interval covers sampling noise only. Systematic terms are added later.
    """
    rng = np.random.default_rng(seed)
    n = daily_flux.shape[0]
    hw = fan_half_width(t_hours, float(np.mean(wind_speeds)))
    best = fit_emg(t_hours, stack_profile(daily_flux, yr, hw))
    if best is None:
        return None
    boots = []
    for _ in range(n_boot):
        f = fit_emg(t_hours, stack_profile(daily_flux[rng.integers(0, n, n)], yr, hw))
        if f is not None:
            boots.append(nox_tonnes_per_year(f["q"], **conv))
    lo, hi = np.percentile(boots, [2.5, 97.5]) if len(boots) >= 50 else (np.nan, np.nan)
    return dict(best, nox_t_yr=nox_tonnes_per_year(best["q"], **conv),
                ci95=(float(lo), float(hi)), n_days=n, n_boot_ok=len(boots))


def failed_gates(est, min_days=40):
    """Names of the quality gates an estimate fails. Empty list means usable."""
    if est is None:
        return ["no_fit"]
    fails = []
    if est["n_days"] < min_days:
        fails.append("too_few_days")
    if est["r2"] < 0.85:
        fails.append("poor_fit")
    if abs(est["t0"]) > 0.5:                 # plume does not start at this site
        fails.append("source_offset")
    if not 1.0 <= est["tau"] <= 8.0:
        fails.append("lifetime_out_of_range")
    lo, hi = est["ci95"]
    if np.isfinite(lo) and est["nox_t_yr"] < 3.0 * (hi - lo) / 3.92:
        fails.append("low_signal_to_noise")
    return fails
```

`pipeline/tests/test_core_math.py` (five tests, about 20 seconds)

```python
"""Synthetic end-to-end tests: can the pipeline recover a known emission,
and does it refuse to report one where there is none?"""
import warnings

import numpy as np
from scipy.ndimage import gaussian_filter

from core_math import (EARTH_R_KM, M_NO2, SEC_PER_YEAR, daily_flux_density,
                       estimate_emission, failed_gates)

LAT0, LON0 = 51.27, 19.33
YR = np.arange(-80.0, 80.1, 2.0)          # crosswind grid, km
T = np.arange(-2.0, 6.01, 0.1)            # travel-time grid, hours


def mol_s(nox_t_yr):
    """NOx tonnes per year (as NO2) to NO2 mol/s, the inverse of the pipeline's conversion."""
    return nox_t_yr * 1000.0 / SEC_PER_YEAR / M_NO2 / 1.38


def make_days(n_days, centre_t_yr, neighbour_t_yr, tau_h=3.5, seed=0, dir_err_deg=15.0,
              spd_err=0.15, noise=10e-6, cloud_frac=0.3):
    """Daily scenes: decaying Gaussian plumes, noise, cloud gaps, imperfect wind."""
    rng = np.random.default_rng(seed)
    lats = np.arange(LAT0 - 2.4, LAT0 + 2.4001, 0.03)
    lons = np.arange(LON0 - 3.8, LON0 + 3.8001, 0.03)
    LON, LAT = np.meshgrid(lons, lats)
    X = np.radians(LON - LON0) * EARTH_R_KM * np.cos(np.radians(LAT0))
    Y = np.radians(LAT - LAT0) * EARTH_R_KM
    days = []
    while len(days) < n_days:
        w = float(np.clip(rng.weibull(2.0) * 6.0, 0.5, 14.0))
        if w < 2.0:                                   # calm days are excluded
            continue
        th = rng.uniform(0, 2 * np.pi)

        def plume(xs, ys, q):
            c, s = np.cos(th), np.sin(th)
            xr = c * (X - xs) + s * (Y - ys)
            yr = -s * (X - xs) + c * (Y - ys)
            sig = np.sqrt(3.0**2 + (0.10 * np.clip(xr, 0, None))**2) * 1000.0
            col = (q / (np.sqrt(2 * np.pi) * sig * w)
                   * np.exp(-(yr * 1000.0)**2 / (2 * sig**2))
                   * np.exp(-np.clip(xr, 0, None) * 1000.0 / (w * tau_h * 3600.0)))
            return np.where(xr > 0, col, 0.0)

        f = plume(0, 0, mol_s(centre_t_yr)) + plume(38.0, 22.0, mol_s(neighbour_t_yr))
        f = gaussian_filter(f, sigma=(2.5 / 3.34, 2.5 / 2.09))   # pixel footprint blur
        f += 30e-6 + rng.normal(0, 8e-6) + 4e-6 * (X / 200.0)    # background + gradient
        f += gaussian_filter(rng.normal(0, noise, f.shape), 1.0) * 2.5
        mask = gaussian_filter(rng.normal(0, 1, f.shape), 8.0)
        f[mask > np.quantile(mask, 1 - cloud_frac)] = np.nan     # cloud gaps
        th_e = th + np.radians(rng.normal(0, dir_err_deg))       # reanalysis wind is not the truth
        w_e = w * (1 + rng.normal(0, spd_err))
        days.append(dict(field=f, u=w_e * np.cos(th_e), v=w_e * np.sin(th_e)))
    return lats, lons, days


def run(centre_t_yr, neighbour_t_yr, seed, n_days=120, n_boot=0, **kw):
    lats, lons, days = make_days(n_days, centre_t_yr, neighbour_t_yr, seed=seed, **kw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        flux = np.array([daily_flux_density(d["field"], lats, lons, LAT0, LON0,
                                            d["u"], d["v"], T, YR) for d in days])
    speeds = [np.hypot(d["u"], d["v"]) for d in days]
    return estimate_emission(flux, T, YR, speeds, n_boot=n_boot)


def test_recovers_large_source():
    ratios = [run(20000.0, 5000.0, s)["nox_t_yr"] / 20000.0 for s in range(4)]
    assert 0.9 < np.mean(ratios) < 1.1


def test_recovers_small_source():
    ratios = [run(4000.0, 1000.0, s)["nox_t_yr"] / 4000.0 for s in range(4)]
    assert 0.8 < np.mean(ratios) < 1.25


def test_large_source_passes_gates():
    assert failed_gates(run(20000.0, 5000.0, 0, n_boot=100)) == []


def test_empty_site_next_to_big_neighbour_is_rejected():
    assert failed_gates(run(0.0, 20000.0, 0, n_boot=100)) != []


def test_pure_noise_is_rejected():
    assert failed_gates(run(0.0, 0.0, 0, n_boot=100)) != []
```

How `observe.py` uses it, in outline:

```python
flux = np.array([
    daily_flux_density(day.field, lats, lons, lat0, lon0, day.u, day.v, T, YR)
    for day in days                       # days already filtered: valid, sunlit, wind >= 2 m/s
])
est = estimate_emission(flux, T, YR, [d.speed for d in days],
                        nox_to_no2=1.38, amf_correction=1.61)
status = failed_gates(est)                # [] means publishable
```

---

## Appendix B: data contract examples

All numbers below are made up to show the shape.

`/data/v1/manifest.json`

```json
{
  "built_at": "2026-12-01T09:30:00Z",
  "data_version": "2026-11",
  "commit": "abc1234",
  "modules": [
    {"id": "pollution-hunter", "title": "Pollution Hunter", "hue": "amber",
     "status": "live", "method_version": "ph-emg-1.0", "base": "/data/v1/pollution-hunter"}
  ]
}
```

One entry of `/data/v1/pollution-hunter/findings.json`

```json
{
  "id": "ph-eu-000123-2024",
  "module": "pollution-hunter",
  "subject": {
    "id": "ph-eu-000123", "kind": "facility", "name": "Example Power Station",
    "operator": "Example Energy S.A.", "sector": "Thermal power", "country": "PL",
    "lat": 51.27, "lon": 19.33, "register": "EEA", "register_id": "example-id"
  },
  "period": {"label": "2024", "start": "2024-01-01", "end": "2024-12-31"},
  "claimed": {
    "value": 18400, "unit": "t NOx/yr", "basis": "measured",
    "source": "EEA Industrial Reporting database v16",
    "footprint_radius_km": 20, "footprint_facilities": 1
  },
  "observed": {
    "value": 21900, "lo": 10800, "hi": 44200, "unit": "t NOx/yr",
    "method": "ph-emg-1.0", "n_days": 96, "lifetime_h": 3.4
  },
  "ratio": {"value": 1.19, "lo": 0.59, "hi": 2.40},
  "verdict": "consistent",
  "grade": "A",
  "gates": {"failed": [], "flags": []},
  "versions": {"data": "2026-11", "method": "ph-emg-1.0", "commit": "abc1234"}
}
```

The detail file `/finding/<id>.json` adds:

```json
{
  "series": [{"window_end": "2024-06", "value": 20100, "lo": 9900, "hi": 40600, "n_days": 91}],
  "reported_series": [{"year": 2023, "value": 19800, "basis": "measured"}],
  "profile": {"t_h": [-2.0, -1.9], "flux_mol_s": [0.1, -0.2], "fit": {"q": 6.8, "tau": 3.4, "sigma": 0.4, "t0": 0.05, "r2": 0.97}},
  "days": [{"date": "2024-05-14", "wind_ms": 5.2, "wind_dir_deg": 240, "detected": true, "z": 6.1}],
  "evidence": {"stack_image": "/img/ph/000123/stack-2024.webp", "flipbook": "/img/ph/000123/flipbook-2024.webp"},
  "footprint": [{"name": "Example Power Station", "reported_t": 18400}],
  "sources": ["EEA Industrial Reporting database v16", "Copernicus Sentinel-5P", "ERA5"]
}
```

---

## Appendix C: sources

Satellite and wind data
- Sentinel-5P mission status: https://www.eoportal.org/satellite-missions/copernicus-sentinel-5p
- Earth Engine NO2 collection: https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_OFFL_L3_NO2
- Earth Engine ERA5 hourly: https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_HOURLY
- Earth Engine noncommercial tiers: https://developers.google.com/earth-engine/guides/noncommercial_tiers
- `ee.data.computePixels`: https://developers.google.com/earth-engine/apidocs/ee-data-computepixels
- Copernicus Data Space quotas: https://documentation.dataspace.copernicus.eu/Quotas.html
- TROPOMI NO2 processor versions: https://www.temis.nl/airpollution/no2col/tropomi_no2_data_versions.php
- Sentinel-4: https://www.eumetsat.int/sentinel-4

Reported emissions
- EEA Industrial Reporting database: https://www.eea.europa.eu/en/datahub/datahubitem-view/9405f714-8015-4b5b-a63c-280b82861b3d
- E-PRTR reporting thresholds (Annex II): https://www.legislation.gov.uk/eur/2006/166/annex/II/2019-07-26?view=plain
- EPA CAMPD: https://campd.epa.gov/
- EPA CAM API portal: https://www.epa.gov/power-sector/cam-api-portal
- PUDL hourly CEMS: https://catalystcoop-pudl.readthedocs.io/en/latest/data_sources/epacems.html
- EPA greenhouse gas reporting deadline extension: https://www.federalregister.gov/documents/2026/10/14/2026-20982/extending-the-reporting-deadline-under-the-greenhouse-gas-reporting-rule-for-reporting-year-2025-to
- Climate TRACE: https://climatetrace.org/

Method papers
- Beirle et al. 2023, point source catalogue v2: https://doi.org/10.5194/essd-15-3051-2023 (data: https://doi.org/10.26050/WDCC/No_xPointEmissionsV2)
- Beirle et al. 2019, pinpointing NOx emissions from space: https://doi.org/10.1126/sciadv.aax9800
- Beirle et al. 2011, megacity emissions and lifetimes: https://doi.org/10.1126/science.1207824
- Goldberg et al. 2019, NOx from North American cities and power plants: https://doi.org/10.1021/acs.est.9b04488
- Lange et al. 2022, emission fluxes and lifetimes: https://doi.org/10.5194/acp-22-2745-2022
- van der A et al. 2024, European NOx emissions from space: https://acp.copernicus.org/articles/24/7523/2024/
- Kuhlmann et al. 2024, the ddeq Python library for emission quantification: https://gmd.copernicus.org/articles/17/4773/2024/
- van Geffen et al. 2022, NO2 retrieval version 2: https://doi.org/10.5194/amt-15-2037-2022
- Schuit et al. 2023, automated methane super-emitter detection: https://doi.org/10.5194/acp-23-9071-2023

Methane catalogues
- UNEP IMEO Eye on Methane: https://methanedata.unep.org/
- Carbon Mapper data portal: https://data.carbonmapper.org

Frontend and hosting
- MapLibre globe with atmosphere example: https://maplibre.org/maplibre-gl-js/docs/examples/display-a-globe-with-an-atmosphere/
- MapLibre GL JS v6 release notes: https://newreleases.io/project/github/maplibre/maplibre-gl-js/release/v6.0.0
- deck.gl release notes: https://deck.gl/docs/whats-new
- Cloudflare pricing and free limits: https://developers.cloudflare.com/workers/platform/pricing/
- PMTiles on cloud storage: https://docs.protomaps.com/pmtiles/cloud-storage
- OpenFreeMap: https://openfreemap.org
- NASA GIBS: https://www.earthdata.nasa.gov/gibs
- Sentinel-2 cloudless: https://s2maps.eu
- GitHub Actions pricing: https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/

Legal context
- Defamation (Amendment) Act 2026 commencement: https://www.gov.ie/en/department-of-justice-home-affairs-and-migration/press-releases/minister-jim-ocallaghan-signs-defamation-amendment-act-commencement-order-2026/
- Law Society Gazette overview: https://www.lawsociety.ie/gazette/in-depth/2026/april/the-truth-carriers/

---

## Appendix D: glossary

| Term | Meaning |
|---|---|
| TROPOMI | The instrument on the Sentinel-5P satellite that measures NO2, methane and other gases |
| Column | Amount of a gas above one square metre of ground, in mol/m2 |
| NOx | NO plus NO2. Reported as if it were all NO2. |
| EMG | Exponentially modified Gaussian, the curve fitted to the plume |
| Lifetime | Time for NO2 in the plume to fall to 37% of its starting amount |
| Air mass factor | The retrieval's conversion from what the satellite sees along its slanted light path to a vertical column |
| ERA5 | A global hourly weather reanalysis from ECMWF, used here for wind |
| CEMS | Continuous emission monitoring system: a sensor in the stack |
| E-PRTR | European Pollutant Release and Transfer Register, now part of the EEA Industrial Reporting database |
| LCP | Large combustion plant |
| EECU | Earth Engine compute unit, the currency of the Earth Engine quota |
| PMTiles | A single-file map tile archive that a browser reads with range requests |
| Bootstrap | Resampling your data with replacement to see how much an estimate varies |

