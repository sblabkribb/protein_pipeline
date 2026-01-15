ARG BASE_IMAGE=runpod/pytorch:1.0.3-cu1290-torch291-ubuntu2204
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip && \
    python -m pip install "runpod>=1.7.0,<2" numpy

ARG PROTEINMPNN_REF=main
RUN git clone --depth 1 --branch "${PROTEINMPNN_REF}" https://github.com/dauparas/ProteinMPNN.git /opt/ProteinMPNN

ENV PROTEINMPNN_DIR=/opt/ProteinMPNN

RUN python - <<'PY'\nimport numpy  # noqa: F401\nimport torch  # noqa: F401\nfrom pathlib import Path\n\nmpnn = Path('/opt/ProteinMPNN')\nassert (mpnn / 'protein_mpnn_run.py').is_file()\nassert (mpnn / 'soluble_model_weights' / 'v_48_010.pt').is_file()\nassert (mpnn / 'soluble_model_weights' / 'v_48_020.pt').is_file()\nPY

WORKDIR /workspace
COPY handler.py /workspace/handler.py

CMD ["python", "-u", "/workspace/handler.py"]
