from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import get_settings

class BudgetExceededError(Exception):
    """Raised when the daily LLM budget has been exceeded."""
    pass

def get_daily_spent_usd(db: Session) -> Decimal:
    """
    Queries the database to calculate the total spent USD on LLM calls today (UTC).
    """
    from app.models import LLMCallTrace  # Lazy import to avoid circular dependencies
    
    start_of_today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    total_spent = db.query(func.sum(LLMCallTrace.total_cost_usd))\
        .filter(LLMCallTrace.created_at >= start_of_today)\
        .scalar()
        
    if total_spent is None:
        return Decimal("0.000000")
        
    return Decimal(str(total_spent))

def check_budget_limit(db: Session, additional_cost: Decimal = Decimal("0.0")) -> bool:
    """
    Checks if the daily budget limit is exceeded, including any proposed additional cost.
    Raises BudgetExceededError if the limit is exceeded.
    """
    settings = get_settings()
    daily_spent = get_daily_spent_usd(db)
    
    total_projected = daily_spent + additional_cost
    
    if total_projected >= settings.deepseek_daily_budget_usd:
        raise BudgetExceededError(
            f"Daily LLM budget of ${settings.deepseek_daily_budget_usd:.4f} USD exceeded. "
            f"Currently spent: ${daily_spent:.4f} USD. Projected: ${total_projected:.4f} USD."
        )
        
    return True
