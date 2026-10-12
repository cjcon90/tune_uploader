import logging

import requests

from app import config

log = logging.getLogger(__name__)


def send(title: str, message: str) -> None:
    log.error("%s: %s", title, message)
    try:
        requests.post(
            config.NTFY_URL,
            data=message.encode(),
            headers={
                "Title": title,
                "Priority": "high",
                "Authorization": f"Bearer {config.NTFY_TOKEN}",
            },
            timeout=10,
        )
    except requests.RequestException:
        log.exception("ntfy unreachable")
