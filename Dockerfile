FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION=0.1.0-alpha.1
ARG BUILD_ARCH=local

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3 py3-pip

COPY requirements.txt /requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r /requirements.txt

COPY run.sh /run.sh
COPY app /app/app
COPY web /app/web

RUN chmod a+x /run.sh
WORKDIR /app

CMD [ "/run.sh" ]

