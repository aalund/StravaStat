"""Power-based FTP estimation from indoor cycling (MOWL) sessions.

Methods
-------
- Best 20-minute average power x 0.95 (classic Coggan estimate).
- Best 60-minute average power used directly when a >=55 min effort exists.

The recommended FTP is the highest defensible candidate, rounded to the
nearest 5 W.
"""

from __future__ import annotations

from dataclasses import dataclass

FTP_20MIN_FACTOR = 0.95
MIN_60MIN_EFFORT_SECONDS = 55 * 60


@dataclass
class PowerSeries:
    """Per-second power samples in watts."""

    watts: list[float]

    def __post_init__(self) -> None:
        if not self.watts:
            raise ValueError("empty power series")


def resample_to_seconds(
    times: list[float], values: list[float]
) -> list[float]:
    """Resample sparse samples onto a uniform 1-second grid.

    Linear interpolation between samples; the first and last sample are held
    constant outside their range. Requires strictly increasing ``times``.
    """
    if len(times) != len(values) or len(times) < 2:
        raise ValueError("need equally matched times/values with >= 2 samples")
    duration = int(times[-1]) - int(times[0])
    if duration <= 0:
        raise ValueError("non-increasing timestamps")
    grid: list[float] = []
    start = int(times[0])
    j = 0
    for second in range(duration + 1):
        t = start + second
        while j < len(times) - 2 and times[j + 1] < t:
            j += 1
        t0, t1 = times[j], times[j + 1]
        v0, v1 = values[j], values[j + 1]
        if t1 == t0:
            grid.append(v1)
        else:
            frac = (t - t0) / (t1 - t0)
            grid.append(v0 + frac * (v1 - v0))
    return grid


def _prefix_sums(values: list[float]) -> list[float]:
    sums = [0.0]
    for v in values:
        sums.append(sums[-1] + v)
    return sums


def best_average_power(series: PowerSeries, window_seconds: int) -> tuple[float, int] | None:
    """Best rolling average power over ``window_seconds``.

    Returns ``(average_watts, start_index)`` or ``None`` when the series is
    shorter than the window.
    """
    watts = series.watts
    if len(watts) < window_seconds:
        return None
    sums = _prefix_sums(watts)
    best_avg = -1.0
    best_start = 0
    for start in range(len(watts) - window_seconds + 1):
        avg = (sums[start + window_seconds] - sums[start]) / window_seconds
        if avg > best_avg:
            best_avg = avg
            best_start = start
    return best_avg, best_start


def normalized_power(series: PowerSeries, window_seconds: int = 30) -> float | None:
    """Coggan Normalized Power (30 s rolling average, quartic mean)."""
    watts = series.watts
    if len(watts) < window_seconds:
        return None
    sums = _prefix_sums(watts)
    rolling: list[float] = []
    for start in range(len(watts) - window_seconds + 1):
        rolling.append((sums[start + window_seconds] - sums[start]) / window_seconds)
    mean_quartic = sum(v**4 for v in rolling) / len(rolling)
    return mean_quartic**0.25


def round_to_5(watts: float) -> int:
    return int(round(watts / 5.0) * 5)


@dataclass
class FtpCandidate:
    ftp_watts: float
    method: str
    source_value: float


def estimate_ftp_candidates(
    series: PowerSeries,
) -> list[FtpCandidate]:
    """All defensible FTP estimates for one power series."""
    candidates: list[FtpCandidate] = []
    best20 = best_average_power(series, 20 * 60)
    if best20 is not None:
        candidates.append(
            FtpCandidate(
                ftp_watts=best20[0] * FTP_20MIN_FACTOR,
                method="best 20-min power x 0.95",
                source_value=best20[0],
            )
        )
    if len(series.watts) >= MIN_60MIN_EFFORT_SECONDS:
        best60 = best_average_power(series, 60 * 60)
        if best60 is not None:
            candidates.append(
                FtpCandidate(
                    ftp_watts=best60[0],
                    method="best 60-min power",
                    source_value=best60[0],
                )
            )
    return candidates


def recommend_ftp(
    candidates: list[FtpCandidate], round_to: int = 5
) -> FtpCandidate | None:
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c.ftp_watts)
    step = float(round_to)
    rounded_ftp = round(best.ftp_watts / step) * step
    return FtpCandidate(
        ftp_watts=rounded_ftp, method=best.method, source_value=best.source_value
    )
