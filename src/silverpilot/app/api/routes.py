from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from silverpilot.app.api.schemas import (
    AccountResponse,
    BacktestRunResponse,
    BacktestRunSummaryResponse,
    BankResponse,
    ExecutionInstrumentResponse,
    HealthResponse,
    IndicatorSnapshotResponse,
    MarketRegimeSnapshotResponse,
    PaginatedResponse,
    PaperTradeResponse,
    PositionResponse,
    PriceQuoteResponse,
    ReportResponse,
    WalletResponse,
)
from silverpilot.app.api.services import ApiQueryService, Pagination
from silverpilot.app.core.settings import Settings, get_settings
from silverpilot.app.db.session import get_db_session

api_router = APIRouter(prefix="/api/v1")


def pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


def query_service(session: Annotated[Session, Depends(get_db_session)]) -> ApiQueryService:
    return ApiQueryService(session)


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
def api_health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@api_router.get("/system/health", response_model=HealthResponse, tags=["system"])
def system_health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@api_router.get("/accounts", response_model=PaginatedResponse[AccountResponse], tags=["accounts"])
def list_accounts(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> PaginatedResponse[AccountResponse]:
    return service.list_accounts(page_request, status=status_filter)


@api_router.get("/accounts/{account_id}", response_model=AccountResponse, tags=["accounts"])
def get_account(
    account_id: UUID,
    service: Annotated[ApiQueryService, Depends(query_service)],
) -> AccountResponse:
    account = service.get_account(account_id)
    if account is None:
        raise _not_found("account", account_id)
    return account


@api_router.get(
    "/accounts/{account_id}/wallets",
    response_model=list[WalletResponse],
    tags=["accounts"],
)
def list_account_wallets(
    account_id: UUID,
    service: Annotated[ApiQueryService, Depends(query_service)],
) -> list[WalletResponse]:
    wallets = service.list_wallets(account_id)
    if wallets is None:
        raise _not_found("account", account_id)
    return wallets


@api_router.get("/banks", response_model=PaginatedResponse[BankResponse], tags=["banks"])
def list_banks(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> PaginatedResponse[BankResponse]:
    return service.list_banks(page_request, status=status_filter)


@api_router.get(
    "/instruments/execution",
    response_model=PaginatedResponse[ExecutionInstrumentResponse],
    tags=["instruments"],
)
def list_execution_instruments(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> PaginatedResponse[ExecutionInstrumentResponse]:
    return service.list_execution_instruments(page_request, status=status_filter)


@api_router.get(
    "/prices/latest",
    response_model=PaginatedResponse[PriceQuoteResponse],
    tags=["prices"],
)
def list_latest_prices(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
    bank_instrument_id: UUID | None = None,
) -> PaginatedResponse[PriceQuoteResponse]:
    return service.list_latest_prices(page_request, bank_instrument_id=bank_instrument_id)


@api_router.get(
    "/indicators/latest",
    response_model=PaginatedResponse[IndicatorSnapshotResponse],
    tags=["indicators"],
)
def list_latest_indicators(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
    instrument_type: str | None = None,
    instrument_id: UUID | None = None,
    timeframe: str | None = None,
    indicator_name: str | None = None,
) -> PaginatedResponse[IndicatorSnapshotResponse]:
    return service.list_latest_indicators(
        page_request,
        instrument_type=instrument_type,
        instrument_id=instrument_id,
        timeframe=timeframe,
        indicator_name=indicator_name,
    )


@api_router.get(
    "/regimes/latest",
    response_model=PaginatedResponse[MarketRegimeSnapshotResponse],
    tags=["regimes"],
)
def list_latest_regimes(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
    instrument_type: str | None = None,
    instrument_id: UUID | None = None,
    timeframe: str | None = None,
) -> PaginatedResponse[MarketRegimeSnapshotResponse]:
    return service.list_latest_regimes(
        page_request,
        instrument_type=instrument_type,
        instrument_id=instrument_id,
        timeframe=timeframe,
    )


@api_router.get("/trades", response_model=PaginatedResponse[PaperTradeResponse], tags=["trades"])
def list_trades(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
    account_id: UUID | None = None,
) -> PaginatedResponse[PaperTradeResponse]:
    return service.list_trades(page_request, account_id=account_id)


@api_router.get(
    "/positions",
    response_model=PaginatedResponse[PositionResponse],
    tags=["positions"],
)
def list_positions(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
    account_id: UUID | None = None,
) -> PaginatedResponse[PositionResponse]:
    return service.list_positions(page_request, account_id=account_id)


@api_router.get(
    "/backtests",
    response_model=PaginatedResponse[BacktestRunSummaryResponse],
    tags=["backtests"],
)
def list_backtests(
    service: Annotated[ApiQueryService, Depends(query_service)],
    page_request: Annotated[Pagination, Depends(pagination)],
) -> PaginatedResponse[BacktestRunSummaryResponse]:
    return service.list_backtests(page_request)


@api_router.get("/backtests/{run_id}", response_model=BacktestRunResponse, tags=["backtests"])
def get_backtest(
    run_id: UUID,
    service: Annotated[ApiQueryService, Depends(query_service)],
) -> BacktestRunResponse:
    run = service.get_backtest(run_id)
    if run is None:
        raise _not_found("backtest", run_id)
    return run


@api_router.get(
    "/reports/backtests/{run_id}",
    response_model=ReportResponse,
    tags=["reports"],
)
def get_backtest_report(
    run_id: UUID,
    service: Annotated[ApiQueryService, Depends(query_service)],
) -> ReportResponse:
    report = service.get_backtest_report(run_id)
    if report is None:
        raise _not_found("backtest", run_id)
    return report


def _not_found(resource: str, resource_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "not_found",
            "message": f"{resource} not found",
            "details": {"id": str(resource_id)},
        },
    )
