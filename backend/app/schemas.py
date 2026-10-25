import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address')
        return value


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


def https_url(value, local=False):
    if not value:
        return value
    if local and re.fullmatch(r'/cars/[A-Za-z0-9_.-]+', value):
        return value
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use an HTTPS URL')
    return value


class VehicleImage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(max_length=2000)
    alt: str = Field(default='Representative vehicle photo', max_length=200)
    credit: str = Field(default='', max_length=300)
    source_url: str = Field(default='', max_length=2000)
    license: str = Field(default='', max_length=100)

    @field_validator('url')
    @classmethod
    def safe_image(cls, value):
        return https_url(value, local=True)

    @field_validator('source_url')
    @classmethod
    def safe_source(cls, value):
        return https_url(value)


class VehicleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    make: Text
    model: Text
    category: Text
    price: Decimal = Field(ge=0, le=1000000000, max_digits=12, decimal_places=2, allow_inf_nan=False)
    quantity: int = Field(ge=0, le=1000000, strict=True)
    condition: Literal['new', 'used'] = 'new'
    year: int = Field(default=2025, ge=1990, le=date.today().year + 1, strict=True)
    trim: str = Field(default='', max_length=100)
    mileage_km: int = Field(default=0, ge=0, le=2000000, strict=True)
    fuel_type: Literal['Petrol', 'Diesel', 'Electric', 'Hybrid', 'CNG'] = 'Petrol'
    transmission: Literal['Manual', 'Automatic'] = 'Manual'
    color: str = Field(default='White', max_length=80)
    city: str = Field(default='Bengaluru', max_length=100)
    description: str = Field(default='', max_length=4000)
    info_url: str = Field(default='', max_length=2000)
    stock_number: str = Field(default='', max_length=80)
    vin: str = Field(default='', max_length=30)
    images: list[VehicleImage] = Field(default_factory=list, max_length=8)

    @field_validator('info_url')
    @classmethod
    def safe_info_url(cls, value):
        return https_url(value)

    @model_validator(mode='after')
    def used_car_is_individual(self):
        if self.condition == 'used' and self.quantity > 1:
            raise ValueError('A used listing represents one car; quantity must be 0 or 1')
        return self


class Restock(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quantity: int = Field(gt=0, le=1000000, strict=True)


class CSVImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    csv: str = Field(min_length=1, max_length=500000)
