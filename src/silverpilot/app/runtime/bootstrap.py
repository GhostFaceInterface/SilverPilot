import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from silverpilot.app.db.models import (
    BankInstrumentModel,
    BankModel,
    CurrencyModel,
    ExecutionInstrumentModel,
    ExecutionVenueModel,
    InstrumentMappingModel,
    MetalModel,
    ReferenceMarketInstrumentModel,
    StrategyModel,
    UnitConversionRuleModel,
    UnitModel,
    UserModel,
    VirtualAccountInstrumentModel,
    VirtualAccountModel,
    WalletModel,
)
from silverpilot.app.db.session import create_db_engine
from silverpilot.app.providers.yahoo_finance import YAHOO_RESEARCH_SOURCE_NAME


@dataclass(frozen=True)
class BootstrapResult:
    account_id: UUID
    bank_instrument_id: UUID
    execution_instrument_id: UUID
    strategy_id: UUID
    wallet_id: UUID
    yahoo_reference_instrument_ids: dict[str, UUID]
    created: dict[str, bool]

    def to_json(self) -> dict[str, object]:
        return {
            "account_id": str(self.account_id),
            "bank_instrument_id": str(self.bank_instrument_id),
            "execution_instrument_id": str(self.execution_instrument_id),
            "strategy_id": str(self.strategy_id),
            "wallet_id": str(self.wallet_id),
            "yahoo_reference_instrument_ids": {
                symbol: str(instrument_id)
                for symbol, instrument_id in self.yahoo_reference_instrument_ids.items()
            },
            "created": self.created,
        }


def bootstrap_paper_runtime(
    session: Session,
    *,
    starting_balance: Decimal = Decimal("10000"),
    now: datetime | None = None,
) -> BootstrapResult:
    if starting_balance <= Decimal("0"):
        raise ValueError("starting_balance must be greater than zero")
    created_at = now or datetime.now(UTC)
    created: dict[str, bool] = {}

    gram = _get_or_create(
        session,
        UnitModel,
        UnitModel.code == "GRAM",
        created,
        "unit_gram",
        code="GRAM",
        name="Gram",
        precision=6,
        created_at=created_at,
    )
    ounce = _get_or_create(
        session,
        UnitModel,
        UnitModel.code == "OZ",
        created,
        "unit_ounce",
        code="OZ",
        name="Troy ounce",
        precision=6,
        created_at=created_at,
    )
    try_currency = _get_or_create(
        session,
        CurrencyModel,
        CurrencyModel.code == "TRY",
        created,
        "currency_try",
        code="TRY",
        name="Turkish Lira",
        decimal_places=2,
        created_at=created_at,
    )
    usd_currency = _get_or_create(
        session,
        CurrencyModel,
        CurrencyModel.code == "USD",
        created,
        "currency_usd",
        code="USD",
        name="US Dollar",
        decimal_places=2,
        created_at=created_at,
    )
    metal = _get_or_create(
        session,
        MetalModel,
        MetalModel.code == "XAG",
        created,
        "metal_xag",
        code="XAG",
        name="Silver",
        default_unit=gram,
        created_at=created_at,
    )
    gold = _get_or_create(
        session,
        MetalModel,
        MetalModel.code == "XAU",
        created,
        "metal_xau",
        code="XAU",
        name="Gold",
        default_unit=gram,
        created_at=created_at,
    )
    _get_or_create(
        session,
        UnitConversionRuleModel,
        (UnitConversionRuleModel.from_unit_id == ounce.id)
        & (UnitConversionRuleModel.to_unit_id == gram.id)
        & (UnitConversionRuleModel.effective_to.is_(None)),
        created,
        "conversion_oz_to_gram",
        from_unit=ounce,
        to_unit=gram,
        factor=Decimal("31.1034768"),
        effective_from=created_at,
        created_at=created_at,
    )
    bank = _get_or_create(
        session,
        BankModel,
        BankModel.code == "kuveyt_turk",
        created,
        "bank_kuveyt_turk",
        code="kuveyt_turk",
        name="Kuveyt Turk",
        country_code="TR",
        status="active",
        source_policy="official public indicative finance portal",
        created_at=created_at,
    )
    venue = _get_or_create(
        session,
        ExecutionVenueModel,
        ExecutionVenueModel.code == "kuveyt_turk",
        created,
        "execution_venue_kuveyt_turk",
        venue_type="bank",
        bank=bank,
        code="kuveyt_turk",
        name="Kuveyt Turk paper venue",
        status="active",
        created_at=created_at,
    )
    bank_instrument = _get_or_create(
        session,
        BankInstrumentModel,
        (BankInstrumentModel.bank_id == bank.id)
        & (BankInstrumentModel.metal_id == metal.id)
        & (BankInstrumentModel.currency_id == try_currency.id)
        & (BankInstrumentModel.unit_id == gram.id),
        created,
        "bank_instrument_xag_gram_try",
        bank=bank,
        metal=metal,
        currency=try_currency,
        unit=gram,
        symbol="KT-XAG-GRAM-TRY",
        min_trade_amount=Decimal("100"),
        quantity_precision=4,
        price_precision=4,
        status="active",
        created_at=created_at,
    )
    execution_instrument = _get_or_create(
        session,
        ExecutionInstrumentModel,
        (ExecutionInstrumentModel.execution_venue_id == venue.id)
        & (ExecutionInstrumentModel.metal_id == metal.id)
        & (ExecutionInstrumentModel.currency_id == try_currency.id)
        & (ExecutionInstrumentModel.unit_id == gram.id),
        created,
        "execution_instrument_xag_gram_try",
        execution_venue=venue,
        bank_instrument=bank_instrument,
        metal=metal,
        currency=try_currency,
        unit=gram,
        symbol="KT-XAG-GRAM-TRY",
        status="active",
        created_at=created_at,
    )
    silver_reference = _get_or_create(
        session,
        ReferenceMarketInstrumentModel,
        (ReferenceMarketInstrumentModel.symbol == "SI=F")
        & (ReferenceMarketInstrumentModel.source == YAHOO_RESEARCH_SOURCE_NAME),
        created,
        "reference_yahoo_si_f",
        symbol="SI=F",
        source=YAHOO_RESEARCH_SOURCE_NAME,
        metal=metal,
        currency=usd_currency,
        unit=ounce,
        status="active",
        provider="yahoo_finance_chart",
        exchange="COMEX",
        timezone="America/New_York",
        data_delay_seconds=None,
        delay_policy="manual_review",
        session_calendar_code="yahoo-research-manual-review",
        source_terms_status="research_only",
        created_at=created_at,
    )
    gold_reference = _get_or_create(
        session,
        ReferenceMarketInstrumentModel,
        (ReferenceMarketInstrumentModel.symbol == "GC=F")
        & (ReferenceMarketInstrumentModel.source == YAHOO_RESEARCH_SOURCE_NAME),
        created,
        "reference_yahoo_gc_f",
        symbol="GC=F",
        source=YAHOO_RESEARCH_SOURCE_NAME,
        metal=gold,
        currency=usd_currency,
        unit=ounce,
        status="active",
        provider="yahoo_finance_chart",
        exchange="COMEX",
        timezone="America/New_York",
        data_delay_seconds=None,
        delay_policy="manual_review",
        session_calendar_code="yahoo-research-manual-review",
        source_terms_status="research_only",
        created_at=created_at,
    )
    _get_or_create(
        session,
        InstrumentMappingModel,
        (InstrumentMappingModel.reference_market_instrument_id == silver_reference.id)
        & (InstrumentMappingModel.execution_instrument_id == execution_instrument.id),
        created,
        "mapping_yahoo_si_f_to_kuveyt_xag",
        reference_market_instrument=silver_reference,
        execution_instrument=execution_instrument,
        fx_pair="USDTRY",
        unit_conversion_rule=None,
        status="active",
        created_at=created_at,
    )
    user = _get_or_create(
        session,
        UserModel,
        UserModel.external_id == "silverpilot-paper-runtime",
        created,
        "user_paper_runtime",
        external_id="silverpilot-paper-runtime",
        status="active",
        created_at=created_at,
    )
    account = _get_or_create(
        session,
        VirtualAccountModel,
        (VirtualAccountModel.user_id == user.id) & (VirtualAccountModel.name == "Paper TRY"),
        created,
        "account_paper_try",
        user=user,
        name="Paper TRY",
        base_currency=try_currency,
        execution_venue=venue,
        starting_balance=starting_balance,
        status="active",
        created_at=created_at,
    )
    wallet = _get_or_create(
        session,
        WalletModel,
        (WalletModel.virtual_account_id == account.id)
        & (WalletModel.currency_id == try_currency.id),
        created,
        "wallet_try",
        virtual_account=account,
        currency=try_currency,
        available_amount=starting_balance,
        reserved_amount=Decimal("0"),
        created_at=created_at,
    )
    _get_or_create(
        session,
        VirtualAccountInstrumentModel,
        (VirtualAccountInstrumentModel.virtual_account_id == account.id)
        & (VirtualAccountInstrumentModel.execution_instrument_id == execution_instrument.id),
        created,
        "allowed_execution_instrument",
        virtual_account=account,
        execution_instrument=execution_instrument,
        status="active",
        created_at=created_at,
    )
    strategy = _get_or_create(
        session,
        StrategyModel,
        (StrategyModel.name == "trend_up_pullback") & (StrategyModel.version == "v1"),
        created,
        "strategy_trend_up_pullback",
        name="trend_up_pullback",
        version="v1",
        parameters={"cash_amount": "1000"},
        enabled=True,
        created_at=created_at,
    )
    session.flush()
    return BootstrapResult(
        account_id=account.id,
        bank_instrument_id=bank_instrument.id,
        execution_instrument_id=execution_instrument.id,
        strategy_id=strategy.id,
        wallet_id=wallet.id,
        yahoo_reference_instrument_ids={
            silver_reference.symbol: silver_reference.id,
            gold_reference.symbol: gold_reference.id,
        },
        created=created,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the SilverPilot paper runtime.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--starting-balance", default="10000")
    args = parser.parse_args(argv)

    engine = create_db_engine(args.database_url)
    with Session(engine) as session:
        result = bootstrap_paper_runtime(
            session,
            starting_balance=Decimal(args.starting_balance),
        )
        session.commit()
    print(json.dumps(result.to_json(), sort_keys=True))
    return 0


def _get_or_create(
    session: Session,
    model_type: type[Any],
    criterion: ColumnElement[bool],
    created: dict[str, bool],
    key: str,
    **values: object,
) -> Any:
    existing = session.scalar(select(model_type).where(criterion))
    if existing is not None:
        created[key] = False
        return existing
    model = model_type(**values)
    session.add(model)
    session.flush()
    created[key] = True
    return model


if __name__ == "__main__":
    raise SystemExit(main())
