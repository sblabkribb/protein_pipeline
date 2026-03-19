# RFD3 and BioEmu Control Redesign

**Goal:** Make RFD3 harder to misuse for near-native full-chain reconstruction, and make BioEmu safer by default while exposing steering controls for guided exploration.

**Scope**

- Add explicit RFD3 modes to backend and UI.
- Stop treating `rfd3_contig` as a universal required field.
- Change RFD3 `partial_t` handling from hard-coded global default injection to mode-aware behavior.
- Add RFD3 duplicate-backbone QA so repeated structures are visible in run artifacts.
- Restore BioEmu `filter_samples=true` as the default.
- Expose BioEmu steering config from pipeline/frontend to the RunPod handler.

**Design**

- RFD3 uses a canonical spec builder that depends on `rfd3_mode`.
- Supported modes:
  - `legacy_contig`: existing simple `input + contig` flow for backward compatibility.
  - `binder`: requires `contig`; optionally adds `hotspots`, `infer_ori_strategy`, and `is_non_loopy`.
  - `enzyme`: builds specs from `unindex`, `length`, and `select_fixed_atoms`.
  - `local_diversify`: starts from `input.pdb`; uses `partial_t` only when explicitly provided or when the mode default applies.
  - `advanced`: accepts `rfd3_inputs` / `rfd3_inputs_text` directly and bypasses simple synthesis.
- `rfd3_partial_t` becomes `float | None`.
- Default `partial_t=10.0` applies only to `local_diversify` when the user did not specify a value.
- `rfd3_contig` remains available, but only binder and legacy modes require it.

**UI**

- Setup and Studio show `rfd3_mode` first.
- RFD3 fields render conditionally:
  - `legacy_contig`: `rfd3_input_pdb`, `rfd3_contig`, `rfd3_max_return_designs`
  - `binder`: `rfd3_input_pdb`, `rfd3_contig`, `rfd3_hotspots`, `rfd3_infer_ori_strategy`, `rfd3_is_non_loopy`, `rfd3_max_return_designs`
  - `enzyme`: `rfd3_input_pdb`, `rfd3_unindex`, `rfd3_length`, `rfd3_select_fixed_atoms`, `rfd3_max_return_designs`
  - `local_diversify`: `rfd3_input_pdb`, `rfd3_partial_t`, `rfd3_max_return_designs`
  - `advanced`: `rfd3_inputs_text`, `rfd3_max_return_designs`
- BioEmu keeps the simple top-level flow, but adds advanced controls:
  - `bioemu_filter_samples`
  - `bioemu_steering_config_text`

**Artifacts and QA**

- RFD3 writes a `rfd3/diversity_summary.json` artifact containing duplicate groups and unique-count statistics.
- Exact duplicate CA-coordinate sets are grouped together. The pipeline does not drop them yet; it reports them so downstream issues are visible immediately.

**Testing**

- Backend tests cover:
  - BioEmu default `filter_samples=true`
  - BioEmu steering config pass-through
  - RFD3 mode-specific required inputs and spec synthesis
  - `local_diversify` default `partial_t=10.0`
  - duplicate-backbone QA summary generation
- Frontend tests cover:
  - new defaults in Setup/Studio metadata
  - mode-specific field visibility and filtering
  - payload shaping for RFD3/BioEmu advanced controls
