from typing import Literal

from pydantic import BaseModel, Field

type ComponentStatus = Literal["ok", "warning", "blocking", "unavailable", "unknown"]
type ReadinessStatus = Literal["ok", "blocking", "unavailable"]


class ComponentState(BaseModel):
    name: str
    status: ComponentStatus
    code: str
    summary: str
    blocking: bool = False
    details: dict[str, str | int | bool] = Field(default_factory=dict)


class SystemReadiness(BaseModel):
    status: ReadinessStatus
    trading_mode: Literal["paper"] = "paper"
    blocking: bool
    components: list[ComponentState]
