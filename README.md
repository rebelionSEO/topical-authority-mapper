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
- **Cannibalization Detection** — flags clusters where multiple URLs compete for the same keywords
- **Conversion Risk Analysis** — flags blog posts competing against service/money pages
- **Near-Duplicate Detection** — page pairs with 80%+ content similarity
- **Search Intent Classification** — informational, commercial, transactional, navigational
- **Content Freshness Scoring** — sitemap lastmod-based stale-content flagging
- **Brand Voice Alignment** — scores each page against a brand voice profile
- **Competitor Gap Analysis** — auto-crawls competitor sites, clusters them, diffs topic maps
- **Cluster Merge Suggestions** — fragmented clusters that should be combined
- **Page Type Classification** — labels every URL (service, blog, case study, etc.)

All ingestion + clustering uses local sentence-transformers. No LLM API calls. Zero token cost.

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

All outputs go to `--output-dir` (default `./output/`):

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

Embeddings are cached at `<cache_dir>/embeddings.pkl`. Delete the cache directory to force a
full recomputation:

```bash
rm -rf cache/
```

The site config (`site_config.json`) and brand profile (`brand_profile.json`) also live in
the cache directory.

## Hosted weekly audits via GitHub Actions

The repo ships with a workflow that runs the pipeline weekly against every site config
in `examples/sites/*.yaml`, commits the snapshot back to the repo, and publishes the
dashboards to GitHub Pages.

### One-time setup

1. **Push this repo to GitHub** (it must be a GitHub-hosted repo).
2. **Enable Pages:** repo → Settings → Pages → Source: **GitHub Actions**.
3. **Allow Actions to write to the repo:** Settings → Actions → General → Workflow permissions: **Read and write permissions**.

### Add sites

Drop one YAML per site into [`examples/sites/`](examples/sites/). See [`examples/sites/_README.md`](examples/sites/_README.md) for the schema. A real example is shipped in [`examples/sites/acme.yaml`](examples/sites/acme.yaml).

### Trigger a run

- **Weekly cron:** Mondays at 06:00 UTC, no action needed.
- **Manual:** Actions tab → **Weekly Audit** → Run workflow → optionally pick a single site.

### Where the dashboards live

After the first successful run, your dashboards are at:

```
https://<github-username>.github.io/<repo-name>/                 # Index of all sites
https://<github-username>.github.io/<repo-name>/<site-slug>/dashboard.html
https://<github-username>.github.io/<repo-name>/<site-slug>/exec_summary.html
https://<github-username>.github.io/<repo-name>/<site-slug>/dashboard_artifact.tsx
```

Each card on the index shows the composite Site Health score, totals, last run timestamp,
QA status, and links to the full dashboard, the 1-page exec summary, and the Claude
artifact `.tsx` (downloadable).

### Run snapshots (the version-controlled history)

Every successful run is committed back to the repo at `runs/<site-slug>/<timestamp>/`,
including the full output dir + site_config + qa_report. So `git log runs/acme/` shows
the audit history for that site, and any past dashboard is one `git checkout` away.

### Cost

Free tier covers it: ~5-8 min per site per run with the model + pip cache warm. With
4 sites running weekly that's ~25 min/month, well under the GitHub Actions free
allotment (2,000 minutes/month for free accounts).
