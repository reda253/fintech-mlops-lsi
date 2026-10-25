#!/bin/sh
set -eu

GATEWAY_UPSTREAM=${GATEWAY_UPSTREAM:-http://api-gateway:8080}
# Only an internal HTTP host:port is accepted, never a path or nginx directives.
case "$GATEWAY_UPSTREAM" in
    *[!A-Za-z0-9:/._-]*)
        echo 'GATEWAY_UPSTREAM contains forbidden characters' >&2
        exit 1
        ;;
esac
if ! printf '%s\n' "$GATEWAY_UPSTREAM" | grep -Eq '^http://[A-Za-z0-9][A-Za-z0-9._-]*:[0-9]{1,5}$'; then
    echo 'GATEWAY_UPSTREAM must be http://host:port (no path or credentials)' >&2
    exit 1
fi
port=${GATEWAY_UPSTREAM##*:}
if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
    echo 'GATEWAY_UPSTREAM port must be between 1 and 65535' >&2
    exit 1
fi
export GATEWAY_UPSTREAM
envsubst '${GATEWAY_UPSTREAM}' < /etc/nginx/frontend.conf.template > /tmp/frontend.conf
exec nginx -c /tmp/frontend.conf -g 'daemon off;'
