import os

AUDIO_HOST = "audio.paulinemahon.com"
PRIVATE_BUCKET = "pm-tunes"
AUDIO_BUCKET = "pm-audio"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_LIST_ID = os.environ.get("CF_LIST_ID", "")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
PASSWORD_HASH = os.environ.get("PASSWORD_HASH", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
NTFY_URL = os.environ.get("NTFY_URL", "http://192.168.0.14/alerts")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")
