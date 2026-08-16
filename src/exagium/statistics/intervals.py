from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist


@dataclass(frozen=True, slots=True)
class WilsonInterval:
    """以 0 到 1 比例表示的 Wilson 二项比例区间。"""

    lower: float
    upper: float
    confidence_level: float


def wilson_interval(
    successes: int,
    total: int,
    *,
    confidence_level: float = 0.95,
) -> WilsonInterval | None:
    """计算 Wilson score interval；没有可评估样本时返回空值。"""

    if isinstance(successes, bool) or isinstance(total, bool):
        raise TypeError("successes and total must be integers")
    if not isinstance(successes, int) or not isinstance(total, int):
        raise TypeError("successes and total must be integers")
    if total < 0:
        raise ValueError("total must be non-negative")
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between zero and one")
    if total == 0:
        return None

    z = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    observed = successes / total
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = (observed + z_squared / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            observed * (1 - observed) / total + z_squared / (4 * total * total)
        )
        / denominator
    )
    return WilsonInterval(
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
        confidence_level=confidence_level,
    )
