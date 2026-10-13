#!/usr/bin/with-contenv bashio
set -e

cd /app

# The Supervisor service declaration makes the MQTT broker available through
# Bashio, but it does not populate MQTT_HOST/MQTT_PORT automatically. Resolve
# the service here so the bridge can publish Home Assistant MQTT Discovery.
mqtt_host="$(bashio::services mqtt "host" 2>/dev/null || true)"
mqtt_port="$(bashio::services mqtt "port" 2>/dev/null || true)"
mqtt_user="$(bashio::services mqtt "username" 2>/dev/null || true)"
mqtt_password="$(bashio::services mqtt "password" 2>/dev/null || true)"
if [ -n "${mqtt_host}" ]; then
  export MQTT_HOST="${mqtt_host}"
  export MQTT_PORT="${mqtt_port:-1883}"
  export MQTT_USER="${mqtt_user}"
  export MQTT_PASSWORD="${mqtt_password}"
fi

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8100

