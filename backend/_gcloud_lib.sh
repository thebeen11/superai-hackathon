#!/usr/bin/env bash
#
# Shared gcloud helpers for deploy.sh / init_db_job.sh.
#
# Why this exists: the Cloud SQL Admin API (sqladmin.googleapis.com) enforces a
# per-project, per-minute request quota shared by every administrative caller. When you
# exceed it, gcloud fails with 429 / rateLimitExceeded. The old scripts hid that behind
# `2>/dev/null || echo "already exists"`, so a quota error looked like success and the
# deploy carried on against resources that might not exist.
#
# These helpers do the opposite: they keep stderr, tell "already exists" apart from
# "throttled" apart from "actually broken", back off on throttling, and fail loudly on
# anything unexpected.
#
# Source this file; don't execute it. Targets bash 3.2 (macOS default) — no namerefs.

# Results of the last run_gcloud/gcloud_read/retry_gcloud call. Globals rather than
# command substitution on purpose: `$(...)` runs in a subshell, where both variable
# assignments and `exit` (see die) would be silently lost.
GCLOUD_STDERR=""
GCLOUD_STDOUT=""

# run_gcloud <gcloud args...>
# One gcloud call. stdout streams through to the terminal (so `run deploy` stays live);
# stderr is captured into $GCLOUD_STDERR instead of being discarded. Returns gcloud's code.
run_gcloud() {
  local err_file status
  err_file="$(mktemp)"
  status=0
  gcloud "$@" 2>"${err_file}" || status=$?
  GCLOUD_STDERR="$(cat "${err_file}")"
  GCLOUD_STDOUT=""
  rm -f "${err_file}"
  return "${status}"
}

# gcloud_read <gcloud args...>
# Same as run_gcloud, but captures stdout into $GCLOUD_STDOUT rather than printing it.
# Use for value reads (`--format='value(...)'`) so the caller keeps $GCLOUD_STDERR too.
gcloud_read() {
  local out_file err_file status
  out_file="$(mktemp)"; err_file="$(mktemp)"
  status=0
  gcloud "$@" >"${out_file}" 2>"${err_file}" || status=$?
  GCLOUD_STDOUT="$(cat "${out_file}")"
  GCLOUD_STDERR="$(cat "${err_file}")"
  rm -f "${out_file}" "${err_file}"
  return "${status}"
}

# gcloud_status [stderr-text]
# Classifies a gcloud failure. Defaults to $GCLOUD_STDERR when no argument is given.
# Echoes exactly one of: ALREADY_EXISTS | NOT_FOUND | RATE_LIMITED | OTHER
gcloud_status() {
  local text="${1-${GCLOUD_STDERR}}"
  # Rate limiting is checked FIRST: a throttled create can also name the resource, and
  # misreading a 429 as ALREADY_EXISTS is the exact bug this library exists to prevent.
  if printf '%s' "${text}" | grep -qiE 'ratelimitexceeded|quota exceeded|exceeded.*quota|resource_exhausted|too many requests|(^|[^0-9])429([^0-9]|$)|operation limit'; then
    echo RATE_LIMITED
  elif printf '%s' "${text}" | grep -qiE 'already exists|already_exists|(^|[^0-9])409([^0-9]|$)'; then
    echo ALREADY_EXISTS
  elif printf '%s' "${text}" | grep -qiE 'not found|not_found|does not exist|(^|[^0-9])404([^0-9]|$)'; then
    echo NOT_FOUND
  else
    echo OTHER
  fi
}

# _retry_with <runner> <max_attempts> -- <gcloud args...>
# Shared backoff loop. Retries ONLY on rate limiting (2,4,8,16,32s). Any other failure
# returns immediately with gcloud's exit code and $GCLOUD_STDERR intact, so the caller can
# classify it (e.g. treat ALREADY_EXISTS as fine).
_retry_with() {
  local runner="$1" max_attempts="$2"; shift 2
  [[ "${1:-}" == "--" ]] && shift
  local attempt=1 delay=2 status

  while :; do
    status=0
    "${runner}" "$@" || status=$?
    [[ ${status} -eq 0 ]] && return 0
    [[ "$(gcloud_status)" != RATE_LIMITED ]] && return "${status}"

    if [[ ${attempt} -ge ${max_attempts} ]]; then
      echo "    !! Cloud SQL Admin API still rate-limited after ${max_attempts} attempts." >&2
      echo "       gcloud: ${GCLOUD_STDERR}" >&2
      return "${status}"
    fi

    echo "    .. rate-limited (attempt ${attempt}/${max_attempts}); retrying in ${delay}s" >&2
    sleep "${delay}"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
  done
}

# retry_gcloud <max_attempts> -- <gcloud args...>   (stdout streams through)
retry_gcloud() { _retry_with run_gcloud "$@"; }

# retry_gcloud_read <max_attempts> -- <gcloud args...>   (stdout lands in $GCLOUD_STDOUT)
retry_gcloud_read() { _retry_with gcloud_read "$@"; }

# die <message...>
# Abort with the last gcloud stderr attached, so quota errors are never silent.
# Call from the main shell only — never inside $( ), where exit would not reach the script.
die() {
  echo "ERROR: $*" >&2
  [[ -n "${GCLOUD_STDERR}" ]] && echo "       gcloud: ${GCLOUD_STDERR}" >&2
  exit 1
}

# resource_exists <gcloud args...>
# Read-only existence probe, for use directly in `if` (NOT in `$( )`).
# Returns 0 if the resource exists, 1 if it is genuinely absent. A rate-limited or
# otherwise unexpected probe aborts the script rather than reporting "missing" — reading a
# 429 as "missing" would send us straight into a create call and deepen the throttling.
resource_exists() {
  if retry_gcloud_read 5 -- "$@"; then
    return 0
  fi
  case "$(gcloud_status)" in
    NOT_FOUND) return 1 ;;
    RATE_LIMITED) die "Cloud SQL Admin API quota exhausted while checking: gcloud $*" ;;
    *) die "unexpected failure while checking: gcloud $*" ;;
  esac
}
