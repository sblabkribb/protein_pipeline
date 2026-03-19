# Rosetta Relax Validation Checklist

**Purpose:** Verify that Rosetta FastRelax can run on the NPC before any permanent pipeline integration or host installation.

**Important**

- If the intended use is commercial, customer-facing, or otherwise outside Rosetta's non-commercial path, stop here and resolve licensing before downloading or running Rosetta.
- If the intended use is academic or otherwise non-commercial research, continue with the Docker smoke test below.

---

## 1. Confirm local prerequisites

Run:

```bash
docker --version
systemctl is-active docker.service
```

Expected:

- Docker prints a version.
- `docker.service` is `active`.

## 2. Pull the official Rosetta image

Run:

```bash
docker pull rosettacommons/rosetta:latest
```

Expected:

- The image pulls successfully without local build steps.

## 3. Inspect the image for FastRelax and database paths

Run:

```bash
docker run --rm rosettacommons/rosetta:latest bash -lc '
find / -maxdepth 5 -type f -name "relax*.linux*release" 2>/dev/null | sort | head -n 20
echo "---"
find / -maxdepth 5 -type d -name database 2>/dev/null | sort | head -n 20
'
```

Expected:

- At least one Rosetta relax executable path is shown.
- At least one Rosetta `database` directory path is shown.

Record the discovered values before continuing.

## 4. Prepare a smoke-test workspace

Run:

```bash
mkdir -p /opt/protein_pipeline/tmp/rosetta_relax_smoke
cd /opt/protein_pipeline/tmp/rosetta_relax_smoke
```

Add one representative PDB as `input.pdb`.

Suggested source:

- one AF2 `ranked_0.pdb` from an existing pipeline run
- or a small known-good test PDB already available locally

## 5. Run FastRelax in Docker

Replace:

- `<RELAX_BIN>` with the discovered executable path
- `<ROSETTA_DB>` with the discovered database path

Run:

```bash
docker run --rm \
  -v /opt/protein_pipeline/tmp/rosetta_relax_smoke:/work \
  -w /work \
  rosettacommons/rosetta:latest \
  bash -lc '
  "<RELAX_BIN>" \
    -database "<ROSETTA_DB>" \
    -s /work/input.pdb \
    -relax:fast \
    -nstruct 1 \
    -out:file:scorefile /work/score.sc \
    -out:path:all /work/out
  '
```

Expected:

- command exits with code `0`
- `/opt/protein_pipeline/tmp/rosetta_relax_smoke/score.sc` exists
- `/opt/protein_pipeline/tmp/rosetta_relax_smoke/out/` contains a relaxed PDB

## 6. Inspect score output

Run:

```bash
sed -n '1,20p' /opt/protein_pipeline/tmp/rosetta_relax_smoke/score.sc
```

Expected:

- the file contains Rosetta score columns
- at least one row is present for the generated output structure

Capture:

- `total_score`
- output structure name

## 7. Decide the runtime path

If the smoke test passes:

- short-term validation runtime: Docker wrapper
- steady-state pipeline runtime: native host install under `/opt/rosetta/...`

If the smoke test fails:

- keep Docker mode as the debugging surface
- do not wire `pipeline-mcp` to Rosetta yet

## 8. Exit criteria for code integration

Do not start backend integration until all of the following are true:

- license path is confirmed
- Docker smoke test succeeded
- an example `score.sc` was parsed manually
- the chosen representative metric is `score_per_residue` for cutoff purposes
