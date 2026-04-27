#!/bin/bash
# One-shot script: run an audit pipeline, then deploy the live dashboard to a
# WordPress-hosted subdirectory via SSH/rsync.
#
# Safety:
#   - Reads SSH config from ~/.seolab-creds.env (SSH_HOST, SSH_PORT, SSH_USER, WP_ROOT)
#   - Deploys ONLY into a dedicated subdirectory of WP_ROOT (set via --target)
#   - Refuses to deploy if the target path looks suspicious
#   - Uses rsync without --delete on the first push (safe: existing files preserved
#     under other paths)
#   - Local pipeline run can be skipped with --skip-pipeline if you've already run it
#
# Usage:
#   ./scripts/ship.sh --target acme-audit --config examples/sites/acme.yaml
#   ./scripts/ship.sh --skip-pipeline --target acme-audit  # redeploy current output/
#   ./scripts/ship.sh --target acme-audit --dry-run        # preview, no SSH writes

set -euo pipefail

# Resolve project root (this script lives in scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Args ---
SKIP_PIPELINE=false
DRY_RUN=false
TARGET_SLUG=""
SITE_CONFIG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-pipeline) SKIP_PIPELINE=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --target) TARGET_SLUG="$2"; shift 2 ;;
    --config) SITE_CONFIG="$2"; shift 2 ;;
    -h|--help)
      grep '^#' "$0" | head -25
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# --- Required args ---
if [[ -z "$TARGET_SLUG" ]]; then
  echo "❌ --target is required (deploy subdirectory under WP_ROOT, e.g. acme-audit)" >&2
  exit 1
fi
if [[ -z "$SITE_CONFIG" && "$SKIP_PIPELINE" == "false" ]]; then
  echo "❌ --config is required when running the pipeline (path to a site YAML)" >&2
  exit 1
fi

# --- Sanity checks on target slug ---
if [[ ! "$TARGET_SLUG" =~ ^[a-z0-9-]+$ ]]; then
  echo "❌ --target must be lowercase letters, numbers, hyphens only (got: $TARGET_SLUG)" >&2
  exit 1
fi
if [[ "$TARGET_SLUG" == "wp-admin" || "$TARGET_SLUG" == "wp-content" || "$TARGET_SLUG" == "wp-includes" ]]; then
  echo "❌ Refusing to deploy to a reserved WordPress path: $TARGET_SLUG" >&2
  exit 1
fi

# --- Load SSH creds ---
CREDS="$HOME/.seolab-creds.env"
if [[ ! -f "$CREDS" ]]; then
  echo "❌ Missing $CREDS — required for SSH deploy. Aborting." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$CREDS"

for var in SSH_HOST SSH_PORT SSH_USER WP_ROOT; do
  if [[ -z "${!var:-}" ]]; then
    echo "❌ $var not set in $CREDS" >&2
    exit 1
  fi
done

REMOTE_DIR="$WP_ROOT/$TARGET_SLUG"
SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"

# Defensive: REMOTE_DIR must contain TARGET_SLUG and not be a known WP path
case "$REMOTE_DIR" in
  *"$TARGET_SLUG"*) ;;
  *) echo "❌ Computed remote path doesn't contain target slug — refusing." >&2; exit 1 ;;
esac

# --- Step 1: run the pipeline (unless skipped) ---
cd "$PROJECT_ROOT"

if [[ "$SKIP_PIPELINE" == "false" ]]; then
  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "  Step 1/3 — Running pipeline (config: $SITE_CONFIG)"
  echo "  ETA: ~25-40 min on first run (model download + 6 competitors)"
  echo "════════════════════════════════════════════════════════════"

  if [[ ! -d "venv" ]]; then
    echo "❌ venv/ not found at $PROJECT_ROOT — create it first:" >&2
    echo "   python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt" >&2
    exit 1
  fi

  # shellcheck source=/dev/null
  source venv/bin/activate

  python -m src.main --config "$SITE_CONFIG"
else
  echo "→ Skipping pipeline (--skip-pipeline)"
  if [[ ! -d "venv" ]]; then
    echo "❌ venv/ not found at $PROJECT_ROOT" >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  source venv/bin/activate
fi

# --- Step 1b: render dashboard + PDF + exec summary + Claude artifact ---
# These read from the output dir, so they work whether main ran fresh or we --skip-pipeline.
# Re-running them is idempotent and ensures the artifacts always reflect the current data.
echo ""
echo "→ Recomputing site health (so exec/artifact pick up any post-pipeline edits)..."
python -m src.site_health --quiet || true
echo "→ Rendering dashboard.html..."
python -m src.dashboard
echo "→ Rendering exec summary..."
python -m src.exec_summary
echo "→ Rendering Claude artifact..."
python -m src.dashboard_artifact
echo "→ Rendering PDF report..."
python -m src.report || echo "   (PDF render skipped — wkhtmltopdf or Chrome not found; HTML report still produced)"

# --- Step 2: verify output ---
DASHBOARD="$PROJECT_ROOT/output/dashboard.html"
EXEC_SUMMARY="$PROJECT_ROOT/output/exec_summary.html"

if [[ ! -f "$DASHBOARD" ]]; then
  echo "❌ $DASHBOARD not found. Pipeline must have failed." >&2
  exit 1
fi

DASHBOARD_SIZE=$(wc -c < "$DASHBOARD")
echo ""
echo "→ Local outputs ready:"
echo "   dashboard.html        $(printf '%6d' $DASHBOARD_SIZE) bytes"
[[ -f "$EXEC_SUMMARY" ]] && echo "   exec_summary.html     $(printf '%6d' $(wc -c < "$EXEC_SUMMARY")) bytes"
[[ -f "$PROJECT_ROOT/output/dashboard_artifact.tsx" ]] && echo "   dashboard_artifact.tsx $(printf '%6d' $(wc -c < "$PROJECT_ROOT/output/dashboard_artifact.tsx")) bytes"

# --- Step 3: deploy ---
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Step 2/3 — Deploying to $SSH_USER@$SSH_HOST:$REMOTE_DIR"
echo "════════════════════════════════════════════════════════════"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "→ DRY RUN — would rsync $PROJECT_ROOT/output/ → $REMOTE_DIR/"
  rsync -avz --dry-run -e "ssh $SSH_OPTS -p $SSH_PORT" \
    --exclude=".DS_Store" --exclude="*.csv" --exclude="*.json" --exclude="report.html" \
    "$PROJECT_ROOT/output/" "$SSH_USER@$SSH_HOST:$REMOTE_DIR/"
  echo ""
  echo "→ Skipping actual deploy (--dry-run)"
  exit 0
fi

# Create remote dir + an .htaccess that prevents directory listing
ssh $SSH_OPTS -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "mkdir -p '$REMOTE_DIR'"

# Copy dashboard.html → index.html locally so the URL root works
cp "$DASHBOARD" "$PROJECT_ROOT/output/index.html"

# Push only the rendered files (skip raw CSVs, JSONs, the in-progress report.html)
rsync -avz -e "ssh $SSH_OPTS -p $SSH_PORT" \
  --exclude=".DS_Store" \
  --exclude="*.csv" \
  --exclude="*.json" \
  --exclude="report.html" \
  --exclude="Topical_Authority_Audit_*.pdf" \
  "$PROJECT_ROOT/output/" "$SSH_USER@$SSH_HOST:$REMOTE_DIR/"

# Optional: push the PDF too, with a stable name
PDF=$(ls "$PROJECT_ROOT"/output/Topical_Authority_Audit_*.pdf 2>/dev/null | head -1)
if [[ -n "$PDF" ]]; then
  scp $SSH_OPTS -P "$SSH_PORT" -q "$PDF" "$SSH_USER@$SSH_HOST:$REMOTE_DIR/audit.pdf"
  echo "   PDF deployed as audit.pdf"
fi

# Tidy up the local index.html copy (the original dashboard.html is the source of truth)
rm -f "$PROJECT_ROOT/output/index.html"

# --- Step 4: print URLs + sanity check ---
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Step 3/3 — Live"
echo "════════════════════════════════════════════════════════════"

# Best-effort domain inference from the WP_ROOT path
DOMAIN="${WP_SITE:-https://geramejia.com}"
DOMAIN="${DOMAIN%/}"

echo ""
echo "  Live dashboard:   $DOMAIN/$TARGET_SLUG/"
echo "  1-page summary:   $DOMAIN/$TARGET_SLUG/exec_summary.html"
echo "  Claude artifact:  $DOMAIN/$TARGET_SLUG/dashboard_artifact.tsx (download)"
[[ -n "$PDF" ]] && echo "  PDF report:       $DOMAIN/$TARGET_SLUG/audit.pdf"
echo ""
echo "  Open locally:     open $PROJECT_ROOT/output/dashboard.html"
echo ""

# Optionally open the live URL in the default browser
if command -v open >/dev/null 2>&1; then
  read -p "Open the live URL in your browser now? (y/N): " ans
  if [[ "$ans" == "y" ]]; then
    open "$DOMAIN/$TARGET_SLUG/"
  fi
fi

echo "🎉 Done."
