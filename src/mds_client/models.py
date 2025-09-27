from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class _Base(BaseModel):
    class Config:
        frozen = True


class Bar(_Base):
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
    id: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        return v.upper()


class Fundamentals(_Base):
    tenant_id: str
    vendor: str
    symbol: str
    asof: datetime
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    id: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        return v.upper()


class News(_Base):
    tenant_id: str
    vendor: str
    published_at: datetime
    title: str
    id: Optional[str] = None
    symbol: Optional[str] = None
    url: Optional[str] = None
    sentiment_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v


class OptionSnap(_Base):
    tenant_id: str
    vendor: str
    symbol: str
    expiry: date
    option_type: str  # "C"|"P"
    strike: float
    ts: datetime
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    oi: Optional[int] = None
    volume: Optional[int] = None
    spot: Optional[float] = None
    id: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        return v.upper()


class LatestPrice(_Base):
    tenant_id: str
    vendor: str
    symbol: str
    price: float
    price_timestamp: datetime
