#!/usr/bin/env bash
# Chromium 151 binds the DevTools endpoint to 127.0.0.1 only (it ignores
# --remote-debugging-address). Since `docker -p` forwards to the container's
# veth IP rather than its localhost, we run Chrome on an internal localhost
# port and bridge 0.0.0.0:9222 -> 127.0.0.1:9223 with socat. CDP clients that
# resolve the endpoint by URL (Playwright connect_over_cdp, Puppeteer connect)
# work transparently through the bridge.
set -euo pipefail
INTERNAL=9223
EXTERNAL=9222

# Keep the bridge's internal port authoritative, including split-value flags.
args=()
while (($#)); do
  case "$1" in
    --remote-debugging-port)
      echo "docker-entrypoint: ignoring --remote-debugging-port; CDP uses $EXTERNAL" >&2
      shift
      if (($#)) && [[ "$1" != --* ]]; then shift; fi
      ;;
    --remote-debugging-port=*)
      echo "docker-entrypoint: ignoring --remote-debugging-port; CDP uses $EXTERNAL" >&2
      shift
      ;;
    *) args+=("$1"); shift ;;
  esac
done

/opt/tilion/tilion \
  --headless=new \
  --no-sandbox \
  --enable-unsafe-swiftshader \
  --remote-debugging-port="$INTERNAL" \
  --user-data-dir=/tmp/tilion-profile \
  "${args[@]}" &
CHROME_PID=$!
BRIDGE_PID=""
cleanup() {
  for pid in "$CHROME_PID" "$BRIDGE_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
      wait "$pid" || echo "docker-entrypoint: child $pid terminated during cleanup" >&2
    fi
  done
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# Wait for Chrome's internal DevTools port to come up.
ready=0
for _ in $(seq 1 80); do
  if ! kill -0 "$CHROME_PID" 2>/dev/null; then
    echo "docker-entrypoint: browser exited before CDP became ready" >&2
    wait "$CHROME_PID" || exit $?
    exit 1
  fi
  if (exec 3<>"/dev/tcp/127.0.0.1/$INTERNAL") 2>/dev/null; then exec 3>&-; ready=1; break; fi
  sleep 0.5
done

if (( ! ready )); then
  echo "docker-entrypoint: timed out waiting for browser CDP on $INTERNAL" >&2
  exit 1
fi

socat TCP-LISTEN:"$EXTERNAL",fork,reuseaddr TCP:127.0.0.1:"$INTERNAL" &
BRIDGE_PID=$!
status=0
wait -n "$CHROME_PID" "$BRIDGE_PID" || status=$?
if (( status != 0 )); then
  echo "docker-entrypoint: browser or CDP bridge exited with status $status" >&2
fi
exit "$status"
