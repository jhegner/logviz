#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Proposta 3 — Upload para S3: Meta + Detail com particionamento 3 níveis
#
# Estrutura no bucket:
#   jornadas/meta/ano=YYYY/mes=MM/dia=DD/records.json          → crawleado pelo Glue / Athena
#   jornadas/detail/ano=YYYY/mes=MM/dia=DD/{idJornada}.json    → download via presigned URL
#
# Vantagens sobre proposta 2 (data=YYYY-MM-DD):
#   - S3 Lifecycle por prefixo de ano ou mês inteiro (sem datas exatas)
#   - Partition pruning real no Athena para queries por mês/ano
#   - Menor custo de scan no Athena (3 colunas de partição independentes)
#
# Bucket : bucket-logs-eventos
# Região : us-east-1
# Auth   : credenciais locais (~/.aws/credentials)
# ---------------------------------------------------------------------------

BUCKET="bucket-logs-eventos"
REGION="us-east-1"
S3_PREFIX="jornadas"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)/proposta-3/jornadas"

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
  echo "  [1/2] Subindo arquivos META (NDJSON — 3 níveis de partição)"
  echo "        Partição : ano=YYYY/mes=MM/dia=DD"
  echo "        Destino  : s3://$BUCKET/$S3_PREFIX/meta/"
  echo "        Crawleado pelo Glue — colunas de partição: ano, mes, dia"
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
  echo "  [2/2] Subindo arquivos DETAIL (JSON por jornada — 3 níveis de partição)"
  echo "        Partição : ano=YYYY/mes=MM/dia=DD"
  echo "        Destino  : s3://$BUCKET/$S3_PREFIX/detail/"
  echo "        NÃO crawleado — acessado via presigned URL"
  echo "        Partition pruning de Lifecycle aplica por prefixo de ano ou mês"
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
# Uso: presign_detail <idJornada> <ano> <mes> <dia> [expires_in_seconds]
# Exemplo: presign_detail J12345 2024 06 15
presign_detail() {
  local id_jornada="${1:?'Informe o idJornada (ex: J12345)'}"
  local ano="${2:?'Informe o ano (ex: 2024)'}"
  local mes="${3:?'Informe o mes com zero (ex: 06)'}"
  local dia="${4:?'Informe o dia com zero (ex: 15)'}"
  local expires="${5:-$PRESIGN_EXPIRES}"
  local s3_key="$S3_PREFIX/detail/ano=${ano}/mes=${mes}/dia=${dia}/${id_jornada}.json"

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
echo "  LogViz — Upload Proposta 3 (Meta + Detail, 3 níveis)"
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
echo "  Athena — colunas de partição: ano, mes, dia"
echo "    LOCATION: s3://$BUCKET/$S3_PREFIX/meta/"
echo ""
echo "  Exemplos de query:"
echo "    -- Dia exato"
echo "    SELECT idJornada, canal, s3_detail_path"
echo "    FROM jornadas_meta"
echo "    WHERE ano='2024' AND mes='06' AND dia='15';"
echo ""
echo "    -- Mês inteiro"
echo "    SELECT canal, COUNT(*) FROM jornadas_meta"
echo "    WHERE ano='2024' AND mes='06' GROUP BY canal;"
echo ""
echo "    -- Ano inteiro com erros"
echo "    SELECT idJornada, total_erros_integracao, s3_detail_path"
echo "    FROM jornadas_meta"
echo "    WHERE ano='2024' AND total_erros_integracao > 0;"
echo ""
echo "  Para baixar o detalhe de uma jornada:"
echo "    AWS CLI : aws s3 presign s3://$BUCKET/$S3_PREFIX/detail/ano=YYYY/mes=MM/dia=DD/<idJornada>.json --expires-in $PRESIGN_EXPIRES"
echo "    Script  : presign_detail <idJornada> <ano> <mes> <dia>  (source este script e chame a função)"
echo ""
echo "  S3 Lifecycle — exemplo de regra por ano inteiro:"
echo "    Prefixo: jornadas/detail/ano=2023/ → transição para GLACIER ou expiração"
echo "========================================================"
