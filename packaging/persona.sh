#!/usr/bin/env bash
# Small independent public profile set; this is not the private upstream corpus.
# Sourced by the portable Linux launcher. No network lookup is performed.
uxr_random_uint32() {
  local value attempt
  for attempt in 1 2 3; do
    value="$(od -An -N4 -tu4 /dev/urandom)"
    value="${value//[[:space:]]/}"
    if [[ "$value" =~ ^[0-9]+$ ]] && (( value > 0 )); then
      printf '%s' "$value"
      return
    fi
  done
  [[ "$value" =~ ^[0-9]+$ ]] && (( value > 0 )) || {
    echo "tilion: could not obtain a nonzero random seed" >&2
    return 1
  }
  printf '%s' "$value"
}

uxr_prepare_persona() {
  local seed="${TILION_SEED:-}" country="${TILION_COUNTRY:-US}"
  local timezone="${TILION_TZ:-}" languages="${TILION_LANG:-}"
  local supplied_timezone="" supplied_languages="" accept_language=""
  local arg checksum index threads width height
  UXR_ARGS=()
  UXR_DEFAULTS=()
  while (($#)); do
    arg="$1"; shift
    case "$arg" in
      --user-agent)
        echo 'tilion: ignoring --user-agent; use --uxr-ua-*' >&2
        if (($#)) && [[ "$1" != --* ]]; then shift; fi ;;
      --user-agent=*|--enable-automation)
        echo 'tilion: ignoring flag that breaks persona coherence' >&2 ;;
      --uxr-*=*) UXR_ARGS+=("$arg") ;;
      --uxr-*)
        if (($#)) && [[ "$1" != --* ]]; then
          UXR_ARGS+=("$arg=$1"); shift
        else UXR_ARGS+=("$arg"); fi ;;
      *) UXR_ARGS+=("$arg") ;;
    esac
  done
  if [[ -n "${TILION_NO_DEFAULTS:-}" ]]; then
    [[ -z "$timezone" ]] || export TZ="$timezone"
    return
  fi
  local kept=()
  for arg in "${UXR_ARGS[@]}"; do
    case "$arg" in
      --uxr-seed=*) seed="${arg#*=}" ;;
      --uxr-country=*) country="${arg#*=}" ;;
      --uxr-timezone=*) supplied_timezone="${arg#*=}" ;;
      --uxr-languages=*) supplied_languages="${arg#*=}" ;;
      --accept-lang=*) accept_language="${arg#*=}" ;;
      --uxr-canvas-seed=*|--uxr-audio-seed=*)
        echo 'tilion: rendering noise is fresh per launch; use --uxr-seed for a structural profile' >&2
        continue ;;
    esac
    kept+=("$arg")
  done
  UXR_ARGS=("${kept[@]}")
  case "${country^^}" in
    US) UXR_TZ=America/New_York; UXR_LANG=en-US,en ;;
    GB) UXR_TZ=Europe/London; UXR_LANG=en-GB,en ;;
    DE) UXR_TZ=Europe/Berlin; UXR_LANG=de-DE,de,en ;;
    FR) UXR_TZ=Europe/Paris; UXR_LANG=fr-FR,fr,en ;;
    IT) UXR_TZ=Europe/Rome; UXR_LANG=it-IT,it,en ;;
    ID) UXR_TZ=Asia/Jakarta; UXR_LANG=id-ID,id,en ;;
    SG) UXR_TZ=Asia/Singapore; UXR_LANG=en-SG,en ;;
    JP) UXR_TZ=Asia/Tokyo; UXR_LANG=ja-JP,ja,en ;;
    AU) UXR_TZ=Australia/Sydney; UXR_LANG=en-AU,en ;;
    *)
      if [[ -z "${supplied_timezone:-$timezone}" || -z "${supplied_languages:-${languages:-$accept_language}}" ]]; then
        echo 'tilion: unknown country; provide timezone and languages explicitly' >&2
        return 2
      fi
      UXR_TZ="$timezone"; UXR_LANG="$languages" ;;
  esac
  UXR_TZ="${supplied_timezone:-${timezone:-$UXR_TZ}}"
  UXR_LANG="${supplied_languages:-${languages:-${accept_language:-$UXR_LANG}}}"
  if [[ -n "$accept_language" && "$accept_language" != "$UXR_LANG" ]]; then
    echo 'tilion: --accept-lang and persona languages must agree' >&2
    return 2
  fi
  [[ -n "$seed" ]] || seed="$(uxr_random_uint32)"
  checksum="$(printf '%s' "$seed" | cksum)"
  index=$(( ${checksum%% *} % 4 ))
  # All automatic profiles remain in the NVIDIA/D3D11 family supported by
  # the public numeric WebGL patches. Do not invent unsupported Apple/AMD limits.
  case "$index" in
    0) threads=8; width=1920; height=1080 ;;
    1) threads=12; width=1920; height=1080 ;;
    2) threads=16; width=2560; height=1440 ;;
    3) threads=16; width=1920; height=1200 ;;
  esac
  UXR_DEFAULTS=(
    --uxr-platform=Win32 --uxr-ua-platform=Windows
    '--uxr-ua-os=Windows NT 10.0; Win64; x64'
    --uxr-ua-arch=x86 --uxr-ua-bitness=64 --uxr-ua-platform-version=15.0.0
    '--uxr-ua-brand=Google Chrome'
    "--uxr-hw-concurrency=$threads" --uxr-device-memory=8
    '--uxr-webgl-vendor=Google Inc. (NVIDIA)'
    '--uxr-webgl-renderer=ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)'
    --uxr-webgl-fullparams=1 --uxr-webgpu-vendor=nvidia --uxr-webgpu-architecture=ampere
    --uxr-webgpu-description=
    "--uxr-canvas-seed=$(uxr_random_uint32)" "--uxr-audio-seed=$(uxr_random_uint32)"
    "--uxr-timezone=$UXR_TZ" "--uxr-languages=$UXR_LANG" "--accept-lang=$UXR_LANG"
    "--uxr-screen-width=$width" "--uxr-screen-height=$height"
    --uxr-webrtc-policy=disable_non_proxied_udp
  )
  export TZ="$UXR_TZ"
}
