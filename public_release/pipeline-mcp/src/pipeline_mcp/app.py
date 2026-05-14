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
from .config import load_config
from .pipeline import PipelineRunner


def build_runner() -> PipelineRunner:
    cfg = load_config()
    runpod = RunPodClient(
        api_key=cfg.runpod.api_key,
        ca_bundle=cfg.runpod.ca_bundle,
        skip_verify=cfg.runpod.skip_verify,
    )
    mmseqs = MMseqsClient(runpod=runpod, endpoint_id=cfg.runpod.mmseqs_endpoint_id)
    if cfg.proteinmpnn.provider == "gpu_http":
        proteinmpnn = ProteinMPNNClient(
            runpod=None,
            endpoint_id=None,
            gpu_url=cfg.proteinmpnn.gpu_url,
            gpu_token=cfg.proteinmpnn.gpu_token,
            gpu_timeout_s=cfg.proteinmpnn.gpu_timeout_s,
        )
    else:
        proteinmpnn = ProteinMPNNClient(runpod=runpod, endpoint_id=cfg.runpod.proteinmpnn_endpoint_id)

    soluprot = SoluProtClient(url=cfg.services.soluprot_url) if cfg.services.soluprot_url else None
    colabfold = None
    if cfg.runpod.colabfold_endpoint_id:
        colabfold = AlphaFold2RunPodClient(runpod=runpod, endpoint_id=cfg.runpod.colabfold_endpoint_id)

    af2 = None
    if cfg.runpod.alphafold2_endpoint_id:
        af2 = AlphaFold2RunPodClient(runpod=runpod, endpoint_id=cfg.runpod.alphafold2_endpoint_id)
    elif cfg.services.af2_url:
        af2 = AlphaFold2Client(url=cfg.services.af2_url)

    rfd3 = None
    if cfg.runpod.rfd3_endpoint_id:
        rfd3 = RFD3RunPodClient(runpod=runpod, endpoint_id=cfg.runpod.rfd3_endpoint_id)

    bioemu = None
    if cfg.runpod.bioemu_endpoint_id:
        bioemu = BioEmuRunPodClient(runpod=runpod, endpoint_id=cfg.runpod.bioemu_endpoint_id)

    diffdock = None
    if cfg.runpod.diffdock_endpoint_id:
        diffdock = DiffDockRunPodClient(runpod=runpod, endpoint_id=cfg.runpod.diffdock_endpoint_id)

    rosetta_relax = None
    rosetta_docker_bin = cfg.rosetta.docker_bin or shutil.which("docker")

    if cfg.runpod.relax_endpoint_id:
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
