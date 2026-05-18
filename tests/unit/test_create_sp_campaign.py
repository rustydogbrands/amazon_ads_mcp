"""Tests for create_sp_campaign date handling.

Coverage for the SP v3 startDate-format fix: the auto-injected default
must be ISO ``YYYY-MM-DD`` (the v3 campaigns API rejects the legacy v2
``YYYYMMDD`` form), and an explicitly-passed legacy date must be
normalized rather than forwarded as-is.

Mirrors the mock/response contract of test_archive_sp_campaign.py.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from amazon_ads_mcp.tools import campaign_management
from amazon_ads_mcp.tools.campaign_management import _to_iso_date


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        return self._payload


def _patch_client(monkeypatch, resp: _FakeResponse) -> MagicMock:
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    monkeypatch.setattr(
        "amazon_ads_mcp.utils.http_client.get_authenticated_client",
        AsyncMock(return_value=client),
    )
    return client


_OK = _FakeResponse(
    207, {"campaigns": {"success": [{"index": 0, "campaignId": "C1"}], "error": []}}
)


def _posted_campaign(client: MagicMock) -> dict:
    return client.post.call_args.kwargs["json"]["campaigns"][0]


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("2026-05-18", "2026-05-18"),  # already ISO -> passthrough
        ("20260518", "2026-05-18"),  # legacy 8-digit -> converted
        ("  20260518 ", "2026-05-18"),  # stripped then converted
        ("2026/05/18", "2026/05/18"),  # unknown shape -> unchanged (API validates)
    ],
)
def test_to_iso_date(value, expected):
    assert _to_iso_date(value) == expected


@pytest.mark.asyncio
async def test_default_start_date_is_iso(monkeypatch):
    client = _patch_client(monkeypatch, _OK)

    await campaign_management.create_sp_campaign(
        name="N", targeting_type="AUTO", budget_amount=10.0
    )

    posted = _posted_campaign(client)
    assert posted["startDate"] == datetime.now().strftime("%Y-%m-%d")
    # Guard against the regressed %Y%m%d form explicitly.
    assert "-" in posted["startDate"] and len(posted["startDate"]) == 10


@pytest.mark.asyncio
async def test_explicit_legacy_start_date_normalized(monkeypatch):
    client = _patch_client(monkeypatch, _OK)

    await campaign_management.create_sp_campaign(
        name="N",
        targeting_type="AUTO",
        budget_amount=10.0,
        start_date="20260518",
        end_date="20261231",
    )

    posted = _posted_campaign(client)
    assert posted["startDate"] == "2026-05-18"
    assert posted["endDate"] == "2026-12-31"


@pytest.mark.asyncio
async def test_explicit_iso_dates_passthrough(monkeypatch):
    client = _patch_client(monkeypatch, _OK)

    await campaign_management.create_sp_campaign(
        name="N",
        targeting_type="AUTO",
        budget_amount=10.0,
        start_date="2026-05-18",
        end_date="2026-12-31",
    )

    posted = _posted_campaign(client)
    assert posted["startDate"] == "2026-05-18"
    assert posted["endDate"] == "2026-12-31"
