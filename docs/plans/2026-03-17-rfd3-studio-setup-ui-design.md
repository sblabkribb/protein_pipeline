# RFD3 Setup/Studio UI Design

## Goal

Make RFD3 mode-specific inputs discoverable in Setup, keep RFD3 mode names in English across both locales, localize Studio field help text, and remove the misleading Studio "New Workflow" action.

## Problems

- Setup hides `enzyme` and `advanced` inputs in generic config cards far below the `RFD3 mode` selector.
- `rfd3_contig` is treated differently from other mode-specific fields, so only contig-based modes feel discoverable.
- Studio shows English-only labels/help for several RFD3/BioEmu fields even in Korean UI.
- Studio's `New Workflow` action is not actually a new workflow; it clones the current session node order.
- The compact option board exposes `ligand_mask_use_original_target` as a shortened toggle even though it is not a core decision.

## Approved Direction

1. Keep the five RFD3 mode names in English in both locales:
   - `Local Diversify`
   - `Legacy Contig`
   - `Binder`
   - `Enzyme`
   - `Advanced`
2. In Setup, render a dedicated RFD3 mode details card directly after the `RFD3 mode` selector.
3. Show all mode-specific inputs in that card, not just contig-related ones.
4. Localize Studio field labels/help via i18n keys while keeping domain terms like `Binder`, `hotspots`, `orientation`, and `non-loopy` in English where appropriate.
5. Remove Studio workflow creation actions instead of renaming them.
6. Move `ligand_mask_use_original_target` out of the compact core option board so it remains available but stops competing with higher-value controls.

## UI Behavior

### Setup

- `RFD3 mode` remains in the options step.
- A new `RFD3 mode inputs` card appears immediately after the mode card when RFD3 is active.
- Visible controls by mode:
  - `Local Diversify`: no extra card fields beyond the existing `partial_t` parameter card.
  - `Legacy Contig`: `rfd3_contig`
  - `Binder`: `rfd3_contig`, `rfd3_hotspots`, `rfd3_infer_ori_strategy`, `rfd3_is_non_loopy`
  - `Enzyme`: `rfd3_unindex`, `rfd3_length`, `rfd3_select_fixed_atoms`
  - `Advanced`: `rfd3_inputs_text`
- These fields stop rendering again later as detached generic config cards.

### Studio

- Remove both toolbar and inline `New Workflow` actions.
- Keep adopting existing workflow runs from Monitor.
- RFD3/BioEmu field labels/help use i18n-backed copy in both locales.
- RFD3 mode names remain English in the selector for both locales.

## Validation

- Frontend tests should verify:
  - Studio no longer renders or wires `studio.action.new`.
  - RFD3 mode choice labels stay English in Korean locale source strings.
  - Setup source contains a dedicated RFD3 mode details card/render path.
  - Localized question keys exist for mode-specific RFD3/BioEmu fields.
