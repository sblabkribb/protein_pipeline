# 폐기 사유 — staging 누락 (2026-09-12)

이 디렉터리의 산출물은 **원본 CATH PDB 를 그대로** RFD3/BioEmu 에 보내서
만들어졌다. 검증된 경로(`25_generate_holdout_backbones.py::stage_target`)는
`first_model_only` -> `drop_ca_less_atoms` -> `preprocess_pdb(strip_nonpositive,
renumber_from_1)` 를 거친 구조를 보낸다.

그 차이로 RFD3 가 5 개 타겟에서 `Residue ... not found in atom array` 로 죽었다.
`drop_ca_less_atoms` 의 docstring 이 이미 같은 실패를 적어 두었다 -
"CA 가 없는 잔기가 번호에 끼면 contig 가 원자 배열에 없는 잔기를 가리켜
검증에서 죽는다 (2iayA00: contig A3-113 인데 A28 이 없다)".

측정으로 확인: `1o22A00` 은 원본으로 u=0, staging 후 u=10/10 (attempts 40).

죽지 않은 19 개도 원본 구조로 생성됐으므로 RMSD 기준 구조와 contig 가
staging 판과 다르다. 숫자만 보고 살릴 수 없어 전부 다시 만든다.

남기는 이유: 어떤 실행이 왜 버려졌는지가 산출물에서 보여야 한다.
