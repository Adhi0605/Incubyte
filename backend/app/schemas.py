import re
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class VehicleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    make: Text
    model: Text
    category: Text
    price: Decimal = Field(ge=0, le=1000000000, max_digits=12, decimal_places=2, allow_inf_nan=False)
    quantity: int = Field(ge=0, le=1000000, strict=True)


class Restock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(gt=0, le=1000000, strict=True)
