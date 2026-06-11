from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models.entities import PriceSnapshot, RawNews, RiskDecision
    from app.services.strategy import StrategyDecision
else:
    Session = Any
    PriceSnapshot = Any
    RawNews = Any
    RiskDecision = Any
    StrategyDecision = Any


class BasePriceScraper(ABC):
    @abstractmethod
    def fetch_price(self, db: Session, asset: str) -> PriceSnapshot:
        pass


class BaseNewsCollector(ABC):
    @abstractmethod
    def collect(self, db: Session) -> list[RawNews]:
        pass


class BaseCostModel(ABC):
    @abstractmethod
    def calculate_cost(self, amount: Decimal, price: Decimal) -> Decimal:
        pass


class BaseRiskGuard(ABC):
    @abstractmethod
    def evaluate_risk(self, db: Session, context: dict) -> RiskDecision:
        pass


class BaseIndicator(ABC):
    @abstractmethod
    def calculate(self, db: Session, asset_symbol: str) -> None:
        pass


class BaseStrategy(ABC):
    @abstractmethod
    async def evaluate(self, db: Session, context: dict) -> StrategyDecision:
        pass
