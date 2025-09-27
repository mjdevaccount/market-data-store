"""
Pydantic data models for Market Data Store Client.

All models include tenant isolation and validation.
"""

from pydantic import BaseModel, validator
from datetime import datetime, date
from typing import Optional


class Bar(BaseModel):
    """OHLCV bar data with tenant isolation."""

    tenant_id: str
    vendor: str
    symbol: str
    timeframe: str
    ts: datetime
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    volume: Optional[int] = None
    id: Optional[str] = None  # uuid string, not unique globally

    @validator("symbol")
    def _upcase(cls, v):
        return v.upper()

    @validator("timeframe")
    def _validate_timeframe(cls, v):
        valid_timeframes = {"1s", "1m", "5m", "15m", "1h", "4h", "1d"}
        if v not in valid_timeframes:
            raise ValueError(f"Invalid timeframe: {v}. Must be one of {valid_timeframes}")
        return v


class Fundamentals(BaseModel):
    """Financial fundamentals data with tenant isolation."""

    tenant_id: str
    vendor: str
    symbol: str
    asof: datetime
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    id: Optional[str] = None

    @validator("symbol")
    def _upcase(cls, v):
        return v.upper()


class News(BaseModel):
    """Market news with sentiment analysis and tenant isolation."""

    tenant_id: str
    vendor: str
    published_at: datetime
    id: Optional[str] = None
    symbol: Optional[str] = None
    title: str
    url: Optional[str] = None
    sentiment_score: Optional[float] = None

    @validator("symbol")
    def _upcase_symbol(cls, v):
        if v is not None:
            return v.upper()
        return v

    @validator("sentiment_score")
    def _validate_sentiment(cls, v):
        if v is not None and not (-1.0 <= v <= 1.0):
            raise ValueError("Sentiment score must be between -1.0 and 1.0")
        return v


class OptionSnap(BaseModel):
    """Options chain snapshot with tenant isolation."""

    tenant_id: str
    vendor: str
    symbol: str
    expiry: date
    option_type: str  # 'C' or 'P'
    strike: float
    ts: datetime
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    oi: Optional[int] = None
    volume: Optional[int] = None
    spot: Optional[float] = None
    id: Optional[str] = None

    @validator("symbol")
    def _upcase(cls, v):
        return v.upper()

    @validator("option_type")
    def _validate_option_type(cls, v):
        if v not in {"C", "P"}:
            raise ValueError("Option type must be 'C' or 'P'")
        return v.upper()

    @validator("strike")
    def _validate_strike(cls, v):
        if v <= 0:
            raise ValueError("Strike price must be positive")
        return v


class LatestPrice(BaseModel):
    """Latest price snapshot for hot cache."""

    tenant_id: str
    vendor: str
    symbol: str
    price: float
    price_timestamp: datetime

    @validator("symbol")
    def _upcase(cls, v):
        return v.upper()
