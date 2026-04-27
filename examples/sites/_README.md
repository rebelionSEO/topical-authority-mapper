# Site configs

Each `*.yaml` file in this directory becomes a site that the GitHub Actions workflow
audits weekly. Files starting with `_` (like this README) and `example.yaml` are skipped.

## Add a site

Copy [example.yaml](example.yaml) and edit:

```yaml
site:
  name: "Acme Inc"          # Display label in titles
  domain: "acme.com"        # Bare hostname
  industry: "b2b-saas"      # Optional vertical hint

input:
  sitemap: "https://acme.com/sitemap.xml"

competitors:
  - "competitor1.com"
  - "competitor2.com"

max_urls_per_competitor: 100   # Cap per competitor

skip_patterns:
  - "/legal/"

listing_patterns:
  - "^https?://[^/]+/customers/?$"
```

Commit, then trigger the workflow:

- **Manual:** Actions → Weekly Audit → Run workflow → optionally pick a single site
- **Automatic:** runs every Monday at 06:00 UTC

After a successful run, the outputs are uploaded as workflow artifacts (private,
14-day retention). Snapshots are NOT committed back to the repo and are NOT
published to GitHub Pages — keeping per-site audit data out of a public repo is
a hard rule. Download the artifact from the workflow run's summary page.

## File naming

The workflow uses each YAML's filename (without extension) as the site slug, both as
the matrix job ID and the artifact name. Use lowercase, no spaces:
`acme.yaml` → artifact `audit-acme`.

## Notes

- The workflow caches the sentence-transformers model and pip deps, so subsequent runs
  are fast (~3-5 min per site after the first run).
- The full pipeline runs locally too — see the project root README for CLI usage.
