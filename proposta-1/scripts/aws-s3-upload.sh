#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Upload das jornadas para S3
# Bucket : bucket-logs-eventos
# Região : us-east-1
# Auth   : credenciais locais (~/.aws/credentials)
# ---------------------------------------------------------------------------

BUCKET="bucket-logs-eventos"
REGION="us-east-1"
S3_PREFIX="jornadas"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)/jornadas"

# Perfil AWS (deixe vazio para usar o default)
AWS_PROFILE="${AWS_PROFILE:-default}"

# ---------------------------------------------------------------------------
# Verificações
# ---------------------------------------------------------------------------

if ! command -v aws &>/dev/null; then
  echo "[ERRO] AWS CLI não encontrado. Instale: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
  exit 1
fi

if [[ ! -d "$LOCAL_DIR" ]]; then
  echo "[ERRO] Diretório local não encontrado: $LOCAL_DIR"
  exit 1
fi

if ! aws s3 ls "s3://$BUCKET" --region "$REGION" --profile "$AWS_PROFILE" &>/dev/null; then
  echo "[ERRO] Bucket '$BUCKET' não acessível na região '$REGION' com o perfil '$AWS_PROFILE'."
  echo "       Verifique ~/.aws/credentials e as permissões IAM."
  exit 1
fi

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

echo "========================================================"
echo "  Iniciando upload para s3://$BUCKET/$S3_PREFIX/"
echo "  Origem  : $LOCAL_DIR"
echo "  Região  : $REGION"
echo "  Perfil  : $AWS_PROFILE"
echo "========================================================"

aws s3 sync "$LOCAL_DIR" "s3://$BUCKET/$S3_PREFIX/" \
  --region "$REGION" \
  --profile "$AWS_PROFILE" \
  --exclude "*.DS_Store" \
  --exclude ".gitkeep" \
  --content-type "application/json" \
  --no-progress

echo ""
echo "========================================================"
echo "  Upload concluído."
echo ""
echo "  Tabelas no Athena — use LOCATION:"
echo "    meta        -> s3://$BUCKET/$S3_PREFIX/meta/"
echo "    servicos    -> s3://$BUCKET/$S3_PREFIX/servicos/"
echo "    integracoes -> s3://$BUCKET/$S3_PREFIX/integracoes/"
echo "========================================================"
