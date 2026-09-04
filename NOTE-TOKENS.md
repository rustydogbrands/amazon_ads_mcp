# Token Sources

This repo uses two refresh-token sources, one per brand. Two MCP server entries
in `~/.claude.json` (`amazon-ads` for PBN, `amazon-ads-sh` for SH) load them
side-by-side so both brands are reachable in the same Claude Code session.

> **The two servers are NOT a brand boundary.** The PBN token reaches Sap Happy
> profiles. See "Token scope" below before assuming the namespace protects you.

## Token scope (verified live)

### `amazon-ads` entry → PBN token
`/v2/profiles` with this token returns **six** profiles, spanning both brands
(verified live 2026-09-03, region `na`, `sandbox: false`):

| Profile | Marketplace | Profile ID |
| --- | --- | --- |
| PBN US (default) | US | 3987763286122956 |
| PBN CA | CA | 2560467967906921 |
| PBN BR | BR | 660397960864425 |
| PBN MX | MX | 3373299208287812 |
| **SH US** | US | **3778622964304303** |
| **SH MX** | MX | **351892444800497** |

Tools surface as `mcp__amazon-ads__*`.

### `amazon-ads-sh` entry → SH token
- Refresh token for Sap Happy Sugarin' Supplies.
- Default profile: 3778622964304303 (SH US seller).
- Also covers SH CA (1018256446748374) and SH MX (351892444800497) — same
  token, just switch active_profile.
- Tools surface as `mcp__amazon-ads-sh__*`.

### WARNING — the PBN server can write to Sap Happy's live account

A `set_active_profile` to 3778622964304303 (SH US) or 351892444800497 (SH MX)
**on the `amazon-ads` (PBN) server succeeds**, and every subsequent call on that
server then hits Sap Happy's live account. Nothing in the server, the token, or
the tool namespace blocks it — the PBN token genuinely carries those grants.

Consequences to internalize:

- **Server namespacing alone does NOT isolate the two brands.** Calling
  `mcp__amazon-ads__*` is not by itself evidence that you are acting on PBN.
- The *profile id* is the only real brand boundary. Verify it before any write:
  `get_active_profile` returns the id currently in force.
- A stale or inherited active profile is the dangerous case — the PBN server
  left pointed at an SH profile will silently execute PBN-intended changes
  against Sap Happy.
- SH profile ids to treat as tripwires on the PBN server: `3778622964304303`,
  `351892444800497`.

### CRITICAL GOTCHA — "Rusty Dog Outdoors" label is SH

When you call `/v2/profiles` with the SH token, every profile comes back with
`accountInfo.name = 'Rusty Dog Outdoors'`. That's the original account name
Craig set when creating the SH Seller Central account; Amazon will not let him
rename it. **It is still SH.** Do not let the `accountInfo.name` mislead you
into thinking these are RDO profiles — RDO is a separate brand that does not
have its own Amazon Ads presence.

## .env at project root
- Originally held the SH refresh token under the misleading "RDO" framing.
- Now redundant: `~/.claude.json` `amazon-ads-sh` entry is the source of truth.
- Kept on disk as a backup; do not load from helper scripts. Use the MCP tools
  instead, namespaced by brand.

## Pattern to follow
- **Default to MCP tool calls** for all Amazon Ads API access. The MCP handles
  token sourcing, region routing, and endpoint shape correctly.
- For PBN work, use `mcp__amazon-ads__*` tools. For SH work, use
  `mcp__amazon-ads-sh__*` tools. Pick the right server before acting — but
  treat that as a convention, not a guard: **confirm the active profile id**
  with `get_active_profile` before any write, because the PBN token can reach
  SH US and SH MX.
- Avoid raw httpx in helper scripts — past bugs (SP v3 expression-type case
  mismatch, GET /v2/portfolios endpoint shape) lived in helper scripts that
  bypassed the MCP. See `src/amazon_ads_mcp/utils/sp_enum_normalize.py` (commit
  2b506a2) for the SP v3 normalization helper that should be imported by any
  script that does need to parse response types.

## Fork CI — Release workflow is disabled
- The inherited `Release` workflow (auto version bump + tag + GitHub Release +
  PyPI publish) is **disabled** on `rustydogbrands/amazon_ads_mcp` as of
  2026-09-04: PyPI Trusted Publishing for `amazon-ads-mcp` is registered to
  upstream `KuudoAI/amazon_ads_mcp`, so every push to `main` here failed with
  `invalid-publisher` — after already bumping the version, tagging, and pushing
  a commit to `main`. Re-enable only if this fork ships its own renamed package.

---
*Created 2026-05-05 during a Marketing weekly review session that surfaced the token-source split. Source: Rusty Dog Brands Cowork PPC pipeline.*
*Updated 2026-09-03: corrected the PBN token scope to the verified six profiles (including SH US and SH MX) and added the cross-brand warning.*
*Updated 2026-09-04: noted the disabled fork Release workflow (see "Fork CI").*
