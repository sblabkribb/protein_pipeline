---
marp: true
theme: default
class: lead
paginate: true
backgroundColor: #f8f9fa
---

# Protein Pipeline: AI-Driven Autonomous Design
### 지능형 자율 단백질 엔지니어링 파이프라인

- **미래형 실험실의 시작**
  - "단백질 엔지니어링의 미래, 지능형 자율 파이프라인 Protein Pipeline에 오신 것을 환영합니다."
- **자연어 기반 Context Copilot & Orchestration Agent**
  - 복잡한 파라미터 설정 대신, Copilot에게 자연어로 요청하세요.
  - 마스터 에이전트(Orchestration Agent)가 사용자의 타겟 PDB와 실험 의도를 이해하여, Temperature 및 컷오프 임계값을 스스로 조율하며 **다라운드 반복 설계(Multi-Round Iterative Design)**를 설계합니다.

![Login](/opt/protein_pipeline/docs/assets/user-manual/login.png)
![Copilot](/opt/protein_pipeline/docs/assets/user-manual/copilot.png)

---

# Autonomous Orchestration
### 전 과정 자율 오케스트레이션 시스템

- **단계별 자율 수행 (msa -> rfd3 -> bioemu -> design -> soluprot -> af2 -> novelty)**
  - 진화적 보존성 분석(MSA)부터 백본 생성, 역산 서열 설계(ProteinMPNN), 용해도 예측(SoluProt), 3D 구조 신뢰도 평가(AF2/ColabFold)까지 분산 모델 기반 전 과정 자동화
- **해석 및 설계 에이전트의 점진적 최적화 (Iterative Funnel)**
  - **해석 에이전트(Evaluation)**가 이전 라운드의 실패/성공(pLDDT, RMSD)을 분석합니다.
  - **설계 에이전트(Prompting)**가 성공 부위를 고정(fixed-position)하고 유연 부위를 재마스킹하여 타겟 구조에 수렴시킵니다.
- **효과**: 무거운 GPU 연산과 가벼운 연산을 모듈화하여 분산 할당하고, 자율 피드백 루프를 통해 연구자의 개입 없이 성공 확률 극대화

![Studio](/opt/protein_pipeline/docs/assets/user-manual/studio.png)
![Monitor](/opt/protein_pipeline/docs/assets/user-manual/monitor.png)

---

# Analysis, Verification & MCP Integration
### 정밀 분석 및 통합 연구 환경

- **입체적 구조 검증 및 다중 라운드 Hit 선별**
  - PyMOL이 연동된 분석 모듈로 3D 구조를 정밀 비교하고, 상위 1~5%의 신규성(Novelty)을 갖춘 혁신적 서열을 'Top-K Hit List'로 확정
- **능동 학습(Active Learning) 엔진 결합**
  - 에이전트가 가상 실험 오라클(SoluProt, AF2)과 능동 학습 모델을 결합해 복잡한 비선형적 변이 시너지(Epistasis)를 자율적으로 수학적 최적화
- **MCP 기반 생태계 연동**
  - 웹 브라우저부터 VS Code 등 IDE까지 끊김 없이 연결되는 연구 환경 (MCP) 제공

![Analyze](/opt/protein_pipeline/docs/assets/user-manual/analyze.png)
![Residue Picker](/opt/protein_pipeline/docs/assets/user-manual/residue_picker.png)