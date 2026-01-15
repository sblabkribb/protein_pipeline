# ProteinMPNN on Runpod Serverless

ProteinMPNN(https://github.com/dauparas/ProteinMPNN)을 Runpod Serverless로 호출해서 서열을 생성하고, 결과를 JSON으로 돌려주는 컨테이너 템플릿입니다.

기본값으로 **soluble model**(`--use_soluble_model`)을 사용하도록 되어 있습니다.

## 1) Docker 이미지 빌드/푸시

```bash
docker build -t <DOCKERHUB_USER>/proteinmpnn-runpod:latest .
docker push <DOCKERHUB_USER>/proteinmpnn-runpod:latest
```

ProteinMPNN 코드는 Docker build 중에 GitHub에서 clone 합니다. 특정 태그/브랜치를 쓰고 싶으면:

```bash
docker build --build-arg PROTEINMPNN_REF=<tag-or-branch> -t <DOCKERHUB_USER>/proteinmpnn-runpod:latest .
```

Runpod 기본 베이스 이미지를 바꾸고 싶으면(예: CUDA/torch 버전 변경):

```bash
docker build --build-arg BASE_IMAGE=runpod/pytorch:<tag> -t <DOCKERHUB_USER>/proteinmpnn-runpod:latest .
```

## 2) Runpod Serverless 배포

Runpod Serverless에서 새 Endpoint를 만들 때:

- Container image: 위에서 푸시한 이미지
- GPU: 원하는 타입 선택
- Command / Entrypoint: 기본값(CMD) 그대로 사용 (`python -u /workspace/handler.py`)

## 3) 요청/응답 스키마

요청(`input`)은 아래 키들을 지원합니다.

- `pdb` (string) 또는 `pdb_base64` (string, base64) 중 1개 필수
- `pdb_name` (string, optional, 기본: `"input"`)
- `use_soluble_model` (bool, optional, 기본: `true`)  ✅ 요구사항
- `model_name` (string, optional, 기본: `"v_48_020"`)
- `pdb_path_chains` (string 또는 list, optional) 예: `"A B"` 또는 `["A","B"]`
- `fixed_positions` (object, optional) 체인별 고정 residue index(1-based) 예: `{"A":[1,2,3], "B":[10,11]}`
- `num_seq_per_target` (int, optional, 기본: `1`)
- `batch_size` (int, optional, 기본: `1`)  (※ `num_seq_per_target % batch_size == 0` 이어야 함)
- `sampling_temp` (float/string/list, optional, 기본: `0.1`)
- `seed` (int, optional, 기본: `0`이면 랜덤)
- `backbone_noise` (float, optional, 기본: `0.0`)
- `cleanup` (bool, optional, 기본: `true`) `/tmp` 작업폴더 삭제

응답은 아래처럼 나옵니다.

- `native`: 입력 구조의 native sequence + 메타데이터
- `samples`: 생성된 sequences 리스트 (각 entry에 `T`, `sample`, `score`, `global_score`, `seq_recovery` 등이 포함)

## 4) Runpod API 호출 예시

### job 실행

```bash
export RUNPOD_API_KEY=...
export ENDPOINT_ID=...
python -m pip install requests

python - <<'PY'
import base64, json, os, requests

endpoint = os.environ["ENDPOINT_ID"]
api_key = os.environ["RUNPOD_API_KEY"]

with open("example.pdb","rb") as f:
    pdb_b64 = base64.b64encode(f.read()).decode()

payload = {
  "input": {
    "pdb_base64": pdb_b64,
    "use_soluble_model": True,
    "model_name": "v_48_020",
    "num_seq_per_target": 8,
    "batch_size": 1,
    "sampling_temp": 0.1,
    "seed": 1,
    "pdb_path_chains": "A"
  }
}

url = f"https://api.runpod.ai/v2/{endpoint}/run"
r = requests.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=60)
r.raise_for_status()
print(r.json())
PY
```

### status polling

```bash
curl -H "Authorization: Bearer $RUNPOD_API_KEY" \
  "https://api.runpod.ai/v2/$ENDPOINT_ID/status/<JOB_ID>"
```

## 5) client_example.py

```powershell
python -m pip install requests truststore
$env:ENDPOINT_ID="..."
$env:RUNPOD_API_KEY="..."
$env:PDB_PATH="example.pdb"
$env:RUNPOD_USE_TRUSTSTORE="1"
또는
$env:RUNPOD_SSL_VERIFY="0”
python client_example.py
```

기본으로 결과를 로컬에 저장합니다:

- JSON: `outputs/<JOB_ID>.json`
- FASTA: `outputs/<JOB_ID>.fasta`

환경변수로 제어:

- `OUTPUT_DIR` (기본: `outputs`)
- `OUTPUT_PREFIX` (기본: `<JOB_ID>`)
- `SAVE_JSON` / `SAVE_FASTA` (0/false로 끄기)
