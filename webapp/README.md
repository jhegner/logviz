# LogViz — Jornadas Detail Viewer (proposta-2)

A **Streamlit** web application that lets developers browse and inspect JSON detail files stored on **AWS S3** (`jornadas/detail/data=YYYY-MM-DD/{idJornada}.json`) without downloading them locally.

## Features

- 📁 Browse date partitions (`data=YYYY-MM-DD` folders) in S3
- 📄 List JSON files per partition and click to view content
- 🔍 Structured viewer: metrics, stages, services, integrations, request/response bodies
- ⬇️ One-click download of any JSON file
- ⚙️ Configurable via sidebar (bucket, prefix, region, AWS profile)
- 🔑 Uses default `~/.aws/credentials` — no hardcoded secrets
- 🐳 Docker-ready for EKS deployment

## Local Development

### Prerequisites

- Python 3.12+
- AWS credentials configured (`~/.aws/credentials` with at least `s3:GetObject` and `s3:ListBucket`)

### Python Virtual Env

```bash
python3 -m venv .venv

source .venv/bin/activate # linux

source .venv\Scripts\activate # windows

deactivate # desativa
```

### Install & Run

```bash
cd proposta-2/webapp

# Install dependencies
pip install -r requirements.txt

# (Optional) set defaults via environment
export S3_BUCKET=bucket-logs-eventos
export AWS_REGION=us-east-1

# Start the app
streamlit run app.py
```

The app will open at <http://localhost:8501>.

### Environment Variables

| Variable      | Required | Default           | Description                             |
| ------------- | -------- | ----------------- | --------------------------------------- |
| `S3_BUCKET`   | ✅ yes    | —                 | S3 bucket name                          |
| `S3_PREFIX`   | no       | `jornadas/detail` | Prefix inside the bucket                |
| `AWS_REGION`  | no       | `us-east-1`       | AWS region                              |
| `AWS_PROFILE` | no       | `default`         | Named profile from `~/.aws/credentials` |

Copy `.env.example` to `.env` and adjust the values. You can also change all settings via the sidebar inside the app.

## Docker (EKS)

```bash
# Build
docker build -t logviz-webapp .

# Run locally (mounts ~/.aws for credentials)
docker run -p 8501:8501 \
  -e S3_BUCKET=bucket-logs-eventos \
  -v "$HOME/.aws:/root/.aws:ro" \
  logviz-webapp

# Or use docker-compose
docker-compose up --build
```

On EKS, attach an **IAM Role for Service Account (IRSA)** with `s3:GetObject` and `s3:ListBucket` permissions — no `~/.aws` volume needed.

## Running Tests

```bash
cd proposta-2/webapp
pip install -r requirements.txt pytest
python -m pytest tests/ -v
```

## S3 Structure (proposta-2)

```
s3://bucket-logs-eventos/
└── jornadas/
    ├── detail/
    │   └── data=YYYY-MM-DD/
    │       ├── J12345.json    ← full jornada JSON (viewed by this app)
    │       └── J12346.json
    └── meta/
        └── data=YYYY-MM-DD/
            └── records.json   ← NDJSON queried by Athena
```

## Athena and Glue Infos

- Set output: lab-logviz-database
- IAM role: AWSGlueServiceRole-logviz-labs
- Data sources: s3://bucket-logs-eventos/jornadas/meta/
- Set crawler: lab-logviz-meta-crawler
