"""
qa/synthetic/scenarios.py
Canonical dispute scenarios for NyayaNode QA.
All members reference this file — data must remain identical across all tests.
"""

SCENARIO_1 = {
    "name": "Damaged Kurta",
    "dispute_type": "DAMAGED_ITEM",
    "dispute_amount_inr": 499.0,
    "buyer_id": "ondc_buyer_001",
    "seller_id": "ondc_seller_042",
    "logistics_id": "ondc_lsp_007",
    "order_id": "order_demo_001",
    "evidence": [
        {
            "type": "text",
            "content": "Package arrived with torn box. Kurta has a large stain.",
        },
        {
            "type": "image_url",
            "content": "https://placehold.co/400x300?text=Damaged+Package",
        },
    ],
    "mock_logistics_status": "DELIVERED",
    "mock_package_condition": "DAMAGED",
    "mock_seller_stance": "REJECT_REFUND",
    "expected_decision": "FULL_REFUND",
    "expected_status": "RESOLVED",
    "max_budget_inr": 5.0,
    "description": "Logistics scan confirms damage. Seller wrongly rejects. Agent overrules.",
}

SCENARIO_2 = {
    "name": "Claimed Not Delivered",
    "dispute_type": "NOT_DELIVERED",
    "dispute_amount_inr": 1299.0,
    "buyer_id": "ondc_buyer_002",
    "seller_id": "ondc_seller_015",
    "logistics_id": "ondc_lsp_003",
    "order_id": "order_demo_002",
    "evidence": [
        {
            "type": "text",
            "content": "I never received this package. It shows delivered but I was home.",
        },
    ],
    "mock_logistics_status": "DELIVERED",
    "mock_package_condition": "INTACT",
    "mock_delivery_confirmed_by": "OTP",
    "mock_seller_stance": "REJECT_REFUND",
    "expected_decision": "REJECTED",
    "expected_status": "RESOLVED",
    "max_budget_inr": 5.0,
    "description": "OTP-confirmed delivery. Buyer claim not supported. Agent sides with seller.",
}

SCENARIO_3 = {
    "name": "Wrong Size Sent",
    "dispute_type": "WRONG_ITEM",
    "dispute_amount_inr": 799.0,
    "buyer_id": "ondc_buyer_003",
    "seller_id": "ondc_seller_088",
    "logistics_id": "ondc_lsp_011",
    "order_id": "order_demo_003",
    "evidence": [
        {
            "type": "text",
            "content": "Ordered XL, received M. Size tag clearly shows M.",
        },
        {
            "type": "image_url",
            "content": "https://placehold.co/400x300?text=Wrong+Size+Tag",
        },
    ],
    "mock_logistics_status": "DELIVERED",
    "mock_package_condition": "INTACT",
    "mock_seller_stance": "PARTIAL_REFUND",
    "mock_seller_counter_offer_inr": 400.0,
    "expected_decision": "PARTIAL_REFUND",
    "expected_refund_inr": 400.0,
    "expected_status": "RESOLVED",
    "max_budget_inr": 5.0,
    "description": "Seller offers partial. Agent negotiates and accepts reasonable settlement.",
}

SCENARIO_4 = {
    "name": "Refund Being Ignored",
    "dispute_type": "REFUND_DENIED",
    "dispute_amount_inr": 249.0,
    "buyer_id": "ondc_buyer_004",
    "seller_id": "ondc_seller_031",
    "logistics_id": "ondc_lsp_005",
    "order_id": "order_demo_004",
    "evidence": [
        {
            "type": "text",
            "content": "Returned item 10 days ago. Seller not processing refund.",
        },
        {
            "type": "tracking_data",
            "content": "Return tracking: RTN_TRK_00491 — DELIVERED TO SELLER",
        },
    ],
    "mock_logistics_status": "DELIVERED",
    "mock_seller_stance": "PENDING_REVIEW",
    "expected_decision": "FULL_REFUND",
    "expected_status": "RESOLVED",
    "max_budget_inr": 5.0,
    "description": "Return confirmed by logistics. Seller silence overruled. Full refund issued.",
}

SCENARIO_5 = {
    "name": "Expensive Watch — Ambiguous",
    "dispute_type": "DAMAGED_ITEM",
    "dispute_amount_inr": 8999.0,
    "buyer_id": "ondc_buyer_005",
    "seller_id": "ondc_seller_077",
    "logistics_id": "ondc_lsp_002",
    "order_id": "order_demo_005",
    "evidence": [
        {
            "type": "text",
            "content": "Watch dial scratched but logistics shows no damage flag.",
        },
        {
            "type": "image_url",
            "content": "https://placehold.co/400x300?text=Scratched+Watch",
        },
    ],
    "mock_logistics_status": "DELIVERED",
    "mock_package_condition": "INTACT",
    "mock_seller_stance": "REJECT_REFUND",
    "expected_decision": "PENDING",
    "expected_status": "ESCALATED",
    "max_budget_inr": 5.0,
    "description": "High value + ambiguous evidence + no logistics confirmation → human review.",
}

ALL_SCENARIOS = [SCENARIO_1, SCENARIO_2, SCENARIO_3, SCENARIO_4, SCENARIO_5]


def get_scenario_by_name(name: str) -> dict:
    """Return a scenario dict by its name field. Raises ValueError if not found."""
    for s in ALL_SCENARIOS:
        if s["name"] == name:
            return s
    raise ValueError(f"Scenario '{name}' not found")
