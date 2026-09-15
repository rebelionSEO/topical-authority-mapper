# Validation

## Automated regression suite

Run `python -m pytest -q` after installing `requirements-test.txt`.
Local result: 21 passed (two expected UMAP warnings about deterministic execution).
Fixtures cover changed/reordered embedding inputs, corrupt and legacy caches, small
sites, numeric cluster labels, empty report tables, brand isolation, complete artifact
generation, retrieval, nested/gzipped/cyclic sitemaps, partial sitemap failure, URL
normalization, robots/noindex/canonical signals, redirects, HTTP failures, bounded
responses, missing dates, audit isolation, failed audits and manifest checksums.

## Public-site smoke test — 2026-09-15

Input: eight URLs in `examples/smoke-urls.txt` (Python tutorial documentation).
Environment: macOS ARM64, Python 3.14, local `all-MiniLM-L6-v2`, LLM disabled.

Observed successful run:

- Eight requested and analyzed pages, zero skipped requests.
- Eighteen text chunks and two clusters.
- Eight freshness records with HTML-derived dates.
- Thirteen intra-cluster similarity rows.
- QA: zero critical findings and zero warnings.
- Dashboard, executive summary, vector map, manifest, status page and PDF generated.
- Brand analysis and competitors omitted because no inputs were supplied.
- A second successful audit reused the embedding cache, preserved earlier output
  directories, and generated a historical snapshot. All 21 artifact hashes matched.

An earlier run failed QA because a numeric code example became a cluster label.
The run stopped before report generation and retained its failed manifest. The label
extractor was corrected and the case added to the regression suite.

The live test validates pipeline execution and output consistency, not the semantic
accuracy of clusters or SEO recommendations. Reports remain heuristic. Audit outputs,
downloaded models and machine-local paths are excluded from Git.
