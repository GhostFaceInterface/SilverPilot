from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, Currency, Instrument, MeasurementUnit, Portfolio, Provider, ProviderAccount


REFERENCE_CURRENCIES = {
    "USD": {"name": "US Dollar", "numeric_code": "840", "minor_unit": 2},
    "TRY": {"name": "Turkish Lira", "numeric_code": "949", "minor_unit": 2},
    "EUR": {"name": "Euro", "numeric_code": "978", "minor_unit": 2},
}

REFERENCE_UNITS = {
    "gram": {
        "name": "Gram",
        "unit_type": "mass",
        "to_base_factor": Decimal("1.00000000"),
        "base_unit_code": "gram",
    },
    "troy_ounce": {
        "name": "Troy Ounce",
        "unit_type": "mass",
        "to_base_factor": Decimal("31.10350000"),
        "base_unit_code": "gram",
    },
    "currency_unit": {
        "name": "Currency Unit",
        "unit_type": "currency",
        "to_base_factor": Decimal("1.00000000"),
        "base_unit_code": "currency_unit",
    },
}

REFERENCE_INSTRUMENTS = {
    "XAG": {"name": "Silver", "instrument_type": "metal", "native_unit": "troy_ounce"},
    "XAU": {"name": "Gold", "instrument_type": "metal", "native_unit": "troy_ounce"},
    "USD": {"name": "US Dollar", "instrument_type": "currency", "native_currency": "USD"},
    "TRY": {"name": "Turkish Lira", "instrument_type": "currency", "native_currency": "TRY"},
    "EUR": {"name": "Euro", "instrument_type": "currency", "native_currency": "EUR"},
}

ASSET_MAPPINGS = {
    "XAG": {"instrument": "XAG", "unit": "troy_ounce", "quote_currency": "USD"},
    "XAG_GRAM": {"instrument": "XAG", "unit": "gram", "quote_currency": "USD"},
    "XAG_TRY": {"instrument": "XAG", "unit": "gram", "quote_currency": "TRY"},
    "USD": {"instrument": "USD", "unit": "currency_unit", "quote_currency": "USD"},
    "TRY": {"instrument": "TRY", "unit": "currency_unit", "quote_currency": "TRY"},
    "EUR": {"instrument": "EUR", "unit": "currency_unit", "quote_currency": "EUR"},
}


def ensure_reference_data(db: Session) -> None:
    currencies = {code: get_or_create_currency(db, code) for code in REFERENCE_CURRENCIES}
    units = {code: get_or_create_unit(db, code) for code in REFERENCE_UNITS}

    for symbol, payload in REFERENCE_INSTRUMENTS.items():
        instrument = db.execute(select(Instrument).where(Instrument.symbol == symbol)).scalar_one_or_none()
        if instrument is None:
            instrument = Instrument(
                symbol=symbol,
                name=payload["name"],
                instrument_type=payload["instrument_type"],
                is_active=True,
                metadata_json={},
            )
            db.add(instrument)
        instrument.native_currency = currencies.get(payload.get("native_currency"))
        instrument.native_unit = units.get(payload.get("native_unit"))

    db.flush()
    map_existing_assets(db)


def get_or_create_currency(db: Session, code: str) -> Currency:
    currency = db.execute(select(Currency).where(Currency.code == code)).scalar_one_or_none()
    if currency is not None:
        return currency
    payload = REFERENCE_CURRENCIES[code]
    currency = Currency(
        code=code,
        name=payload["name"],
        numeric_code=payload["numeric_code"],
        minor_unit=payload["minor_unit"],
        is_active=True,
    )
    db.add(currency)
    db.flush()
    return currency


def get_or_create_unit(db: Session, code: str) -> MeasurementUnit:
    unit = db.execute(select(MeasurementUnit).where(MeasurementUnit.code == code)).scalar_one_or_none()
    if unit is not None:
        return unit
    payload = REFERENCE_UNITS[code]
    unit = MeasurementUnit(
        code=code,
        name=payload["name"],
        unit_type=payload["unit_type"],
        to_base_factor=payload["to_base_factor"],
        base_unit_code=payload["base_unit_code"],
        is_active=True,
    )
    db.add(unit)
    db.flush()
    return unit


def map_existing_assets(db: Session) -> None:
    for symbol, payload in ASSET_MAPPINGS.items():
        asset = db.execute(select(Asset).where(Asset.symbol == symbol)).scalar_one_or_none()
        if asset is None:
            continue
        asset.instrument = db.execute(
            select(Instrument).where(Instrument.symbol == payload["instrument"])
        ).scalar_one_or_none()
        asset.unit = db.execute(select(MeasurementUnit).where(MeasurementUnit.code == payload["unit"])).scalar_one()
        asset.quote_currency = db.execute(
            select(Currency).where(Currency.code == payload["quote_currency"])
        ).scalar_one()


def get_or_create_default_provider_account(db: Session, portfolio: Portfolio) -> ProviderAccount:
    ensure_reference_data(db)

    settings = get_settings()
    provider = db.execute(select(Provider).where(Provider.name == settings.default_provider_name)).scalar_one_or_none()
    if provider is None:
        provider = Provider(
            name=settings.default_provider_name,
            display_name=settings.default_provider_name.replace("_", " ").title(),
            is_active=True,
            config_json={},
        )
        db.add(provider)
        db.flush()

    base_currency = get_or_create_currency(db, portfolio.base_currency)
    account_key = f"portfolio:{portfolio.id}:paper"
    account = db.execute(
        select(ProviderAccount).where(
            ProviderAccount.tenant_id == "default",
            ProviderAccount.provider_id == provider.id,
            ProviderAccount.account_key == account_key,
        )
    ).scalar_one_or_none()
    if account is not None:
        return account

    account = ProviderAccount(
        tenant_id="default",
        provider_id=provider.id,
        portfolio_id=portfolio.id,
        account_key=account_key,
        display_name=f"{portfolio.name} paper account",
        account_type="paper",
        base_currency_id=base_currency.id,
        is_paper=True,
        is_active=True,
        metadata_json={"portfolio_name": portfolio.name},
    )
    db.add(account)
    db.flush()
    return account
