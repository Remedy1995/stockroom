from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Credentials(StrictModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        return v.lower()

    @field_validator('password', mode='before')
    @classmethod
    def preserve_password(cls, v):
        return v

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)


class Registration(Credentials):
    name: str = Field(min_length=2, max_length=80)
    workspace: str = Field(min_length=2, max_length=80)

    @field_validator('name', 'workspace')
    @classmethod
    def nonblank(cls, v):
        if len(v.strip()) < 2:
            raise ValueError('Must contain at least two visible characters')
        return v.strip()


class MemberCreate(Credentials):
    name: str = Field(min_length=2, max_length=80)
    role: Literal['editor', 'viewer']


class PasswordChange(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class EmailVerification(StrictModel):
    token: str = Field(min_length=32, max_length=256)


class PasswordResetRequest(StrictModel):
    email: EmailStr

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        return v.lower()


class PasswordReset(EmailVerification):
    new_password: str = Field(min_length=12, max_length=128)


class ProductCreate(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    sku: str = Field(min_length=2, max_length=40, pattern=r'^[a-zA-Z0-9_-]+$')
    category: str = Field(min_length=2, max_length=40)
    description: str = Field(default='', max_length=2000)
    quantity: int = Field(default=0, ge=0, le=1000000, strict=True)
    price_cents: int = Field(default=0, ge=0, le=100000000, strict=True)
    reorder_point: int = Field(default=10, ge=0, le=1000000, strict=True)

    @field_validator('sku')
    @classmethod
    def uppercase_sku(cls, v):
        return v.upper()


class ProductUpdate(ProductCreate):
    version: int = Field(ge=1, strict=True)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    role: str
    workspace_id: str
    is_email_verified: bool


class ProductOut(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    created_at: int
    updated_at: int
    status: str
