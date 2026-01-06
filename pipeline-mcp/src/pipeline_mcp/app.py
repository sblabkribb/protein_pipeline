from __future__ import annotations

from .clients.alphafold2 import AlphaFold2Client
from .clients.alphafold2_runpod import AlphaFold2RunPodClient
from .clients.mmseqs import MMseqsClient
from .clients.proteinmpnn import ProteinMPNNClient
from .clients.runpod import RunPodClient
from .clients.soluprot import SoluProtClient
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
    proteinmpnn = ProteinMPNNClient(runpod=runpod, endpoint_id=cfg.runpod.proteinmpnn_endpoint_id)

    soluprot = SoluProtClient(url=cfg.services.soluprot_url) if cfg.services.soluprot_url else None
    af2 = None
    if cfg.runpod.alphafold2_endpoint_id:
        af2 = AlphaFold2RunPodClient(runpod=runpod, endpoint_id=cfg.runpod.alphafold2_endpoint_id)
    elif cfg.services.af2_url:
        af2 = AlphaFold2Client(url=cfg.services.af2_url)

    return PipelineRunner(
        output_root=cfg.output_root,
        mmseqs=mmseqs,
        proteinmpnn=proteinmpnn,
        soluprot=soluprot,
        af2=af2,
    )
