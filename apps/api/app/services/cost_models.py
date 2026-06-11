from decimal import Decimal
from app.services.base import BaseCostModel


class KuveytTurkCostModel(BaseCostModel):
    def calculate_cost(self, amount: Decimal, price: Decimal) -> Decimal:
        # Amount is quantity, price is unit price
        # Total cost is just the buy tax (0.2%)
        return (amount * price * Decimal("0.002")).quantize(Decimal("0.0001"))

    def calculate_fees(self, amount: Decimal, price: Decimal, is_buy: bool) -> Decimal:
        return Decimal("0.0")

    def calculate_taxes(self, amount: Decimal, price: Decimal, is_buy: bool) -> Decimal:
        return (amount * price * Decimal("0.002")).quantize(Decimal("0.0001")) if is_buy else Decimal("0.0")


class ZiraatCostModel(BaseCostModel):
    def calculate_cost(self, amount: Decimal, price: Decimal) -> Decimal:
        # Ziraat has 0.2% tax + 0.1% commission fee
        return (amount * price * Decimal("0.003")).quantize(Decimal("0.0001"))

    def calculate_fees(self, amount: Decimal, price: Decimal, is_buy: bool) -> Decimal:
        # 0.1% commission fee on both buys and sells
        return (amount * price * Decimal("0.001")).quantize(Decimal("0.0001"))

    def calculate_taxes(self, amount: Decimal, price: Decimal, is_buy: bool) -> Decimal:
        return (amount * price * Decimal("0.002")).quantize(Decimal("0.0001")) if is_buy else Decimal("0.0")


COST_MODEL_REGISTRY = {
    "kuveyt_turk": KuveytTurkCostModel(),
    "ziraat": ZiraatCostModel(),
}
