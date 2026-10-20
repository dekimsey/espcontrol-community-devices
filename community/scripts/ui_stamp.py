#!/usr/bin/env python3
"""
ui_stamp.py – Keep the `ui=` cache buster in each device's js_url current.

Self-built devices (the esphome.yaml / dashboard path) load the web UI from
Pages via the js_url in devices/<slug>/packages.yaml. That URL carried only
`v=${firmware_version}`, which does not change when we redeploy a rebuilt
bundle — so a UI fix reached self-builders only once the browser's cached
copy expired (Pages serves max-age=600).

Upstream solves this with a hand-maintained constant (`&ui=20260714-shared`
in common/device/core_infra.yaml). Ours is derived instead, so it cannot be
forgotten: the stamp is a digest of the inputs that determine what the built
bundle contains. Change any of them and the stamp changes, so every browser
refetches on the next load instead of waiting out the TTL.

Released firmware is unaffected either way — its factory build sets
js_url: "" and embeds the bundle (see issue #54).

Usage:
    python3 community/scripts/ui_stamp.py            # print the stamp
    python3 community/scripts/ui_stamp.py --check    # CI: packages.yaml current?
    python3 community/scripts/ui_stamp.py --write    # restamp packages.yaml
    python3 community/scripts/ui_stamp.py --self-test
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# What the bundle is built from: upstream's sources at the pin, our catalog
# fragment merged into the device catalog (this is where per-device web
# geometry lives), and the postprocess pass that rewrites the built bundle.
# assemble.py's build_web() is the authority on this list — if it grows a new
# community input, add it here or the stamp goes stale without anyone noticing.
STAMP_INPUTS = (
    os.path.join("community", "upstream-ref.txt"),
    os.path.join("community", "catalog-fragment.json"),
    os.path.join("community", "scripts", "postprocess_www.py"),
)

STAMP_LEN = 12

# js_url line in a converted packages.yaml, with or without an existing stamp.
JS_URL_RE = re.compile(
    r"^(?P<prefix>\s*js_url:\s*\S*?www\.js\?[^\s]*?"
    r"v=\$\{firmware_version\})(?:&ui=(?P<stamp>[0-9a-f]+))?(?P<suffix>\s*)$",
    re.MULTILINE,
)


def compute_stamp(repo_root=REPO_ROOT):
    """Digest of the bundle's inputs. Stable across machines and checkouts."""
    digest = hashlib.sha256()
    for rel in STAMP_INPUTS:
        path = os.path.join(repo_root, rel)
        with open(path, "rb") as f:
            payload = f.read()
        # Name the input as well, so moving content between files still moves
        # the stamp.
        digest.update(rel.encode("utf-8"))
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    # assemble.py offers the camera screensaver in the web UI on exactly the
    # devices whose packages.yaml sets screensaver_camera_supported "true", so
    # that list shapes the built bundle too. It lives in the packages.yaml
    # files themselves, which carry the stamp, so it cannot be a file input.
    digest.update(b"camera-screensaver-slugs-v1:")
    digest.update(",".join(camera_supported_slugs(repo_root)).encode("utf-8"))
    return digest.hexdigest()[:STAMP_LEN]


CAMERA_SUPPORTED_RE = re.compile(
    r'^\s*screensaver_camera_supported:\s*"true"\s*$', re.MULTILINE)


def camera_supported_slugs(repo_root=REPO_ROOT):
    """Devices whose packages.yaml says the firmware has the camera screensaver."""
    try:
        with open(os.path.join(repo_root, "community", "devices.json")) as f:
            slugs = json.load(f)["devices"]
    except (OSError, ValueError, KeyError):
        return []
    found = []
    for slug in slugs:
        try:
            with open(os.path.join(repo_root, "devices", slug, "packages.yaml")) as f:
                if CAMERA_SUPPORTED_RE.search(f.read()):
                    found.append(slug)
        except OSError:
            continue
    return sorted(found)


def packages_files(repo_root=REPO_ROOT):
    """Every registered device's packages.yaml, in devices.json order."""
    with open(os.path.join(repo_root, "community", "devices.json")) as f:
        slugs = json.load(f)["devices"]
    return [
        os.path.join(repo_root, "devices", slug, "packages.yaml") for slug in slugs
    ]


def restamp(content, stamp):
    """Return ``content`` with the js_url stamp set to ``stamp``."""
    return JS_URL_RE.sub(
        lambda m: f"{m.group('prefix')}&ui={stamp}{m.group('suffix')}", content
    )


def current_stamp(content):
    """The stamp a packages.yaml currently carries, or None if it has none."""
    match = JS_URL_RE.search(content)
    return match.group("stamp") if match else None


def check(repo_root=REPO_ROOT):
    stamp = compute_stamp(repo_root)
    stale = []
    for path in packages_files(repo_root):
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if not JS_URL_RE.search(content):
            stale.append((path, "no js_url found"))
        elif current_stamp(content) != stamp:
            stale.append((path, f"has ui={current_stamp(content)}, expected {stamp}"))

    if stale:
        print(f"[ui_stamp] UI cache stamp is out of date (expected {stamp}):")
        for path, why in stale:
            print(f"  {os.path.relpath(path, repo_root)}: {why}")
        print("\nRun: python3 community/scripts/ui_stamp.py --write")
        return 1
    print(f"[ui_stamp] all packages.yaml carry the current stamp ({stamp})")
    return 0


def write(repo_root=REPO_ROOT):
    stamp = compute_stamp(repo_root)
    changed = []
    for path in packages_files(repo_root):
        with open(path, encoding="utf-8") as f:
            content = f.read()
        updated = restamp(content, stamp)
        if updated != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
            changed.append(os.path.relpath(path, repo_root))
    for path in changed:
        print(f"[ui_stamp] restamped {path}")
    print(f"[ui_stamp] stamp is {stamp} ({len(changed)} file(s) updated)")
    return 0


def self_test():
    import shutil
    import tempfile

    failures = []
    base = (
        "web_server:\n"
        "  js_url: https://example.test/webserver/www.js"
        "?device=${device_slug}&v=${firmware_version}\n"
    )

    stamped = restamp(base, "abc123")
    if "&ui=abc123\n" not in stamped:
        failures.append(f"stamp not appended: {stamped!r}")
    if current_stamp(stamped) != "abc123":
        failures.append(f"stamp not read back: {current_stamp(stamped)}")

    # Restamping is idempotent and replaces rather than accumulates.
    twice = restamp(stamped, "def456")
    if "abc123" in twice or twice.count("&ui=") != 1:
        failures.append(f"restamp did not replace cleanly: {twice!r}")
    if restamp(twice, "def456") != twice:
        failures.append("restamp is not idempotent")

    # The rest of the URL must survive untouched.
    if "?device=${device_slug}&v=${firmware_version}" not in twice:
        failures.append(f"query string was mangled: {twice!r}")

    # A file with no js_url is left alone (and check() reports it).
    if restamp("web_server:\n  port: 80\n", "abc123") != "web_server:\n  port: 80\n":
        failures.append("non-js_url content was modified")

    tmp = tempfile.mkdtemp(prefix="ui_stamp_test_")
    try:
        for rel in STAMP_INPUTS:
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write("seed\n")
        first = compute_stamp(tmp)
        if len(first) != STAMP_LEN:
            failures.append(f"stamp length {len(first)} != {STAMP_LEN}")
        if compute_stamp(tmp) != first:
            failures.append("stamp is not deterministic")

        # The bundle inputs each move the stamp — this is the whole point:
        # the #52 fix lived in catalog-fragment.json.
        for rel in STAMP_INPUTS:
            path = os.path.join(tmp, rel)
            with open(path, "w") as f:
                f.write("changed\n")
            if compute_stamp(tmp) == first:
                failures.append(f"stamp did not change when {rel} changed")
            with open(path, "w") as f:
                f.write("seed\n")
        if compute_stamp(tmp) != first:
            failures.append("stamp did not return after reverting inputs")

        # check()/write() round trip over a fake device tree.
        os.makedirs(os.path.join(tmp, "devices", "demo"), exist_ok=True)
        with open(os.path.join(tmp, "community", "devices.json"), "w") as f:
            json.dump({"devices": ["demo"]}, f)
        pkg = os.path.join(tmp, "devices", "demo", "packages.yaml")
        with open(pkg, "w") as f:
            f.write(base)
        if check(tmp) == 0:
            failures.append("check() passed an unstamped packages.yaml")
        write(tmp)
        if check(tmp) != 0:
            failures.append("check() failed right after write()")
        with open(os.path.join(tmp, STAMP_INPUTS[1]), "w") as f:
            f.write("new geometry\n")
        if check(tmp) == 0:
            failures.append("check() passed after an input changed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        for msg in failures:
            print(f"[ui_stamp] self-test: {msg}", file=sys.stderr)
        return 1
    print("[ui_stamp] self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify packages.yaml")
    parser.add_argument("--write", action="store_true", help="restamp packages.yaml")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())
    if args.check:
        sys.exit(check())
    if args.write:
        sys.exit(write())
    print(compute_stamp())


if __name__ == "__main__":
    main()
