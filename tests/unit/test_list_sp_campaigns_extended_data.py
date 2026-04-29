"""Tests for include_extended_data on list_sp_campaigns.

Surfaces serving_status (the OOB delivery-health signal) plus the extended
metadata fields the Amazon Ads SP v3 endpoint returns when
includeExtendedDataFields is set on the request.
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


def _bind_client(monkeypatch, client):
    monkeypatch.setattr(
        "amazon_ads_mcp.utils.http_client.get_authenticated_client",
        AsyncMock(return_value=client),
    )


@pytest.mark.asyncio
async def test_extended_data_flag_passed_to_api(monkeypatch):
    payload = {"campaigns": []}
    client = MagicMock()
    client.post = AsyncMock(return_value=_FakeResponse(200, payload))
    _bind_client(monkeypatch, client)

    await campaign_management.list_sp_campaigns(include_extended_data=True)

    sent_body = client.post.call_args.kwargs["json"]
    assert sent_body.get("includeExtendedDataFields") is True


@pytest.mark.asyncio
async def test_extended_data_flag_omitted_by_default(monkeypatch):
    payload = {"campaigns": []}
    client = MagicMock()
    client.post = AsyncMock(return_value=_FakeResponse(200, payload))
    _bind_client(monkeypatch, client)

    await campaign_management.list_sp_campaigns()

    sent_body = client.post.call_args.kwargs["json"]
    assert "includeExtendedDataFields" not in sent_body


@pytest.mark.asyncio
async def test_serving_status_surfaced_on_items(monkeypatch):
    payload = {
        "campaigns": [
            {
                "campaignId": "C1",
                "name": "Test Campaign",
                "state": "ENABLED",
                "extendedData": {
                    "servingStatus": "CAMPAIGN_OUT_OF_BUDGET",
                    "servingStatusDetails": [
                        {
                            "name": "CAMPAIGN_OUT_OF_BUDGET",
                            "message": "Campaign daily budget reached.",
                            "helpUrl": "https://advertising.amazon.com/help",
                        }
                    ],
                    "creationDateTime": "2024-04-08T10:00:00Z",
                    "lastUpdateDateTime": "2026-04-28T18:30:00Z",
                },
            }
        ]
    }
    client = MagicMock()
    client.post = AsyncMock(return_value=_FakeResponse(200, payload))
    _bind_client(monkeypatch, client)

    result = await campaign_management.list_sp_campaigns(include_extended_data=True)

    assert result["success"] is True
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["serving_status"] == "CAMPAIGN_OUT_OF_BUDGET"
    assert item["serving_status_details"][0]["name"] == "CAMPAIGN_OUT_OF_BUDGET"
    assert item["creation_date_time"] == "2024-04-08T10:00:00Z"
    assert item["last_update_date_time"] == "2026-04-28T18:30:00Z"


@pytest.mark.asyncio
async def test_no_extended_data_yields_none_for_extended_fields(monkeypatch):
    payload = {
        "campaigns": [
            {"campaignId": "C2", "name": "Plain", "state": "ENABLED"}
        ]
    }
    client = MagicMock()
    client.post = AsyncMock(return_value=_FakeResponse(200, payload))
    _bind_client(monkeypatch, client)

    result = await campaign_management.list_sp_campaigns()

    item = result["items"][0]
    assert item["serving_status"] is None
    assert item["serving_status_details"] is None
    assert item["creation_date_time"] is None
    assert item["last_update_date_time"] is None
    # Pre-existing fields still present
    assert item["campaign_id"] == "C2"
    assert item["state"] == "ENABLED"
