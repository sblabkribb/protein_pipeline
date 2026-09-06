"""RAPID 모델 레지스트리와 목적 기반 라우팅 계약.

이 테스트가 지키는 규칙은 세 가지다.
  1. 비용과 성능 숫자는 provenance 없이 존재할 수 없다. 측정하지 않은 것을
     측정한 것처럼 보여주면 사용자는 그것을 근거로 예산을 잡는다.
  2. 라우트는 조용히 대체하지 않는다. 실행 불가능하면 이유를 말한다.
  3. "선언된 가용성"과 "지금 살아 있는지"는 다른 사실이다. 섞지 않는다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.model_routing import (
    COST_PROVENANCE,
    ROLES,
    ModelRegistry,
    UnknownPurposeError,
    load_registry,
)


class RegistryLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry()

    def test_registry_declares_its_version_and_freeze_state(self):
        self.assertTrue(self.reg.policy_version)
        self.assertIn(self.reg.freeze_state, {"frozen", "draft"})

    def test_every_model_has_a_known_role(self):
        for model in self.reg.models.values():
            self.assertIn(model.role, ROLES, f"{model.model_id} role={model.role}")

    def test_cost_provenance_is_always_declared(self):
        for model in self.reg.models.values():
            self.assertIn(
                model.cost.provenance, COST_PROVENANCE,
                f"{model.model_id} cost.provenance={model.cost.provenance!r}",
            )

    def test_measured_cost_requires_a_source_and_a_scope(self):
        """91 s/fold(62 aa) 를 186 s/fold(59-274 aa) 와 바꿔 쓸 수 없게 한다."""
        for model in self.reg.models.values():
            if model.cost.provenance in {"measured", "reported"}:
                self.assertTrue(model.cost.source, f"{model.model_id}: source 없음")
                self.assertTrue(model.cost.scope, f"{model.model_id}: scope 없음")
                self.assertIsNotNone(model.cost.value, f"{model.model_id}: value 없음")

    def test_unmeasured_cost_carries_no_number(self):
        for model in self.reg.models.values():
            if model.cost.provenance == "unmeasured":
                self.assertIsNone(
                    model.cost.value,
                    f"{model.model_id}: 측정하지 않았는데 숫자가 있다",
                )

    def test_served_by_endpoints_are_unique_per_model(self):
        seen: dict[str, str] = {}
        for model in self.reg.models.values():
            if not model.endpoint:
                continue
            self.assertNotIn(
                model.endpoint, seen,
                f"{model.model_id} 와 {seen.get(model.endpoint)} 가 같은 endpoint 를 주장한다",
            )
            seen[model.endpoint] = model.model_id


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry()

    def test_unknown_purpose_raises_rather_than_guessing(self):
        with self.assertRaises(UnknownPurposeError):
            self.reg.route("make_me_a_protein")

    def test_every_declared_purpose_routes(self):
        self.assertTrue(self.reg.purposes)
        for purpose in self.reg.purposes:
            route = self.reg.route(purpose)
            self.assertEqual(route.purpose, purpose)
            self.assertTrue(route.stages, f"{purpose}: 스테이지가 비었다")

    def test_route_stages_reference_known_models(self):
        for purpose in self.reg.purposes:
            for stage in self.reg.route(purpose).stages:
                self.assertIn(
                    stage.model_id, self.reg.models,
                    f"{purpose}/{stage.stage}: 미등록 모델 {stage.model_id}",
                )

    def test_route_stages_are_gate_ordered(self):
        order = {"gate0": 0, "gate1": 1, "gate2": 2, None: 3}
        for purpose in self.reg.purposes:
            gates = [order[s.gate] for s in self.reg.route(purpose).stages if s.gate]
            self.assertEqual(gates, sorted(gates), f"{purpose}: 게이트 순서가 뒤집혔다")

    def test_a_route_needing_an_unavailable_model_is_not_executable(self):
        """없는 모델을 다른 모델로 몰래 바꾸지 않는다."""
        for purpose in self.reg.purposes:
            route = self.reg.route(purpose)
            blocking = [
                s for s in route.stages
                if s.required and not self.reg.is_runnable(s.model_id)
            ]
            if blocking:
                self.assertFalse(route.executable, f"{purpose}: 막혔는데 실행 가능하다고 한다")
                self.assertTrue(route.blocked_reason, f"{purpose}: 이유가 없다")
                for stage in blocking:
                    self.assertIn(stage.model_id, route.blocked_reason)
            else:
                self.assertTrue(route.executable, f"{purpose}: {route.blocked_reason}")

    def test_blocked_route_still_lists_its_stages(self):
        """실행 못 해도 무엇이 필요한지는 보여줘야 사용자가 판단한다."""
        blocked = [p for p in self.reg.purposes if not self.reg.route(p).executable]
        for purpose in blocked:
            self.assertTrue(self.reg.route(purpose).stages)

    def test_executable_and_validated_are_separate_axes(self):
        """클라이언트가 붙었다는 사실과 그 경로를 측정했다는 사실은 다르다."""
        for purpose in self.reg.purposes:
            route = self.reg.route(purpose)
            if route.unvalidated_stages:
                self.assertFalse(
                    route.validated,
                    f"{purpose}: 미검증 스테이지가 있는데 validated 라고 한다",
                )
            else:
                self.assertEqual(route.validated, route.executable)

    def test_binder_route_is_runnable_but_not_claimed_validated(self):
        route = self.reg.route("protein_binder_design")
        self.assertTrue(route.executable, route.blocked_reason)
        self.assertFalse(route.validated)
        self.assertTrue(route.unvalidated_stages)

    def test_validated_purpose_points_at_the_measured_pipeline(self):
        route = self.reg.route("monomer_solubility_redesign")
        self.assertTrue(route.executable, route.blocked_reason)
        self.assertTrue(route.validated)
        ids = [s.model_id for s in route.stages]
        for expected in ("proteinmpnn", "soluprot", "colabfold"):
            self.assertIn(expected, ids)


class ObjectiveCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry()

    def test_measurable_objectives_come_from_production_evaluators(self):
        measurable = self.reg.measurable_objectives()
        self.assertIn("solubility", measurable)
        self.assertIn("structural_preservation", measurable)

    def test_binding_is_not_silently_counted_as_validated(self):
        """binding 평가자를 붙였다고 해서 binding 을 측정했다고 말하지 않는다."""
        self.assertNotIn("binding", self.reg.measurable_objectives())
        self.assertIn("binding", self.reg.measurable_objectives(include_unvalidated=True))

    def test_an_objective_is_measurable_only_if_some_model_claims_it(self):
        claimed = set()
        for model in self.reg.models.values():
            if model.availability == "production":
                claimed.update(model.measures)
        self.assertTrue(self.reg.measurable_objectives() <= claimed)

    def test_evaluators_for_returns_only_production_models(self):
        for objective in self.reg.measurable_objectives():
            models = self.reg.evaluators_for(objective)
            self.assertTrue(models, objective)
            for model in models:
                self.assertEqual(model.availability, "production")
                self.assertIn(objective, model.measures)

    def test_unmeasurable_objective_returns_empty_not_a_substitute(self):
        self.assertEqual(self.reg.evaluators_for("telepathy"), ())


class EvidenceExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry()

    def test_route_exports_evidence_dicts_for_every_stage(self):
        route = self.reg.route("monomer_solubility_redesign")
        for item in route.evidence():
            self.assertIn(item["kind"], {"internal_measurement", "literature", "assumption"})
            if item["kind"] != "assumption":
                self.assertTrue(item["source"])

    def test_cost_estimate_reports_unknown_instead_of_zero(self):
        """모르는 비용을 0 으로 더하면 예산이 거짓말이 된다."""
        route = self.reg.route("monomer_solubility_redesign")
        estimate = route.cost_estimate(n_designs=10, length_aa=200)
        self.assertIn("known_seconds", estimate)
        self.assertIn("unknown_stages", estimate)
        self.assertIsInstance(estimate["unknown_stages"], list)

    def test_af2_cost_uses_the_length_scaling_fit_not_a_single_probe(self):
        route = self.reg.route("monomer_solubility_redesign")
        short = route.cost_estimate(n_designs=1, length_aa=60)["known_seconds"]
        long = route.cost_estimate(n_designs=1, length_aa=254)["known_seconds"]
        self.assertGreater(long, short * 1.5)


class LivenessTests(unittest.TestCase):
    def test_liveness_is_reported_separately_from_declared_availability(self):
        reg = load_registry()

        def fake_probe(url: str, timeout: float):
            if "18101" in url:
                return {"ok": True, "ready": True, "model": "proteinmpnn"}
            raise OSError("connection refused")

        status = reg.probe_liveness(probe=fake_probe)
        self.assertEqual(status["proteinmpnn"]["reachable"], True)
        down = [k for k, v in status.items() if v["reachable"] is False]
        self.assertTrue(down)
        # 선언된 availability 는 probe 결과로 바뀌지 않는다.
        self.assertEqual(reg.models["colabfold"].availability, "production")

    def test_a_worker_reporting_the_declared_checkpoint_is_not_a_mismatch(self):
        """ESM 워커는 'facebook/esm2_t6_8M_UR50D' 를 보고한다. 레지스트리가 그
        체크포인트를 선언했다면 이름이 달라도 같은 모델이다."""
        reg = load_registry()

        def fake_probe(url: str, timeout: float):
            if "18170" in url:
                return {"ok": True, "ready": True, "model_name": "facebook/esm2_t6_8M_UR50D"}
            raise OSError("skip")

        status = reg.probe_liveness(probe=fake_probe)
        self.assertFalse(status["esm2_embedding"]["model_mismatch"])

    def test_probe_records_the_model_name_the_worker_reports(self):
        reg = load_registry()

        def fake_probe(url: str, timeout: float):
            return {"ok": True, "ready": True, "model": "something-else"}

        status = reg.probe_liveness(probe=fake_probe)
        mismatched = [k for k, v in status.items() if v.get("model_mismatch")]
        self.assertTrue(mismatched, "워커가 다른 모델을 보고해도 아무도 알아채지 못한다")


if __name__ == "__main__":
    unittest.main()


class ClientClaimTests(unittest.TestCase):
    """레지스트리가 '클라이언트가 있다' 고 말하면 실제로 있어야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry()
        cls.pkg = PROJECT_ROOT / "pipeline-mcp" / "src" / "pipeline_mcp"

    def test_runnable_models_declare_a_client_that_exists(self):
        for model in self.reg.models.values():
            if not model.runnable or not model.endpoint:
                continue
            self.assertTrue(model.client, f"{model.model_id}: runnable 인데 client 가 비었다")
            for rel in [c.strip() for c in model.client.split(",") if c.strip()]:
                if rel.endswith("/"):
                    continue
                path = self.pkg / rel if rel.startswith("clients/") else PROJECT_ROOT / rel
                self.assertTrue(path.exists(), f"{model.model_id}: 없는 클라이언트 {rel}")

    def test_not_wired_models_declare_no_client(self):
        for model in self.reg.models.values():
            if model.availability == "not_wired":
                self.assertEqual(model.client, "", f"{model.model_id}: not_wired 인데 client 를 주장한다")

    def test_declared_sources_exist_on_disk(self):
        for model in self.reg.models.values():
            for src in {model.cost.source, (model.performance or {}).get("source")}:
                if not src:
                    continue
                self.assertTrue((PROJECT_ROOT / src).exists(), f"{model.model_id}: 없는 근거 파일 {src}")


class CostModelTests(unittest.TestCase):
    """비용 모델의 형태를 잘못 적용하면 예산이 조용히 틀린다."""

    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry()

    def test_affine_intercept_is_charged_once_not_per_design(self):
        """ProteinMPNN 의 2.3 초는 호출당 고정비다. 설계마다 붙이면 안 된다."""
        mpnn = self.reg.models["proteinmpnn"]
        one = mpnn.cost.total_seconds(n_designs=1)
        sixteen = mpnn.cost.total_seconds(n_designs=16)
        # 16개가 1개의 16배보다 싸야 한다 - 고정비를 한 번만 내기 때문이다.
        self.assertLess(sixteen, one * 16)
        self.assertAlmostEqual(sixteen, 2.298 + 0.5602 * 16, places=3)

    def test_affine_model_matches_the_measured_medians(self):
        mpnn = self.reg.models["proteinmpnn"]
        for n, observed in ((1, 2.88), (4, 4.52), (16, 11.27)):
            predicted = mpnn.cost.total_seconds(n_designs=n)
            self.assertLess(abs(predicted - observed), 1.0, f"n={n}: {predicted} vs {observed}")

    def test_power_law_is_charged_per_design(self):
        """AF2 는 설계마다 한 번씩 접는다. 고정비 모델이 아니다."""
        af2 = self.reg.models["colabfold"]
        one = af2.cost.total_seconds(n_designs=1, length_aa=254)
        ten = af2.cost.total_seconds(n_designs=10, length_aa=254)
        self.assertAlmostEqual(ten, one * 10, places=3)
        self.assertLess(abs(one - 181.9), 1.0)

    def test_unmeasured_cost_totals_to_none_not_zero(self):
        self.assertIsNone(self.reg.models["soluprot"].cost.total_seconds(n_designs=100))

    def test_client_overhead_is_reported_and_not_folded_into_model_cost(self):
        """폴링 바닥값은 모델의 비용이 아니다. 섞으면 최적화 대상을 못 찾는다."""
        mpnn = self.reg.models["proteinmpnn"]
        overhead = mpnn.extra.get("client_overhead")
        self.assertIsNotNone(overhead)
        self.assertEqual(overhead["value"], 9.0)
        self.assertNotIn(9.0, {mpnn.cost.value})

    def test_route_cost_uses_the_right_model_per_stage(self):
        route = self.reg.route("monomer_solubility_redesign")
        estimate = route.cost_estimate(n_designs=16, length_aa=254)
        by_stage = {b["stage"]: b for b in estimate["breakdown"]}
        self.assertAlmostEqual(by_stage["sequence_design"]["seconds"], 2.298 + 0.5602 * 16, places=1)
        self.assertAlmostEqual(by_stage["structure_verify"]["seconds"], 181.9 * 16, delta=5)


class RuntimeDependencyTests(unittest.TestCase):
    """서비스는 PyYAML 없이도 레지스트리를 읽을 수 있어야 한다.

    dev 배포에서 `No module named 'yaml'` 로 guided 화면 전체가 죽었다. 모델
    목록만이 아니라 objective_planner 가 model_routing 을 import 하므로
    plan_from_objective / explain_plan / approve_plan 까지 같이 내려갔다.

    배포는 파일 복사 + systemd 재시작이고 중간에 pip install 단계가 없다. 그런
    경로에 서드파티 파서 의존을 넣으면, 그 라이브러리가 우연히 있는 환경에서만
    동작한다 - 실제로 prod venv 에는 있었고 dev venv 에는 없었다.

    그래서 런타임 소스는 JSON 이다. YAML 은 사람이 쓰는 원본이고 그 주석이
    문서다. PyYAML 이 있는 환경에서는 둘이 어긋났는지 확인한다.
    """

    #: PyYAML 을 못 찾게 만든 하위 인터프리터에서 돌린다. 같은 프로세스에서
    #: importlib.reload 로 흉내내면 클래스 정체성이 갈라져 다른 테스트를
    #: 오염시키고, 무엇보다 배포 환경을 그대로 재현하지 못한다.
    _BLOCK_YAML = (
        "import sys\n"
        "class _NoYaml:\n"
        "    def find_module(self, name, path=None):\n"
        "        if name == 'yaml':\n"
        "            raise ModuleNotFoundError(\"No module named 'yaml'\")\n"
        "        return None\n"
        "sys.meta_path.insert(0, _NoYaml())\n"
        "sys.path.insert(0, %r)\n"
    )

    def _run_without_yaml(self, body: str):
        import subprocess

        src = str(PROJECT_ROOT / "pipeline-mcp" / "src")
        script = (self._BLOCK_YAML % src) + body
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0,
                         f"PyYAML 없는 환경에서 실패했다\nstdout: {result.stdout}\n"
                         f"stderr: {result.stderr}")
        return result.stdout.strip()

    def test_the_registry_loads_without_pyyaml(self):
        out = self._run_without_yaml(
            "from pipeline_mcp.model_routing import load_registry\n"
            "r = load_registry()\n"
            "print(len(r.models), len(r.purposes))\n"
        )
        models, purposes = (int(x) for x in out.split())
        self.assertGreater(models, 0)
        self.assertGreater(purposes, 0)

    def test_the_module_does_not_import_yaml_at_top_level(self):
        source = (PROJECT_ROOT / "pipeline-mcp" / "src" / "pipeline_mcp"
                  / "model_routing.py").read_text(encoding="utf-8")
        top_level = [l for l in source.splitlines() if l.startswith("import yaml")]
        self.assertEqual(top_level, [],
                         "최상위 import 는 배포 환경에서 모듈 전체를 못 쓰게 만든다")

    def test_the_json_mirror_exists_beside_the_yaml_source(self):
        from pipeline_mcp.model_routing import REGISTRY_JSON_PATH, REGISTRY_PATH

        self.assertTrue(REGISTRY_PATH.exists())
        self.assertTrue(REGISTRY_JSON_PATH.exists(),
                        "JSON 미러가 없으면 PyYAML 없는 환경에서 서비스가 죽는다")

    def test_the_json_mirror_matches_the_yaml_source(self):
        """YAML 을 고치고 미러를 다시 만들지 않으면 런타임이 옛 값을 읽는다."""
        yaml = __import__("importlib").util.find_spec("yaml")
        if yaml is None:
            self.skipTest("PyYAML 이 없는 환경에서는 대조할 원본을 읽을 수 없다")
        from pipeline_mcp.model_routing import REGISTRY_JSON_PATH, REGISTRY_PATH, read_yaml_source
        import json

        self.assertEqual(read_yaml_source(REGISTRY_PATH),
                         json.loads(REGISTRY_JSON_PATH.read_text(encoding="utf-8")),
                         "MODEL_REGISTRY_V1.json 이 YAML 과 어긋났다. "
                         "scripts/transcoder/19_sync_model_registry.py 로 다시 생성한다")

    def test_drift_is_detected_when_pyyaml_is_available(self):
        from pipeline_mcp.model_routing import registry_drift

        self.assertEqual(registry_drift(), [])

    def test_the_whole_guided_flow_works_without_pyyaml(self):
        """guided 화면을 죽인 실제 경로. 세 툴이 모두 model_routing 을 거친다."""
        out = self._run_without_yaml(
            "from pipeline_mcp.objective_planner import Objective, build_plan, "
            "suggest_questions, apply_edits, plan_to_request_overrides\n"
            "plan = build_plan(Objective(weights={'solubility': 1.0}))\n"
            "suggest_questions(plan)\n"
            "plan_to_request_overrides(apply_edits(plan, {}))\n"
            "print(len(plan['decisions']), plan['route']['purpose'])\n"
        )
        count, purpose = out.split()
        self.assertGreater(int(count), 0)
        self.assertEqual(purpose, "monomer_solubility_redesign")

    def test_the_list_models_tool_answers_without_pyyaml(self):
        out = self._run_without_yaml(
            "from pipeline_mcp import tools\n"
            "d = tools.ToolDispatcher(type('R', (), {'gemini': None})())\n"
            "r = d.call_tool('pipeline.list_models', {})\n"
            "print(r['policy_version'], len(r['purposes']))\n"
        )
        version, purposes = out.split()
        self.assertTrue(version)
        self.assertGreater(int(purposes), 0)

    def test_the_json_mirror_is_tracked_and_not_gitignored(self):
        """미러가 배포되지 않으면 서비스는 YAML 로 넘어가고 dev 에서 다시 죽는다.

        저장소는 `*.json` 을 통째로 무시하고 예외를 열거한다. 미러는 산출물이
        아니라 소스이므로 그 예외 목록에 있어야 한다.
        """
        import subprocess

        from pipeline_mcp.model_routing import REGISTRY_JSON_PATH

        # check-ignore 는 부정 규칙에 걸려도 0 을 돌려주므로 쓸 수 없다. 실제로
        # 필요한 속성은 "추적되고 있다" 이고, 그것을 그대로 묻는다.
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(REGISTRY_JSON_PATH)],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"미러가 추적되지 않는다 - 배포에 포함되지 않는다: "
                         f"{result.stderr.strip()}")
