FROM python:3.13-slim

ARG MUSESCORE_URL=https://github.com/musescore/MuseScore/releases/download/v4.7.5/MuseScore-Studio-4.7.5.260831071-x86_64.AppImage
ARG MUSESCORE_SHA256=a31b2da2dbcc2191bcc98beb7be5c15f2f517bedb3444def96fe3088b74d3a1e
# MuseScore 4.7 ignores QT_QPA_PLATFORM=offscreen and insists on X11, hence Xvfb.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates ffmpeg poppler-utils xvfb xauth \
      libgl1 libegl1 libopengl0 libfontconfig1 libfreetype6 libglib2.0-0t64 libnss3 \
      libasound2t64 libxkbcommon0 libxkbcommon-x11-0 libdbus-1-3 \
      libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
      libxcb-xinerama0 libxcb-xkb1 libxcb-shape0 libxcb-randr0 \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL "$MUSESCORE_URL" -o /tmp/ms.AppImage \
    && echo "$MUSESCORE_SHA256  /tmp/ms.AppImage" | sha256sum -c - \
    && chmod +x /tmp/ms.AppImage \
    && cd /opt && /tmp/ms.AppImage --appimage-extract >/dev/null \
    && mv /opt/squashfs-root /opt/musescore && rm /tmp/ms.AppImage \
    && ln -s /opt/musescore/AppRun /usr/local/bin/mscore
ENV HOME=/tmp LANG=C.UTF-8

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
ARG DEV=0
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$DEV" = 1 ]; then pip install --no-cache-dir -r requirements-dev.txt; fi
COPY . .
RUN useradd --system --no-create-home app
USER app

EXPOSE 8000
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "300", \
     "--bind", "0.0.0.0:8000", "run:app"]
