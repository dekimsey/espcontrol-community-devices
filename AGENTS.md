# Project guidance

## Release tag versioning

Before creating, publishing, or recommending a release tag, read
[`community/DEVICES_POLICY.md`](community/DEVICES_POLICY.md), **Version
numbering** (lines 66–85). Tags are
`community-vX.Y.Z-upstream.vA.B.C[-preview.N]`:

- `X.Y.Z` is the community release version; `A.B.C` is the pinned upstream
  EspControl version. They must be reasoned about independently.
- Do not reuse a community `X.Y.Z` for a different upstream version. A
  v2.11.2 → v2.12.1 upstream bump therefore needs a new community minor
  version (for example, v0.13.1 → v0.14.0), not
  `v0.13.1-upstream.v2.12.1`.
- Increment community `Y` when upstream `A` or `B` changes, when adding a
  device, or for another significant community change. Increment `Z` for an
  upstream patch-only (`C`) bump or a smaller community-side change.
- A preview and its eventual stable release may share the same `X.Y.Z` only
  when they are the same planned community release; `-preview.N` distinguishes
  the preview. Never infer the stable version from the upstream version alone.
- Before pushing, explicitly verify the target commit and that neither the
  exact proposed tag nor a conflicting community-version release exists in
  Git tags and GitHub Releases.
