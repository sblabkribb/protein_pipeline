from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class RunPodConfig:
    api_key: str
    mmseqs_endpoint_id: str
    proteinmpnn_endpoint_id: str
    alphafold2_endpoint_id: str | None
    rfd3_endpoint_id: str | None
    ca_bundle: str | None
    skip_verify: bool


@dataclass(frozen=True)
class ServiceConfig:
    soluprot_url: str | None
    af2_url: str | None


@dataclass(frozen=True)
class AppConfig:
    runpod: RunPodConfig
    services: ServiceConfig
    output_root: str


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config() -> AppConfig:
    api_key = os.environ.get("RUNPOD_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RUNPOD_API_KEY is required")

    mmseqs_endpoint_id = os.environ.get("MMSEQS_ENDPOINT_ID", "").strip()
    if not mmseqs_endpoint_id:
        raise RuntimeError("MMSEQS_ENDPOINT_ID is required")

    proteinmpnn_endpoint_id = os.environ.get("PROTEINMPNN_ENDPOINT_ID", "").strip()
    if not proteinmpnn_endpoint_id:
        raise RuntimeError("PROTEINMPNN_ENDPOINT_ID is required")

    alphafold2_endpoint_id = (
        os.environ.get("ALPHAFOLD2_ENDPOINT_ID", "").strip()
        or os.environ.get("AF2_ENDPOINT_ID", "").strip()
        or os.environ.get("ALPHAFOLD2_RUNPOD_ENDPOINT_ID", "").strip()
        or None
    )
    rfd3_endpoint_id = os.environ.get("RFD3_ENDPOINT_ID", "").strip() or None

    ca_bundle = os.environ.get("RUNPOD_CA_BUNDLE", "").strip() or None
    skip_verify = _env_true("RUNPOD_SKIP_VERIFY") or _env_true("RUNPOD_INSECURE")

    soluprot_url = os.environ.get("SOLUPROT_URL", "").strip() or None
    af2_url = os.environ.get("AF2_URL", "").strip() or None

    output_root = os.environ.get("PIPELINE_OUTPUT_ROOT", "outputs").strip() or "outputs"

    return AppConfig(
        runpod=RunPodConfig(
            api_key=api_key,
            mmseqs_endpoint_id=mmseqs_endpoint_id,
            proteinmpnn_endpoint_id=proteinmpnn_endpoint_id,
            alphafold2_endpoint_id=alphafold2_endpoint_id,
            rfd3_endpoint_id=rfd3_endpoint_id,
            ca_bundle=ca_bundle,
            skip_verify=bool(skip_verify),
        ),
        services=ServiceConfig(soluprot_url=soluprot_url, af2_url=af2_url),
        output_root=output_root,
    )
