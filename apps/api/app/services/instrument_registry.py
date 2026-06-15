from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Currency, Portfolio, Provider, ProviderAccount


class InstrumentRegistryError(ValueError):
    pass


def get_currency_by_code(db: Session, code: str) -> Currency | None:
    return db.execute(select(Currency).where(Currency.code == code)).scalar_one_or_none()


def get_provider_account_for_portfolio(db: Session, portfolio: Portfolio) -> ProviderAccount | None:
    return db.execute(
        select(ProviderAccount)
        .where(
            ProviderAccount.portfolio_id == portfolio.id,
            ProviderAccount.is_active.is_(True),
        )
        .order_by(ProviderAccount.is_paper.desc(), ProviderAccount.id.asc())
        .limit(1)
    ).scalar_one_or_none()


def ensure_default_provider_account(db: Session, portfolio: Portfolio) -> ProviderAccount | None:
    account = get_provider_account_for_portfolio(db, portfolio)
    if account is not None:
        return account

    provider = _default_provider(db)
    base_currency = get_currency_by_code(db, portfolio.base_currency)
    if provider is None or base_currency is None:
        return None

    account = ProviderAccount(
        tenant_id="default",
        provider_id=provider.id,
        portfolio_id=portfolio.id,
        account_key=f"portfolio:{portfolio.id}:paper",
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


def _default_provider(db: Session) -> Provider | None:
    settings = get_settings()
    return db.execute(select(Provider).where(Provider.name == settings.default_provider_name)).scalar_one_or_none()
