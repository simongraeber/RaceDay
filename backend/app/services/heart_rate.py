import math


def usable_heart_rate(average: float | None, peak: float | None) -> bool:
    return (
        isinstance(average, (int, float))
        and isinstance(peak, (int, float))
        and math.isfinite(average)
        and math.isfinite(peak)
        and 60 <= average <= peak <= 230
        and peak >= 80
    )
