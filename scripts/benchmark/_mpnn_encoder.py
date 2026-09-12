#!/usr/bin/env python3
"""ProteinMPNN encoder feature extraction (backbone-only, sequence-independent).

The ProteinMPNN encoder starts from a zero node state and is updated only by the
geometric edge features, so the encoder node states do not depend on the
sequence at all. That is what makes a single per-backbone feature vector
well-defined: it can be computed once per backbone and reused for every sequence
designed onto it.

The dev cohort feature file
``public_data/benchmark/gate0/backbones/mpnn_encoder.npy`` is ``(157, 384)`` =
3 encoder layers x 128 hidden, i.e. the mask-mean pooled node state after each
of the three encoder layers, concatenated in layer order. The extractor that
produced it was never committed (commit ``1c2eeb4`` holds artifacts only), so
this module is a re-implementation. Its only warrant is the reproduction check
``scripts/benchmark/21_gate2d_prepare_encoder.py --verify-dev``, which was run
before any holdout feature was extracted:

    shape (157, 384) == (157, 384)
    max abs diff 9.06e-06
    allclose(atol=1e-4) True

Recipe (every element of it is load-bearing for that reproduction):

* soluble ``v_48_020`` checkpoint, ``k_neighbors = checkpoint["num_edges"]`` (48)
* ``augment_eps = 0.0`` (no backbone noise) and ``model.eval()`` -- deterministic
* node state ``h_V`` initialised to zeros, three ``EncLayer`` steps
* **``residue_idx`` is constant**, so every relative-position offset is 0 and the
  relative positional encoding contributes one fixed embedding everywhere. The
  dev features are therefore purely geometric: no sequence, no residue
  numbering. Passing the real ``residue_idx`` changes every value (max abs diff
  0.49 against the dev file), so this is not a cosmetic choice.
* pooling = mean over resolved residues (``mask == 1``), per layer, then
  ``concat(L1, L2, L3)``

Model source and checkpoint live outside the repo at ``/opt/rapid_models/`` and
are never copied in.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

MPNN_SRC = Path(os.environ.get("PROTEIN_MPNN_SRC", "/opt/rapid_models/ProteinMPNN"))
MPNN_CKPT = Path(
    os.environ.get(
        "PROTEIN_MPNN_CKPT",
        str(MPNN_SRC / "soluble_model_weights" / "v_48_020.pt"),
    )
)

#: dev cohort constants. Different values mean a different feature space.
ENCODER_DIM = 384
ENCODER_HIDDEN = 128
ENCODER_LAYERS = 3
ENCODER_CKPT = "v_48_020"

_MODEL = None


def mpnn_utils():
    """Import the ProteinMPNN source tree that matches the checkpoint."""
    if str(MPNN_SRC) not in sys.path:
        sys.path.insert(0, str(MPNN_SRC))
    import protein_mpnn_utils  # noqa: PLC0415

    return protein_mpnn_utils


def load_model(*, ckpt: Path | None = None, backbone_noise: float = 0.0):
    """Load ProteinMPNN with the dev cohort checkpoint on CPU, eval mode."""
    global _MODEL
    if _MODEL is not None and ckpt is None and backbone_noise == 0.0:
        return _MODEL
    import torch  # noqa: PLC0415

    utils = mpnn_utils()
    path = Path(ckpt) if ckpt is not None else MPNN_CKPT
    if not path.exists():
        raise SystemExit(f"ProteinMPNN checkpoint not found: {path}")
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    model = utils.ProteinMPNN(
        ca_only=False,
        num_letters=21,
        node_features=ENCODER_HIDDEN,
        edge_features=ENCODER_HIDDEN,
        hidden_dim=ENCODER_HIDDEN,
        num_encoder_layers=ENCODER_LAYERS,
        num_decoder_layers=ENCODER_LAYERS,
        augment_eps=backbone_noise,
        k_neighbors=checkpoint["num_edges"],
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    if ckpt is None and backbone_noise == 0.0:
        _MODEL = model
    return model


def featurize_pdb(pdb_path: str | Path):
    """parse + tied_featurize a single backbone PDB the way protein_mpnn_run does."""
    import torch  # noqa: PLC0415

    utils = mpnn_utils()
    device = torch.device("cpu")
    pdb_dict_list = utils.parse_PDB(str(pdb_path), ca_only=False)
    dataset = utils.StructureDatasetPDB(
        pdb_dict_list, verbose=False, truncate=None, max_length=1_000_000
    )
    if len(dataset) == 0:
        raise SystemExit(f"no parseable chain in {pdb_path}")
    all_chains = [k[-1:] for k in pdb_dict_list[0] if k[:9] == "seq_chain"]
    chain_id_dict = {pdb_dict_list[0]["name"]: (all_chains, [])}
    out = utils.tied_featurize(
        [dataset[0]], device, chain_id_dict, None, None, None, None, None, ca_only=False
    )
    X, S, mask, chain_encoding_all = out[0], out[1], out[2], out[5]
    residue_idx = out[12]
    return X, S, mask, residue_idx, chain_encoding_all


def encoder_node_states(pdb_path: str | Path, *, model=None, relative_position: bool = False):
    """Per-layer encoder node states ``h_V`` and the residue mask.

    ``h_V`` starts at zero and is driven only by geometric edges, so no sequence
    is involved. Returns ``(states, mask)`` with ``states`` a list of ``(L, 128)``
    arrays, one per encoder layer, and ``mask`` of shape ``(L,)``.

    ``relative_position=False`` (the dev cohort setting) zeroes ``residue_idx``
    so all sequence-separation offsets collapse to 0.
    """
    import torch  # noqa: PLC0415

    utils = mpnn_utils()
    model = model if model is not None else load_model()
    X, _S, mask, residue_idx, chain_encoding_all = featurize_pdb(pdb_path)
    if not relative_position:
        residue_idx = torch.zeros_like(residue_idx)
    with torch.no_grad():
        E, E_idx = model.features(X, mask, residue_idx, chain_encoding_all)
        h_V = torch.zeros((E.shape[0], E.shape[1], E.shape[-1]), device=E.device)
        h_E = model.W_e(E)
        mask_attend = utils.gather_nodes(mask.unsqueeze(-1), E_idx).squeeze(-1)
        mask_attend = mask.unsqueeze(-1) * mask_attend
        states = []
        for layer in model.encoder_layers:
            h_V, h_E = layer(h_V, h_E, E_idx, mask, mask_attend)
            states.append(h_V[0].clone().numpy())
    return states, mask[0].numpy()


def encode_backbone_pdb(
    pdb_path: str | Path,
    *,
    model=None,
    pooling: str = "mask_mean",
    relative_position: bool = False,
):
    """Layer-wise pooled encoder feature for one backbone. Shape ``(384,)``.

    ``pooling``:
      * ``mask_mean`` -- mean over resolved residues (mask == 1). The dev setting.
      * ``full_mean`` -- mean over all padded positions.
      * ``max``       -- max over resolved residues.
    """
    states, mask = encoder_node_states(
        pdb_path, model=model, relative_position=relative_position
    )
    sel = mask.astype(bool)
    pooled = []
    for state in states:
        if pooling == "mask_mean":
            pooled.append(state[sel].mean(axis=0))
        elif pooling == "full_mean":
            pooled.append(state.mean(axis=0))
        elif pooling == "max":
            pooled.append(state[sel].max(axis=0))
        else:
            raise ValueError(f"unknown pooling {pooling!r}")
    vec = np.concatenate(pooled).astype(np.float32)
    if vec.shape[0] != ENCODER_DIM:
        raise SystemExit(f"encoder dim {vec.shape[0]} != {ENCODER_DIM}")
    return vec
