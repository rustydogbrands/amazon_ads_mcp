"""Tests for placement bid adjustment merge in update_sp_campaigns.

Covers the read-modify-write contract: any placement not specified in the
update call must retain its current value, since the v3 PUT endpoint
replaces the dynamicBidding object wholesale.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from amazon_ads_mcp.tools import campaign_management


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> dict:
        return self._payload


def _build_client(list_payload: dict, put_payload: dict) -> MagicMock:
    client = MagicMock()
    client.post = AsyncMock(return_value=_FakeResponse(200, list_payload))
    client.put = AsyncMock(return_value=_FakeResponse(200, put_payload))
    return client


@pytest.mark.asyncio
async def test_placement_update_merges_existing_values(monkeypatch):
    list_payload = {
        "campaigns": [
            {
                "campaignId": "C1",
                "dynamicBidding": {
                    "strategy": "LEGACY_FOR_SALES",
                    "placementBidding": [
                        {"placement": "PLACEMENT_TOP", "percentage": 10},
                        {"placement": "PLACEMENT_PRODUCT_PAGE", "percentage": 15},
                        {"placement": "PLACEMENT_REST_OF_SEARCH", "percentage": 5},
                    ],
                },
            }
        ]
    }
    put_payload = {"campaigns": {"success": [{"index": 0, "campaignId": "C1"}], "error": []}}
    client = _build_client(list_payload, put_payload)
    monkeypatch.setattr(
        "amazon_ads_mcp.utils.http_client.get_authenticated_client",
        AsyncMock(return_value=client),
    )

    result = await campaign_management.update_sp_campaigns(
        campaign_id="C1", placement_top_pct=25
    )

    assert result["success"] is True
    put_body = client.put.call_args.kwargs["json"]
    sent = put_body["campaigns"][0]["dynamicBidding"]
    sent_map = {p["placement"]: p["percentage"] for p in sent["placementBidding"]}
    assert sent_map == {
        "PLACEMENT_TOP": 25,
        "PLACEMENT_PRODUCT_PAGE": 15,
        "PLACEMENT_REST_OF_SEARCH": 5,
    }
    assert sent["strategy"] == "LEGACY_FOR_SALES"


@pytest.mark.asyncio
async def test_strategy_only_update_preserves_existing_placement(monkeypatch):
    list_payload = {
        "campaigns": [
            {
                "campaignId": "C2",
                "dynamicBidding": {
                    "strategy": "LEGACY_FOR_SALES",
                    "placementBidding": [
                        {"placement": "PLACEMENT_TOP", "percentage": 10},
                    ],
                },
            }
        ]
    }
    put_payload = {"campaigns": {"success": [{"index": 0, "campaignId": "C2"}], "error": []}}
    client = _build_client(list_payload, put_payload)
    monkeypatch.setattr(
        "amazon_ads_mcp.utils.http_client.get_authenticated_client",
        AsyncMock(return_value=client),
    )

    result = await campaign_management.update_sp_campaigns(
        campaign_id="C2", bidding_strategy="MANUAL"
    )

    assert result["success"] is True
    sent = client.put.call_args.kwargs["json"]["campaigns"][0]["dynamicBidding"]
    assert sent["strategy"] == "MANUAL"
    assert sent["placementBidding"] == [{"placement": "PLACEMENT_TOP", "percentage": 10}]


@pytest.mark.asyncio
async def test_no_bidding_fields_skips_prefetch(monkeypatch):
    put_payload = {"campaigns": {"success": [{"index": 0, "campaignId": "C3"}], "error": []}}
    client = MagicMock()
    client.post = AsyncMock(side_effect=AssertionError("post should not be called"))
    client.put = AsyncMock(return_value=_FakeResponse(200, put_payload))
    monkeypatch.setattr(
        "amazon_ads_mcp.utils.http_client.get_authenticated_client",
        AsyncMock(return_value=client),
    )

    result = await campaign_management.update_sp_campaigns(
        campaign_id="C3", name="renamed"
    )

    assert result["success"] is True
    sent = client.put.call_args.kwargs["json"]["campaigns"][0]
    assert "dynamicBidding" not in sent
    assert sent["name"] == "renamed"


@pytest.mark.asyncio
async def test_out_of_range_placement_rejected(monkeypatch):
    client = MagicMock()
    client.post = AsyncMock(side_effect=AssertionError("should fail before any HTTP call"))
    client.put = AsyncMock(side_effect=AssertionError("should fail before any HTTP call"))
    monkeypatch.setattr(
        "amazon_ads_mcp.utils.http_client.get_authenticated_client",
        AsyncMock(return_value=client),
    )

    result = await campaign_management.update_sp_campaigns(
        campaign_id="C4", placement_top_pct=901
    )

    assert result["success"] is False
    assert "0-900" in result["error"]


@pytest.mark.asyncio
async def test_empty_dynamic_bidding_creates_fresh_placement(monkeypatch):
    list_payload = {"campaigns": [{"campaignId": "C5", "dynamicBidding": None}]}
    put_payload = {"campaigns": {"success": [{"index": 0, "campaignId": "C5"}], "error": []}}
    client = _build_client(list_payload, put_payload)
    monkeypatch.setattr(
        "amazon_ads_mcp.utils.http_client.get_authenticated_client",
        AsyncMock(return_value=client),
    )

    result = await campaign_management.update_sp_campaigns(
        campaign_id="C5", placement_top_pct=20
    )

    assert result["success"] is True
    sent = client.put.call_args.kwargs["json"]["campaigns"][0]["dynamicBidding"]
    assert sent["placementBidding"] == [{"placement": "PLACEMENT_TOP", "percentage": 20}]
    assert "strategy" not in sent
