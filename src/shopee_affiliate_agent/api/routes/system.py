from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from shopee_affiliate_agent import __version__

router = APIRouter(prefix="/api/v1", tags=["system"])


class SystemStatus(BaseModel):
    status: Literal["operational"] = "operational"
    version: str
    automatic_publication: Literal["disabled"] = "disabled"
    human_approval: Literal["required"] = "required"


@router.get("/system/status", response_model=SystemStatus)
def system_status() -> SystemStatus:
    return SystemStatus(version=__version__)
