from decimal import Decimal
from typing import Protocol

from silverpilot.app.domain.models import BankInstrument, PriceQuote, Unit


class PriceProvider(Protocol):
    def fetch_quote(self, instrument: BankInstrument) -> PriceQuote:
        """Fetch a quote candidate for the provided bank instrument."""


class UnitConversionService(Protocol):
    def convert(self, value: Decimal, from_unit: Unit, to_unit: Unit) -> Decimal:
        """Convert a Decimal quantity between configured units."""
