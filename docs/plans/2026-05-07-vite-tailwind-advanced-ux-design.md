# Vite Tailwind Advanced UX Design

## Problem

The Protein Pipeline frontend is still a static `index.html`, `app.js`, and `styles.css` surface. This keeps deployment simple, but it makes UI iteration slow, leaves no production build verification, and keeps the Advanced setup screen visually dense. The Advanced screen already has a disabled stepper, but users still see many options at once.

## Goals

- Add a Vite build path without rewriting the application framework.
- Add Tailwind CSS v4 as the frontend styling foundation.
- Keep the current static Caddy deployment working during the first rollout.
- Make Advanced setup feel staged and less error-prone.
- Preserve existing dev, staging, and production deployment boundaries.

## Non-Goals

- No React, Vue, or TypeScript rewrite in this pass.
- No migration of the full 25k-line `frontend/app.js` into components yet.
- No change to the backend API contract.
- No removal of the current CSS until the Vite/Tailwind path has been proven in dev.

## Architecture

The first rollout keeps the current browser entrypoints in place and adds Vite as a build and development layer around them. `frontend/package.json` gains `dev`, `build`, and `preview` scripts. The GitHub Actions test job and server deploy script both run the frontend build so broken imports, CSS processing, and asset errors are caught before deployment completes.

Tailwind v4 is introduced through the Vite plugin and a small CSS entry that can grow into the primary styling layer. Existing `styles.css` remains the compatibility stylesheet for the current Caddy root. Advanced UX improvements are applied to the current static UI first, then progressively moved toward Tailwind utilities and smaller modules.

## Advanced Setup UX

The Advanced setup will be reshaped around a staged mental model:

1. Scope: run mode plus start and stop stages.
2. Input: target PDB/FASTA, notes, and paper mask tools.
3. Core Options: common RFD3, BioEmu, AF2, conservation, and count settings.
4. Expert Options: detailed cutoffs, fixed positions, RFD3 mode internals, and advanced text inputs.
5. Review & Run: a compact summary of the effective run configuration before launch.

The existing hidden `setupStepper` will be activated only for the pipeline-style Advanced path. Non-pipeline specialist modes remain usable in the current compact layout until they receive their own staged UX.

## Visual Direction

The UI should move away from decorative orbs and oversized rounded panels toward a denser laboratory console:

- restrained neutral surface colors with teal accents only for state and action,
- compact cards with radius at or below 8px where possible,
- clear left-to-right workflow hierarchy,
- sticky run summary and primary action,
- visible environment badge for non-production,
- no in-app instruction text that explains obvious UI mechanics.

## Deployment Compatibility

The current Caddy setup serves:

- `/opt/protein_pipeline/frontend`
- `/opt/protein_pipeline-dev/frontend`
- `/opt/protein_pipeline-staging/frontend`

For the first pass, those roots continue to work. Vite `dist` output is built and verified but not required as the only served root yet. A later infrastructure pass can switch Caddy to `frontend/dist` once dev, staging, and production all have confirmed built assets.

## Verification

- `npm --prefix frontend test`
- `npm --prefix frontend run build`
- backend deployment pytest subset from `.github/workflows/deploy.yml`
- GitHub Actions success on `develop`
- dev health check at `https://dev-pipeline.k-biofoundrycopilot.duckdns.org/api/healthz`
- browser screenshot check for the Advanced setup flow after dev deployment

