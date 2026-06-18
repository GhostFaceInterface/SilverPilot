from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import (
    BankInstrumentModel,
    ExecutionInstrumentModel,
    InstrumentMappingModel,
    PriceQuoteModel,
    RiskDecisionModel,
    TradeIntentModel,
    VirtualAccountInstrumentModel,
    VirtualAccountModel,
    WalletModel,
)
from silverpilot.app.domain.enums import RiskDecisionOutcome

_MONEY_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True)
class RiskPolicy:
    version: str = "risk-v1"
    max_position_cash: Decimal = Decimal("5000")
    max_order_cash: Decimal = Decimal("1000")
    max_daily_loss: Decimal = Decimal("250")
    max_drawdown: Decimal = Decimal("0.10")
    min_quote_freshness: timedelta = timedelta(minutes=5)
    max_spread_pct: Decimal = Decimal("0.03")
    min_order_cash: Decimal = Decimal("100")
    min_expected_edge_after_costs: Decimal = Decimal("0")
    max_source_divergence_pct: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("risk policy version is required")
        for field_name in (
            "max_position_cash",
            "max_order_cash",
            "max_daily_loss",
            "max_drawdown",
            "max_spread_pct",
            "min_order_cash",
        ):
            if getattr(self, field_name) < Decimal("0"):
                raise ValueError(f"{field_name} cannot be negative")
        if self.max_order_cash <= Decimal("0"):
            raise ValueError("max_order_cash must be greater than zero")
        if self.max_position_cash <= Decimal("0"):
            raise ValueError("max_position_cash must be greater than zero")
        if self.min_order_cash <= Decimal("0"):
            raise ValueError("min_order_cash must be greater than zero")
        if self.min_quote_freshness <= timedelta(0):
            raise ValueError("min_quote_freshness must be greater than zero")


@dataclass(frozen=True)
class RiskContext:
    execution_instrument_id: UUID
    quote_source: str
    evaluated_at: datetime
    current_position_cash: Decimal | None
    current_drawdown: Decimal | None
    current_daily_loss: Decimal | None
    expected_edge_after_costs: Decimal | None = None
    source_divergence_pct: Decimal | None = None
    cooldown_active: bool = False
    no_trade_window_active: bool = False


@dataclass(frozen=True)
class RiskDecisionResult:
    decision: RiskDecisionModel
    inserted: bool


class RiskManager:
    """Evaluates pending trade intents against a versioned risk policy."""

    def __init__(self, *, session: Session, policy: RiskPolicy | None = None) -> None:
        self._session = session
        self._policy = policy or RiskPolicy()

    def evaluate(self, *, trade_intent_id: UUID, context: RiskContext) -> RiskDecisionResult:
        intent = self._load_intent(trade_intent_id)
        account = self._load_account(intent.account_id)
        execution = AccountBoundExecutionResolver(session=self._session).resolve(
            account=account,
            intent=intent,
            execution_instrument_id=context.execution_instrument_id,
        )
        quote = self._latest_quote(execution.bank_instrument, context)
        wallet = self._base_currency_wallet(account)

        decision_payload = self._evaluate_payload(
            intent=intent,
            execution=execution,
            quote=quote,
            wallet=wallet,
            context=context,
        )
        existing = self._session.scalar(
            select(RiskDecisionModel).where(
                RiskDecisionModel.trade_intent_id == intent.id,
                RiskDecisionModel.policy_version == self._policy.version,
            )
        )
        values = {
            "execution_instrument_id": (
                execution.execution_instrument.id
                if execution.execution_instrument is not None
                else context.execution_instrument_id
            ),
            "quote_id": quote.id if quote is not None else None,
            "decision": decision_payload.outcome.value,
            "requested_cash_amount": intent.cash_amount,
            "approved_cash_amount": decision_payload.approved_cash_amount,
            "approved_quantity": decision_payload.approved_quantity,
            "reasons": decision_payload.reasons,
            "constraints_applied": decision_payload.constraints_applied,
            "evaluated_at": context.evaluated_at,
        }
        if existing is not None:
            for field_name, value in values.items():
                setattr(existing, field_name, value)
            existing.updated_at = context.evaluated_at
            self._session.flush()
            return RiskDecisionResult(decision=existing, inserted=False)

        decision = RiskDecisionModel(
            trade_intent_id=intent.id,
            policy_version=self._policy.version,
            created_at=context.evaluated_at,
            **values,
        )
        self._session.add(decision)
        self._session.flush()
        return RiskDecisionResult(decision=decision, inserted=True)

    def _evaluate_payload(
        self,
        *,
        intent: TradeIntentModel,
        execution: "ExecutionResolution",
        quote: PriceQuoteModel | None,
        wallet: WalletModel | None,
        context: RiskContext,
    ) -> "_RiskDecisionPayload":
        constraints: dict[str, object] = {
            "policy_version": self._policy.version,
            "requested_cash_amount": str(intent.cash_amount),
            "max_order_cash": str(self._policy.max_order_cash),
            "max_position_cash": str(self._policy.max_position_cash),
            "max_daily_loss": str(self._policy.max_daily_loss),
            "max_drawdown": str(self._policy.max_drawdown),
            "max_spread_pct": str(self._policy.max_spread_pct),
            "min_quote_freshness_seconds": int(self._policy.min_quote_freshness.total_seconds()),
            "execution_instrument_id": str(context.execution_instrument_id),
        }
        missing = self._missing_context(context)
        if missing:
            return _RiskDecisionPayload.reject(
                reasons=[f"missing_risk_context:{','.join(missing)}"],
                constraints_applied=constraints,
            )
        if execution.reasons:
            return _RiskDecisionPayload.reject(
                reasons=execution.reasons,
                constraints_applied=constraints,
            )
        if execution.bank_instrument is None:
            return _RiskDecisionPayload.reject(
                reasons=["missing_bank_instrument"],
                constraints_applied=constraints,
            )
        constraints["bank_instrument_id"] = str(execution.bank_instrument.id)
        constraints["bank_min_trade_amount"] = str(execution.bank_instrument.min_trade_amount)
        constraints["bank_quantity_precision"] = execution.bank_instrument.quantity_precision
        if wallet is None:
            return _RiskDecisionPayload.reject(
                reasons=["missing_base_currency_wallet"],
                constraints_applied=constraints,
            )
        constraints["available_cash"] = str(wallet.available_amount)
        constraints["current_position_cash"] = str(context.current_position_cash)
        constraints["current_drawdown"] = str(context.current_drawdown)
        constraints["current_daily_loss"] = str(context.current_daily_loss)

        if quote is None:
            return _RiskDecisionPayload.reject(
                reasons=["missing_quote"],
                constraints_applied=constraints,
            )
        constraints["quote_id"] = str(quote.id)
        constraints["quote_freshness_status"] = quote.freshness_status
        observed_at = _aware_datetime(quote.observed_at)
        quote_age_seconds = (context.evaluated_at - observed_at).total_seconds()
        constraints["quote_age_seconds"] = str(quote_age_seconds)

        if quote.freshness_status != "fresh":
            return _RiskDecisionPayload.reject(
                reasons=["stale_quote"],
                constraints_applied=constraints,
            )
        if observed_at > context.evaluated_at:
            return _RiskDecisionPayload.reject(
                reasons=["future_quote"],
                constraints_applied=constraints,
            )
        if context.evaluated_at - observed_at > self._policy.min_quote_freshness:
            return _RiskDecisionPayload.reject(
                reasons=["stale_quote"],
                constraints_applied=constraints,
            )

        spread_pct = _spread_pct(quote)
        constraints["spread_pct"] = str(spread_pct)
        if spread_pct > self._policy.max_spread_pct:
            return _RiskDecisionPayload.reject(
                reasons=["spread_above_threshold"],
                constraints_applied=constraints,
            )
        if (
            context.current_daily_loss is not None
            and context.current_daily_loss > self._policy.max_daily_loss
        ):
            return _RiskDecisionPayload.reject(
                reasons=["daily_loss_limit_breached"],
                constraints_applied=constraints,
            )
        if (
            context.current_drawdown is not None
            and context.current_drawdown > self._policy.max_drawdown
        ):
            return _RiskDecisionPayload.reject(
                reasons=["max_drawdown_breached"],
                constraints_applied=constraints,
            )
        if context.cooldown_active:
            return _RiskDecisionPayload.reject(
                reasons=["cooldown_active"],
                constraints_applied=constraints,
            )
        if context.no_trade_window_active:
            return _RiskDecisionPayload.reject(
                reasons=["no_trade_window_active"],
                constraints_applied=constraints,
            )
        if (
            self._policy.max_source_divergence_pct is not None
            and context.source_divergence_pct is not None
            and context.source_divergence_pct > self._policy.max_source_divergence_pct
        ):
            return _RiskDecisionPayload.reject(
                reasons=["source_divergence_above_threshold"],
                constraints_applied=constraints,
            )
        if (
            context.expected_edge_after_costs is not None
            and context.expected_edge_after_costs < self._policy.min_expected_edge_after_costs
        ):
            return _RiskDecisionPayload.reject(
                reasons=["expected_edge_below_costs"],
                constraints_applied=constraints,
            )

        requested_cash = Decimal(intent.cash_amount)
        approved_cash = requested_cash
        reasons = ["risk_approved"]
        if requested_cash > self._policy.max_order_cash:
            approved_cash = self._policy.max_order_cash
            reasons = ["reduced:max_order_cash"]

        position_room = self._policy.max_position_cash - Decimal(str(context.current_position_cash))
        constraints["position_room_cash"] = str(position_room)
        if position_room < approved_cash:
            approved_cash = max(position_room, Decimal("0"))
            reasons = ["reduced:max_position_cash"]

        if wallet.available_amount < approved_cash:
            return _RiskDecisionPayload.reject(
                reasons=["insufficient_balance"],
                constraints_applied=constraints,
            )
        if approved_cash < self._policy.min_order_cash:
            return _RiskDecisionPayload.reject(
                reasons=["approved_size_below_min_order"],
                constraints_applied=constraints,
            )
        if approved_cash < Decimal(execution.bank_instrument.min_trade_amount):
            return _RiskDecisionPayload.reject(
                reasons=["approved_size_below_bank_min_trade"],
                constraints_applied=constraints,
            )

        approved_quantity = _quantize_quantity(
            approved_cash / Decimal(quote.bank_sell_price),
            execution.bank_instrument.quantity_precision,
        )
        approved_cash = (approved_quantity * Decimal(quote.bank_sell_price)).quantize(
            _MONEY_QUANTUM,
            rounding=ROUND_DOWN,
        )
        if approved_quantity <= Decimal("0"):
            return _RiskDecisionPayload.reject(
                reasons=["approved_quantity_below_precision"],
                constraints_applied=constraints,
            )
        if approved_cash < self._policy.min_order_cash:
            return _RiskDecisionPayload.reject(
                reasons=["approved_size_below_min_order_after_precision"],
                constraints_applied=constraints,
            )
        if approved_cash < Decimal(execution.bank_instrument.min_trade_amount):
            return _RiskDecisionPayload.reject(
                reasons=["approved_size_below_bank_min_trade_after_precision"],
                constraints_applied=constraints,
            )
        if approved_cash < requested_cash and not reasons[0].startswith("reduced"):
            reasons = ["reduced:quantity_precision"]
        constraints["approved_cash_amount"] = str(approved_cash)
        constraints["approved_quantity"] = str(approved_quantity)
        outcome = (
            RiskDecisionOutcome.REDUCE
            if approved_cash < requested_cash
            else RiskDecisionOutcome.APPROVE
        )
        return _RiskDecisionPayload(
            outcome=outcome,
            approved_cash_amount=approved_cash,
            approved_quantity=approved_quantity,
            reasons=reasons,
            constraints_applied=constraints,
        )

    def _load_intent(self, trade_intent_id: UUID) -> TradeIntentModel:
        intent = self._session.get(TradeIntentModel, trade_intent_id)
        if intent is None:
            raise ValueError(f"trade intent was not found: {trade_intent_id}")
        if intent.status != "pending_risk":
            raise ValueError(f"trade intent is not pending risk: {trade_intent_id}")
        return intent

    def _load_account(self, account_id: UUID) -> VirtualAccountModel:
        account = self._session.get(VirtualAccountModel, account_id)
        if account is None:
            raise ValueError(f"account was not found: {account_id}")
        if account.status != "active":
            raise ValueError(f"account is not active: {account_id}")
        return account

    def _latest_quote(
        self,
        bank_instrument: BankInstrumentModel | None,
        context: RiskContext,
    ) -> PriceQuoteModel | None:
        if bank_instrument is None:
            return None
        return self._session.scalar(
            select(PriceQuoteModel)
            .where(
                PriceQuoteModel.bank_instrument_id == bank_instrument.id,
                PriceQuoteModel.source == context.quote_source,
                PriceQuoteModel.observed_at <= context.evaluated_at,
            )
            .order_by(PriceQuoteModel.observed_at.desc(), PriceQuoteModel.fetched_at.desc())
        )

    def _base_currency_wallet(self, account: VirtualAccountModel) -> WalletModel | None:
        return self._session.scalar(
            select(WalletModel).where(
                WalletModel.virtual_account_id == account.id,
                WalletModel.currency_id == account.base_currency_id,
            )
        )

    def _missing_context(self, context: RiskContext) -> list[str]:
        missing: list[str] = []
        if context.current_position_cash is None:
            missing.append("current_position_cash")
        if context.current_drawdown is None:
            missing.append("current_drawdown")
        if context.current_daily_loss is None:
            missing.append("current_daily_loss")
        if context.expected_edge_after_costs is None:
            missing.append("expected_edge_after_costs")
        if (
            self._policy.max_source_divergence_pct is not None
            and context.source_divergence_pct is None
        ):
            missing.append("source_divergence_pct")
        return missing


@dataclass(frozen=True)
class ExecutionResolution:
    execution_instrument: ExecutionInstrumentModel | None
    bank_instrument: BankInstrumentModel | None
    reasons: list[str]


class AccountBoundExecutionResolver:
    """Resolves an intent to the account-bound executable bank instrument."""

    def __init__(self, *, session: Session) -> None:
        self._session = session

    def resolve(
        self,
        *,
        account: VirtualAccountModel,
        intent: TradeIntentModel,
        execution_instrument_id: UUID,
    ) -> ExecutionResolution:
        execution_instrument = self._session.get(ExecutionInstrumentModel, execution_instrument_id)
        if execution_instrument is None:
            return ExecutionResolution(None, None, ["execution_instrument_not_found"])
        bank_instrument = execution_instrument.bank_instrument
        if execution_instrument.status != "active":
            return ExecutionResolution(
                execution_instrument,
                bank_instrument,
                ["execution_instrument_inactive"],
            )
        if execution_instrument.execution_venue_id != account.execution_venue_id:
            return ExecutionResolution(
                execution_instrument,
                bank_instrument,
                ["execution_instrument_wrong_venue"],
            )
        allowed = self._session.scalar(
            select(VirtualAccountInstrumentModel).where(
                VirtualAccountInstrumentModel.virtual_account_id == account.id,
                VirtualAccountInstrumentModel.execution_instrument_id == execution_instrument.id,
            )
        )
        if allowed is None or allowed.status != "active":
            return ExecutionResolution(
                execution_instrument,
                bank_instrument,
                ["execution_instrument_not_allowed"],
            )
        if bank_instrument is None:
            return ExecutionResolution(execution_instrument, None, ["missing_bank_instrument"])
        if bank_instrument.status != "active":
            return ExecutionResolution(
                execution_instrument,
                bank_instrument,
                ["bank_instrument_inactive"],
            )
        if (
            account.execution_venue.bank_id is not None
            and bank_instrument.bank_id != account.execution_venue.bank_id
        ):
            return ExecutionResolution(
                execution_instrument,
                bank_instrument,
                ["bank_instrument_wrong_bank"],
            )

        strategy_run = intent.strategy_run
        if strategy_run.instrument_type == "reference":
            mapping = self._session.scalar(
                select(InstrumentMappingModel).where(
                    InstrumentMappingModel.reference_market_instrument_id
                    == strategy_run.instrument_id,
                    InstrumentMappingModel.execution_instrument_id == execution_instrument.id,
                    InstrumentMappingModel.status == "active",
                )
            )
            if mapping is None:
                return ExecutionResolution(
                    execution_instrument,
                    bank_instrument,
                    ["missing_reference_execution_mapping"],
                )
        elif (
            strategy_run.instrument_type == "execution"
            and strategy_run.instrument_id != execution_instrument.id
        ):
            return ExecutionResolution(
                execution_instrument,
                bank_instrument,
                ["execution_instrument_mismatch"],
            )

        return ExecutionResolution(execution_instrument, bank_instrument, [])


@dataclass(frozen=True)
class _RiskDecisionPayload:
    outcome: RiskDecisionOutcome
    approved_cash_amount: Decimal | None
    approved_quantity: Decimal | None
    reasons: list[str]
    constraints_applied: dict[str, object]

    @classmethod
    def reject(
        cls,
        *,
        reasons: list[str],
        constraints_applied: dict[str, object],
    ) -> "_RiskDecisionPayload":
        return cls(
            outcome=RiskDecisionOutcome.REJECT,
            approved_cash_amount=Decimal("0"),
            approved_quantity=Decimal("0"),
            reasons=reasons,
            constraints_applied=constraints_applied,
        )


def _spread_pct(quote: PriceQuoteModel) -> Decimal:
    sell_price = Decimal(quote.bank_sell_price)
    if sell_price <= Decimal("0"):
        return Decimal("1")
    return (Decimal(quote.bank_sell_price) - Decimal(quote.bank_buy_price)) / sell_price


def _quantize_quantity(value: Decimal, precision: int) -> Decimal:
    quantum = Decimal("1").scaleb(-precision)
    return value.quantize(quantum, rounding=ROUND_DOWN)


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value
