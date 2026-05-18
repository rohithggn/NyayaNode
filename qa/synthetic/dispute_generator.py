"""
qa/synthetic/dispute_generator.py
Faker-based dispute stub generator for NyayaNode QA.
"""

import os
import random
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from faker import Faker
from pydantic import BaseModel, Field

# Support both `python -m pytest` (package import) and `python dispute_generator.py` (direct run)
try:
    from qa.synthetic.scenarios import ALL_SCENARIOS
except ModuleNotFoundError:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from qa.synthetic.scenarios import ALL_SCENARIOS

VALID_DISPUTE_TYPES = [
    "DAMAGED_ITEM",
    "NOT_DELIVERED",
    "WRONG_ITEM",
    "REFUND_DENIED",
]


class DisputeRequestStub(BaseModel):
    """Pydantic v2 model representing a dispute request stub."""

    dispute_id: str = Field(description="UUID4 string identifying the dispute")
    buyer_id: str
    seller_id: str
    logistics_id: str
    order_id: str
    dispute_type: str = Field(description="One of the 4 valid dispute types")
    dispute_amount_inr: float
    evidence: list[dict[str, Any]]
    created_at: str = Field(description="ISO 8601 timestamp")
    description: str


class DisputeFactory:
    """Generates reproducible dispute stubs for testing."""

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._faker = Faker("en_IN")
        Faker.seed(seed)
        random.seed(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, n: int = 1) -> list[DisputeRequestStub]:
        """Generate *n* random but valid dispute stubs."""
        stubs: list[DisputeRequestStub] = []
        for _ in range(n):
            stubs.append(self._random_stub())
        return stubs

    def from_scenario(self, scenario: dict) -> DisputeRequestStub:
        """Convert a canonical scenario dict into a DisputeRequestStub."""
        return DisputeRequestStub(
            dispute_id=str(uuid.uuid4()),
            buyer_id=scenario["buyer_id"],
            seller_id=scenario["seller_id"],
            logistics_id=scenario["logistics_id"],
            order_id=scenario["order_id"],
            dispute_type=scenario["dispute_type"],
            dispute_amount_inr=float(scenario["dispute_amount_inr"]),
            evidence=list(scenario.get("evidence", [])),
            created_at=datetime.now(timezone.utc).isoformat(),
            description=scenario.get("description", ""),
        )

    def generate_edge_cases(self) -> list[DisputeRequestStub]:
        """Return exactly 6 edge-case stubs covering boundary and unusual inputs."""
        base_ts = datetime.now(timezone.utc).isoformat()

        # 1. Minimum amount: ₹1.00
        min_amount = DisputeRequestStub(
            dispute_id=str(uuid.uuid4()),
            buyer_id="ondc_buyer_edge_001",
            seller_id="ondc_seller_edge_001",
            logistics_id="ondc_lsp_edge_001",
            order_id="order_edge_001",
            dispute_type="DAMAGED_ITEM",
            dispute_amount_inr=1.00,
            evidence=[{"type": "text", "content": "Item damaged on arrival."}],
            created_at=base_ts,
            description="Edge case: minimum dispute amount ₹1.00",
        )

        # 2. Maximum amount: ₹99999.00
        max_amount = DisputeRequestStub(
            dispute_id=str(uuid.uuid4()),
            buyer_id="ondc_buyer_edge_002",
            seller_id="ondc_seller_edge_002",
            logistics_id="ondc_lsp_edge_002",
            order_id="order_edge_002",
            dispute_type="DAMAGED_ITEM",
            dispute_amount_inr=99999.00,
            evidence=[{"type": "text", "content": "High-value item damaged."}],
            created_at=base_ts,
            description="Edge case: maximum dispute amount ₹99999.00",
        )

        # 3. Unicode buyer name with Hindi characters
        unicode_buyer = DisputeRequestStub(
            dispute_id=str(uuid.uuid4()),
            buyer_id="ondc_buyer_\u0905\u0930\u094d\u091c\u0941\u0928_003",
            seller_id="ondc_seller_edge_003",
            logistics_id="ondc_lsp_edge_003",
            order_id="order_edge_003",
            dispute_type="NOT_DELIVERED",
            dispute_amount_inr=599.0,
            evidence=[
                {
                    "type": "text",
                    "content": "\u092e\u0941\u091d\u0947 \u092a\u0948\u0915\u0947\u091c \u0928\u0939\u0940\u0902 \u092e\u093f\u0932\u093e",
                }
            ],
            created_at=base_ts,
            description="Edge case: buyer_id and evidence contain Hindi Unicode characters",
        )

        # 4. Zero evidence items (valid stub; backend validation will reject)
        zero_evidence = DisputeRequestStub(
            dispute_id=str(uuid.uuid4()),
            buyer_id="ondc_buyer_edge_004",
            seller_id="ondc_seller_edge_004",
            logistics_id="ondc_lsp_edge_004",
            order_id="order_edge_004",
            dispute_type="REFUND_DENIED",
            dispute_amount_inr=349.0,
            evidence=[],
            created_at=base_ts,
            description="Edge case: zero evidence items — backend should reject this",
        )

        # 5. Exactly 10 evidence items
        ten_evidence = DisputeRequestStub(
            dispute_id=str(uuid.uuid4()),
            buyer_id="ondc_buyer_edge_005",
            seller_id="ondc_seller_edge_005",
            logistics_id="ondc_lsp_edge_005",
            order_id="order_edge_005",
            dispute_type="WRONG_ITEM",
            dispute_amount_inr=1499.0,
            evidence=[
                {"type": "text", "content": f"Evidence item {i + 1} of 10."}
                for i in range(10)
            ],
            created_at=base_ts,
            description="Edge case: exactly 10 evidence items",
        )

        # 6. Very long description (500+ characters)
        long_desc_text = (
            "This dispute involves a highly complex situation where the buyer "
            "ordered a premium handcrafted silk saree from a reputed seller on "
            "the ONDC network. The package was dispatched on time according to "
            "the logistics partner's records, however upon arrival the outer "
            "packaging showed clear signs of mishandling — multiple dents, "
            "moisture damage, and a broken seal. The saree inside was stained "
            "with what appears to be oil or grease, rendering it completely "
            "unwearable. The buyer has photographic evidence, a video of "
            "unboxing, and a written statement from a neighbour who witnessed "
            "the delivery. The seller has refused to acknowledge the damage "
            "claim citing their internal quality-check certificate issued "
            "before dispatch. This is a clear case requiring agent intervention."
        )
        assert len(long_desc_text) >= 500, "Long description must be 500+ chars"

        long_description = DisputeRequestStub(
            dispute_id=str(uuid.uuid4()),
            buyer_id="ondc_buyer_edge_006",
            seller_id="ondc_seller_edge_006",
            logistics_id="ondc_lsp_edge_006",
            order_id="order_edge_006",
            dispute_type="DAMAGED_ITEM",
            dispute_amount_inr=4599.0,
            evidence=[
                {"type": "text", "content": "Saree arrived heavily stained and damaged."},
                {"type": "image_url", "content": "https://placehold.co/400x300?text=Damaged+Saree"},
            ],
            created_at=base_ts,
            description=long_desc_text,
        )

        return [
            min_amount,
            max_amount,
            unicode_buyer,
            zero_evidence,
            ten_evidence,
            long_description,
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _random_stub(self) -> DisputeRequestStub:
        """Build one random but structurally valid dispute stub."""
        dispute_type = random.choice(VALID_DISPUTE_TYPES)
        amount = round(random.uniform(50.0, 9999.0), 2)
        num_evidence = random.randint(1, 4)
        evidence = [
            {"type": "text", "content": self._faker.sentence(nb_words=12)}
            for _ in range(num_evidence)
        ]
        return DisputeRequestStub(
            dispute_id=str(uuid.uuid4()),
            buyer_id=f"ondc_buyer_{self._faker.numerify('###')}",
            seller_id=f"ondc_seller_{self._faker.numerify('###')}",
            logistics_id=f"ondc_lsp_{self._faker.numerify('###')}",
            order_id=f"order_{self._faker.bothify('??##??##')}",
            dispute_type=dispute_type,
            dispute_amount_inr=amount,
            evidence=evidence,
            created_at=datetime.now(timezone.utc).isoformat(),
            description=self._faker.sentence(nb_words=20),
        )


# ---------------------------------------------------------------------------
# Quick smoke-test when run directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    factory = DisputeFactory()
    disputes = factory.generate(3)
    for d in disputes:
        print(d.model_dump_json(indent=2))
