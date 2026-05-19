"""Mock ONDC buyer, seller, and logistics party APIs for demos and integration tests."""

from fastapi import APIRouter

from core.mock_schemas import (
    BuyerProfileResponse,
    LogisticsTrackingResponse,
    SellerOrderResponse,
)
from services.mock_ondc import (
    build_buyer_profile,
    build_logistics_tracking,
    build_seller_order,
)

router = APIRouter()


@router.get(
    "/logistics/{tracking_id}",
    response_model=LogisticsTrackingResponse,
    summary="Mock LSP tracking",
)
async def get_logistics_tracking(tracking_id: str) -> LogisticsTrackingResponse:
    """
    Return deterministic mock shipment tracking from an ONDC logistics provider.

    The same ``tracking_id`` always yields the same scenario (status, scans, condition).
    No API key is required — this simulates an external LSP callback surface.
    """
    return build_logistics_tracking(tracking_id)


@router.get(
    "/seller/{seller_id}/order/{order_id}",
    response_model=SellerOrderResponse,
    summary="Mock seller order",
)
async def get_seller_order(
    seller_id: str,
    order_id: str,
) -> SellerOrderResponse:
    """
    Return deterministic mock seller order and dispute stance for an ONDC retail order.

    ``seller_id`` and ``order_id`` together select one of four stance presets.
    Partial refund presets include ``seller_counter_offer_inr`` at 50% of item value.
    """
    return build_seller_order(seller_id, order_id)


@router.get(
    "/buyer/{buyer_id}",
    response_model=BuyerProfileResponse,
    summary="Mock buyer profile",
)
async def get_buyer_profile(buyer_id: str) -> BuyerProfileResponse:
    """
    Return a deterministic mock ONDC buyer profile for dispute risk context.

    The same ``buyer_id`` always maps to the same name, KYC flag, and history stats.
    """
    return build_buyer_profile(buyer_id)
