from sqlmodel import Field

from solbot_common.models.base import Base


class TokenInfo(Base, table=True):
    __tablename__ = "token_info"  # type: ignore

    mint: str = Field(nullable=False, index=True, unique=True)
    token_name: str = Field(nullable=False)
    symbol: str = Field(nullable=False)
    decimals: int = Field(nullable=False)
    token_program: str = Field(nullable=False)
