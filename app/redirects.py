"""Cloudflare Bulk Redirect list items. Append and delete only: replace-all could wipe every QR."""

import time

import requests

API = "https://api.cloudflare.com/client/v4"


class RedirectError(RuntimeError):
    pass


class Redirects:
    def __init__(
        self,
        account_id: str,
        list_id: str,
        token: str,
        host: str,
        poll_interval: float = 1.0,
        poll_timeout: float = 60.0,
    ) -> None:
        self._account = f"{API}/accounts/{account_id}"
        self._items_url = f"{self._account}/rules/lists/{list_id}/items"
        self._host = host
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"

    def items(self) -> dict[str, tuple[str, str]]:
        found: dict[str, tuple[str, str]] = {}
        params: dict[str, str] = {}
        while True:
            body = self._call("GET", self._items_url, params=params)
            for item in body["result"]:
                redirect = item["redirect"]
                source = redirect["source_url"].removeprefix(f"{self._host}/")
                target = redirect["target_url"].removeprefix(f"https://{self._host}/")
                found[source] = (item["id"], target)
            after = body.get("result_info", {}).get("cursors", {}).get("after")
            if not after:
                return found
            params = {"cursor": after}

    def point(self, source: str, target: str) -> None:
        existing = self.items().get(source)
        if existing and existing[1] == target:
            return
        if existing:
            self._wait(self._call("DELETE", self._items_url, json={"items": [{"id": existing[0]}]}))
        item = {
            "redirect": {
                "source_url": f"{self._host}/{source}",
                "target_url": f"https://{self._host}/{target}",
                "status_code": 302,
                "preserve_query_string": False,
                "subpath_matching": False,
                "include_subdomains": False,
                "preserve_path_suffix": False,
            }
        }
        self._wait(self._call("POST", self._items_url, json=[item]))

    def _call(self, method: str, url: str, **kwargs) -> dict:
        response = self._session.request(method, url, timeout=30, **kwargs)
        body = response.json()
        if not response.ok or not body.get("success"):
            raise RedirectError(f"{method} {url}: {response.status_code} {body.get('errors')}")
        return body

    def _wait(self, body: dict) -> None:
        op_url = f"{self._account}/rules/lists/bulk_operations/{body['result']['operation_id']}"
        deadline = time.monotonic() + self._poll_timeout
        while time.monotonic() < deadline:
            result = self._call("GET", op_url)["result"]
            if result["status"] == "completed":
                return
            if result["status"] == "failed":
                raise RedirectError(result.get("error", "bulk operation failed"))
            time.sleep(self._poll_interval)
        raise RedirectError(f"bulk operation {op_url} did not finish")
