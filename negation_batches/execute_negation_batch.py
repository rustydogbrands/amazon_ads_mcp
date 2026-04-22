"""Execute ad-group-level negative keyword + negative product target batches
for PBN cross-family negation plan.

Reads plan from plan_{ts}.json. Writes results to results_{ts}.json.
Uses the amazon-ads-mcp auth machinery (same LWA credentials as MCP server).
"""

import asyncio
import datetime
import json
import sys
from pathlib import Path

from amazon_ads_mcp.utils.http_client import get_authenticated_client

PLAN_FILE = sys.argv[1] if len(sys.argv) > 1 else "plan.json"
RESULTS_FILE = PLAN_FILE.replace("plan_", "results_")
NEG_KW_CT = "application/vnd.spNegativeKeyword.v3+json"
NEG_TGT_CT = "application/vnd.spNegativeTargetingClause.v3+json"


async def create_negative_keywords(client, campaign_id, ad_group_id, terms, match_type):
    """match_type: NEGATIVE_PHRASE or NEGATIVE_EXACT."""
    if not terms:
        return {"attempted": 0, "success": [], "error": []}
    body = {
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


async def create_negative_asin_targets(client, campaign_id, ad_group_id, asins):
    if not asins:
        return {"attempted": 0, "success": [], "error": []}
    body = {
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


async def main():
    plan = json.load(open(PLAN_FILE))
    client = await get_authenticated_client()
    results = {
        "plan_file": str(Path(PLAN_FILE).name),
        "executed_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "campaigns": [],
    }
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
                c["phrase_negatives"], "NEGATIVE_PHRASE",
            )
            entry["phrase"] = r
            print(f"  PHRASE: attempted={r['attempted']} success={len(r['success'])} errors={len(r['error'])}")
            for e in r["error"]:
                print(f"    err: {e}")
        if c.get("exact_negatives"):
            r = await create_negative_keywords(
                client, c["campaign_id"], c["ad_group_id"],
                c["exact_negatives"], "NEGATIVE_EXACT",
            )
            entry["exact"] = r
            print(f"  EXACT : attempted={r['attempted']} success={len(r['success'])} errors={len(r['error'])}")
            for e in r["error"]:
                print(f"    err: {e}")
        if c.get("negative_asins"):
            r = await create_negative_asin_targets(
                client, c["campaign_id"], c["ad_group_id"], c["negative_asins"],
            )
            entry["asin_targets"] = r
            print(f"  ASIN  : attempted={r['attempted']} success={len(r['success'])} errors={len(r['error'])}")
            for e in r["error"]:
                print(f"    err: {e}")
        results["campaigns"].append(entry)
    Path(RESULTS_FILE).write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults written to {RESULTS_FILE}")


asyncio.run(main())
