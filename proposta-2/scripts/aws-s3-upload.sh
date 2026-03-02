#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Proposta 2 — Upload para S3: Meta (NDJSON) + Detail (JSON por jornada)
#
# Estrutura no bucket:
#   jornadas/meta/data=YYYY-MM-DD/records.json   → crawleado pelo Glue / Athena
#   jornadas/detail/{idJornada}.json             → download via presigned URL
#
# Bucket : bucket-logs-eventos
# Região : us-east-1
# Auth   : credenciais locais (~/.aws/credentials)
# ---------------------------------------------------------------------------

BUCKET="bucket-logs-eventos"
REGION="us-east-1"
S3_PREFIX="jornadas"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)/jornadas"

AWS_PROFILE="${AWS_PROFILE:-default}"

# Validade padrão das presigned URLs em segundos (1 hora)
PRESIGN_EXPIRES="${PRESIGN_EXPIRES:-3600}"

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
# Funções auxiliares
# ---------------------------------------------------------------------------

upload_meta() {
  echo "--------------------------------------------------------"
  echo "  [1/2] Subindo arquivos META (NDJSON particionado por data)"
  echo "        Destino: s3://$BUCKET/$S3_PREFIX/meta/"
  echo "--------------------------------------------------------"

  aws s3 sync "$LOCAL_DIR/meta" "s3://$BUCKET/$S3_PREFIX/meta/" \
    --region "$REGION" \
    --profile "$AWS_PROFILE" \
    --exclude "*.DS_Store" \
    --exclude ".gitkeep" \
    --content-type "application/json" \
    --no-progress

  echo "  Meta enviado."
}

upload_detail() {
  echo "--------------------------------------------------------"
  echo "  [2/2] Subindo arquivos DETAIL (JSON por jornada)"
  echo "        Destino: s3://$BUCKET/$S3_PREFIX/detail/"
  echo "--------------------------------------------------------"

  aws s3 sync "$LOCAL_DIR/detail" "s3://$BUCKET/$S3_PREFIX/detail/" \
    --region "$REGION" \
    --profile "$AWS_PROFILE" \
    --exclude "*.DS_Store" \
    --exclude ".gitkeep" \
    --content-type "application/json" \
    --no-progress

  echo "  Detail enviado."
}

# Gera presigned URL para download do arquivo de detalhe de uma jornada
# Uso: presign_detail <idJornada> <data=YYYY-MM-DD> [expires_in_seconds]
presign_detail() {
  local id_jornada="$1"
  local data_particao="${2:?'Informe a data no formato data=YYYY-MM-DD'}"
  local expires="${3:-$PRESIGN_EXPIRES}"
  local s3_key="$S3_PREFIX/detail/${data_particao}/${id_jornada}.json"

  echo "  Gerando presigned URL para: $id_jornada (válida por ${expires}s)"
  aws s3 presign "s3://$BUCKET/$s3_key" \
    --region "$REGION" \
    --profile "$AWS_PROFILE" \
    --expires-in "$expires"
}

# ---------------------------------------------------------------------------
# Execução principal
# ---------------------------------------------------------------------------

echo "========================================================"
echo "  LogViz — Upload Proposta 2 (Meta + Detail)"
echo "  Origem  : $LOCAL_DIR"
echo "  Bucket  : s3://$BUCKET/$S3_PREFIX/"
echo "  Região  : $REGION"
echo "  Perfil  : $AWS_PROFILE"
echo "========================================================"
echo ""

upload_meta
echo ""
upload_detail

echo ""
echo "========================================================"
echo "  Upload concluído."
echo ""
echo "  Athena — apenas a tabela meta é consultada:"
echo "    LOCATION: s3://$BUCKET/$S3_PREFIX/meta/"
echo ""
echo "  Exemplo de query:"
echo "    SELECT idJornada, canal, produto, dataHoraInicio,"
echo "           total_erros_integracao, s3_detail_path"
echo "    FROM jornadas_meta"
echo "    WHERE data = '2024-06-15'"
echo "      AND total_erros_integracao > 0;"
echo ""
echo "  Para baixar o detalhe de uma jornada específica:"
  echo "    AWS CLI : aws s3 presign s3://$BUCKET/$S3_PREFIX/detail/data=YYYY-MM-DD/<idJornada>.json --expires-in $PRESIGN_EXPIRES"
  echo "    Script  : presign_detail <idJornada> <data=YYYY-MM-DD>  (source este script e chame a função)"
echo "========================================================"
