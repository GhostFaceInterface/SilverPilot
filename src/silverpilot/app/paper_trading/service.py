from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import (
    LedgerEntryModel,
    PaperOrderModel,
    PaperTradeModel,
    PositionModel,
    PriceQuoteModel,
    RiskDecisionModel,
    WalletModel,
)
from silverpilot.app.domain.enums import PaperOrderSide, PaperOrderStatus

_MONEY_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True)
class PaperCostModel:
    fee_rate: Decimal = Decimal("0.001")
    tax_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.fee_rate < Decimal("0"):
            raise ValueError("fee_rate cannot be negative")
        if self.tax_rate < Decimal("0"):
            raise ValueError("tax_rate cannot be negative")


@dataclass(frozen=True)
class PaperOrderRequest:
    risk_decision_id: UUID
    side: PaperOrderSide
    executed_at: datetime
    quote_id: UUID | None = None


@dataclass(frozen=True)
class PaperBrokerResult:
    order: PaperOrderModel
    trade: PaperTradeModel
    inserted: bool


class LedgerService:
    """Append-only ledger writer."""

    def __init__(self, *, session: Session) -> None:
        self._session = session

    def append(self, entries: list[LedgerEntryModel]) -> list[LedgerEntryModel]:
        if not entries:
            raise ValueError("ledger entries are required")
        for entry in entries:
            if entry.id is None:
                entry.id = uuid4()
            self._session.add(entry)
        self._session.flush()
        return entries


class PaperBroker:
    """Executes risk-approved paper orders without touching real bank systems."""

    def __init__(
        self,
        *,
        session: Session,
        cost_model: PaperCostModel | None = None,
        ledger: LedgerService | None = None,
    ) -> None:
        self._session = session
        self._cost_model = cost_model or PaperCostModel()
        self._ledger = ledger or LedgerService(session=session)

    def execute(self, request: PaperOrderRequest) -> PaperBrokerResult:
        decision = self._load_approved_decision(request.risk_decision_id)
        existing_order = self._session.scalar(
            select(PaperOrderModel).where(PaperOrderModel.risk_decision_id == decision.id)
        )
        if existing_order is not None:
            existing_trade = self._session.scalar(
                select(PaperTradeModel).where(PaperTradeModel.order_id == existing_order.id)
            )
            if existing_trade is None:
                raise ValueError("paper order exists without trade")
            return PaperBrokerResult(order=existing_order, trade=existing_trade, inserted=False)

        quote = self._load_quote(decision=decision, quote_id=request.quote_id)
        wallet = self._load_base_wallet(decision)
        position = self._load_position(decision=decision)
        execution_instrument = decision.execution_instrument
        approved_quantity = decision.approved_quantity
        assert execution_instrument is not None
        assert approved_quantity is not None
        bank_instrument_id = self._bank_instrument_id(decision)

        quantity = Decimal(approved_quantity)
        execution_price = (
            Decimal(quote.bank_sell_price)
            if request.side == PaperOrderSide.BUY
            else Decimal(quote.bank_buy_price)
        )
        gross_cash_amount = _money(quantity * execution_price)
        fees = _money(gross_cash_amount * self._cost_model.fee_rate)
        taxes = _money(gross_cash_amount * self._cost_model.tax_rate)
        spread_cost = _money(
            (Decimal(quote.bank_sell_price) - Decimal(quote.bank_buy_price)) * quantity
        )

        if request.side == PaperOrderSide.BUY:
            net_cash_amount = _money(gross_cash_amount + fees + taxes)
            realized_pnl = Decimal("0.00000000")
            self._apply_buy(
                wallet=wallet,
                decision=decision,
                position=position,
                quantity=quantity,
                gross_cash_amount=gross_cash_amount,
                net_cash_amount=net_cash_amount,
                executed_at=request.executed_at,
            )
        else:
            net_cash_amount = _money(gross_cash_amount - fees - taxes)
            realized_pnl = self._apply_sell(
                wallet=wallet,
                position=position,
                quantity=quantity,
                net_cash_amount=net_cash_amount,
                executed_at=request.executed_at,
            )

        order = PaperOrderModel(
            id=uuid4(),
            account_id=decision.trade_intent.account_id,
            trade_intent_id=decision.trade_intent_id,
            risk_decision_id=decision.id,
            execution_instrument_id=decision.execution_instrument_id,
            bank_instrument_id=bank_instrument_id,
            side=request.side.value,
            requested_quantity=quantity,
            approved_quantity=quantity,
            status=PaperOrderStatus.EXECUTED.value,
            created_at=request.executed_at,
            updated_at=request.executed_at,
        )
        trade = PaperTradeModel(
            id=uuid4(),
            order=order,
            account_id=order.account_id,
            execution_instrument_id=order.execution_instrument_id,
            bank_instrument_id=order.bank_instrument_id,
            quote_id=quote.id,
            side=request.side.value,
            quantity=quantity,
            execution_price=execution_price,
            gross_cash_amount=gross_cash_amount,
            fees=fees,
            taxes=taxes,
            spread_cost=spread_cost,
            net_cash_amount=net_cash_amount,
            realized_pnl=realized_pnl,
            executed_at=request.executed_at,
            created_at=request.executed_at,
        )
        self._session.add_all([order, trade])
        self._session.flush()
        self._append_trade_ledger(
            decision=decision,
            trade=trade,
            gross_cash_amount=gross_cash_amount,
            fees=fees,
            taxes=taxes,
            executed_at=request.executed_at,
        )
        self._session.flush()
        return PaperBrokerResult(order=order, trade=trade, inserted=True)

    def _load_approved_decision(self, risk_decision_id: UUID) -> RiskDecisionModel:
        decision = self._session.get(RiskDecisionModel, risk_decision_id)
        if decision is None:
            raise ValueError(f"risk decision was not found: {risk_decision_id}")
        if decision.decision not in {"approve", "reduce"}:
            raise ValueError("paper execution requires an approving risk decision")
        if decision.execution_instrument_id is None or decision.execution_instrument is None:
            raise ValueError("risk decision has no execution instrument")
        execution_instrument = decision.execution_instrument
        if execution_instrument.bank_instrument_id is None:
            raise ValueError("execution instrument has no bank instrument")
        if decision.approved_quantity is None or Decimal(decision.approved_quantity) <= Decimal(
            "0"
        ):
            raise ValueError("risk decision has no approved quantity")
        return decision

    def _load_quote(
        self,
        *,
        decision: RiskDecisionModel,
        quote_id: UUID | None,
    ) -> PriceQuoteModel:
        selected_quote_id = quote_id or decision.quote_id
        if selected_quote_id is None:
            raise ValueError("paper execution requires a quote")
        quote = self._session.get(PriceQuoteModel, selected_quote_id)
        if quote is None:
            raise ValueError(f"quote was not found: {selected_quote_id}")
        if quote.bank_instrument_id != self._bank_instrument_id(decision):
            raise ValueError("quote does not match decision bank instrument")
        return quote

    def _load_base_wallet(self, decision: RiskDecisionModel) -> WalletModel:
        wallet = self._session.scalar(
            select(WalletModel).where(
                WalletModel.virtual_account_id == decision.trade_intent.account_id,
                WalletModel.currency_id == decision.trade_intent.account.base_currency_id,
            )
        )
        if wallet is None:
            raise ValueError("base currency wallet was not found")
        return wallet

    def _load_position(
        self,
        *,
        decision: RiskDecisionModel,
    ) -> PositionModel | None:
        return self._session.scalar(
            select(PositionModel).where(
                PositionModel.account_id == decision.trade_intent.account_id,
                PositionModel.bank_instrument_id == self._bank_instrument_id(decision),
            )
        )

    def _apply_buy(
        self,
        *,
        wallet: WalletModel,
        decision: RiskDecisionModel,
        position: PositionModel | None,
        quantity: Decimal,
        gross_cash_amount: Decimal,
        net_cash_amount: Decimal,
        executed_at: datetime,
    ) -> None:
        if Decimal(wallet.available_amount) < net_cash_amount:
            raise ValueError("insufficient cash for paper buy")
        if position is None:
            position = PositionModel(
                id=uuid4(),
                account_id=decision.trade_intent.account_id,
                bank_instrument_id=self._bank_instrument_id(decision),
                quantity=Decimal("0"),
                average_cost=Decimal("0"),
                realized_pnl=Decimal("0"),
                created_at=executed_at,
            )
            self._session.add(position)
        old_quantity = Decimal(position.quantity)
        old_cost_basis = old_quantity * Decimal(position.average_cost)
        new_quantity = old_quantity + quantity
        wallet.available_amount = _money(Decimal(wallet.available_amount) - net_cash_amount)
        wallet.updated_at = executed_at
        position.quantity = quantity + Decimal(position.quantity)
        position.average_cost = _money((old_cost_basis + net_cash_amount) / new_quantity)
        position.updated_at = executed_at

    def _apply_sell(
        self,
        *,
        wallet: WalletModel,
        position: PositionModel | None,
        quantity: Decimal,
        net_cash_amount: Decimal,
        executed_at: datetime,
    ) -> Decimal:
        if position is None:
            raise ValueError("insufficient position for paper sell")
        if Decimal(position.quantity) < quantity:
            raise ValueError("insufficient position for paper sell")
        cost_basis = _money(quantity * Decimal(position.average_cost))
        realized_pnl = _money(net_cash_amount - cost_basis)
        wallet.available_amount = _money(Decimal(wallet.available_amount) + net_cash_amount)
        wallet.updated_at = executed_at
        position.quantity = _money(Decimal(position.quantity) - quantity)
        if position.quantity == Decimal("0"):
            position.average_cost = Decimal("0")
        position.realized_pnl = _money(Decimal(position.realized_pnl) + realized_pnl)
        position.updated_at = executed_at
        return realized_pnl

    def _bank_instrument_id(self, decision: RiskDecisionModel) -> UUID:
        execution_instrument = decision.execution_instrument
        if execution_instrument is None or execution_instrument.bank_instrument_id is None:
            raise ValueError("execution instrument has no bank instrument")
        return execution_instrument.bank_instrument_id

    def _append_trade_ledger(
        self,
        *,
        decision: RiskDecisionModel,
        trade: PaperTradeModel,
        gross_cash_amount: Decimal,
        fees: Decimal,
        taxes: Decimal,
        executed_at: datetime,
    ) -> None:
        sign = Decimal("-1") if trade.side == PaperOrderSide.BUY.value else Decimal("1")
        account_id = decision.trade_intent.account_id
        currency_id = decision.trade_intent.account.base_currency_id
        entries = [
            LedgerEntryModel(
                id=uuid4(),
                account_id=account_id,
                currency_id=currency_id,
                amount=_money(sign * gross_cash_amount),
                entry_type=f"paper_{trade.side}_cash",
                reference_type="paper_trade",
                reference_id=trade.id,
                metadata_json={"order_id": str(trade.order_id)},
                created_at=executed_at,
            )
        ]
        if fees > Decimal("0"):
            entries.append(
                LedgerEntryModel(
                    id=uuid4(),
                    account_id=account_id,
                    currency_id=currency_id,
                    amount=-fees,
                    entry_type="paper_fee",
                    reference_type="paper_trade",
                    reference_id=trade.id,
                    metadata_json={"order_id": str(trade.order_id)},
                    created_at=executed_at,
                )
            )
        if taxes > Decimal("0"):
            entries.append(
                LedgerEntryModel(
                    id=uuid4(),
                    account_id=account_id,
                    currency_id=currency_id,
                    amount=-taxes,
                    entry_type="paper_tax",
                    reference_type="paper_trade",
                    reference_id=trade.id,
                    metadata_json={"order_id": str(trade.order_id)},
                    created_at=executed_at,
                )
            )
        self._ledger.append(entries)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
