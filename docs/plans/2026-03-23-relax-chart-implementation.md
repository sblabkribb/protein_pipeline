# Relax Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Relax/res scatter charts to Analyze and report outputs without cluttering the default chart view.

**Architecture:** Keep the existing SVG chart pipeline in `frontend/app.js`, add two new metric-pair scatter builders, and expose them only when relax metrics exist in current Analyze data. Reuse existing relax visibility helpers so table/compare/chart behavior stays consistent.

**Tech Stack:** Vanilla JS frontend, node:test, existing SVG chart rendering helpers.

---

### Task 1: Lock in missing chart behavior with tests

**Files:**
- Modify: `frontend/tests/pipeline.test.js`

**Step 1: Write the failing test**

Add tests that assert:
- `frontend/app.js` declares relax chart option keys and chart ids.
- relax chart options are gated behind relax metric helpers rather than always-on static behavior.

**Step 2: Run test to verify it fails**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: FAIL because the new relax chart ids and option keys are not present yet.

### Task 2: Add relax chart options and SVG builders

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`

**Step 1: Write minimal implementation**

Add:
- translation keys for `pLDDT vs Relax/res` and `RMSD vs Relax/res`
- shared scatter builder for metric pairs
- conditional chart option population for Analyze
- report SVG path support and report section chart defs for the new views

**Step 2: Run tests to verify they pass**

Run: `node --test frontend/tests/pipeline.test.js`
Expected: PASS

### Task 3: Verify syntax and behavior contract

**Files:**
- Modify: none

**Step 1: Run syntax checks**

Run:
- `node --check frontend/app.js`
- `node --check frontend/lib/compare.js`

**Step 2: Confirm relax cutoff remains optional**

Verify existing logic still keeps `relax_score_per_residue_cutoff` optional while `relax_enabled=true` controls execution.
