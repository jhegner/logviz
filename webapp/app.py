"""LogViz — JSON file viewer and Athena query tool for jornadas-detail on AWS S3.

Run locally:
    streamlit run app.py

Configuration (via sidebar or environment variables):
    S3_BUCKET           : S3 bucket name
    S3_PREFIX           : prefix inside the bucket (default: jornadas/detail)
    AWS_REGION          : AWS region (optional)
    AWS_PROFILE         : named profile from ~/.aws/credentials (optional)
    ATHENA_DATABASE     : Athena database name (default: eventos_db)
    ATHENA_WORKGROUP    : Athena workgroup (default: primary)
    ATHENA_OUTPUT       : S3 output location for query results
"""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st

from athena_client import AthenaClient
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


def _init_athena_client(
    database: str, workgroup: str, output: str, region: str, profile: str
) -> AthenaClient:
    return AthenaClient(
        database=database,
        workgroup=workgroup,
        output_location=output or None,
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

st.sidebar.markdown("---")
st.sidebar.subheader("🔎 Athena")

athena_database = st.sidebar.text_input(
    "Database",
    value=os.environ.get("ATHENA_DATABASE", "eventos_db"),
    help="Nome do database no Athena (ex.: eventos_db).",
)
athena_workgroup = st.sidebar.text_input(
    "Workgroup",
    value=os.environ.get("ATHENA_WORKGROUP", "primary"),
    help="Workgroup do Athena (ex.: primary).",
)
athena_output = st.sidebar.text_input(
    "Output S3",
    value=os.environ.get("ATHENA_OUTPUT", ""),
    help="Bucket S3 para resultados do Athena (ex.: s3://bucket/athena-results/).",
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


@st.cache_resource(show_spinner=False)
def get_athena_client(
    _database: str, _workgroup: str, _output: str, _region: str, _profile: str
) -> AthenaClient:
    return _init_athena_client(_database, _workgroup, _output, _region, _profile)


try:
    client = get_client(bucket, prefix, region, aws_profile)
except Exception as exc:
    st.error(f"Erro ao criar cliente S3: {exc}")
    st.stop()

tab_browser, tab_query = st.tabs(["📁 Navegador S3", "🔎 Consulta Athena"])

# ---------------------------------------------------------------------------
# Tab 1 — S3 Browser
# ---------------------------------------------------------------------------

with tab_browser:

    # -----------------------------------------------------------------------
    # Step 1 — Type the partition path
    # -----------------------------------------------------------------------

    st.subheader("📁 1. Informe a partição")

    with st.form("form_partition"):
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            partition_input = st.text_input(
                "Partição",
                value=st.session_state.get("partition", ""),
                placeholder="Ex.: data=2024-06-15  ou  ano=2024/mes=06/dia=15/canal=web",
                help=(
                    "Digite o caminho da partição dentro do prefixo configurado. "
                    "Exemplo: data=2024-06-15 ou ano=2024/mes=06/dia=15."
                ),
                label_visibility="collapsed",
            )
        with col_btn:
            submitted = st.form_submit_button("🔍 Buscar", type="primary", use_container_width=True)

    if submitted and partition_input:
        st.session_state["partition"] = partition_input

    selected_partition = st.session_state.get("partition", "")

    if not selected_partition:
        st.info("Digite o caminho da partição acima e clique em **Buscar** (ou pressione Enter).")
        st.stop()

    # -----------------------------------------------------------------------
    # Step 2 — Choose a file
    # -----------------------------------------------------------------------

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

    # -----------------------------------------------------------------------
    # Step 3 — Load and display the JSON
    # -----------------------------------------------------------------------

    st.subheader("🔍 3. Conteúdo da Jornada")

    if st.button("📂 Carregar JSON", type="primary", key="btn_load_json_browser"):
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

# ---------------------------------------------------------------------------
# Tab 2 — Athena Query
# ---------------------------------------------------------------------------

with tab_query:
    st.subheader("🔎 Consulta Athena (estilo Splunk)")
    st.caption(
        f"Database: **{athena_database}** | Workgroup: **{athena_workgroup}**"
    )

    _DEFAULT_QUERY = (
        "SELECT idJornada, meta.canal, meta.produto, meta.ambiente,\n"
        "       meta.dataHoraInicio, meta.dataHoraFim\n"
        f"FROM {athena_database}.eventos\n"
        "WHERE ano = 2024\n"
        "  AND mes = 6\n"
        "  AND dia = 15\n"
        "LIMIT 50;"
    )

    query_sql = st.text_area(
        "SQL Query",
        value=st.session_state.get("athena_query", _DEFAULT_QUERY),
        height=180,
        help=(
            "Escreva uma query SQL compatível com Athena (Presto/Trino). "
            "Use partições (ano, mes, dia, canal, produto, ambiente) para "
            "filtrar e reduzir o custo da consulta."
        ),
    )
    st.session_state["athena_query"] = query_sql

    col_run, col_hint = st.columns([1, 4])
    run_query = col_run.button("▶️ Executar", type="primary")

    with col_hint:
        with st.expander("💡 Exemplos de queries"):
            st.code(
                "-- Jornadas com erro (status >= 400)\n"
                "SELECT idJornada, meta.canal, meta.produto,\n"
                "       servico.nome, servico.statusCode, servico.url\n"
                f"FROM {athena_database}.eventos\n"
                "CROSS JOIN UNNEST(etapas) AS t(etapa)\n"
                "CROSS JOIN UNNEST(etapa.servicos) AS s(servico)\n"
                "WHERE ano=2024 AND mes=6 AND dia=15\n"
                "  AND servico.statusCode >= 400\n"
                "LIMIT 100;",
                language="sql",
            )
            st.code(
                "-- Buscar por idJornada específico\n"
                "SELECT *\n"
                f"FROM {athena_database}.eventos\n"
                "WHERE ano=2024 AND mes=6\n"
                "  AND idJornada = 'J12345'\n"
                "LIMIT 1;",
                language="sql",
            )
            st.code(
                "-- Taxa de erro por serviço\n"
                "SELECT servico.nome,\n"
                "       COUNT(*) AS total,\n"
                "       SUM(CASE WHEN servico.statusCode >= 400 THEN 1 ELSE 0 END) AS erros\n"
                f"FROM {athena_database}.eventos\n"
                "CROSS JOIN UNNEST(etapas) AS t(etapa)\n"
                "CROSS JOIN UNNEST(etapa.servicos) AS s(servico)\n"
                "WHERE ano=2024 AND mes=6\n"
                "GROUP BY servico.nome\n"
                "ORDER BY erros DESC;",
                language="sql",
            )

    if run_query:
        if not athena_output:
            st.warning(
                "Configure o **Output S3** do Athena na barra lateral antes de executar."
            )
        else:
            try:
                athena = get_athena_client(
                    athena_database,
                    athena_workgroup,
                    athena_output,
                    region,
                    aws_profile,
                )
                with st.spinner("Executando query no Athena…"):
                    results = athena.run_query(query_sql)
                st.success(
                    f"✅ Query concluída — {len(results)} linha(s) retornada(s)."
                )
                if results:
                    import pandas as pd

                    df = pd.DataFrame(results)
                    st.dataframe(df, use_container_width=True)

                    csv = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="⬇️ Baixar CSV",
                        data=csv,
                        file_name="athena_results.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("A query não retornou resultados.")
            except Exception as exc:
                st.error(f"Erro ao executar query no Athena: {exc}")
