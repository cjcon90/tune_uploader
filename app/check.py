import threading
import time

import requests

from app import notify

# A QR is one redirect from its tune: /<id> -> /<slug>. Anything longer is a chain.
MAX_HOPS = 1


def check_link(url: str, expected: str) -> str | None:
    session = requests.Session()
    session.max_redirects = MAX_HOPS
    try:
        with session.get(url, stream=True, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            if response.status_code != 200 or not content_type.startswith("audio/mpeg"):
                return f"{url} -> {response.url}: {response.status_code} {content_type}"
            if response.url != expected:
                return f"{url} -> {response.url}: expected {expected}"
            return None
    except requests.TooManyRedirects:
        return f"{url}: more than {MAX_HOPS} redirect (loop or chain?)"
    except requests.RequestException as e:
        return f"{url}: {e}"


def check_later(url: str, expected: str, attempts: int = 8, delay: float = 15.0) -> None:
    # Redirect changes take a little while to reach Cloudflare's edge.
    threading.Thread(
        target=_check_with_retries, args=(url, expected, attempts, delay), daemon=True
    ).start()


def _check_with_retries(url: str, expected: str, attempts: int, delay: float) -> None:
    for _ in range(attempts):
        problem = check_link(url, expected)
        if problem is None:
            return
        time.sleep(delay)
    notify.send("Tune QR link broken", problem)


def check_all(links: list[tuple[str, str]]) -> list[str]:
    return [problem for url, expected in links if (problem := check_link(url, expected))]
