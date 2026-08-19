FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache \
      python3 \
      py3-pip \
      git \
      rsync \
      tar \
      zstd \
      ca-certificates \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir requests esphome

COPY app.py /app.py
COPY web_ui.py /web_ui.py
COPY ui.html /ui.html
COPY run.sh /run.sh
RUN chmod 0755 /run.sh

CMD ["/run.sh"]
