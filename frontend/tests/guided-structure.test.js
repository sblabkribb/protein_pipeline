import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  pdbArtifactLabel,
  pdbArtifactOptions,
  parsePdbChains,
  residueSelectionChips,
} from "../guided/structure.js";

// 이 파일은 순수 함수만 직접 실행한다. structure.js 의 모듈 최상위는 DOM 을
// 만지지 않는다(브라우저 배선은 facade 의 initStructureTab 이 한다) - 그래서
// node 에서 document 없이 import 된다.

test("pdbArtifactOptions keeps .pdb files only, with file-type allowlist", () => {
  // list_artifacts 는 파일과 디렉터리를 함께 돌려준다. dir 을 read_artifact 에
  // 넘기면 실패하므로 파일만 허용한다(monitor.js 와 같은 관행).
  const options = pdbArtifactOptions([
    { type: "file", path: "target.pdb" },
    { type: "file", path: "tiers/50/soluprot.json" },
    { type: "file", path: "tiers/50/af2/D0001/ranked_0.pdb" },
    { type: "dir", path: "tiers/50" },
    { type: "file", path: "backbones/bb1/designs/bb1.pdb" },
    { type: "file", path: "conservation.json" },
    { type: "file", path: "wt/af2/ranked_0.cif" },
  ]);
  assert.deepEqual(options.map((option) => option.path), [
    "target.pdb",
    "backbones/bb1/designs/bb1.pdb",
    "tiers/50/af2/D0001/ranked_0.pdb",
  ]);
});

test("pdbArtifactOptions dedupes repeated paths", () => {
  const options = pdbArtifactOptions([
    { type: "file", path: "target.pdb" },
    { type: "file", path: "target.pdb" },
  ]);
  assert.equal(options.length, 1);
});

test("pdbArtifactOptions tolerates junk input", () => {
  assert.deepEqual(pdbArtifactOptions(null), []);
  assert.deepEqual(pdbArtifactOptions("nope"), []);
  assert.deepEqual(pdbArtifactOptions([{}, { path: "" }]), []);
  // type 이 없으면 파일로 본다 - 서버가 type 을 빠뜨려도 목록이 사라지지 않게.
  const options = pdbArtifactOptions([{ path: "target.pdb" }]);
  assert.equal(options.length, 1);
});

test("pdbArtifactOptions sorts shallow paths before deep tier models", () => {
  // 기본 선택이 첫 번째 옵션이다. 루트의 target.pdb 와 백본 설계가 티어 랭크
  // 모델보다 먼저 와야 기본 선택이 의미가 있다.
  const options = pdbArtifactOptions([
    { type: "file", path: "tiers/90/af2/D0009/ranked_0.pdb" },
    { type: "file", path: "wt/af2/ranked_0.pdb" },
    { type: "file", path: "rfd3/designs/bb1.pdb" },
    { type: "file", path: "target.pdb" },
  ]);
  assert.deepEqual(options.map((option) => option.path), [
    "target.pdb",
    "rfd3/designs/bb1.pdb",
    "wt/af2/ranked_0.pdb",
    "tiers/90/af2/D0009/ranked_0.pdb",
  ]);
});

test("pdbArtifactLabel keeps short paths whole and keeps the tier on deep ones", () => {
  assert.equal(pdbArtifactLabel("target.pdb"), "target.pdb");
  assert.equal(pdbArtifactLabel("wt/af2/ranked_0.pdb"), "wt/af2/ranked_0.pdb");
  // tiers/<티어>/… 는 축약해도 티어를 잃지 않는다 - 어느 티어의 모델인지가 핵심
  // 정보이므로.
  assert.equal(
    pdbArtifactLabel("tiers/50/af2/D0001/ranked_0.pdb"),
    "t50/af2/D0001/ranked_0.pdb",
  );
  assert.equal(pdbArtifactLabel("backbones/bb1/designs/bb1.pdb"), "…/bb1/designs/bb1.pdb");
  assert.equal(pdbArtifactLabel(""), "");
  assert.equal(pdbArtifactLabel(null), "");
});

const PDB_TEXT = [
  "ATOM      1  CA  ALA A  10      11.111  12.222  13.333  1.00  0.00           C",
  "ATOM      2  CA  ARG A  11      14.111  15.222  16.333  1.00  0.00           C",
  "HETATM    3  CA  CA  A  12      17.111  18.222  19.333  1.00  0.00          Ca",
  "ATOM      4  CA  GLY B   5      21.111  22.222  23.333  1.00  0.00           C",
  "END",
].join("\n");

test("parsePdbChains reads ATOM records only, mapping three-letter to one-letter", () => {
  // HETATM 의 CA 는 알파탄소가 아니라 칼슘일 수 있다 - 잔기로 읽지 않는다.
  const { sequenceByChain, residueOrderByChain } = parsePdbChains(PDB_TEXT);
  assert.equal(sequenceByChain.A, "AR");
  assert.equal(sequenceByChain.B, "G");
  assert.deepEqual(residueOrderByChain.A, [10, 11]);
  assert.deepEqual(residueOrderByChain.B, [5]);
});

test("parsePdbChains tolerates junk, blank chains and unknown residues", () => {
  assert.deepEqual(parsePdbChains(null), { sequenceByChain: {}, residueOrderByChain: {} });
  assert.deepEqual(parsePdbChains(""), { sequenceByChain: {}, residueOrderByChain: {} });
  const blank = "ATOM      1  CA  UNK     1      11.111  12.222  13.333  1.00  0.00           C";
  const parsed = parsePdbChains(blank);
  // 사슬 칸이 비면 residue-picker 의 관행처럼 "_" 로 정규화한다.
  assert.equal(parsed.sequenceByChain._, "X");
  assert.deepEqual(parsed.residueOrderByChain._, [1]);
});

test("residueSelectionChips flattens the selection map in a stable order", () => {
  // 3D 뷰와 스트립 어느 쪽에서 골라도 같은 순서로 보여야 칩 목록이 흔들리지 않는다.
  const chips = residueSelectionChips({ B: [7, 3], A: [12] });
  assert.deepEqual(chips.map((chip) => chip.key), ["A:12", "B:3", "B:7"]);
  assert.deepEqual(residueSelectionChips({}), []);
  assert.deepEqual(residueSelectionChips(null), []);
});

test("source contract: structure reads pipeline artifacts into 3Dmol, stale-guarded", () => {
  const structure = readFileSync(new URL("../guided/structure.js", import.meta.url), "utf8");
  // 백엔드 계약: list_artifacts 의 .pdb 산출물을 read_artifact 텍스트로 읽는다.
  assert.ok(structure.includes("pipeline.read_artifact"));
  // 뷰어는 기존 앱과 같은 3Dmol(script 태그는 guided.html 이 이미 싣는다).
  assert.ok(structure.includes("$3Dmol"));
  assert.ok(/cartoon/.test(structure));
  // await 뒤에는 반드시 세대를 물어본다 - 낡은 구조가 새 실행 화면에 덧그려지면 안 된다.
  assert.ok(/isStale\(\) \|\| gen !== renderGen/.test(structure));
  // viewer 이중 초기화 방지: 붙어 있는 컨테이너가 있으면 재사용한다.
  assert.ok(/viewerEl\.isConnected/.test(structure));
  // 숨은 패널의 캔버스는 0×0 다 - 드러날 때 다시 재고 그리는 훅이 있어야
  // 첫 방문이 빈 박스가 되지 않는다.
  assert.ok(/export function onStructurePanelRevealed\(\)/.test(structure));
  assert.ok(/viewer\.resize\(\);\s*\n\s*viewer\.render\(\);/.test(structure));

  const facade = readFileSync(new URL("../guided.js", import.meta.url), "utf8");
  // Results·Evidence 와 같은 자리에서, 같은 isStale 술어로 채운다.
  assert.ok(facade.includes("refreshStructure(runId, {"));
  assert.ok(facade.includes("initStructureTab()"));
  // showPanel 이 Structure 탭을 드러낼 때 그 훅을 부른다.
  assert.ok(/name === "structure"\) onStructurePanelRevealed\(\)/.test(facade));
  assert.ok(facade.includes('getElementById("structureViewer")'));
  assert.ok(facade.includes("구조를 불러오지 못했습니다"));
});

test("source contract: guided.html wires the four structure anchors and 3Dmol", () => {
  const html = readFileSync(new URL("../guided.html", import.meta.url), "utf8");
  for (const id of ["structureFiles", "structureViewer", "residueStrip", "residueSelection"]) {
    assert.ok(html.includes(`id="${id}"`), `layout needs #${id}`);
  }
  // 구조 선택은 select 다 - 옵션 목록에서 고르는 동작이어야 스트립·3D 와 함께
  // 세 개의 조작 대상이 명확히 갈린다.
  assert.ok(/<select id="structureFiles"/.test(html));
  const tag = html.match(/<script[^>]*3Dmol-min\.js[^>]*>/s);
  assert.ok(tag, "the page must load 3Dmol");
  assert.ok(/integrity="sha384-/.test(tag[0]), "3Dmol must be pinned by hash");
});
