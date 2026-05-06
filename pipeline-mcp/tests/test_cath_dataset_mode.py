import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCathDatasetMode(unittest.TestCase):
    def test_build_cath_request_uses_input_only_dense_labels(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        module = _load_module(
            "run_cath_batch_script",
            repo_root / "scripts" / "02_run_cath_batch.py",
        )

        request = module.build_cath_request("END\n")

        self.assertFalse(bool(request.rfd3_use))
        self.assertFalse(bool(request.bioemu_use))
        self.assertEqual(int(request.num_seq_per_tier), 40)
        self.assertEqual(float(request.soluprot_cutoff), 0.0)
        self.assertEqual(int(request.af2_max_candidates_per_tier), 0)
        self.assertEqual(int(request.af2_top_k), 0)
        self.assertFalse(bool(request.relax_enabled))
        self.assertFalse(bool(request.novelty_enabled))
        self.assertFalse(bool(request.wt_compare))
        self.assertEqual(str(request.stop_after), "af2")

    def test_train_cath_surrogate_exports_relax_model(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        module = _load_module(
            "train_cath_surrogate_script",
            repo_root / "scripts" / "train_cath_surrogate.py",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs_root = root / "outputs"
            run_root = outputs_root / "cath_train_demo"
            tier_dir = run_root / "tiers" / "30"
            tier_dir.mkdir(parents=True, exist_ok=True)

            samples = []
            soluprot_scores: dict[str, float] = {}
            plddt_scores: dict[str, float] = {}
            relax_scores: dict[str, float] = {}
            for idx in range(20):
                seq_id = f"seq_{idx:02d}"
                sequence = "ACDEFGHIKLMNPQRSTVWY"[idx % 20 :] + "ACDEFGHIKLMNPQRSTVWY"[: idx % 20]
                samples.append({"id": seq_id, "sequence": sequence})
                soluprot_scores[seq_id] = round(0.2 + (idx * 0.01), 4)
                plddt_scores[seq_id] = float(70 + idx)
                relax_scores[seq_id] = float(-3.5 + (idx * 0.05))

            (run_root / "summary.json").write_text(
                json.dumps({"tiers": [{"tier": 0.3, "proteinmpnn_samples": samples}]}),
                encoding="utf-8",
            )
            (tier_dir / "soluprot.json").write_text(
                json.dumps({"scores": soluprot_scores}),
                encoding="utf-8",
            )
            (tier_dir / "af2_scores.json").write_text(
                json.dumps({"scores": plddt_scores}),
                encoding="utf-8",
            )
            (tier_dir / "relax_scores.json").write_text(
                json.dumps({"score_per_residue": relax_scores}),
                encoding="utf-8",
            )

            module.PROJECT_ROOT = root
            module.OUTPUTS_ROOT = outputs_root
            module.META_ROOT = root / "meta_surrogate_prototype"
            module.MODEL_ROOT = root / "pipeline-mcp" / "models"
            module._generate_embeddings = lambda sequences, model_name: np.arange(
                len(sequences) * 4, dtype=float
            ).reshape(len(sequences), 4)
            module._train_regressor = (
                lambda X, y, hidden_layers: {
                    "rows": int(len(y)),
                    "hidden_layers": tuple(hidden_layers),
                }
            )

            with mock.patch.object(sys, "argv", ["train_cath_surrogate.py", "--subsets", "train"]):
                exit_code = module.main()

            self.assertEqual(exit_code, 0)
            relax_model = module.MODEL_ROOT / "global_relax_v1.pkl"
            self.assertTrue(relax_model.exists())

            summary_path = module.META_ROOT / "training_summary_train.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["artifacts"]["relax_model"], str(relax_model))


if __name__ == "__main__":
    unittest.main()
