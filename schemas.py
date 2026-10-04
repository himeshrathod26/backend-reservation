from pydantic import BaseModel, Field, field_validator
from typing import Literal

class ShowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    seats: list[str] = Field(min_length=1, max_length=10000)
    price_paise: int = Field(ge=0)
    per_user_limit: int = Field(default=4, ge=1)

    @field_validator("seats")
    @classmethod
    def unique_seats(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("seats must be unique")
        return v

class ReserveRequest(BaseModel):
    seats: list[str] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=200)

    @field_validator("seats")
    @classmethod
    def unique_seats(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("seats must be unique")
        return v
