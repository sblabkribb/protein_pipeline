from __future__ import annotations

import shutil

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - exercised via subprocess test
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False

# Load environment variables early
load_dotenv()

from .clients.alphafold2 import AlphaFold2Client
from .clients.alphafold2_runpod import AlphaFold2RunPodClient
from .clients.bioemu_runpod import BioEmuRunPodClient
from .clients.diffdock_runpod import DiffDockRunPodClient
from .clients.mmseqs import MMseqsClient
from .clients.proteinmpnn import ProteinMPNNClient
from .clients.rosetta_relax import RosettaRelaxClient
from .clients.rfd3_runpod import RFD3RunPodClient
from .clients.runpod import RunPodClient
from .clients.soluprot import SoluProtClient
from .clients.gemini import GeminiClient
from .clients.local_http import LocalHTTPAlphaFold2Client
from .clients.local_http import LocalHTTPBioEmuClient
from .clients.local_http import LocalHTTPDiffDockClient
from .clients.local_http import LocalHTTPMMseqsClient
from .clients.local_http import LocalHTTPRFD3Client
from .clients.local_http import LocalHTTPRosettaRelaxClient
from .config import load_config
from .model_providers import ModelProviderStore
from .pipeline import PipelineRunner


def _provider(store: ModelProviderStore, model_key: str) -> dict:
    return store.get_effective(model_key, include_secret=True)


def _provider_is_http(provider: dict) -> bool:
    return bool(provider.get("enabled", True)) and provider.get("provider_type") == "http_api" and bool(provider.get("base_url"))


def _provider_is_runpod(provider: dict) -> bool:
    return bool(provider.get("enabled", True)) and provider.get("provider_type") == "runpod" and bool(provider.get("endpoint_id"))


def build_runner() -> PipelineRunner:
    cfg = load_config()
    provider_store = ModelProviderStore(cfg.output_root)
    runpod = RunPodClient(
        api_key=cfg.runpod.api_key,
        ca_bundle=cfg.runpod.ca_bundle,
        skip_verify=cfg.runpod.skip_verify,
    )
    mmseqs_provider = _provider(provider_store, "mmseqs")
    if _provider_is_http(mmseqs_provider):
        mmseqs = LocalHTTPMMseqsClient(
            base_url=mmseqs_provider["base_url"],
            token=mmseqs_provider.get("token") or None,
            timeout_s=float(mmseqs_provider.get("timeout_s") or 21600),
        )
    else:
        mmseqs_endpoint_id = str(mmseqs_provider.get("endpoint_id") or cfg.runpod.mmseqs_endpoint_id)
        mmseqs = MMseqsClient(runpod=runpod, endpoint_id=mmseqs_endpoint_id)

    proteinmpnn_provider = _provider(provider_store, "proteinmpnn")
    if _provider_is_http(proteinmpnn_provider):
        proteinmpnn = ProteinMPNNClient(
            runpod=None,
            endpoint_id=None,
            gpu_url=proteinmpnn_provider["base_url"],
            gpu_token=proteinmpnn_provider.get("token") or None,
            gpu_timeout_s=float(proteinmpnn_provider.get("timeout_s") or 21600),
        )
    elif _provider_is_runpod(proteinmpnn_provider):
        proteinmpnn = ProteinMPNNClient(runpod=runpod, endpoint_id=str(proteinmpnn_provider["endpoint_id"]))
    elif cfg.proteinmpnn.provider == "gpu_http":
        proteinmpnn = ProteinMPNNClient(
            runpod=None,
            endpoint_id=None,
            gpu_url=cfg.proteinmpnn.gpu_url,
            gpu_token=cfg.proteinmpnn.gpu_token,
            gpu_timeout_s=cfg.proteinmpnn.gpu_timeout_s,
        )
    else:
        proteinmpnn_endpoint_id = str(proteinmpnn_provider.get("endpoint_id") or cfg.runpod.proteinmpnn_endpoint_id or "")
        proteinmpnn = ProteinMPNNClient(runpod=runpod, endpoint_id=proteinmpnn_endpoint_id)

    soluprot = SoluProtClient(url=cfg.services.soluprot_url) if cfg.services.soluprot_url else None
    colabfold = None
    colabfold_provider = _provider(provider_store, "colabfold")
    if _provider_is_http(colabfold_provider):
        colabfold = LocalHTTPAlphaFold2Client(
            base_url=colabfold_provider["base_url"],
            token=colabfold_provider.get("token") or None,
            timeout_s=float(colabfold_provider.get("timeout_s") or 21600),
            endpoint_id="local-http-colabfold",
        )
    elif _provider_is_runpod(colabfold_provider):
        colabfold = AlphaFold2RunPodClient(runpod=runpod, endpoint_id=str(colabfold_provider["endpoint_id"]))
    elif cfg.runpod.colabfold_endpoint_id:
        colabfold = AlphaFold2RunPodClient(runpod=runpod, endpoint_id=cfg.runpod.colabfold_endpoint_id)

    af2 = None
    af2_provider = _provider(provider_store, "alphafold2")
    if _provider_is_http(af2_provider):
        af2 = LocalHTTPAlphaFold2Client(
            base_url=af2_provider["base_url"],
            token=af2_provider.get("token") or None,
            timeout_s=float(af2_provider.get("timeout_s") or 21600),
            endpoint_id="local-http-af2",
        )
    elif _provider_is_runpod(af2_provider):
        af2 = AlphaFold2RunPodClient(runpod=runpod, endpoint_id=str(af2_provider["endpoint_id"]))
    elif cfg.runpod.alphafold2_endpoint_id:
        af2 = AlphaFold2RunPodClient(runpod=runpod, endpoint_id=cfg.runpod.alphafold2_endpoint_id)
    elif cfg.services.af2_url:
        af2 = AlphaFold2Client(url=cfg.services.af2_url)

    rfd3 = None
    rfd3_provider = _provider(provider_store, "rfd3")
    if _provider_is_http(rfd3_provider):
        rfd3 = LocalHTTPRFD3Client(
            base_url=rfd3_provider["base_url"],
            token=rfd3_provider.get("token") or None,
            timeout_s=float(rfd3_provider.get("timeout_s") or 21600),
        )
    elif _provider_is_runpod(rfd3_provider):
        rfd3 = RFD3RunPodClient(runpod=runpod, endpoint_id=str(rfd3_provider["endpoint_id"]))
    elif cfg.runpod.rfd3_endpoint_id:
        rfd3 = RFD3RunPodClient(runpod=runpod, endpoint_id=cfg.runpod.rfd3_endpoint_id)

    bioemu = None
    bioemu_provider = _provider(provider_store, "bioemu")
    if _provider_is_http(bioemu_provider):
        bioemu = LocalHTTPBioEmuClient(
            base_url=bioemu_provider["base_url"],
            token=bioemu_provider.get("token") or None,
            timeout_s=float(bioemu_provider.get("timeout_s") or 21600),
        )
    elif _provider_is_runpod(bioemu_provider):
        bioemu = BioEmuRunPodClient(runpod=runpod, endpoint_id=str(bioemu_provider["endpoint_id"]))
    elif cfg.runpod.bioemu_endpoint_id:
        bioemu = BioEmuRunPodClient(runpod=runpod, endpoint_id=cfg.runpod.bioemu_endpoint_id)

    diffdock = None
    diffdock_provider = _provider(provider_store, "diffdock")
    if _provider_is_http(diffdock_provider):
        diffdock = LocalHTTPDiffDockClient(
            base_url=diffdock_provider["base_url"],
            token=diffdock_provider.get("token") or None,
            timeout_s=float(diffdock_provider.get("timeout_s") or 21600),
        )
    elif _provider_is_runpod(diffdock_provider):
        diffdock = DiffDockRunPodClient(runpod=runpod, endpoint_id=str(diffdock_provider["endpoint_id"]))
    elif cfg.runpod.diffdock_endpoint_id:
        diffdock = DiffDockRunPodClient(runpod=runpod, endpoint_id=cfg.runpod.diffdock_endpoint_id)

    rosetta_relax = None
    rosetta_docker_bin = cfg.rosetta.docker_bin or shutil.which("docker")
    rosetta_provider = _provider(provider_store, "rosetta_relax")

    if _provider_is_http(rosetta_provider):
        rosetta_relax = LocalHTTPRosettaRelaxClient(
            base_url=rosetta_provider["base_url"],
            token=rosetta_provider.get("token") or None,
            timeout_s=float(rosetta_provider.get("timeout_s") or cfg.rosetta.timeout_s),
        )
    elif _provider_is_runpod(rosetta_provider):
        rosetta_relax = RosettaRelaxClient(
            timeout_s=cfg.rosetta.timeout_s,
        )  # Client picks up RUNPOD_RELAX_ENDPOINT_ID internally
    elif cfg.runpod.relax_endpoint_id:
        rosetta_relax = RosettaRelaxClient(
            timeout_s=cfg.rosetta.timeout_s,
        )  # Client picks up RUNPOD_RELAX_ENDPOINT_ID internally
    elif cfg.rosetta.relax_binary and cfg.rosetta.score_binary and cfg.rosetta.database_path:
        rosetta_relax = RosettaRelaxClient(
            relax_binary=cfg.rosetta.relax_binary,
            score_binary=cfg.rosetta.score_binary,
            database_path=cfg.rosetta.database_path,
            timeout_s=cfg.rosetta.timeout_s,
        )
    elif rosetta_docker_bin:
        rosetta_relax = RosettaRelaxClient(
            docker_bin=rosetta_docker_bin,
            docker_image=cfg.rosetta.docker_image or "rosettacommons/rosetta:latest",
            timeout_s=cfg.rosetta.timeout_s,
        )
    
    gemini = None
    if cfg.gemini.api_key:
        gemini = GeminiClient(api_key=cfg.gemini.api_key, model_name=cfg.gemini.model_name)

    return PipelineRunner(
        output_root=cfg.output_root,
        mmseqs=mmseqs,
        proteinmpnn=proteinmpnn,
        soluprot=soluprot,
        colabfold=colabfold,
        af2=af2,
        rfd3=rfd3,
        bioemu=bioemu,
        diffdock=diffdock,
        rosetta_relax=rosetta_relax,
        gemini=gemini,
    )
