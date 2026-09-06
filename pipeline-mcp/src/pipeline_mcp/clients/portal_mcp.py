"""bio model portal 의 MCP 클라이언트.

포털은 `list_models` / `run_model` / `run_chain` / `job_status` / `job_result` 를
제공하고, 그 카탈로그에 antifold, anarcii, alphafold3, esmfold, boltz2 가 들어
있다. 이 경로를 쓰면 모델마다 클라이언트를 따로 쓰지 않고도 그 모델들에 닿는다.

닿는 것과 쓸 수 있는 것은 다르다. 항체 설계는 어느 영역을 열지 정하는 마스크
정책이 있어야 하는데 포털은 region 토큰을 검증할 뿐 그 결정을 내려주지 않는다.
그래서 이 클라이언트를 붙여도 항체 경로는 계속 막혀 있고, 레지스트리는 그
이유를 transport 가 아니라 design_policy 로 적는다.

프로토콜: `POST {base}/mcp` 에 JSON-RPC 2.0, `Authorization: Bearer <PAT>`.
`tools/call` 의 결과는 `result.content[0].text` 안에 JSON 문자열로 들어오고,
실패 여부는 `result.isError` 로 따로 온다.

설정은 환경변수로만 받는다. 기본 URL 을 넣지 않는 이유는, 잘못된 기본값이
있으면 "설정하지 않았다" 가 "연결에 실패했다" 로 둔갑하기 때문이다.
"""

from __future__ import annotations

from typing import Any, Callable
import json
import os
import urllib.error
import urllib.request

#: 설정 환경변수. .env 로만 받고 저장소에 값을 적지 않는다.
URL_ENV = "RAPID_PORTAL_MCP_URL"
TOKEN_ENV = "RAPID_PORTAL_MCP_TOKEN"


class PortalMcpError(RuntimeError):
    pass


def portal_config_from_env(env: dict | None = None) -> dict:
    """포털 MCP 설정 상태. 토큰 값 자체는 절대 돌려주지 않는다."""
    source = os.environ if env is None else env
    base_url = str(source.get(URL_ENV) or "").strip().rstrip("/")
    token = str(source.get(TOKEN_ENV) or "").strip()
    missing = []
    if not base_url:
        missing.append("url")
    if not token:
        missing.append("token")
    return {
        "configured": not missing,
        "base_url": base_url,
        "has_token": bool(token),
        "missing": missing,
        "url_env": URL_ENV,
        "token_env": TOKEN_ENV,
    }


def _http_post(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    request = urllib.request.Request(  # noqa: S310 - 운영자가 설정한 엔드포인트
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(body or "{}")
        except json.JSONDecodeError:
            raise PortalMcpError(f"포털이 JSON 이 아닌 HTTP {exc.code} 를 돌려줬다: {body[:200]}") from exc


class PortalMcpClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_s: float = 120.0,
        transport: Callable[[str, dict, dict, float], dict] | None = None,
    ) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        if not self.base_url:
            raise ValueError(f"포털 MCP URL 이 없다. {URL_ENV} 를 설정한다.")
        self.token = str(token or "").strip()
        if not self.token:
            raise ValueError(f"포털 MCP PAT 이 없다. {TOKEN_ENV} 를 설정한다.")
        self.timeout_s = float(timeout_s)
        self._transport = transport or _http_post
        self._next_id = 0

    @classmethod
    def from_env(cls, env: dict | None = None, **kwargs) -> "PortalMcpClient | None":
        """설정이 없으면 None. 예외를 던지지 않는 이유는 미설정이 오류가 아니기 때문이다."""
        source = os.environ if env is None else env
        config = portal_config_from_env(source)
        if not config["configured"]:
            return None
        return cls(base_url=config["base_url"], token=str(source[TOKEN_ENV]), **kwargs)

    def _rpc(self, method: str, params: dict) -> dict:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        try:
            response = self._transport(
                f"{self.base_url}/mcp", payload,
                {"Authorization": f"Bearer {self.token}"}, self.timeout_s,
            )
        except PortalMcpError:
            raise
        except Exception as exc:  # noqa: BLE001 - 어떤 전송 실패든 클라이언트 오류다
            raise PortalMcpError(f"포털 MCP 요청 실패: {exc}") from exc
        if not isinstance(response, dict):
            raise PortalMcpError("포털 MCP 응답이 객체가 아니다")
        if response.get("error"):
            error = response["error"]
            raise PortalMcpError(
                f"포털 MCP 오류 {error.get('code')}: {error.get('message')}"
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise PortalMcpError("포털 MCP 응답에 result 가 없다")
        return result

    def call_tool(self, name: str, arguments: dict) -> dict:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        blocks = result.get("content") or []
        text = ""
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = str(block.get("text") or "")
                break
        try:
            body = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            # 파싱 실패를 빈 결과로 삼키면 호출자는 도구가 아무것도 안 준 줄 안다.
            raise PortalMcpError(
                f"포털 도구 {name} 의 응답을 JSON 으로 읽을 수 없다: {text[:200]}"
            ) from exc
        if result.get("isError"):
            raise PortalMcpError(
                f"포털 도구 {name} 실패: {body.get('error') or text[:200]}"
            )
        return body if isinstance(body, dict) else {"result": body}

    def list_tools(self) -> list[dict]:
        return list(self._rpc("tools/list", {}).get("tools") or [])

    def list_model_keys(self) -> list[str]:
        body = self.call_tool("list_models", {})
        models = body.get("models")
        if not isinstance(models, list):
            raise PortalMcpError(
                "포털 list_models 가 models 목록을 돌려주지 않았다. 빈 목록으로 "
                "간주하면 '모델이 없다' 와 '물어보지 못했다' 가 구별되지 않는다."
            )
        return [str(m.get("key") or "").strip() for m in models if isinstance(m, dict)]
