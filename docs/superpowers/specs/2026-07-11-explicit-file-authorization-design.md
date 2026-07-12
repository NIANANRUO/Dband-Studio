# Explicit File Authorization Design

## Contract

One selected primary file grants access only to that path. Auxiliary structure,
metadata, and spin-partner paths enter the parser exclusively through
`PDOSInputContext`. Directory proximity is never treated as authorization.

## User States

- `Ready`: authorized inputs are sufficient.
- `Needs input`: the primary file is valid but requires explicit metadata or
  another auxiliary input.
- `Blocked`: the selected primary or explicitly selected auxiliary file is
  malformed, mismatched, or unsupported.

Numeric atom selection requires no structure. Element selection requires an
explicit structure. Ambiguous SOC layouts require explicit metadata. VASPKIT
split-spin analysis requires an explicit partner.

## Persistence and Provenance

Workspace schema 1.1 stores auxiliary paths but never derives them during
migration. Cache identity includes every authorized file fingerprint. CSV
results record structure, metadata, and SAXIS sources by display-safe basename.
