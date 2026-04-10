# Topical Authority Mapper

AI-powered SEO tool that maps website content into semantic topic clusters, detects cannibalization, identifies competitor gaps, and generates interactive dashboards and PDF reports.

## What It Does

Takes any website's sitemaps (or a list of URLs), extracts all page content, converts it into AI embeddings, clusters pages by topic, then layers on multiple analysis passes:

- **Topic Clustering** — groups all pages into semantic clusters using UMAP + HDBSCAN
- **Cannibalization Detection** — finds clusters where multiple URLs compete for the same keywords
- **Conversion Risk Analysis** — flags when blog posts compete against service/money pages
- **Near-Duplicate Detection** — identifies page pairs with 80%+ content similarity
- **Search Intent Classification** — categorizes every URL as informational, commercial, transactional, or navigational
- **Content Freshness Scoring** — flags stale content using sitemap lastmod dates
- **Brand Voice Alignment** — scores each page against a brand voice profile (from PDF or JSON)
- **Competitor Gap Analysis** — crawls competitors via Screaming Frog MCP, clusters their content, and diffs topic maps
- **Cluster Merge Suggestions** — detects fragmented clusters that should be combined
- **Page Type Classification** — labels every URL (service, blog, case study, tool review, local landing, etc.)

All processing uses local models. No LLM API calls. Zero token cost.

## Quick Start

```bash
# Clone
git clone https://github.com/rebelionSEO/topical-authority-mapper.git
cd topical-authority-mapper

# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run with a sitemap
python -m src.main --sitemap https://example.com/post-sitemap.xml

# Or with a URL file
python -m src.main --input urls.txt

# With brand voice PDF
python -m src.main --sitemap https://example.com/sitemap.xml --brand-voice brand.pdf

# Debug mode (10 URLs only, skip FAISS)
python -m src.main --sitemap https://example.com/sitemap.xml --debug
```

## Output Files

All outputs go to `output/`:

| File | Description |
|------|-------------|
| `dashboard.html` | Interactive tabbed dashboard (open in any browser) |
| `Topical_Authority_Audit_*.pdf` | PDF report for stakeholders |
| `clusters.csv` | All topic clusters with keywords |
| `url_mapping.csv` | Every URL mapped to its cluster |
| `cannibalization.csv` | Clusters with competing URLs |
| `recommendations.csv` | Content recommendations per cluster (brand voice aligned) |
| `similarity_scores.csv` | URL pairs with similarity scores, page types, conversion risk flags |
| `search_intent.csv` | Intent classification for every URL |
| `content_freshness.csv` | Freshness scores for every URL |
| `brand_voice_scores.csv` | Brand voice alignment scores |
| `competitor_*.csv` | Competitor cluster maps and gap analysis |
| `cluster_merge_suggestions.csv` | Cluster pairs that should be combined |
| `skipped_urls.csv` | Pages filtered out (thin content, legal pages) |

## Generating the Dashboard

```bash
python -m src.dashboard
open output/dashboard.html
```

The dashboard has 11 tabs:

1. **Summary & Actions** — stats, key findings, prioritized action items
2. **Topic Clusters** — treemap + searchable cluster table with drill-down
3. **Cannibalization** — per-cluster analysis with page types and per-URL actions
4. **Duplicates** — similarity pairs with conversion risk detection
5. **Thin Content** — pages needing expansion (excludes listing/archive pages)
6. **Search Intent** — informational / commercial / transactional / navigational split
7. **Freshness** — content age distribution
8. **Brand Voice** — alignment scores and worst-performing pages
9. **Competitors** — topic gap analysis vs competitor sites
10. **Cluster Merges** — fragmented clusters to combine
11. **URL Explorer** — search any URL

## Generating the PDF Report

```bash
python -m src.report
open output/Topical_Authority_Audit_*.pdf
```

Requires Google Chrome installed (uses headless Chrome for PDF conversion).

## Running Enhancements

After the main pipeline runs, generate enhancement analyses:

```python
import pickle, pandas as pd
from src.enhancements import (
    compute_similarity_scores,
    classify_search_intent,
    detect_cluster_merges,
    score_content_freshness,
    score_brand_voice,
    competitor_gap_analysis,
)

# Load cached data
chunks_df = pd.read_pickle('cache/chunks_df.pkl')
with open('cache/embeddings.pkl', 'rb') as f:
    embeddings = pickle.load(f)
clusters = pd.read_csv('output/clusters.csv')

# Run analyses
compute_similarity_scores(chunks_df, embeddings)
classify_search_intent(chunks_df)
detect_cluster_merges(clusters, chunks_df, embeddings)
score_content_freshness([])
score_brand_voice(chunks_df)
```

## Competitor Analysis

Requires [Screaming Frog MCP](https://github.com/) connection for crawling competitor sites.

```bash
# Crawl competitors via SF MCP, then:
python3 -c "
from src.enhancements import competitor_gap_analysis
import pandas as pd

azarian = pd.read_csv('output/clusters.csv')
competitor = pd.read_csv('output/competitor_nogood_clusters.csv')
competitor_gap_analysis(azarian, competitor, 'NoGood')
"
```

## Brand Voice

The tool accepts a brand voice PDF document and converts it into a structured JSON profile (`cache/brand_profile.json`). The PDF is processed once and never re-read. The profile is used to:

- Generate tone-aligned content recommendations per cluster
- Score every page's brand voice alignment (0-100)

You can also manually create `cache/brand_profile.json`:

```json
{
  "brand_name": "Your Brand",
  "tone": ["strategic", "decisive", "confident"],
  "writing_style": {
    "sentence_length": "short",
    "complexity": "intermediate"
  },
  "audience": "CMOs and marketing leaders at growth-stage companies",
  "do": ["use clear explanations", "focus on benefits", "be direct"],
  "dont": ["avoid jargon", "avoid fluff", "avoid hype"],
  "example_phrases": [],
  "content_goals": ["convert", "build trust", "educate"]
}
```

## Architecture

```
src/
  config.py          — constants, thresholds, skip patterns
  ingestion.py       — URL fetching, text extraction (trafilatura), chunking, sitemap parsing
  embedding.py       — sentence-transformer embeddings, FAISS index
  clustering.py      — UMAP reduction, HDBSCAN clustering, TF-IDF keyword extraction
  brand_voice.py     — PDF extraction, brand profile JSON, content recommendations
  output.py          — CSV exports, cannibalization detection
  main.py            — pipeline orchestrator with CLI
  enhancements.py    — similarity scoring, intent classification, freshness, brand voice,
                       competitor gaps, cluster merges, page type classification
  dashboard.py       — data preparation for dashboard
  dashboard_html.py  — tabbed HTML template with Plotly charts
  report.py          — PDF report generator (HTML → Chrome headless → PDF)
```

## Tech Stack

- **sentence-transformers** (all-MiniLM-L6-v2) — text embeddings (local, no API)
- **UMAP** — dimensionality reduction
- **HDBSCAN** — density-based clustering
- **scikit-learn TF-IDF** — keyword extraction (2-3 word phrases, generic terms filtered)
- **FAISS** — fast similarity search index
- **trafilatura** — web content extraction
- **Plotly.js** — interactive charts in dashboard
- **Chrome headless** — PDF generation
- **Screaming Frog MCP** — competitor crawling (optional)
- **pandas / numpy** — data handling

## Configuration

Key settings in `src/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `MAX_CHARS_PER_PAGE` | 7000 | Max characters extracted per page |
| `MIN_WORDS_THRESHOLD` | 300 | Pages below this are flagged as thin |
| `CHUNK_SIZE_WORDS` | 600 | Target words per chunk (500-700 range) |
| `UMAP_N_COMPONENTS` | 5 | Dimensions after UMAP reduction |
| `HDBSCAN_MIN_CLUSTER_SIZE` | 3 | Minimum pages to form a cluster |
| `TOP_N_KEYWORDS` | 10 | Keywords extracted per cluster |
| `CANNIBALIZATION_URL_THRESHOLD` | 2 | Min URLs to flag cannibalization |
| `DEBUG_URL_LIMIT` | 10 | URLs processed in debug mode |

## Caching

The tool caches embeddings (`cache/embeddings.pkl`) and the brand profile (`cache/brand_profile.json`). Delete the cache directory to force recomputation:

```bash
rm -rf cache/
```

## Using with Claude AI

A condensed data file (`output/dashboard_data.json`, ~94KB) and prompt (`output/claude_artifact_prompt.md`) are generated for recreating the dashboard as a Claude AI artifact. Paste the prompt into claude.ai and attach the JSON file.
