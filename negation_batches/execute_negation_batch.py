"""Execute ad-group-level negative keyword + negative product target batches
for PBN cross-family negation plan.

Reads plan from plan_{ts}.json. Writes results to results_{ts}.json.
Uses the amazon-ads-mcp auth machinery (same LWA credentials as MCP server).

Pass --dry-run to preview outgoing payloads without sending anything to Amazon.
"""

import argparse
import asyncio
import datetime
import json
from pathlib import Path

NEG_KW_CT = "application/vnd.spNegativeKeyword.v3+json"
NEG_TGT_CT = "application/vnd.spNegativeTargetingClause.v3+json"


def _build_neg_kw_body(campaign_id, ad_group_id, terms, match_type):
    return {
        "negativeKeywords": [
            {
                "campaignId": campaign_id,
                "adGroupId": ad_group_id,
                "keywordText": t,
                "matchType": match_type,
                "state": "ENABLED",
            }
            for t in terms
        ]
    }


def _build_neg_tgt_body(campaign_id, ad_group_id, asins):
    return {
        "negativeTargetingClauses": [
            {
                "campaignId": campaign_id,
                "adGroupId": ad_group_id,
                "expression": [{"type": "ASIN_SAME_AS", "value": a}],
                "state": "ENABLED",
            }
            for a in asins
        ]
    }


def _print_dry_run(method, endpoint, body):
    print(f"    [DRY-RUN] {method} {endpoint}")
    for line in json.dumps(body, indent=2).splitlines():
        print(f"    {line}")


async def create_negative_keywords(client, campaign_id, ad_group_id, terms, match_type, dry_run=False):
    """match_type: NEGATIVE_PHRASE or NEGATIVE_EXACT."""
    if not terms:
        return {"attempted": 0, "success": [], "error": []}
    body = _build_neg_kw_body(campaign_id, ad_group_id, terms, match_type)
    if dry_run:
        _print_dry_run("POST", "/sp/negativeKeywords", body)
        return {"attempted": len(terms), "dry_run": True, "success": [], "error": []}
    resp = await client.post(
        "/sp/negativeKeywords",
        json=body,
        headers={"Accept": NEG_KW_CT, "Content-Type": NEG_KW_CT},
    )
    raw = resp.json()
    if resp.status_code not in (200, 207):
        return {
            "attempted": len(terms),
            "http_status": resp.status_code,
            "success": [],
            "error": [{"message": f"HTTP {resp.status_code}", "body": raw}],
        }
    # V3 response: {"negativeKeywords": {"success": [...], "error": [...]}}
    wrap = raw.get("negativeKeywords", {})
    return {
        "attempted": len(terms),
        "http_status": resp.status_code,
        "success": wrap.get("success", []),
        "error": wrap.get("error", []),
    }


async def create_negative_asin_targets(client, campaign_id, ad_group_id, asins, dry_run=False):
    if not asins:
        return {"attempted": 0, "success": [], "error": []}
    body = _build_neg_tgt_body(campaign_id, ad_group_id, asins)
    if dry_run:
        _print_dry_run("POST", "/sp/negativeTargets", body)
        return {"attempted": len(asins), "dry_run": True, "success": [], "error": []}
    resp = await client.post(
        "/sp/negativeTargets",
        json=body,
        headers={"Accept": NEG_TGT_CT, "Content-Type": NEG_TGT_CT},
    )
    raw = resp.json()
    if resp.status_code not in (200, 207):
        return {
            "attempted": len(asins),
            "http_status": resp.status_code,
            "success": [],
            "error": [{"message": f"HTTP {resp.status_code}", "body": raw}],
        }
    wrap = raw.get("negativeTargetingClauses", {})
    return {
        "attempted": len(asins),
        "http_status": resp.status_code,
        "success": wrap.get("success", []),
        "error": wrap.get("error", []),
    }


async def main(plan_file, dry_run):
    plan = json.load(open(plan_file))
    client = None
    if not dry_run:
        # Only import + init the HTTP client when we actually need to send.
        # Standalone bootstrap — the module-level singleton populated by
        # ServerBuilder.build() does not exist when this CLI runs directly.
        from amazon_ads_mcp.utils.http_client import bootstrap_standalone_client
        client = await bootstrap_standalone_client()

    results = {
        "plan_file": str(Path(plan_file).name),
        "executed_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "dry_run": dry_run,
        "campaigns": [],
    }
    counts = {"NEGATIVE_PHRASE": 0, "NEGATIVE_EXACT": 0, "NEGATIVE_ASIN": 0}

    for c in plan["campaigns"]:
        print(f"\n>>> {c['name']}")
        entry = {
            "name": c["name"],
            "campaign_id": c["campaign_id"],
            "ad_group_id": c["ad_group_id"],
        }
        if c.get("phrase_negatives"):
            r = await create_negative_keywords(
                client, c["campaign_id"], c["ad_group_id"],
                c["phrase_negatives"], "NEGATIVE_PHRASE", dry_run=dry_run,
            )
            entry["phrase"] = r
            counts["NEGATIVE_PHRASE"] += r["attempted"]
            if not dry_run:
                print(f"  PHRASE: attempted={r['attempted']} success={len(r['success'])} errors={len(r['error'])}")
                for e in r["error"]:
                    print(f"    err: {e}")
        if c.get("exact_negatives"):
            r = await create_negative_keywords(
                client, c["campaign_id"], c["ad_group_id"],
                c["exact_negatives"], "NEGATIVE_EXACT", dry_run=dry_run,
            )
            entry["exact"] = r
            counts["NEGATIVE_EXACT"] += r["attempted"]
            if not dry_run:
                print(f"  EXACT : attempted={r['attempted']} success={len(r['success'])} errors={len(r['error'])}")
                for e in r["error"]:
                    print(f"    err: {e}")
        if c.get("negative_asins"):
            r = await create_negative_asin_targets(
                client, c["campaign_id"], c["ad_group_id"], c["negative_asins"], dry_run=dry_run,
            )
            entry["asin_targets"] = r
            counts["NEGATIVE_ASIN"] += r["attempted"]
            if not dry_run:
                print(f"  ASIN  : attempted={r['attempted']} success={len(r['success'])} errors={len(r['error'])}")
                for e in r["error"]:
                    print(f"    err: {e}")
        results["campaigns"].append(entry)

    if dry_run:
        print("\n=== DRY-RUN SUMMARY — nothing sent to Amazon ===")
        print(f"  NEGATIVE_PHRASE payloads: {counts['NEGATIVE_PHRASE']}")
        print(f"  NEGATIVE_EXACT  payloads: {counts['NEGATIVE_EXACT']}")
        print(f"  NEGATIVE_ASIN   payloads: {counts['NEGATIVE_ASIN']}")
        print(f"  TOTAL would-be API objects: {sum(counts.values())}")
    else:
        results_file = str(plan_file).replace("plan_", "results_")
        Path(results_file).write_text(json.dumps(results, indent=2, default=str))
        print(f"\nResults written to {results_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan_file", help="Path to plan_{ts}.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print outgoing payloads without sending to Amazon; skip results file write.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.plan_file, args.dry_run))
