# Compare Metadata Scope Selector Design

## Goal

Add a frontend-only selector to the Advanced setup tab's compact parameter board so users can decide whether Compare metadata should show RMSD against the input structure, the working backbone, both, or neither. The default must be off.

## Context

The current Compare metadata panel only shows WT structural RMSD. Users want to selectively re-enable the input/backbone RMSD comparisons without restoring them unconditionally.

This selector is a UI preference, not a pipeline execution parameter:

- It should be visible in the Advanced compact parameter board.
- It should not be sent to backend run payloads.
- It should default to `off`.
- It should control metadata rows in Compare/Analyze for the current frontend state.

## Options

Use a four-state selector:

- `off`
- `input`
- `backbone`
- `both`

These labels should be localized in English and Korean.

## Data Flow

1. Add a new setup answer key for compare metadata scope.
2. Render it in the compact parameter board as a select control instead of a numeric input.
3. Keep it in frontend answers/drafts so the UI can reference it.
4. Strip it from `buildRunArguments()` so backend requests remain unchanged.
5. Use the selected mode when building compare preview metadata:
   - `off`: show only existing WT RMSD rows
   - `input`: add input-structure RMSD
   - `backbone`: add working-backbone RMSD
   - `both`: add both

## Persistence

The selector should live in frontend draft/session state with a default of `off`. Because it is not part of the backend request contract, loading an older run request should still fall back to `off` unless the current frontend draft/session already carries a value.

## Testing

Add frontend tests that cover:

- source-level presence of the new compact parameter field and its default
- stripping the field from `buildRunArguments()`
- hydration/default behavior in `buildSetupDraftFromRequest()`
- compare metadata localization/tooltip coverage for the new rows
