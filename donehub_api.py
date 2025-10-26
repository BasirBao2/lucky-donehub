"""DoneHub API 客户端封装."""

import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class DoneHubAPIError(Exception):
    """DoneHub API 调用异常."""


class DoneHubAPI:
    """DoneHub 后台接口轻量封装."""

    def __init__(self, base_url: str, access_token: str, quota_unit: int = 500000, timeout: int = 10):
        if not base_url:
            raise ValueError("DoneHub base_url 未配置")
        if not access_token:
            raise ValueError("DoneHub access_token 未配置")

        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.quota_unit = quota_unit
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise DoneHubAPIError(str(exc)) from exc

        if response.status_code >= 500:
            raise DoneHubAPIError(f"服务器错误 {response.status_code}")

        if response.status_code == 204:
            return {}

        text = (response.text or "").strip()
        if not text:
            return {}

        try:
            data = response.json()
        except ValueError as exc:
            # 某些接口可能返回纯文本（如 "OK" 或 html 错误页）
            lowered = text.lower()
            if response.status_code < 400 and lowered in {"ok", "success", "true"}:
                return {"success": True}
            if response.status_code >= 400:
                raise DoneHubAPIError(text[:200])
            raise DoneHubAPIError(f"响应非 JSON: {text[:120]}") from exc

        if isinstance(data, dict) and "error" in data:
            message = data.get("error", {}).get("message") or data.get("error")
            raise DoneHubAPIError(str(message))

        if isinstance(data, dict) and data.get("success") is False:
            raise DoneHubAPIError(str(data.get("message", "未知错误")))

        return data

    def get_current_user(self) -> Dict[str, Any]:
        data = self._request("GET", "/api/user/self")
        return data.get("data")

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        data = self._request("GET", f"/api/user/{user_id}")
        return data.get("data")

    def search_users(self, keyword: str) -> Dict[str, Any]:
        params = {"keyword": keyword}
        data = self._request("GET", "/api/user/", params=params)
        return data.get("data", {})

    def get_user_by_linuxdo_username(self, linuxdo_username: str) -> Optional[Dict[str, Any]]:
        if not linuxdo_username:
            return None

        users_data = self.search_users(linuxdo_username)
        items = users_data.get("data", [])
        if not items:
            return None

        for item in items:
            if item.get("linuxdo_username") == linuxdo_username:
                return item
        for item in items:
            if item.get("username") == linuxdo_username:
                return item

        return items[0]

    def get_user_by_linuxdo_id(self, linuxdo_id: str) -> Optional[Dict[str, Any]]:
        if not linuxdo_id:
            return None

        keyword = str(linuxdo_id)
        users_data = self.search_users(keyword)
        items = users_data.get("data", [])
        if not items:
            return None

        for item in items:
            candidate = item.get("linuxdo_id")
            if candidate is None:
                continue
            if str(candidate) == keyword:
                return item

        return None

    def change_user_quota(self, user_id: int, quota_delta_units: int, remark: str = "") -> None:
        payload = {"quota": quota_delta_units}
        if remark:
            payload["remark"] = remark
        data = self._request("POST", f"/api/user/quota/{user_id}", json=payload)
        if data.get("success") is False:
            raise DoneHubAPIError(str(data.get("message", "调整额度失败")))
