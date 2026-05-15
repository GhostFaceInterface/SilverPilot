from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


TradeAction = Literal["paper_buy", "paper_sell", "hold", "blocked"]


class PaperTradeRequest(BaseModel):
    portfolio_name: str = "default-paper"
    asset_symbol: str = "XAG"
    action: TradeAction
    quantity: Decimal | None = Field(default=None, ge=Decimal("0"))
    cash_amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    buy_price: Decimal = Field(ge=Decimal("0"))
    sell_price: Decimal = Field(ge=Decimal("0"))
    fees: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    taxes: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))

    @model_validator(mode="after")
    def validate_trade_shape(self) -> "PaperTradeRequest":
        if self.action == "paper_buy":
            if self.buy_price <= 0:
                raise ValueError("paper_buy requires buy_price greater than zero")
            if self.quantity is None and self.cash_amount is None:
                raise ValueError("paper_buy requires quantity or cash_amount")
            if self.quantity is not None and self.quantity <= 0:
                raise ValueError("paper_buy quantity must be greater than zero")
        if self.action == "paper_sell":
            if self.sell_price <= 0:
                raise ValueError("paper_sell requires sell_price greater than zero")
            if self.quantity is None or self.quantity <= 0:
                raise ValueError("paper_sell requires quantity greater than zero")
        return self


class PaperTradePayload(BaseModel):
    id: int
    portfolio_id: int
    asset_id: int
    action: str
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    fees: Decimal
    taxes: Decimal
    net_amount: Decimal
    risk_decision_id: int


class RiskDecisionPayload(BaseModel):
    id: int
    decision: str
    reason_code: str
    risk_level: str
    confidence: Decimal
    details: dict


class PortfolioSnapshotPayload(BaseModel):
    id: int
    portfolio_id: int
    cash_balance: Decimal
    asset_quantity: Decimal
    portfolio_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


class PaperTradeResponse(BaseModel):
    trade: PaperTradePayload
    risk_decision: RiskDecisionPayload
    snapshot: PortfolioSnapshotPayload
