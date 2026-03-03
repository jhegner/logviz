#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Delete S3 bucket content recursively
#
# Removes all objects under a given prefix (or the entire bucket) using
# `aws s3 rm --recursive`. Supports dry-run mode and optional prefix filter.
#
# Bucket : bucket-logs-eventos
# Região : us-east-1
# Auth   : credenciais locais (~/.aws/credentials)
#
# Usage:
#   ./aws-s3-delete.sh                        # deletes all objects in bucket
#   ./aws-s3-delete.sh jornadas/meta          # deletes only the given prefix
#   DRY_RUN=true ./aws-s3-delete.sh           # preview without deleting
#   PREFIX=jornadas/detail DRY_RUN=true \
#     ./aws-s3-delete.sh                      # preview for a specific prefix
# ---------------------------------------------------------------------------

BUCKET="bucket-logs-eventos"
REGION="us-east-1"
AWS_PROFILE="${AWS_PROFILE:-default}"

# Optional prefix — if empty, the entire bucket content is targeted
PREFIX="${1:-${PREFIX:-}}"

# Set DRY_RUN=true to preview the objects that would be deleted without
# actually removing them.
DRY_RUN="${DRY_RUN:-false}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log()  { echo "[INFO]  $*"; }
warn() { echo "[AVISO] $*"; }
err()  { echo "[ERRO]  $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if ! command -v aws &>/dev/null; then
  err "AWS CLI não encontrado. Instale: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
fi

if ! aws s3 ls "s3://$BUCKET" --region "$REGION" --profile "$AWS_PROFILE" &>/dev/null; then
  err "Bucket '$BUCKET' não acessível na região '$REGION' com o perfil '$AWS_PROFILE'." \
      "Verifique ~/.aws/credentials e as permissões IAM."
fi

# ---------------------------------------------------------------------------
# Build target path
# ---------------------------------------------------------------------------

if [[ -n "$PREFIX" ]]; then
  # Normalise: strip leading/trailing slashes
  PREFIX="${PREFIX#/}"
  PREFIX="${PREFIX%/}"
  TARGET="s3://$BUCKET/$PREFIX/"
else
  TARGET="s3://$BUCKET/"
fi

# ---------------------------------------------------------------------------
# Confirmation prompt (skipped when stdin is not a terminal, e.g. CI)
# ---------------------------------------------------------------------------

warn "Alvo           : $TARGET"
warn "Região         : $REGION"
warn "Perfil AWS     : $AWS_PROFILE"

if [[ "$DRY_RUN" == "true" ]]; then
  warn "Modo           : DRY-RUN (nenhum objeto será removido)"
else
  warn "Modo           : EXCLUSÃO REAL"
fi

echo ""

if [[ -t 0 && "$DRY_RUN" != "true" ]]; then
  read -r -p "Confirma a exclusão recursiva de '$TARGET'? [s/N] " CONFIRM
  case "$CONFIRM" in
    [sS]|[sS][iI][mM]) : ;;
    *) log "Operação cancelada pelo usuário."; exit 0 ;;
  esac
fi

# ---------------------------------------------------------------------------
# List objects (dry-run) or delete recursively
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" == "true" ]]; then
  log "Objetos que seriam excluídos em '$TARGET':"
  aws s3 ls "$TARGET" \
    --recursive \
    --region "$REGION" \
    --profile "$AWS_PROFILE" \
    --human-readable \
    --summarize
  log "Dry-run concluído. Nenhum objeto foi removido."
else
  log "Iniciando exclusão recursiva de '$TARGET'..."

  aws s3 rm "$TARGET" \
    --recursive \
    --region "$REGION" \
    --profile "$AWS_PROFILE"

  log "Exclusão concluída com sucesso."

  # Verify the target is now empty
  REMAINING=$(aws s3 ls "$TARGET" --recursive --region "$REGION" --profile "$AWS_PROFILE" | wc -l)
  if [[ "$REMAINING" -eq 0 ]]; then
    log "Verificação OK — nenhum objeto restante em '$TARGET'."
  else
    warn "Ainda existem $REMAINING objeto(s) em '$TARGET'. Verifique manualmente."
  fi
fi
