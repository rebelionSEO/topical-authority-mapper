# Topical Authority Mapper

AI-powered SEO tool that maps any website's content into semantic topic clusters, detects
cannibalization, identifies competitor content gaps, and generates interactive dashboards
and PDF reports.

Site-agnostic: pass a sitemap URL or URL list, optionally a brand-voice PDF, and a list of
competitors. Everything else is auto-derived.

## What It Does

Takes any website's sitemaps (or a list of URLs), extracts all page content, converts it into
AI embeddings, clusters pages by topic, then layers on multiple analysis passes:

- **Topic Clustering** — groups pages into semantic clusters (UMAP + HDBSCAN)
- **Potential Topic Overlap** — flags related URL groups for query/intent review; cluster membership alone does not confirm cannibalization
- **Conversion Risk Analysis** — flags blog posts competing against service/money pages
- **Near-Duplicate Detection** — page pairs with 80%+ content similarity
- **Search Intent Classification** — informational, commercial, transactional, navigational
- **Content Freshness Scoring** — sitemap lastmod-based stale-content flagging
- **Brand Voice Alignment** — scores each page against a brand voice profile
- **Competitor Gap Analysis** — auto-crawls competitor sites, clusters them, diffs topic maps
- **Cluster Merge Suggestions** — fragmented clusters that should be combined
- **Page Type Classification** — labels every URL (service, blog, case study, etc.)

Ingestion and clustering use local sentence-transformers, without LLM token charges.
Optional LLM advisors and the recommendation agent use Anthropic and incur API costs.

## Reliability improvements

The pipeline now generates similarity, cluster-merge and brand-voice outputs explicitly.
Missing brand data produces an empty table. Semantic similarity and topic membership
are review signals, not proof of duplicate content or harmful search competition.
`potential_topic_overlap.csv` is the descriptive export; `cannibalization.csv` remains
a compatibility alias for existing consumers. Unconfirmed overlap does not contribute
to Site Health. Other health dimensions remain heuristics, not ranking predictions.

Run regression tests with `python -m pytest -q` after installing `requirements-test.txt`.
Tests use a local encoder fixture and do not call paid APIs or download embedding models.
See [implementation notes](docs/reliability.md) for scope and remaining work.

## Isolated audit runs

Each invocation creates `<output-dir>/audits/<site-key>/<run-id>/`, with a matching
cache directory under `<cache-dir>/audits/`. Existing audit files are preserved.
`--output-dir` and `--cache-dir` now specify roots, not the final audit folder.
The CLI prints the exact output directory; Python callers receive it in the result.

- `run_status.html`: execution state, configuration, coverage and failed/skipped analyses.
- `run_manifest.json`: timestamps, stage states, source fingerprint and artifact hashes.
- `crawl.csv`: one row per requested URL, including HTTP status, redirect destination,
  canonical, robots directives, title/H1, word count and extraction outcome.

The root cache stores `active_run.json`, pointing to the most recently started audit
(including a failed audit, so older reports are not mistaken for current ones).
Reusable embeddings and brand profiles are scoped by domain. For standalone commands
with a custom cache root, set `TAM_CACHE_DIR=/path/to/cache`.

The crawler uses sequential requests with connection reuse, two retries for transient
HTTP failures, a five-redirect limit, robots.txt checks and bounded response sizes.
Sitemap discovery handles nested indexes, gzip, duplicate URLs and cycles, with limits
of 100 documents, eight levels and 50,000 URLs. Canonical hints are recorded, not treated
as verified Google selections. `eligible` means no blocking directive was observed;
it does not establish that a page is indexed. No JavaScript rendering is performed.

Freshness uses the same recursive sitemap reader. Missing dates get an HTML fallback
(up to 100 URLs), then `Unknown`; unknown dates do not count as fresh in Site Health.

### Live smoke test (explicit network access)

```bash
TAM_LLM_PROVIDER=none python -m src.main --input examples/smoke-urls.txt \
  --site-name "Python tutorial smoke test" \
  --cache-dir .local/smoke-cache --output-dir .local/smoke-output --no-snapshot
```

This reads eight public Python documentation pages and downloads the local embedding
model if necessary. It does not invoke a paid LLM. Open the output directory printed
by the command. Regular CI tests use controlled fixtures without external network calls.

## Quick Start

```bash
# Clone
git clone <repo-url>
cd topical-authority-mapper

# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run with a sitemap (--site-name optional, defaults to the domain)
python -m src.main --sitemap https://example.com/sitemap.xml --site-name "Example Inc"

# Build the dashboard + PDF
python -m src.dashboard
python -m src.report
```

## Recommended: use a config file

For repeatable runs, define a `site.yaml` once and re-run with `--config`:

```bash
python -m src.main --config examples/site.yaml
python -m src.dashboard
python -m src.report
```

See [`examples/site.yaml`](examples/site.yaml) for the full schema.

## CLI reference

| Flag | Description |
|---|---|
| `--config <path>` | YAML config file. CLI args override any value in the file. |
| `--sitemap <url>` *or* `--input <file>` | What to analyze. One is required. |
| `--site-name "Acme"` | Display label. Defaults to the domain. |
| `--site-domain acme.com` | Bare hostname for URL stripping. Auto-derived if omitted. |
| `--industry b2b-saas` | Optional vertical hint. |
| `--sitemap-url <url>` | Extra sitemap for freshness scoring. Repeatable. |
| `--competitor <domain-or-sitemap>` | Auto-crawl + gap analysis. Repeatable. |
| `--max-urls-per-competitor 100` | Cap on URLs per competitor (default 100). |
| `--skip-pattern "/legal/"` | Extra URL substring to skip. Repeatable. |
| `--listing-pattern "^https?://[^/]+/customers/?$"` | Regex for intentionally thin pages. Repeatable. |
| `--output-dir ./runs/acme` | Per-run output isolation. |
| `--cache-dir ./runs/acme/cache` | Per-run cache isolation. |
| `--brand-voice ./brand.pdf` | Brand voice PDF. |
| `--debug` | Process 10 URLs only, skip FAISS, verbose. |

## Output Files

Outputs go to a new audit subdirectory inside `--output-dir` (default root `./output/`):

| File | Description |
|------|-------------|
| `dashboard.html` | Interactive 11-tab dashboard |
| `Topical_Authority_Audit_<site>_<YYYY_MM>.pdf` | PDF report |
| `clusters.csv` | All topic clusters with keywords |
| `url_mapping.csv` | Every URL mapped to its cluster |
| `cannibalization.csv` | Clusters with competing URLs |
| `recommendations.csv` | Per-cluster content recommendations (brand-voice-aligned) |
| `similarity_scores.csv` | URL pairs with similarity scores + conversion risk flags |
| `search_intent.csv` | Intent classification per URL |
| `content_freshness.csv` | Freshness scores per URL |
| `brand_voice_scores.csv` | Brand voice alignment scores |
| `competitor_<name>_clusters.csv` | Competitor cluster maps (one per competitor) |
| `competitor_gap_<name>.csv` | Per-competitor gap analysis |
| `cluster_merge_suggestions.csv` | Cluster pairs that should be combined |
| `skipped_urls.csv` | Pages filtered out (thin content, legal pages) |

## Brand Voice

Pass a brand voice PDF and the tool extracts a structured profile to
`<cache_dir>/brand_profile.json`. The profile drives:

- Per-cluster content recommendations (tone, angle, CTA style)
- A 0-100 brand voice score per page

You can also write `brand_profile.json` by hand:

```json
{
  "brand_name": "Your Brand",
  "tone": ["strategic", "decisive", "confident"],
  "writing_style": {"sentence_length": "short", "complexity": "intermediate"},
  "audience": "your ICP description",
  "do": ["use clear explanations", "focus on benefits"],
  "dont": ["avoid jargon", "avoid fluff"],
  "tone_lexicon": {
    "strategic": ["framework", "roadmap", "playbook"],
    "data-driven": ["metric", "benchmark", "evidence"]
  }
}
```

The optional `tone_lexicon` field overrides the built-in generic word lists for any tone you specify.
This is how you tune scoring for industry-specific vocabulary without forking the code.

## Competitor Analysis

Pass `--competitor <domain>` (or list them in YAML). The tool will:

1. Auto-discover the competitor's sitemap (tries `/sitemap.xml`, `/sitemap_index.xml`, etc.)
2. Crawl up to `--max-urls-per-competitor` pages
3. Cluster them with the same model used for your site
4. Save `competitor_<name>_clusters.csv`
5. Run gap analysis → `competitor_gap_<name>.csv`

The dashboard and PDF auto-discover any `competitor_gap_*.csv` files at render time, so you can
add competitors incrementally.

You can also call it programmatically:

```python
from src.competitor import run_competitor_analyses
import pandas as pd
target = pd.read_csv("output/clusters.csv")
run_competitor_analyses(["competitor-one.com", "competitor-two.com"], target, "Your Brand")
```

## Architecture

```
src/
  config.py          — constants, SiteConfig dataclass, runtime path resolution
  ingestion.py       — URL fetching, text extraction (trafilatura), chunking, sitemap parsing
  embedding.py       — sentence-transformer embeddings, FAISS index
  clustering.py      — UMAP reduction, HDBSCAN clustering, TF-IDF keyword extraction
  brand_voice.py     — PDF extraction, brand profile JSON, content recommendations
  output.py          — CSV exports, cannibalization detection
  enhancements.py    — similarity, intent, freshness, brand voice scoring, page-type classifier,
                       competitor gap analysis
  competitor.py      — auto-crawl + cluster competitor sites
  dashboard.py       — data prep + dashboard generation
  dashboard_html.py  — tabbed HTML template (Plotly charts)
  report.py          — PDF report generator (HTML → wkhtmltopdf / Chrome headless)
  main.py            — CLI orchestrator + YAML config loader
```

## Tech Stack

- **sentence-transformers** (all-MiniLM-L6-v2) — local embeddings, no API
- **UMAP** + **HDBSCAN** — dimensionality reduction + density-based clustering
- **scikit-learn TF-IDF** — keyword extraction (multi-word, generic terms filtered)
- **FAISS** — fast similarity search index
- **trafilatura** — web content extraction
- **Plotly.js** — interactive charts in dashboard
- **wkhtmltopdf / Chrome headless** — PDF generation
- **pandas / numpy** — data handling
- **PyYAML** — config file parsing

## Configuration knobs

In `src/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `MAX_CHARS_PER_PAGE` | 7000 | Max characters extracted per page |
| `MIN_WORDS_THRESHOLD` | 300 | Below this → flagged as thin |
| `CHUNK_SIZE_WORDS` | 600 | Target words per chunk |
| `UMAP_N_COMPONENTS` | 5 | Dimensions after UMAP reduction |
| `HDBSCAN_MIN_CLUSTER_SIZE` | 3 | Minimum pages to form a cluster |
| `TOP_N_KEYWORDS` | 10 | Keywords extracted per cluster |
| `CANNIBALIZATION_URL_THRESHOLD` | 2 | Min URLs to flag cannibalization |
| `DEBUG_URL_LIMIT` | 10 | URLs processed in debug mode |

## Caching

Embeddings are cached at `<cache_dir>/embeddings.pkl.npz`, with a fingerprint of
the ordered input texts and model identity. Changed inputs, changed model IDs and corrupt
caches trigger recomputation. Old embedding pickles are ignored and never deserialized.
Custom encoders must supply a stable `model_id` to opt into persistent caching.
Changing files requires rerunning the main pipeline before using retrieval or reports.

The site config (`site_config.json`) and brand profile (`brand_profile.json`) also live in
the cache directory.

## Hosted weekly audits via GitHub Actions

The repo ships with a workflow that runs the pipeline weekly against every configured
site in `examples/sites/*.yaml` and uploads outputs as workflow artifacts. It does not
commit snapshots or deploy GitHub Pages. Artifact access follows repository visibility
and GitHub permissions; use a private repository for confidential audit data.

### One-time setup

1. **Push this repo to GitHub** (it must be a GitHub-hosted repo).
2. Enable GitHub Actions. The workflow only requires read access to repository contents.

### Add sites

Drop one YAML per site into [`examples/sites/`](examples/sites/). See [`examples/sites/_README.md`](examples/sites/_README.md) for the schema. A template is shipped in [`examples/sites/example.yaml`](examples/sites/example.yaml).

### Trigger a run

- **Weekly cron:** Mondays at 06:00 UTC, no action needed.
- **Manual:** Actions tab → **Weekly Audit** → Run workflow → optionally pick a single site.

### Where the dashboards live

Download the audit artifact and open the dashboard inside `output/audits/<site-key>/<run-id>/`.
The following Pages paths are examples for a future, separately configured deployment:

```
https://<github-username>.github.io/<repo-name>/                 # Index of all sites
https://<github-username>.github.io/<repo-name>/<site-slug>/dashboard.html
https://<github-username>.github.io/<repo-name>/<site-slug>/exec_summary.html
https://<github-username>.github.io/<repo-name>/<site-slug>/dashboard_artifact.tsx
```

Each card on the index shows the composite Site Health score, totals, last run timestamp,
QA status, and links to the full dashboard, the 1-page exec summary, and the Claude
artifact `.tsx` (downloadable).

### Run snapshots

Each weekly run uploads its outputs as a workflow artifact (14-day retention).
Artifact visibility follows repository permissions. Snapshots are NOT committed back to the repo — keeping per-site
audit data out of a public repo is a hard rule (`runs/` is gitignored). If you
need persistent history, push snapshots to a private sibling repo via deploy key
or PAT.

### Cost

Runtime depends on site size, extraction latency and enabled analyses. Measure actual
workflow duration before estimating runner costs; optional LLM calls are billed separately.
