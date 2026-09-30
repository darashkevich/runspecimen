#!/usr/bin/env bash
# Prove shipping RunSpecimenObserve Release has no test-hook symbols.
#
# Scans `nm -Uj` output from the Release app binary and the
# CompanionSecureEnclaveEnrollment.o module object. Forbidden names must be
# absent. Also asserts the shipping Xcode target does not compile
# DevelopmentCompanionSigner.swift (Dev target only).
#
# Optional Debug contrast (when RS_IOS_NM_COMPARE_DEBUG=1, default on when
# building): beforeFinalSignatureDecision must appear under Debug because that
# configuration defines RUNSPECIMEN_TEST_HOOKS.
#
# Not a production / App Store sign-off. Simulator Release is enough for CI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
PROJECT="$ROOT/RunSpecimenObserve.xcodeproj"
PBXPROJ="$PROJECT/project.pbxproj"
SCHEME="${RS_IOS_SCHEME:-RunSpecimenObserve}"
DESTINATION="${RS_IOS_DESTINATION:-generic/platform=iOS Simulator}"
DERIVED="${RS_IOS_DERIVED_DATA:-${TMPDIR:-/tmp}/rs-ios-release-symbols-$$}"
COMPARE_DEBUG="${RS_IOS_NM_COMPARE_DEBUG:-1}"
SKIP_BUILD="${RS_IOS_NM_SKIP_BUILD:-0}"

FORBIDDEN=(
  beforeConsumptionDecision
  beforeExclusiveAccess
  beforeFinalSignatureDecision
  retireUnusableKey
)

die() {
  echo "error: $*" >&2
  exit 1
}

require_xcode() {
  if ! command -v xcodebuild >/dev/null 2>&1; then
    die "xcodebuild not found (need macOS + Xcode)"
  fi
  if ! command -v nm >/dev/null 2>&1; then
    die "nm not found"
  fi
  [[ -d "$PROJECT" ]] || die "missing project: $PROJECT"
  [[ -f "$PBXPROJ" ]] || die "missing pbxproj: $PBXPROJ"
}

assert_shipping_excludes_dev_signer() {
  python3 - "$PBXPROJ" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
name = "RunSpecimenObserve"
idx = text.find(f"\t\t\tname = {name};\n")
if idx < 0:
    raise SystemExit(f"target {name} not found")
native = text.rfind("isa = PBXNativeTarget;", 0, idx)
chunk = text[native:idx]
m = re.search(r"([A-F0-9]+) /\* Sources \*/", chunk)
if not m:
    raise SystemExit("Sources phase id not found for RunSpecimenObserve")
ident = m.group(1)
start = text.find(f"\t\t{ident} /* Sources */ = {{")
end = text.find("\t\t};", start)
phase = text[start:end]
if "DevelopmentCompanionSigner.swift" in phase:
    raise SystemExit("shipping RunSpecimenObserve Sources includes DevelopmentCompanionSigner.swift")
if "DevelopmentCompanionSignView.swift" in phase:
    raise SystemExit("shipping RunSpecimenObserve Sources includes DevelopmentCompanionSignView.swift")
if "CompanionSecureEnclaveEnrollment.swift" not in phase:
    raise SystemExit("shipping RunSpecimenObserve Sources missing CompanionSecureEnclaveEnrollment.swift")
cfg = text
# Shipping Release must not define RUNSPECIMEN_TEST_HOOKS on the app target.
# ObserveSchemaTests and Debug may define it.
shipping_release = None
for m in re.finditer(
    r"/\* Release \*/ = \{\s*isa = XCBuildConfiguration;\s*buildSettings = \{(.*?)\};\s*name = Release;",
    text,
    re.S,
):
    settings = m.group(1)
    if "PRODUCT_BUNDLE_IDENTIFIER = com.darashkevich.runspecimen.observe;" in settings and ".dev" not in settings and "schema-tests" not in settings:
        shipping_release = settings
        break
if shipping_release is None:
    raise SystemExit("shipping Release build settings not found")
if "RUNSPECIMEN_TEST_HOOKS" in shipping_release:
    raise SystemExit("shipping Release defines RUNSPECIMEN_TEST_HOOKS")
if "RS_OBSERVE_DEV_SIGNER" in shipping_release:
    raise SystemExit("shipping Release defines RS_OBSERVE_DEV_SIGNER")
print("pbxproj: shipping Observe Sources exclude DevelopmentCompanionSigner; Release omits RUNSPECIMEN_TEST_HOOKS")
PY
}

build_config() {
  local config="$1"
  echo "==> xcodebuild $SCHEME $config ($DESTINATION)"
  xcodebuild \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -configuration "$config" \
    -destination "$DESTINATION" \
    -derivedDataPath "$DERIVED" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    build
}

product_dir() {
  local config="$1"
  # Simulator Release/Debug land under *-iphonesimulator.
  local cand
  for cand in \
    "$DERIVED/Build/Products/${config}-iphonesimulator" \
    "$DERIVED/Build/Products/${config}-iphoneos" \
    "$DERIVED/Build/Products/${config}"
  do
    if [[ -d "$cand/RunSpecimenObserve.app" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

# Prefer the Mach-O that actually carries app code.
shipping_machos() {
  local config="$1"
  local products app bin dylib
  products="$(product_dir "$config")" || die "no Products dir for $config under $DERIVED"
  app="$products/RunSpecimenObserve.app"
  bin="$app/RunSpecimenObserve"
  [[ -f "$bin" ]] || die "missing app binary: $bin"
  printf '%s\n' "$bin"
  dylib="$app/RunSpecimenObserve.debug.dylib"
  if [[ -f "$dylib" ]]; then
    printf '%s\n' "$dylib"
  fi
}

module_objects() {
  local config="$1"
  # Module equivalent of RunSpecimenCore.o for Observe: enrollment + any
  # Biometric*.o if a future source adds them.
  find "$DERIVED/Build/Intermediates.noindex" \
    -path "*/${config}-*/RunSpecimenObserve.build/Objects-normal/*/CompanionSecureEnclaveEnrollment.o" \
    -o -path "*/${config}-*/RunSpecimenObserve.build/Objects-normal/*/BiometricApproval.o" \
    2>/dev/null | sort -u
}

scan_nm() {
  local label="$1"
  shift
  local path matches count total
  echo "==> nm -Uj ($label)"
  for path in "$@"; do
    [[ -f "$path" ]] || die "missing scan target: $path"
    total="$(nm -Uj "$path" 2>/dev/null | wc -l | tr -d ' ')"
    echo "  file: $path"
    echo "  defined_symbol_lines: $total"
    for name in "${FORBIDDEN[@]}"; do
      matches="$(nm -Uj "$path" 2>/dev/null | grep -F "$name" || true)"
      if [[ -n "$matches" ]]; then
        count="$(printf '%s\n' "$matches" | grep -c . || true)"
      else
        count=0
      fi
      echo "  match[$name]=$count"
      if [[ "$count" != "0" ]]; then
        printf '%s\n' "$matches" | sed 's/^/    /'
      fi
    done
  done
}

assert_absent() {
  local label="$1"
  shift
  local path matches
  for path in "$@"; do
    for name in "${FORBIDDEN[@]}"; do
      matches="$(nm -Uj "$path" 2>/dev/null | grep -F "$name" || true)"
      if [[ -n "$matches" ]]; then
        echo "error: $label still contains $name in $path:" >&2
        printf '%s\n' "$matches" >&2
        exit 1
      fi
    done
    # Dev signer must never ship in Observe Release/Debug shipping target.
    matches="$(nm -Uj "$path" 2>/dev/null | grep -F 'DevelopmentCompanionSigner' || true)"
    if [[ -n "$matches" ]]; then
      echo "error: $label contains DevelopmentCompanionSigner in $path:" >&2
      printf '%s\n' "$matches" >&2
      exit 1
    fi
  done
  echo "ok: $label has empty nm -Uj matches for forbidden + DevelopmentCompanionSigner"
}

assert_debug_hook_present() {
  local path matches
  local found=0
  for path in "$@"; do
    matches="$(nm -Uj "$path" 2>/dev/null | grep -F 'beforeFinalSignatureDecision' || true)"
    if [[ -n "$matches" ]]; then
      found=1
      echo "ok: Debug contrast — beforeFinalSignatureDecision present in $path"
      printf '%s\n' "$matches" | head -n 5 | sed 's/^/  /'
      break
    fi
  done
  [[ "$found" == "1" ]] || die "Debug contrast expected beforeFinalSignatureDecision (RUNSPECIMEN_TEST_HOOKS) but nm -Uj matched nothing"
}

main() {
  cd "$ROOT"
  echo "repo=$REPO"
  echo "project=$PROJECT"
  echo "derived=$DERIVED"

  require_xcode
  assert_shipping_excludes_dev_signer

  if [[ "$SKIP_BUILD" != "1" ]]; then
    mkdir -p "$DERIVED"
    build_config Release
    if [[ "$COMPARE_DEBUG" == "1" ]]; then
      build_config Debug
    fi
  fi

  local release_machos=()
  local release_objs=()
  local path

  while IFS= read -r path; do
    release_machos+=("$path")
  done < <(shipping_machos Release)

  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    release_objs+=("$path")
  done < <(module_objects Release)

  [[ ${#release_machos[@]} -gt 0 ]] || die "no Release Mach-O found"
  [[ ${#release_objs[@]} -gt 0 ]] || die "no Release CompanionSecureEnclaveEnrollment.o found (build first)"

  scan_nm "Release app" "${release_machos[@]}"
  scan_nm "Release module objects" "${release_objs[@]}"
  assert_absent "Release" "${release_machos[@]}" "${release_objs[@]}"

  if [[ "$COMPARE_DEBUG" == "1" ]]; then
    local debug_targets=()
    if product_dir Debug >/dev/null 2>&1; then
      while IFS= read -r path; do
        debug_targets+=("$path")
      done < <(shipping_machos Debug)
    fi
    while IFS= read -r path; do
      [[ -n "$path" ]] || continue
      debug_targets+=("$path")
    done < <(module_objects Debug)
    [[ ${#debug_targets[@]} -gt 0 ]] || die "Debug contrast requested but no Debug artifacts under $DERIVED"
    scan_nm "Debug contrast" "${debug_targets[@]}"
    assert_debug_hook_present "${debug_targets[@]}"
  fi

  echo "==> verify_ios_release_symbols: PASS"
  echo "note: simulator Release build; not a device archive or App Store sign-off"
}

main "$@"
