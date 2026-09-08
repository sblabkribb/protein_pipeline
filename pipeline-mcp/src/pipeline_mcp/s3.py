import os
import re
import boto3
from pathlib import Path
from botocore.client import Config

#: run_id 는 MCP 인자에서 온다. 경로 조각으로 쓰기 전에 좁힌다 - "../" 하나면
#: 다운로드가 outputs/ 밖으로 나간다.
_SAFE_RUN_ID = re.compile(r"\A[A-Za-z0-9_.-]{1,128}\Z")


def _safe_run_id(run_id) -> str | None:
    """경로 조각으로 써도 되는 run_id 만 통과시킨다."""
    text = str(run_id or "")
    if not _SAFE_RUN_ID.fullmatch(text) or text in {".", ".."}:
        return None
    return text


def _inside(base: Path, candidate: Path) -> bool:
    """candidate 가 base 아래로 풀리는가. 심볼릭 링크까지 따져 본다.

    run_id 를 좁히는 것만으로는 부족하다. 원격 key 의 꼬리도 경로 조각이라
    거기에 "../" 가 들어가면 같은 문제가 난다.
    """
    try:
        return candidate.resolve().is_relative_to(base.resolve())
    except (OSError, ValueError):
        return False

class NCPStorage:
    def __init__(self):
        self._client = None
        self._initialized = False
        self.bucket_name = None

    def _ensure_initialized(self):
        if self._initialized:
            return
        
        self.endpoint_url = os.getenv("NCP_S3_ENDPOINT", "https://kr.object.ncloudstorage.com")
        self.access_key = os.getenv("NCP_S3_ACCESS_KEY")
        self.secret_key = os.getenv("NCP_S3_SECRET_KEY")
        self.bucket_name = os.getenv("NCP_S3_BUCKET", "protein-pipeline-outputs")
        self.region_name = os.getenv("NCP_S3_REGION", "kr-standard")
        
        if not self.access_key or not self.secret_key:
            self._client = None
        else:
            try:
                self._client = boto3.client(
                    's3',
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region_name,
                    config=Config(signature_version='s3v4')
                )
            except Exception:
                self._client = None
        self._initialized = True

    @property
    def client(self):
        self._ensure_initialized()
        return self._client

    @property
    def bucket(self):
        self._ensure_initialized()
        return self.bucket_name

    def upload_file(self, local_path, remote_path=None):
        self._ensure_initialized()
        if not self._client: return False
        if remote_path is None:
            remote_path = local_path
        
        try:
            self._client.upload_file(str(local_path), self.bucket_name, str(remote_path))
            return True
        except Exception as e:
            print(f"S3 Upload Failed: {e}")
            return False

    def sync_outputs(self, run_id, local_root="outputs"):
        """Syncs an entire run directory to S3"""
        self._ensure_initialized()
        if not self._client: return
        local_dir = Path(local_root) / run_id
        if not local_dir.exists(): return
        
        print(f"Syncing run {run_id} to NCP S3...")
        for file_path in local_dir.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(Path(local_root).parent)
                self.upload_file(file_path, str(relative_path))

    def list_runs(self, prefix="outputs/"):
        """Lists run directory names under a remote prefix"""
        self._ensure_initialized()
        if not self._client: return []
        runs = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix, Delimiter="/"):
                for cp in page.get("CommonPrefixes", []):
                    runs.append(cp["Prefix"][len(prefix):].rstrip("/"))
        except Exception as e:
            print(f"S3 List Failed: {e}")
        return runs

    def pull_outputs(self, run_id, local_root="outputs"):
        """Downloads an entire run directory from S3 (mirror of sync_outputs)"""
        self._ensure_initialized()
        if not self._client: return False
        run_id = _safe_run_id(run_id)
        if run_id is None:
            print("S3 Pull Refused: run_id 가 경로로 쓰기에 안전하지 않다")
            return False
        remote_prefix = f"outputs/{run_id}/"
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            keys = [obj["Key"] for page in paginator.paginate(Bucket=self.bucket_name, Prefix=remote_prefix) for obj in page.get("Contents", [])]
        except Exception as e:
            print(f"S3 List Failed: {e}")
            return False
        if not keys:
            print(f"No remote files for run {run_id}")
            return False
        local_dir = Path(local_root) / run_id
        local_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        for key in keys:
            relative = key[len("outputs/"):]
            dest_path = local_dir / relative[len(run_id) + 1:]
            # key 는 원격이 준 문자열이다. 그 꼬리가 밖을 가리키면 건너뛴다.
            if not _inside(local_dir, dest_path.parent):
                print(f"S3 Download Skipped (경로가 {local_dir} 밖이다): {key}")
                continue
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not _inside(local_dir, dest_path):
                print(f"S3 Download Skipped (경로가 {local_dir} 밖이다): {key}")
                continue
            try:
                self._client.download_file(self.bucket_name, key, str(dest_path))
                written += 1
            except Exception as e:
                print(f"S3 Download Failed ({key}): {e}")
        print(f"Pulled run {run_id} ({written}/{len(keys)} files) to {local_dir}")
        return True

    def pull_summary(self, run_id, local_root="outputs"):
        """Downloads only summary.json for a run"""
        self._ensure_initialized()
        if not self._client: return False
        run_id = _safe_run_id(run_id)
        if run_id is None:
            print("S3 Pull Refused: run_id 가 경로로 쓰기에 안전하지 않다")
            return False
        local_dir = Path(local_root) / run_id
        if not _inside(Path(local_root), local_dir):
            print("S3 Pull Refused: 대상 경로가 local_root 밖이다")
            return False
        local_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._client.download_file(self.bucket_name, f"outputs/{run_id}/summary.json", str(local_dir / "summary.json"))
            return True
        except Exception as e:
            print(f"S3 Download Failed (summary {run_id}): {e}")
            return False

    def download_model(self, model_name, local_dest="pipeline-mcp/models"):
        """Downloads latest model weights from S3"""
        self._ensure_initialized()
        if not self._client: return False
        dest_path = Path(local_dest) / model_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self._client.download_file(self.bucket_name, f"models/{model_name}", str(dest_path))
            return True
        except Exception:
            return False

ncp_storage = NCPStorage()
