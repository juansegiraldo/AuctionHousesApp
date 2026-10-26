# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python data pipeline that scrapes Latin American / Spanish auction houses and refines the
results through a Medallion (bronze → silver → gold) architecture for analytics. There is no
running web service or database in the current tree — it is a batch scrape-and-transform project
producing JSONL files plus an HTML analytics report.

**The app *is* the frontend.** `data/gold/app/` (`index.html` + `lots.json` + `cards.json`) is
the product: a static, mobile-first app that the repo owner's partner reads on a phone, via a
URL (a Claude Artifact now, Vercel or similar later). Serve it — `python -m http.server -d
data/gold/app` — because `file://` blocks the `fetch` of the two JSON files.

> Note on git status: the tracked `backend/` (FastAPI), `frontend/` (Next.js), `database/`, and
> root `docker-compose.yml` / `Makefile` files show as **deleted** — the project was rebuilt
> around the scraping + pipelines layout and those legacy files no longer exist on disk. They
> remain recoverable from commit `765841b`. Work against the `scraping/`, `pipelines/`,
> `semantic_layer/`, and `data/` directories; ignore the old full-stack files unless explicitly
> asked to restore them. [ESTADO.md](ESTADO.md) documents this in Spanish for the repo owner.

## Setup & commands

All Python commands run **from the repo root**. `pyproject.toml` sets `pythonpath = ["."]`,
`testpaths = ["tests"]`, and `-p no:postgresql` (a leftover `pytest-postgresql` plugin from the
deleted backend crashes collection on `psycopg`/libpq import — do not remove that flag unless
the plugin is uninstalled). Targets Python 3.13.

There is **no top-level `requirements.txt`** (the legacy one was removed). The scraper deps live in
[scraping/requirements.txt](scraping/requirements.txt) — `scrapling[fetchers]`, `pydantic>=2.0`,
`orjson>=3.11`. The code additionally imports `requests` (Duran AJAX session), `pyyaml`
(`pipelines/config`), and `pytest` for tests.

```powershell
python -m venv venv; venv\Scripts\activate
pip install -r scraping/requirements.txt
pip install requests pyyaml pytest typesafe-sdk
```

Run tests (941 pass):

```powershell
python -m pytest                          # full suite
python -m pytest tests/pipelines/         # pipeline + quality-gate tests
python -m pytest tests/scraping/duran_subastas/test_parse_lot_page.py::test_name
```

**Everything runs as a module** (`python -m`), scrapers and pipeline stages alike — the stages
now import from `pipelines.shared`, so file-path invocation breaks:

```powershell
python -m scraping.houses.duran_subastas.run_historic --list-only
python -m scraping.houses.bogota_auctions.run_auction_list --file urls.txt

.\scripts\run_all.ps1                     # whole pipeline in the correct order

python -m pipelines.bronze.ingest
python -m pipelines.silver.build_silver
python -m pipelines.silver.artist_resolve            # identidad de artista + pais
python -m pipelines.enrichments.currency_normalize   # also: artist_canonicalize, category_tag
python -m pipelines.gold.build_gold
python -m pipelines.analytics.report_gold            # writes data/gold/analytics_report.json
python -m pipelines.analytics.build_artifact         # writes the app: data/gold/app/
python -m pipelines.analytics.build_fx_report        # writes data/gold/fx_report.html

python -m scripts.fx_fetch_history                   # MANUAL: baja BCE+TRM -> fx_history.yaml
python scripts/verify_morton_scrape.py               # lotes de cada subasta vs "N Results" de la web
```

`quality_gates.py` is the exception — still a file path, and it takes arguments:

```powershell
python pipelines/silver/quality_gates.py --house-slug duran_subastas
```

## Architecture

Two layers connected by the `data/` directory and the **house registry**.

### 1. Scraping (`scraping/`) — one subpackage per auction house

- `scraping/common/models.py` — shared Pydantic schema for **all** houses: `AuctionMeta` and
  `LotItem`. The schema is intentionally **Dublin Core (DCMI)–compatible** (fields annotated with
  `dcterms:*` mappings) and prices are integers in the house's own currency, which differs per
  house (`COP` for Bogotá and Lefebre, `EUR` for Duran, `USD` for Zorrilla, `MXN` for Morton — the model defaults
  to `COP`, so each house sets `currency` explicitly when building `LotItem`s). Changing this
  schema affects every house and every downstream pipeline stage.
- `scraping/houses/<slug>/` — each house has `parsers.py` (HTML → models) plus three runners with
  the **same interface across houses**: `run_one_auction.py`, `run_auction_list.py`,
  `run_historic.py`. Runners write JSONL into the house's own `output/` directory.
- `scraping/houses/registry.json` — the source of truth mapping `slug → module → output_dir`.
  `pipelines/bronze/ingest.py` reads this to discover what to land. **Adding a house means adding
  a registry entry**, not editing the pipeline.
- House runners share patterns: retry-with-backoff (`--max-retries`, `--timeout`), resume by
  skipping auctions whose output file already exists, per-auction JSON checkpoints under
  `output/checkpoints/`, test limits (`--max-auctions`, `--max-lots-per-auction`), and optional
  thread-pool parallelism (`--workers`; >16 risks HTTP 419 rate limiting).
- Duran discovers lots via an **AJAX endpoint**, not the static page. Its `historic_all_lots.jsonl`
  is a superset of the per-auction files (47,383 lots, 2014→2026, re-scraped 2026-10-15) and is safe to re-ingest —
  Silver dedupes on `lot_url`.
- **Zorrilla (`zorrilla_subastas`) and Morton (`morton_subastas`) are the houses built on the
  `scraping/common/` framework** (frozen `House` + injected `discover`/`fetcher`); Bogotá and Duran
  stay on their legacy duplicated code. Copy Zorrilla or Morton, not them, when adding a house. Two things make it unusual:
  its source is **LiveAuctioneers, not the house's own site** (zorrilla.com.uy unpublishes lots
  after each sale — all 70 historic pages return "No se encontraron resultados"), and its parsers
  read the embedded **`window.__data` JSON** rather than the DOM, because the React UI shows
  "See Sold Price" instead of the number. Run it with `--quick`: the catalog payload already has
  price, estimates, status and title, so per-lot detail fetches add nothing. See
  [scraping/houses/zorrilla_subastas/README.md](scraping/houses/zorrilla_subastas/README.md).
- **Morton (`morton_subastas`, Ciudad de México, MXN) is the only Mexican house, and only its ART
  is here: 57 of its 803 past auctions** (2021→2026, 12,838 lots), chosen by title in
  `parsers.is_art_auction()` — the rest are truck fleets, cars, wine, jewellery, antiques and mixed
  "Subastas de los Sábados". Gold emits `source_is_art_subset` so its volume is never read as the
  house total. Source is `live.mortonsubastas.com` (Bidsquare, server-rendered). Full account in
  [scraping/houses/morton_subastas/README.md](scraping/houses/morton_subastas/README.md). Traps:
  - **Before 2024 the catalog says "Login for Price"**, but each lot page publishes a JSON-LD
    `Product` with the hammer price, so Morton runs **without `--quick`** (~12,800 lot pages,
    ~1h at `--workers 6`). **`availability: Discontinued` ALSO carries a price — the opening bid,
    always below the low estimate** (20/20 checked against the visible label). Only `SoldOut` is a
    sale. "Sold Price excludes BP": hammer, like every other house. A test pins it.
  - **The mojibake is REAL here** (unlike the console artifact below): 2021-2023 titles come
    double-encoded in Morton's own HTML; `fix_mojibake()` repairs it run by run. The JSON-LD also
    carries escaped HTML entities (`M&eacute;xico`), unescaped on read.
  - **Dates are converted to `America/Mexico_City`**: the listing prints the viewer's zone
    ("01:00AM BST") and the JSON-LD US zones; read raw, the 2026 Arte Mexicano lands a day (and on
    a 31st, a month — another FX rate) late. Needs `tzdata` on Windows.
  - **The artist is the UPPERCASE lead of the title** (comma until 2023, period since 2024,
    bilingual "ES | EN" in 2021), with nicknames skipped (`GEORGINA "GOGY" FARÍAS`), honorifics kept
    (`DR. LAKRA`, `MR. BRAINWASH`) and glued separators split (`JAVIER MARÍN,Torso` used to rank
    "Javier" as an artist). Morton writes Mexican birthplaces as *city, state* with no country, so a
    Mexican state reads as `México` in `artist_country` — diagnostics only, as always.
  - **Morton recycles records**: 51 lots of auction 20912 carry a used-car title ("Camioneta
    Chevrolet Tornado 2009", even in the URL) over the real artwork's description and price;
    `lot_title_for()` rebuilds the title from the description.
  - `artist_for_lot()` is separate from `parse_lot_page()` so a rule change can be re-applied to
    the downloaded JSONL without re-fetching 12,838 pages.
- **Lefebre (`lefebre_subastas`) is the only house with two sources in one `output/`**, and that
  is deliberate — each covers a period the other cannot. `from_excel.py` converts a spreadsheet
  curated by hand in 2024 (1,037 lots, 11 auctions, 2021→2023); `parsers.py` + the three runners
  scrape the **Auction Mobility API** for everything from Subasta 27 on (2,821 lots, 19 auctions,
  2023→2026). **3,858 lots total, 30 auctions, COP.** They coexist because `bronze/ingest.py` only
  copies `*.jsonl` from `output_dir` and **never imports the registry's `module`** — that is the
  seam a non-scraped source plugs into. Full account in
  [scraping/houses/lefebre_subastas/README.md](scraping/houses/lefebre_subastas/README.md).
  - **The site looks empty but isn't.** It is an Angular SPA: `curl /auctions/past` returns "no
    past auctions" — the same trap as Zorrilla. No headless browser needed, though: the auction
    list is **server-rendered** inside the page's `viewVars` blob (page 1 holds only 20 of 29 —
    pass `?page=2`), and the lots come from the site's own **unauthenticated AJAX proxy**,
    `GET /ajax/lots/<code>?limit=100`. The upstream backend
    (`production4-server.auctionmobility.com/v1/…`) returns **401** with every header tried,
    including the `amRegistrationKey` the page itself publishes, so `next_page_url()` rewrites
    the JSON's `next_page` back to the proxy.
  - **Free validation oracle**: each auction summary publishes `total_hammer_price` and
    `sold_lot_count`, and the sum of lot prices matches **exactly** — 19/19 auctions. Run
    `python scripts/verify_lefebre_scrape.py`; it catches partial files left by a timeout.
  - **The `lot_url` double slash is intentional.** `BASE_URL + "/" + _detail_url` yields
    `…com//lots/view/…`, reproducing 89/89 of the URLs already in Silver. A "correct" `urljoin`
    would give a single slash, match nothing already ingested, and **duplicate every re-scraped
    lot**. A test pins it. Same reason `_auction_id_from_url()` returns the slug (`subasta-30`)
    and not the code (`4-DLG0WK`): the runner names the output file with it.
  - **The 11 Excel auctions are never scraped**, and not merely to avoid duplicate `excel://`
    keys. The web holds 890 more lots for them, but that is **not missing data**: 93.4% of the
    1,037 kept rows carry a biographical parenthesis versus 0.9% of the 890 dropped ones. That
    is a deliberate curation — keep the art with an attributed artist — and 51% of what was
    dropped is furniture, jewellery and decorative objects (Christofle cutlery, Rosenthal china,
    Versace chairs, mirrors, trunks), plus 5% anonymous `Escuela Quiteña`/`colonial` works.
    Scraping them would turn an art dataset into a generalist catalogue. See
    `parsers.EXCEL_ONLY_AUCTIONS`.
  - **An artist is only recorded when the biographical parenthesis is present.** Lefebre also
    sells jewellery, watches, furniture and vinyl, so "first line is the artist" invents painters
    called `Solitario de Diamante`, `Anillo Tiffany's en oro blanco` and `DURA DURAN` — the very
    defect `_OBJECT_NAMES` filters for Bogotá. 1,564 of 2,821 scraped lots get an artist; the
    other 1,257 **still enter the pipeline** with `artist_name=None`, keeping the house's real
    revenue without polluting the artist ranking. This is the same rule the curator applied by
    hand in 2024.
  - Four traps of the **Excel** source — `Pasado` and `0` both meaning *not sold*, `Order` being
    a row number in 11 of 15 auctions, only 674 of 1,711 rows having a lot URL, and `Title`
    arriving in two formats — are documented with tests in the same README.
- `scraping/` root still holds the original single-house (Bogotá) scripts — the `houses/` layout
  is the current structure; prefer it for new work.

### 2. Pipelines (`pipelines/`) — Medallion transform over `data/`

Data flows one direction through `data/`, and each stage reads the previous layer only:

1. **bronze** (`bronze/ingest.py`): copies each registered house's `output/*.jsonl` into
   `data/bronze/<slug>/ingestion_date=YYYY-MM-DD/`. Immutable raw landing.
2. **silver** (`silver/build_silver.py`): reads all bronze JSONL, calls
   `pipelines.shared.schema.normalize_lot` (adds `house_slug`, `ingested_at`, `source_file`, and a
   `dedupe_key = "<house>|<lot_url>"`), dedupes on that key, and emits `data/silver/lots.jsonl`
   plus a derived `data/silver/auctions.jsonl`. `auction_index.jsonl` files are skipped here.
3. **artist_resolve** (`silver/artist_resolve.py`): runs right after `build_silver` and rewrites
   `lots.jsonl` in place (temp file + atomic replace), adding **seven fields to every lot**:
   `artist_id`, `artist_fold`, `artist_display_name`, `attribution_type`, `artist_country_birth`,
   `artist_nationalities`, `artist_resolution`. Everything downstream assumes they are present.
   It is the single place where artist identity is cleaned — see "El maestro de artistas" below.
   **Jev (TypeSafe) second opinion** ([pipelines/shared/attribution_jev.py](pipelines/shared/attribution_jev.py)):
   the rules end in `return "autor"`, so objects and titles ("Sofá Chester", "Atlas de Colombia")
   ranked as artists. Jev is asked **only** about `fold_only` lots (rules say `autor`, not in the
   master) and can only *remove* a name from the ranking (label applied at `confidence >= 0.90`,
   → `not_an_author`); it never writes identity or country. Silver reads **only** the versioned
   cache `pipelines/config/attribution_jev.jsonl` (keyed by `artist_fold`), so it is reproducible
   offline; the network is used just to fill new folds, and with no key/network the stage carries
   on with rules + cache. Below the threshold the lot stays `autor` and Gold counts it as
   `attribution_low_conf`. The key is `TYPESAFE_API_KEY`, or `type_safe` in `../JEV_v0/.env`.
   `tests/conftest.py` blocks the API and the real cache in every test — keep it.
   Validated with `python -m scripts.jev_attribution_eval` (2026-10-12): 1,176 folds removed,
   ranking 9,769 → 8,656, artist revenue −0.85%, top 200 untouched, ~$0.30 total.
4. **enrichments** (`enrichments/*.py`): optional, independent jobs keyed by `dedupe_key`
   (currency normalize, artist canonicalize, category tag, embeddings stub) → `data/enrichments/`.
5. **gold** (`gold/build_gold.py`): aggregates silver into analytics facts
   (`agg_house_metrics`, `agg_lots_by_year`, …) plus `quality_flags.jsonl` in `data/gold/`.
   `gold/build_insights.py` runs **after** it and adds the second-level aggregates the report
   needs (`agg_artist_metrics`, `agg_country_metrics`, `agg_category_metrics`,
   `agg_month_metrics`, `agg_price_distribution`, `agg_estimate_accuracy`). Unlike
   `build_gold.py` it reads **Silver + enrichments**, not Gold — it needs per-lot
   artist/category/estimate fields that the basic aggregates drop. It groups artists by
   `artist_id or artist_fold` (never the raw name), keeps only `attribution_type == "autor"`,
   and requires `MIN_LOTS_FOR_ARTIST_RANK` sales to rank an artist.
6. **quality_gates** (`silver/quality_gates.py`): coverage report over silver, optionally per
   house. Reports by default; `--fail-on-violation` exits non-zero for CI. `--allowed-categories`
   must match the **English** tags emitted by `category_tag.py` (`painting`, `prints`, …) — the
   old Spanish defaults matched nothing and flagged 100% of rows. Also reports
   `artist_resolution_rate`, `artist_country_coverage`, `attribution_autor_pct` and
   `unmapped_country_values`; the artist gates default to `0.0` (informative, not blocking) and
   skip `HOUSES_WITHOUT_ARTISTS` (Zorrilla is jewellery — 0% forever, not a defect).
7. **analytics/build_artifact.py — the app, and the only renderer** (2026-10-24). It writes
   `data/gold/app/`. The Plotly report (`analytics_report.html`) was retired: two renderers of the
   same data kept diverging. `render_html.py` survives only as the home of the shared pieces the
   app imports (`HOUSE_LABELS`, `HOUSE_COUNTRY`, `MONTH_LABELS`, `_rank_selection`,
   `pack_lot_details`). Things that look odd but are load-bearing:
   - **No CDN, ever.** An Artifact's CSP blocks every external host, and the same folder must
     deploy unchanged to Vercel. Charts are **SVG generated in Python**, and the fonts are system
     stacks (`ui-rounded` for numbers).
   - **Heavy data is fetched, not inlined.** `lots.json` (~7 MB, only for the "Lotes" CSV) is
     fetched when the ⋯ download menu opens, so it is usually in memory by the time the tap lands
     — Safari blocks downloads that fire outside the user gesture. `cards.json` (artist cards,
     rendered in Python by `artist_card()`) is fetched when the Artistas tab opens. Both used to
     be inline and the file weighed 12 MB. `build_cards()` and `build_artist_table()` **must** use
     the same `_rank_selection()`, or `data-card` opens another artist's card (a test pins it).
   - **Each house has a FIXED colour (`HOUSE_SERIES`), never its rank.** It used to come from the
     position in `house_order` (by revenue), and Morton entering second repainted every other house.
   - **Artist cards are keyed by `artist_key`, not position, and the JSON is fetched with a content
     hash (`cards.json?v=…`).** With `ficha-<rank>`, a browser holding last build's `cards.json`
     opened Obregón when tapping Tamayo. Now a mixed old/new pair can at worst show the same
     person's older card.
   - **Every chart mark carries `data-x`/`data-l`/`data-v`**, and one JS handler writes the
     nearest mark into the readout above the chart (drag a finger across it). `<title>` tooltips
     never show on touch screens. Stacked bars use an invisible `.hit` column per year.
   - **The lists are still `<table>`s**, restyled as cards by CSS, because `wire()` (filter,
     pagination, totals, CSV) works on the rows. `[hidden]{display:none!important}` is load-bearing:
     without it, `.pager{display:flex}` beats `hidden`.
   - The `money()` formatter exists twice (Python and JS) on purpose: Python writes the headline
     figure and JS re-animates it, so the two must agree (a test pins the format).
   - The house palette was validated with the dataviz skill's CVD script for adjacent pairs, in
     both themes. The light yellow and aqua sit below 3:1 on white, which is why every
     multi-series chart has a legend and a text readout.
   - **The world map's geometry is versioned, not fetched**: `pipelines/config/world_110m.json`
     (Natural Earth 110m, already projected to Equal Earth, ~93 KB), regenerated by hand with
     `python -m scripts.build_world_map` — manual and rare, like `fx_fetch_history`. It keys on
     **`ISO_A2_EH`, not `ISO_A2`**: in the latter France and Norway are `-99` and would paint gray
     despite millions in sales. Bins are fixed decades (`MAP_BINS`), not quantiles; gray means
     "no artist born there in the ranking", never the lowest bin. Historic countries with no
     shape (Czechoslovakia, `CS`) are declared in the map's notes, never split among today's states.
8. **analytics** (`analytics/report_gold.py`): renders the Gold layer to `analytics_report.json`.
   Reads Gold only — never bronze/silver. It decides *what* goes in the report; `build_artifact.py`
   decides *how it looks*. The insight aggregates are optional: if `build_insights.py` hasn't
   run, those sections are omitted rather than raising.
9. **analytics/build_fx_report.py**: `data/gold/fx_report.html`, the panel for the FX layer.
   Separate from the main report because it answers a different question — not "how much sold"
   but "how far off was the single rate". It plots the **ratio** of each month's rate to the
   static one (so the 1.00× crossing is exactly where the old flat rate flipped from
   undercounting to inflating), plus the per-house ledger and the fallback accounting. SVG
   generated in Python, no CDN, same CSP reasoning as `build_artifact.py`. Its HTML lives in
   `pipelines/analytics/templates/fx_dashboard.html` so the styling can change without touching
   the chart geometry.

Run the whole chain with `.\scripts\run_all.ps1`. Running stages piecemeal is how the layers
previously drifted out of sync (enrichments built in March over a Silver rebuilt in May).
The Duran "massive run" runbook lives in [docs/SCALING_CHECKLIST.md](docs/SCALING_CHECKLIST.md).

### El maestro de artistas (`pipelines/config/artists/`)

Curated YAML, versioned in git — it lives outside `data/` precisely because `data/**` is
gitignored. Loaded only through [pipelines/shared/artist_master.py](pipelines/shared/artist_master.py),
the same single-source-of-truth pattern as `fx.py`. See
[pipelines/config/artists/README.md](pipelines/config/artists/README.md).

**Populated as of 2026-10-26: 3,584 artists** (58 added for Morton's top-200 gaps, then Robert Henri and Myra Landau; figures below are from 2026-08-19), resolving **26,034 lots with a country** (61.8% of
lots that have an author). In the ranking, **2,386 of 9,769 artists (24.4%) cover
89.79% of artist-attributed revenue** — publish both figures, never just the first. Entry
completeness: 87.4% have a country, 94.4% a birth year, 70.9% are complete (country + birth +
death-or-`living`). Everything else stays `fold_only` with no country, and the report publishes the
real coverage rather than looking complete. To extend it:
`python scripts/artist_master_propose.py --min-lots 3`, reviewed shard by shard.

**Continuing this work?** [docs/PLAN_MAESTRO_ARTISTAS.md](docs/PLAN_MAESTRO_ARTISTAS.md) is the
handover plan: what to do next in priority order (its first step, fixing the Durán parser, is done),
the mistakes the last pass made, and the checks to run before calling a batch done. Read it before
adding artists.

**Exhaustive coverage is a three-step cycle, and "100%" means *classified*, not *asserted*.**
`gold/build_artist_master.py` accounts for **all 12,961 author folds** (`author_fold_coverage_rate:
1.0`), sorting each into `verified` / `needs_web` / `needs_review` / `ambiguous` and writing the
versioned queue to `pipelines/config/artist_review/`. `scripts/artist_master_web_research.py` then
researches every `needs_web` fold in Wikidata, writing an evidence journal with `auto_promote:
false`; `scripts/artist_master_promote.py` turns only the unambiguous evidence into YAML entries
for a human to paste. **None of the three ever writes to `pipelines/config/artists/`.** A fold left
in `needs_web` is a visible gap with its flag set — which is the point, not a shortfall.
- **Wikidata cannot close the long tail, and that is a measured result, not a missing feature.**
  Match rate is 65% over the already-curated head but **25% over the uncurated segment**. The
  obvious hypothesis — that comma-inverted names (`MARTINEZ TERRON,VICTORIANO`) fail on the comma
  — was tested by also searching the inversion and **does not rescue them**: they simply aren't in
  Wikidata. **7,343 of the 11,473 uncurated candidates (64%) appear in a single lot**; they are
  local painters no encyclopedic source documents. Comma inversion is for *merging variants of
  artists already in the master*, never for discovering new ones.
- **Birth country comes from the birthplace, resolved in two hops** — P19 (place) → P17 (country)
  → P297 (ISO code) — because `_countries.yaml` only knows major cities (`Barcelona` resolves;
  `Oslo`, `Lausana`, `Manila` do not). **P17 lists every state that ever governed the place**: Oslo
  declares four, Minsk fourteen (Kievan Rus' through Ukraine), so taking the first would publish a
  dead country. Only currently-coded states count, and if more than one survives the gap is left.
  Verified live against the two cases the repo already documents as traps: Steinlen → Lausanne →
  `CH` (not France, where all his work was made) and Monir → Qazvin → `IR`.

It got there in four passes, best source first — see
[pipelines/config/artists/README.md](pipelines/config/artists/README.md) for the full account:

1. **303 entries from the `Artistas` sheet of `FINALL.xlsx`** (+927 lots) — the same hand-curated
   source as the Lefebre house. A curated source still needs auditing: 29 artists with no country
   were dropped rather than added empty, and duos/collectives had their dates stripped because the
   sheet stores **two birth years** in the birth/death columns (publishing Leidy Chávez as dead
   since 1984 was the near-miss).
2. **93 comma-inversion aliases** (+228 lots, no research at all) — `ALCALDE, JUAN` and
   `MIRÓ FERRÁ, JOAN` pointed at artists *already* in the master, just missing that alias, so they
   ranked twice with half their lots countryless. `García Márquez, Gabriel` deliberately stays
   unmerged: 55 book lots by the writer, and the reason inversion is reviewed rather than applied.
3. **140 entries researched in public sources** (+2,050 lots) — Wikipedia, Wikidata, Museo del
   Prado, Reina Sofía, MACBA, Artnet, for the highest-volume unresolved names (mostly 19th–20th c.
   Spanish painters from Durán). Of 176 researched, **36 could not be verified and were left with
   no country**. The payoff isn't only filling gaps: it corrects what a heuristic would call
   obvious — Sáenz de Tejada was born in Tangier, Steinlen in Lausanne, Pinazo Martínez in Rome,
   Gardy Artigas in France, all of them selling into the Spanish market. A test pins those.
4. **6 single-word pseudonyms + 1 alias** (+104 lots) — `Jano`, `Marola`, `Serny`, `Monir`,
   `Rembrandt`, `Durero` looked like one-word noise and are people (Francisco Fernández-Zarza,
   Manuel Rodríguez Lana, Ricardo Summers Ysern, Monir Farmanfarmaian, and Dürer under his
   Spanish name). `Guinovart` turned out to be an **alias of an existing entry**, not a new
   artist. `*Mingorance` was deliberately left unresolved: two different Mingorance painters
   exist and its 10 lots carry no year to tell them apart.
5. **15 entries + 3 aliases closing the top-200 gaps** — lowering `MIN_LOTS_FOR_ARTIST_RANK`
   to 1 lets single-lot artists into the ranking, so the top 200 by revenue filled with
   expensive names that never used to reach the cutoff. Of the 20 gaps: **2 weren't artists**
   (a quoted work title — see the Durán parser bug below), **3 were already in the master and
   only lacked an alias** (`Oswaldo Guaysamín`, a Durán typo; `Salvatore Mangione (Salvo)`;
   `ANDRES DE SANTAMARIA`, which Lefebre writes unspaced and unaccented), and 15 were
   researched and verified. The payoff was again in **correcting the obvious**: Santa María
   was born in Bogotá despite dying in Brussels, Justiniano Asunción is Filipino selling into
   the Spanish market, and Oller gets `PR` — ISO does code Puerto Rico, so neither `ES` nor
   `US` needs forcing. Lempicka and Juan de Juanes stay `confidence: medium` (disputed
   birthplace; the house's 1523 contradicts the c.1503 consensus). **Top 200 now has zero
   artists without a country.** Morton reopened it to 68 (2026-10-25); a batch of 58 entries
   plus 5 comma aliases closed it to 4, and on 2026-10-26 Robert Henri (Wikidata wins over
   Durán's 1926 death year; noted, `confidence: medium`) and Myra Landau (born Bucharest → `RO`)
   left **2, each deliberate**: Gómez Mayorga and Raymundo Martínez — only dealer pages, no
   independent source (Museo Kaluz's site had a broken TLS certificate). Don't chase the edge:
   adding a country never moves the revenue ranking, so #200 stays Landau. Traps it caught:
   Zúñiga → `CR` and Goeritz → `PL` (Danzig) are "Mexican" artists born elsewhere.

The master also **merges variants that don't share a fold** — that is work only the alias list can
do. `Joaquín Sorolla` / `Joaquín Sorolla y Bastida`, `Pablo Picasso` / `Pablo Ruiz Picasso`,
`Fernando Botero` / `Fernando Botero (Colombia, 1932)`, and comma inversions like
`ÚBEDA, AGUSTÍN` / `Agustín Úbeda`. Merging those dropped the ranking from 1,530 to 1,489 rows.
Two lookalikes are deliberately **not** merged: `Después de Pablo Picasso` (a work "after" Picasso,
not by him) and `García Márquez, Gabriel` (a writer in book lots, not a painter).

- **Two-tier resolution, and the difference matters.** Tier 1 is the **explicit alias list** in the
  master (a human decided these names are the same person). Tier 2 is `artist_fold()` — a
  deterministic NFKD+casefold+depunct key that *groups* variants but **never grants a country and
  never asserts identity**. The master keys on aliases, not the fold, because `Francisco Toledo` is
  two different real people sharing one fold; fold-keying would make that error unfixable by
  construction. Same reason `propose_inversion()` (`GARCIA OCHOA, LUIS` → `luis garcia ochoa`) is a
  *suggestion* for `scripts/artist_master_propose.py` and is deliberately **not** in `artist_fold`:
  `García Márquez, Gabriel` is a writer in book lots, not a painter.
- **Never invent a country.** An artist missing from the master gets `artist_country_birth: None` —
  never a guess, and never the auction house's country. Same discipline as `to_eur()` returning
  `None` instead of `1.0`. `HOUSE_COUNTRY` in `render_html.py` is where the *sale* happens; using it
  as nationality would already be wrong for the 46 Spanish, 26 German and 25 Panamanian artists
  Bogotá has sold. There is a test forbidding it.
- **The master wins over the house's free text**, and the disagreement is counted, not silently
  resolved. Neither first-write-wins (the old `build_insights` bug) nor majority vote: Alejandro
  Obregón's raw data says `España` ×17 and `Colombia` ×3, and the right answer is neither alone —
  it's `country_birth: ES` + `nationalities: [CO, ES]`.
- **Countries are ISO 3166-1 alpha-2**, normalized through `_countries.yaml`; the Spanish label is
  resolved at render time. The raw text is unusable as a key (`Inglaterra` and `Reino Unido` for the
  same artist, cities where countries belong). `normalize_country()` returns `None` for unknown
  values instead of passing them through, and `quality_gates` counts them as
  `unmapped_country_values` — that feedback loop is what stops `_countries.yaml` rotting the way
  `houses.yaml` did.
- **Quote `NO` in YAML.** `NO:` (Noruega) parses as boolean `False` under YAML 1.1, which silently
  dropped Norway from the table. `_iso()` in the loader coerces it back, and a test pins it.
- **`agg_country_metrics` groups by country of *birth*** so each lot counts once. A
  by-nationality view would be **non-additive** (a dual-national's lots land in two rows) — label it
  as such, or someone will "fix" the double count by dropping the second nationality and destroy
  the feature. The `country: null` row is kept visible on purpose.

### Data rules that hold up every Gold figure

These are load-bearing. Breaking one silently corrupts the report:

- **Never sum prices across houses.** Each house quotes in its own currency (`COP` for Bogotá,
  `EUR` for Duran, `USD` for Zorrilla — este último **normalizado en origen** por
  LiveAuctioneers, no es la moneda de martillo; ver el flag `currency_normalized_at_source`).
  Gold emits `revenue_native` + `currency` (exact) alongside `revenue_eur`
  (approximate). Any cross-house total must sum `revenue_eur`. Conversion goes through
  `pipelines/shared/fx.py`, the single source of truth, read by both Gold and the currency
  enrichment. `to_eur()` returns `None` for an unknown currency, never `1.0`, so a missing rate
  stays visible instead of masquerading as euros.
- **Conversion uses the rate of the auction's *month*, not one current rate.** `to_eur_at(amount,
  currency, "YYYY-MM")` returns `(amount, method)`; the month comes from
  `pipelines.shared.schema.extract_month()`, the sibling of `extract_year()`. Monthly rates live
  in `pipelines/config/fx_history.yaml` (2013-01 → today, 164 months, versioned in git),
  generated by `python -m scripts.fx_fetch_history` — **manual and rare, not part of
  `run_all.ps1`**: the pipelines never touch the network (sole exception: `artist_resolve` asking
  Jev about *new* folds — see above). MXN comes straight from the ECB (`D.MXN.EUR.SP00.A`). Two sources because **the ECB does not
  publish COP** (`D.COP.EUR.SP00.A` → 404): ECB for EUR/USD, Colombia's official TRM for USD/COP,
  bridged as `COP→EUR = (1/TRM) × (1/EURUSD)`.
  - **The size of the effect is not what the design doc predicted, and the reason matters.** It
    was written expecting Bogotá's 2014 sales to jump ~62%. **Bogotá has no 2014 lots** — its data
    starts in 2019, and the 2014 lots are Durán's, which are EUR and never convert. So house
    totals move only −2% to −4%. The mechanism is still right and still worth having: a COP amount
    converts at **1.61×** the static rate in 2014-01, and even inside Bogotá's real 2019→2026
    window there is a **1.27× spread** between the strongest and weakest month. Don't "fix" the
    small delta — re-derive it from the data before believing any number in the old design doc.
  - **The fallback is for a missing *date*, never a missing *currency*.** A lot with no usable
    month converts with the static `fx.yaml` rate and is **counted** in `quality_flags`
    (`code: "fx_historical"`). It currently reads **0 lots** — every lot in every house converts
    at its own month's rate. An unknown currency still returns
    `None`. **EUR short-circuits before the history** and is always `monthly`: without that,
    Durán's 47,383 EUR lots with no parseable date would have flooded the fallback counter with
    lots that are not approximated at all. A test pins it.
  - `fx_static_timeseries` (warn) became `fx_timeseries` (info): it used to warn that comparing
    years was invalid because of a single rate, which is exactly what this fixed.
- **Year extraction is house-specific**, so always use `pipelines.shared.schema.extract_year()`.
  Bogotá stores ISO (`2024-06-07T19:00`); Duran stores Spanish text (`"Julio 2014"`) and
  sometimes only encodes the year in `auction_id`. It returns `(year, method)` so the report can
  say when a year was *inferred* rather than read.
- **"Sold" means explicit status when the house publishes it** — use
  `pipelines.shared.schema.is_sold()`. Falling back to "has a price" is only valid where status
  is absent.
- **Sell-through is not comparable across houses.** Bogotá reads ~99% because its site publishes
  almost exclusively sold lots (~1,764 lot numbers missing from otherwise contiguous sequences);
  Duran publishes `NO VENDIDO` too and reads ~46%, Zorrilla ~62%, Lefebre ~42% and Morton ~37%.
  Those four are comparable with each other; Bogotá is not. This is a source-data property, not a bug —
  surface it as a warning, never "fix" it by computation. Lefebre carries an extra caveat of its
  own: 1,037 of its lots (all from the Excel source) have no lot number, so the missing-sequence check that
  detects this bias cannot run on them (flag `partial_lot_numbers`).
- `quality_flags.jsonl` carries these caveats into the report's warnings panel. When adding a
  caveat, emit a flag there rather than hardcoding text in the HTML.

### 3. Semantic layer (`semantic_layer/`) — code-first business definitions

`sources.yaml` (which Gold/Silver/enrichment datasets exist), `dimensions.yaml`, and
`metrics.yaml` (KPI expressions like `sell_through_rate`, `revenue_native` / `revenue_eur`).
Intended to be consumed by BI tools / future analytics endpoints — it's metadata, not executed
by the pipelines. Because nothing executes it, it can silently drift from the pipeline: when you
change how a metric is computed in `build_gold.py`, update `metrics.yaml` in the same edit.

The drift is not hypothetical — two instances were found and fixed while adding the artist master:
the `artist` dimension still pointed at the dead `enrichments.artist_canonicalized`, and
`focus_category` filtered on Spanish category names (`'obra_grafica','pintura'`) that match nothing,
the same dead-string bug already fixed in `quality_gates.py`. Metrics that are **non-additive**
(`lots_by_nationality`) carry `additive: false`.

## Conventions

- **All data outputs are gitignored** (`data/bronze|silver|gold|enrichments/*`, every
  `scraping/**/output/*.jsonl`, and checkpoints). Only `.gitkeep` files are tracked. Don't commit
  scrape results.
- JSONL is the interchange format everywhere; writes use `orjson` with `OPT_APPEND_NEWLINE`.
- Tests use HTML **fixtures** under `tests/scraping/<house>/fixtures/` so parser tests run offline;
  prefer adding a fixture over hitting the live site.
- Adding a house or enrichment is registry/config driven — see
  [docs/SCALING_CHECKLIST.md](docs/SCALING_CHECKLIST.md) and [scraping/README.md](scraping/README.md).
- Comments in pipeline code are written in Spanish (the repo owner's language) and explain *why*
  a rule exists, usually citing the bug it prevents. Match that when editing those files.

## Known issues

Don't rediscover these; they're documented in [ESTADO.md](ESTADO.md) too:

- **Bogotá's house parser *is* the legacy one** — `scraping/houses/bogota_auctions/parsers.py` is
  `from scraping.parsers import *`, so it extracts `status` exactly as before (an older note here
  claiming it didn't was wrong; disproved 2026-10-12). The real defect was that `import *` skips
  `_`-prefixed names, so all three Bogotá runners died on `ImportError: _auction_id_from_url`
  until an explicit re-export was added; `test_every_house_runner_imports` now guards every
  house. Inference (`if not status and price_sold: status = "VENDIDO"`) only runs on the
  *catalog* price, so ~1,100 lots whose price comes from the detail page keep `status=None`.
  Harmless: `is_sold()` falls back to "has a price" per lot, so they still count as sold.
- **Bogotá's alt-text parser cut artist names to the first name** (fixed 2026-10-25).
  `_parse_artist_from_alt()` in `scraping/parsers.py` let the country group take several
  capitalised words — written for alts with name and country glued ("Fernando BoteroColombia,
  1932"). With a space, the "country" swallowed the surname: `Fernando` + `Botero Colombia`, so
  Botero's *La plegaria* (340 M COP) ranked under an artist called "Fernando" (38 lots; also
  Negret, Luis Caballero, Wifredo Lam). `_split_alt_artist()` now takes only the LAST word as the
  country (or a known multi-word one: Puerto Rico, `EE. UU.`), the FIRST year as birth, and sets
  nothing when stray digits precede it (`Colombia, 19 - 1972`, `19867`). Botero is #1 again.
  **The landed data is repaired in Silver, not in Bronze** — see the next item.
- **Silver used to keep the OLDEST Bronze copy of each lot** (fixed 2026-10-26). `build_silver.py`
  now walks partitions **newest first** (the first `dedupe_key` still wins), and inside a partition
  puts `historic_all_lots.jsonl` **last**. Bronze copies the whole output on every run, so with
  oldest-first a scraper fix never reached a lot that already existed. Flipping it changed **zero
  fields in all 85,684 lots**. The 1,018 Zorrilla lots once blamed on the order came from inside
  *each* partition: `historic_all_lots.jsonl` is concatenated at the end of a run and was not
  regenerated after 13 auctions were re-scraped with descriptions, so it carries them without an
  artist. Tests pin both rules. `artist_resolve._full_bogota_name()` **is still needed**: the Bogotá
  *output* itself still says `Fernando` (its old auctions were never re-scraped with the fixed
  parser), so newest-first changes nothing there. Remove it only after that re-scrape, with a test
  showing Botero still #1.
- **Bogotá changed its lot-page template from auction 2687 (2026)** (fixed 2026-10-23). The
  detail page no longer has `span.description`; the title lives in
  `.desc-lot-profile-content span.object_title` (with author/technique/size in sibling spans
  `author`, `technique_material`, `medidas`). Before the fix 1,158 of 1,714 lots of 2026 came in
  with an empty `lot_title` and the `lot_title` gate read 0.89. `parse_lot_page()` in
  `scraping/parsers.py` now falls back to `object_title`; fixtures of both templates live in
  `tests/scraping/bogota_auctions/`. If the gate drops again, suspect another template change.
- **`historic_all_lots.jsonl` used to shadow a fresh per-auction scrape** (fixed 2026-10-26).
  Files landed alphabetically, so it beat any auction slug sorting after `h` (`libros-…`,
  `un-recorrido-…`). Silver now reads it last in each partition, so it only contributes lots no
  per-auction file has (Durán's are a superset; Zorrilla's has 47 such lots).
- **Zorrilla is missing ~11% of its lots, and today it cannot be re-scraped** (found 2026-10-26).
  `parsers.LOTS_PER_PAGE` was 28, but a LiveAuctioneers catalog page adds **24** new lots (it
  paints 27; 3 promoted ones repeat on every page), so the last page of almost every catalog was
  never requested: in 21 of the 24 catalogs on the house page's first screen the output holds
  exactly `ceil(N/28)×24` lots (144 of 214514's 149; 6,196 of 6,961 overall). The constant is
  fixed and a test pins it, but **re-scraping is blocked**: as of 2026-10-26 LiveAuctioneers no
  longer embeds `window.__data` (the house page renders JSON-LD `SaleEvent`s with no lot count)
  and Incapsula blocks the second request. Adapting the scraper is a project of its own. Until
  then Zorrilla's totals are an undercount, not a defect to "fix" by computation.
- **Bogotá 2026 looked thin because it was never ingested**, not because sales fell: 9 auctions
  were scraped on 2026-10-12/13 after that day's Bronze run. Now 11 auctions, 1,714 lots, 4,513 M
  COP. Run `run_historic --list-only` to see the live list (it rewrites `auction_index.jsonl`).
- **Bronze skips test-run leftovers, and that filter is load-bearing** (fixed 2026-08-16).
  `bronze/ingest.py` used to copy every `*.jsonl` in a house's `output/` blindly. Two files left
  over from development — `2245_test.jsonl` and `test_info_url.jsonl` in Bogotá — were **catalog
  runs that never fetched the lot detail pages**, so all 300 rows carried `auction_start_date`,
  `artist_name`, `artist_raw`, `medium`, `provenance`, `dimensions` and `price_estimate_max` as
  `None`. Silver dedupes on `lot_url` and **the first file to land wins**, so they silently
  overwrote the complete records: 67 lots of auction 2245 arrived mutilated even though the good
  file held all 127 with full data. It surfaced as the FX layer's 52 `fallback_static` lots —
  the sold subset of those 67. `is_ingestable()` now rejects any filename with `test` as a
  **segment** (`_`/`-`/`.`-delimited), never as a substring, so a real auction slug like
  `arte-contest-2024` or `protesta-social` still ingests. Tests pin both directions. After the
  fix Bogotá's FX coverage is **100%** and total fallback across all houses is **0**.
  Note `2245_full.jsonl` is *not* filtered: it is redundant (a 60-lot subset) but not mutilated,
  and filtering it by name would be guessing. The two offending files now live in
  `scraping/houses/bogota_auctions/_discarded/` (outside the registry's `output_dir`, with a
  README explaining why) — kept for scraper debugging, double-protected by `is_ingestable()`.
  Unrelated despite the name: Lefebre's `subasta-de-prueba-17-de-febrero-de-2022.jsonl` is
  **real data** the house itself titled "Subasta de prueba" — 5 fully populated lots by Jim
  Amaral, Le Parc, Acevedo Bernal and Shepard Fairey. The filter matches the English `test` as
  a segment, so the Spanish `prueba` is correctly left alone.
- **The "mojibake" is a console artifact, not a data defect** (verified 2026-08-01) — except in
  Morton, where it is real and repaired in the parser (see above). Scanning all
  49,541 Silver lots for surrogates (`\udc80`–`\udcff`) returns **zero**: `artist_name` holds a
  clean `Álvaro Barrios`, and the HTML report renders accents correctly. What looks like mojibake
  is the Windows console failing to print UTF-8 — reproduce it with
  `python -c "import sys; sys.stdout.reconfigure(encoding='utf-8')"` and it disappears. Don't
  "fix" the data or re-scrape over this; only reconfigure stdout in scripts that print names.
- **`subasta-541-marzo-2107`** is a typo on Duran's own site (2107 for 2017). `extract_year()`
  only accepts `19xx`/`20xx`, so those 315 lots land in `unknown` rather than a fabricated year.
- Bronze holds overlapping partitions (March and August ingests). Safe — Silver dedupes on
  `lot_url` — but it roughly doubles Bronze disk usage.
- Legacy single-house scripts still sit at the `scraping/` root beside the current
  `scraping/houses/` layout.
- **`artist_country` (the house's own free text) is populated on ~2% of lots and only by Bogotá.**
  Duran and Zorrilla never set it. It is diagnostics only — it feeds `unmapped_country_values` and
  the master-vs-house conflict counter, and never writes `artist_country_birth`.
- **Zorrilla has no artists at all** (3,437 jewellery lots, `artist_name` null in every one), so it
  is exempt from the artist quality gates via `HOUSES_WITHOUT_ARTISTS`.
- **The house universes are nearly disjoint**: only 59 of ~15,000 artist names overlap between Duran
  (Spanish market) and Bogotá (Colombian). Any "Spain vs Colombia" chart is therefore largely
  re-plotting `house_slug` under another name — the report says so, next to the sell-through caveat.
- **`artist_raw` is truncated to 60 chars**, so it can't be re-parsed for full identity — though the
  country, which comes early in `Name (Country, birth - death) : Title`, usually survives.
- A comma form (`ÚBEDA, AGUSTÍN`) ranks separately from `Agustín Úbeda` until an alias is added to
  the master. That is deliberate, not a bug — see the `García Márquez` case above. The main ones
  are already merged; new houses will surface more.
- `scripts/artist_master_propose.py` skips folds the master already covers, so regenerating
  candidates *after* populating returns only the gaps. Pass a patched `_known_folds()` if you need
  the full list again.
- **Reading numbers out of an Excel: never stringify the cell first.** `openpyxl` returns numeric
  cells as `float` (`1250000.0`), so a "strip the thousands separators" regex reads the decimal
  point as a separator and multiplies **every** amount by 10. It cost a full pipeline run to spot
  in `lefebre_subastas/from_excel.py` (total revenue read 57,848 M COP instead of 5,784 M), because
  the sell-through rate — a boolean test — stayed correct and looked plausible. `_to_int()` now
  short-circuits real numbers before the string path, and a test pins the exact total. Ground truth
  for the **Excel-sourced 11 auctions**: **4,118,600,000 COP over 499 sold lots** (the old
  5,784,850,000 / 806 figure covered 15 auctions, before 27–30 were re-scraped from the API).
  Whole house after the scraper: **12,361,725,000 COP over 1,600 sold lots of 3,858**. Every
  scraped auction is independently checkable against the house's own `total_hammer_price` with
  `python scripts/verify_lefebre_scrape.py` — 19/19 match exactly.
- **Lefebre's country data is richer than the master's, and that is not a licence to use it.** The
  curated sheet has a country for 1,396 lots vs the 734 the master resolves. It still lands in
  `artist_country` (diagnostics only) — the way to exploit it is proposing master entries, not
  writing `artist_country_birth` from house text.
- **The scraper put object types and catalogue fields in `artist_name`, and they ranked as
  artists.** Two populations, both filtered in `pipelines/shared/artist_key.py`: 467 lots of object
  types via `_OBJECT_NAMES` (`Cartel` 85 lots, `Collar`, `Florero`, `"Paisaje"`) matched by
  **equality against the whole fold, never a substring** — real artists are surnamed Rivera,
  Marina, Mesa and Prado; and 144 lots of Bogotá's bibliographic `Ciudad` field via
  `_CITY_FIELD_RE` (`Ciudad Bogotá` was the dataset's second-largest "artist"), by prefix because
  it sometimes drags the whole record behind it, but excluding a trailing comma so
  `Ciudad Real, Antonio` survives — with a closed list of country/city tails so
  `Ciudad Cádiz, España` still gets caught. Anyone re-profiling "top unresolved artists" hits these
  first: they are not researchable, they are noise.
- **Durán's parser used to prefer a guess over the real author, and it cost a Botero** (fixed
  in `9b333c2`, re-scraped 2026-10-15). `_infer_artist_from_title()` in
  [scraping/houses/duran_subastas/parsers.py](scraping/houses/duran_subastas/parsers.py)
  takes everything before the first `.` as the artist, so a lot published as
  `"Madre Superiora". Óleo sobre lienzo. 130 x 99…` landed with the **work's title** as
  its artist — 721 lots in 452 variants. The detail page publishes an `autor` field
  (`BOTERO, FERNANDO (1932 - 2023)` for that one, a 120.000 € lot that ranked #39 as an
  artist of its own with no country), and it now **always wins** over the guess
  ([parsers.py:515](scraping/houses/duran_subastas/parsers.py#L515)). After the re-scrape only
  **20 lots** still carry a quoted title as artist (lots with no `autor` on the detail page).
  The safety nets below stay: `_QUOTED_TITLE_RE` in `pipelines/shared/artist_key.py` marks them `not_an_author`, which
  keeps them out of the artist ranking without inventing an attribution; the revenue still
  counts for the house. The rule matches only names that are *entirely* a quoted title —
  29 lots like `"Au merite" art nouveau. Henri Louis Levasseur` carry the real artist
  behind the title and must survive. **The highest-value ones are recovered without a
  re-scrape** via `pipelines/config/artists/_lot_author_fixes.yaml`, a curated
  `lot_url → autor` map read by `load_lot_author_fixes()` and applied in
  `silver/artist_resolve.py`. It is keyed by **`lot_url`, never by name** — a title
  identifies nobody (`"Paisaje"` is 45 lots by 45 different painters), so it can't be a
  master alias, where an alias asserts identity. Values are stored exactly as the house
  prints them and re-enter `attribution_type()` normally, so `ESCUELA ESPAÑOLA S. XIX`
  stays `escuela` instead of being promoted to an author. That recovered the Botero
  (32 → 33 lots, 611,590 → 731,590 €). Note `artist_fold()` does *not* strip the
  biographical parenthesis, so `load_lot_author_fixes()` applies `strip_biography()` on
  load or `BOTERO, FERNANDO (1932 - 2023)` would never match the `BOTERO, FERNANDO` alias.
- **Book authors were deliberately NOT filtered.** 2,528 lots carry the `Autor : Título` pattern in
  `artist_raw` with an inverted name — García Márquez (55), Bolívar (19), Humboldt (14) are writers,
  not painters. But Antonio Caro, Beatriz González and Ana Mercedes Hoyos match the same pattern and
  *are* painters. Neither `medium` (empty for writers, but only statistically) nor `category_tag`
  (Humboldt classifies as `prints` from his books' engravings) separates them reliably, so they stay.
  Filtering on a non-deterministic signal would erase real artists, which is worse.
