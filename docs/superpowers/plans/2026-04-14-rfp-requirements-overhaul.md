# RFP Requirements Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Perform a complete overhaul of the requirements section in `/opt/protein_pipeline/protein_platform_rfp_ko.md` to align with Korean public sector SI standards and include expanded functional/non-functional items.

**Architecture:** Updating Markdown documentation. Ensuring consistency in terminology (DAG, Copilot, Model Registry) and maintaining a formal Korean tone (□, ㅇ, -).

**Tech Stack:** Markdown, Python (for verification if needed).

---

### Task 1: Update Section III.1 (Classification & Counts)

**Files:**
- Modify: `/opt/protein_pipeline/protein_platform_rfp_ko.md`

- [ ] **Step 1: Update the classification table with new counts (Total 61)**

```markdown
| 분류코드 | 분류기준 | 세부 내용 | 항목수 |
| :--- | :--- | :--- | :--- |
| SFR | 시스템 기능 요구사항 (System Function) | 핵심 로직, AI 모델 엔진, 워크플로우, 생물학적 분석 모듈 | 20 |
| DAR | 데이터 요구사항 (Data Requirement) | 데이터베이스, 메타데이터, 라운드 데이터 관리, 마이그레이션 | 8 |
| SER | 보안 요구사항 (Security) | 인증/권한, 암호화, 로그, 네트워크 보안, 격리 | 8 |
| UIR | 사용자 인터페이스 요구사항 (User Interface) | 웹 콘솔, 시각적 레이아웃, 스튜디오, 대화형 UI | 4 |
| SIR | 시스템 인터페이스 요구사항 (System Interface) | MCP 연계, API 연동, 모델 레지스트리 라우팅 | 4 |
| PER | 성능 요구사항 (Performance) | 처리 속도, 동시성, 자원 효율성, 렌더링 최적화 | 3 |
| QUR | 품질 요구사항 (Quality) | 표준 준수, 문서화 품질, 재현성, 코드 품질 | 2 |
| TER | 테스트 요구사항 (Test) | 테스트 단계별 검증, 장애 복구 및 가용성 검증 | 2 |
| COR | 제약 요구사항 (Constraint) | 라이선스, 레거시 호환성, 하드웨어 제약 | 2 |
| PMR | 프로젝트 관리 요구사항 (Project Management) | 보고 체계, 일정/위험 관리, 형상 관리 | 5 |
| PSR | 프로젝트 지원 요구사항 (Project Support) | 교육 훈련, 유지관리, 기술지원, 지식 전수 | 3 |
| 합 계 | | | 61 |
```

### Task 2: Rewrite Section III.2 (Detailed Requirements)

**Files:**
- Modify: `/opt/protein_pipeline/protein_platform_rfp_ko.md`

- [ ] **Step 1: Rewrite SFR (System Function Requirement) Table (SFR-001 to SFR-020)**
    - Include: DAG Studio, AI Copilot, 7 Core Models, Biological Analysis, Model Registry.

- [ ] **Step 2: Rewrite DAR (Data Requirement) Table (DAR-001 to DAR-008)**
    - Include: Model Registry storage, Round DB, Metadata, Migration, AI learning dataset.

- [ ] **Step 3: Rewrite SER (Security Requirement) Table (SER-001 to SER-008)**
    - Include: RBAC, SSO, Encryption, Audit trails, Network isolation.

- [ ] **Step 4: Rewrite UIR, SIR, PER, QUR, TER, COR, PMR, PSR Tables**
    - Match counts: UIR(4), SIR(4), PER(3), QUR(2), TER(2), COR(2), PMR(5), PSR(3).

### Task 3: Rewrite [별지] Sections

**Files:**
- Modify: `/opt/protein_pipeline/protein_platform_rfp_ko.md`

- [ ] **Step 1: Rewrite [별지] 1. 요구사항 총괄표**
    - List all 61 items with IDs and Names.

- [ ] **Step 2: Rewrite [별지] 3. 검수 및 실증 항목**
    - Synchronize with the new requirements.

### Task 4: Final Consistency Check & Commit

**Files:**
- Modify: `/opt/protein_pipeline/protein_platform_rfp_ko.md`

- [ ] **Step 1: Verify all terms (DAG, Copilot, Model Registry) are consistent.**
- [ ] **Step 2: Verify total counts match (61 items).**
- [ ] **Step 3: Commit the changes.**

Run: `git add /opt/protein_pipeline/protein_platform_rfp_ko.md`
Run: `git commit -m "docs: complete overhaul of RFP requirements with formal SI classification and extended items"`
