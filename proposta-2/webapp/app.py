"""LogViz — JSON file viewer for jornadas-detail on AWS S3.

Run locally:
    streamlit run app.py

Configuration (via sidebar or environment variables):
    S3_BUCKET  : S3 bucket name
    S3_PREFIX  : prefix inside the bucket (default: jornadas/detail)
    AWS_REGION : AWS region (optional)
    AWS_PROFILE: named profile from ~/.aws/credentials (optional)
"""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st

from s3_client import S3Client

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="LogViz — Jornadas Detail Viewer",
    page_icon="📋",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_client(bucket: str, prefix: str, region: str, profile: str) -> S3Client:
    return S3Client(
        bucket=bucket,
        prefix=prefix,
        region=region or None,
        profile=profile or None,
    )


def _format_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _status_badge(code: int) -> str:
    """Return a colored Markdown badge for an HTTP status code."""
    if code < 300:
        color = "green"
    elif code < 400:
        color = "orange"
    else:
        color = "red"
    return f":{color}[**{code}**]"


def _render_summary(data: dict[str, Any]) -> None:
    """Render a structured summary of the jornada JSON."""
    meta = data.get("meta", {})
    etapas = data.get("etapas", [])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("ID Jornada", data.get("idJornada", "—"))
    col2.metric("Canal", meta.get("canal", "—"))
    col3.metric("Produto", meta.get("produto", "—"))
    col4.metric("Ambiente", meta.get("ambiente", "—"))

    if meta.get("resumo_ia"):
        st.info(f"🤖 **Resumo IA:** {meta['resumo_ia']}")

    st.markdown(
        f"**Início:** {meta.get('dataHoraInicio', '—')} "
        f"&nbsp;|&nbsp; **Fim:** {meta.get('dataHoraFim', '—')}"
    )

    if not etapas:
        return

    st.markdown("---")
    st.markdown(f"### 🔄 Etapas ({len(etapas)})")

    for etapa in etapas:
        servicos = etapa.get("servicos", [])
        with st.expander(
            f"**{etapa.get('nome', 'Etapa')}** — "
            f"{etapa.get('dataHoraInicio', '')} → {etapa.get('dataHoraFim', '')} "
            f"({len(servicos)} serviço(s))"
        ):
            for svc in servicos:
                code = svc.get("statusCode", 0)
                st.markdown(
                    f"#### 🔧 {svc.get('nome', 'Serviço')} "
                    f"`{svc.get('method', '')} {svc.get('url', '')}` "
                    f"→ {_status_badge(code)}"
                )
                tabs = st.tabs(["Request", "Response", "Integrações", "Headers"])
                with tabs[0]:
                    st.json(svc.get("httpRequest", {}))
                with tabs[1]:
                    st.json(svc.get("httpResponse", {}))
                with tabs[2]:
                    integracoes = svc.get("integracoes", [])
                    if not integracoes:
                        st.caption("Sem integrações.")
                    for integ in integracoes:
                        i_code = integ.get("statusCode", 0)
                        st.markdown(
                            f"- {_status_badge(i_code)} **{integ.get('nome', '')}** "
                            f"`{integ.get('method', '')} {integ.get('url', '')}`"
                        )
                with tabs[3]:
                    headers = svc.get("header", {})
                    if headers:
                        st.json(headers)
                    else:
                        st.caption("Sem headers.")


# ---------------------------------------------------------------------------
# Sidebar — connection settings
# ---------------------------------------------------------------------------

st.sidebar.title("⚙️ Configurações S3")

bucket = st.sidebar.text_input(
    "Bucket S3",
    value=os.environ.get("S3_BUCKET", "bucket-logs-eventos"),
    help="Nome do bucket S3 que contém os arquivos de jornadas.",
)
prefix = st.sidebar.text_input(
    "Prefix",
    value=os.environ.get("S3_PREFIX", "jornadas/detail"),
    help="Prefixo dentro do bucket (ex.: jornadas/detail).",
)
region = st.sidebar.text_input(
    "Região AWS",
    value=os.environ.get("AWS_REGION", "us-east-1"),
    help="Região do bucket (ex.: us-east-1).",
)
aws_profile = st.sidebar.text_input(
    "AWS Profile",
    value=os.environ.get("AWS_PROFILE", "default"),
    help="Perfil de ~/.aws/credentials. Deixe 'default' para usar as credenciais padrão.",
)

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

st.title("📋 LogViz — Visualizador de Jornadas")
st.caption(
    f"Navegando em **s3://{bucket}/{prefix}/** "
    f"| região: **{region}** | perfil: **{aws_profile}**"
)

if not bucket:
    st.warning("Configure o **Bucket S3** na barra lateral para começar.")
    st.stop()


# Build the S3 client (cached per connection parameters)
@st.cache_resource(show_spinner=False)
def get_client(
    _bucket: str, _prefix: str, _region: str, _profile: str
) -> S3Client:
    return _init_client(_bucket, _prefix, _region, _profile)


try:
    client = get_client(bucket, prefix, region, aws_profile)
except Exception as exc:
    st.error(f"Erro ao criar cliente S3: {exc}")
    st.stop()

# ---------------------------------------------------------------------------
# Step 1 — Choose a date partition
# ---------------------------------------------------------------------------

st.subheader("📁 1. Selecione a partição (data)")

try:
    partitions = client.list_partitions()
except Exception as exc:
    st.error(f"Erro ao listar partições: {exc}")
    st.stop()

if not partitions:
    st.info("Nenhuma partição encontrada no prefixo configurado.")
    st.stop()

selected_partition = st.selectbox(
    "Partição disponível",
    options=partitions,
    index=0,
    help="Selecione o folder de data para listar os arquivos de jornada.",
)

# ---------------------------------------------------------------------------
# Step 2 — Choose a file
# ---------------------------------------------------------------------------

st.subheader("📄 2. Selecione o arquivo de jornada")

try:
    files = client.list_files(selected_partition)
except Exception as exc:
    st.error(f"Erro ao listar arquivos em {selected_partition}: {exc}")
    st.stop()

if not files:
    st.info(f"Nenhum arquivo JSON encontrado em **{selected_partition}**.")
    st.stop()

selected_file = st.selectbox(
    "Arquivo JSON",
    options=files,
    help="Clique para visualizar o conteúdo do arquivo.",
)

# ---------------------------------------------------------------------------
# Step 3 — Load and display the JSON
# ---------------------------------------------------------------------------

st.subheader("🔍 3. Conteúdo da Jornada")

if st.button("📂 Carregar JSON", type="primary"):
    try:
        data = client.get_json(selected_partition, selected_file)
        raw = client.get_raw(selected_partition, selected_file)
        st.session_state["json_data"] = data
        st.session_state["json_raw"] = raw
        st.session_state["json_file"] = selected_file
    except Exception as exc:
        st.error(f"Erro ao carregar arquivo: {exc}")
        st.stop()

if (
    "json_data" in st.session_state
    and st.session_state.get("json_file") == selected_file
):
    data = st.session_state["json_data"]
    raw = st.session_state["json_raw"]

    # Download button
    st.download_button(
        label="⬇️ Baixar JSON",
        data=raw,
        file_name=selected_file,
        mime="application/json",
    )

    # Summary metrics
    _render_summary(data)

    # Full JSON viewer
    with st.expander("📝 JSON completo", expanded=False):
        st.code(_format_json(data), language="json")
