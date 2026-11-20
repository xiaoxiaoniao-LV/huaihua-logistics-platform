"""撮合权重校验模型。"""
from pydantic import BaseModel, Field, field_validator

# 与 services.matching.DIMENSION_LABELS 保持一致的维度键
_KEYS = {
    "price_score", "credit_score", "window_score", "type_match",
    "rating_score", "hotness_score", "freshness_score", "preference_score",
}


class MatchWeightsIn(BaseModel):
    weights: dict[str, float] = Field(default_factory=dict)

    @field_validator("weights")
    @classmethod
    def _check(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = set(value) - _KEYS
        if unknown:
            raise ValueError(f"未知的权重维度：{', '.join(sorted(unknown))}")
        for key, weight in value.items():
            if not 0 <= float(weight) <= 5:
                raise ValueError(f"{key} 权重需在 0~5 之间")
        return value


class MatchWeightsOut(BaseModel):
    weights: dict[str, float]
    labels: dict[str, str]
    defaults: dict[str, float]
