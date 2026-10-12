import threading
import time

import requests

from app import notify

MAX_HOPS = 2


def check_link(url: str) -> str | None:
    session = requests.Session()
    session.max_redirects = MAX_HOPS
    try:
        with session.get(url, stream=True, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            if response.status_code == 200 and content_type.startswith("audio/mpeg"):
                return None
            return f"{url} -> {response.url}: {response.status_code} {content_type}"
    except requests.TooManyRedirects:
        return f"{url}: more than {MAX_HOPS} redirects (loop?)"
    except requests.RequestException as e:
        return f"{url}: {e}"


def check_later(url: str, attempts: int = 8, delay: float = 15.0) -> None:
    # Redirect changes take a little while to reach Cloudflare's edge.
    threading.Thread(target=_check_with_retries, args=(url, attempts, delay), daemon=True).start()


def _check_with_retries(url: str, attempts: int, delay: float) -> None:
    for _ in range(attempts):
        problem = check_link(url)
        if problem is None:
            return
        time.sleep(delay)
    notify.send("Tune QR link broken", problem)


def check_all(urls: list[str]) -> list[str]:
    return [problem for url in urls if (problem := check_link(url))]
