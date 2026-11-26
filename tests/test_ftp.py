import unittest

from stravastat.ftp import (
    PowerSeries,
    best_average_power,
    estimate_ftp_candidates,
    normalized_power,
    recommend_ftp,
    resample_to_seconds,
    round_to_5,
)
from stravastat.job import matches_mowl


def constant_series(watts: float, seconds: int) -> PowerSeries:
    return PowerSeries(watts=[watts] * seconds)


class TestResample(unittest.TestCase):
    def test_interpolates_sparse_samples(self):
        times = [0, 10, 20]
        values = [100.0, 200.0, 300.0]
        grid = resample_to_seconds(times, values)
        self.assertEqual(len(grid), 21)
        self.assertEqual(grid[0], 100.0)
        self.assertEqual(grid[5], 150.0)
        self.assertEqual(grid[10], 200.0)
        self.assertEqual(grid[15], 250.0)
        self.assertEqual(grid[20], 300.0)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            resample_to_seconds([0], [1.0])


class TestBestAveragePower(unittest.TestCase):
    def test_constant(self):
        series = constant_series(200, 1200)
        best = best_average_power(series, 1200)
        self.assertEqual(best, (200.0, 0))

    def test_picks_peak_window(self):
        watts = [100.0] * 600 + [300.0] * 600 + [100.0] * 600
        series = PowerSeries(watts=watts)
        best = best_average_power(series, 300)
        self.assertAlmostEqual(best[0], 300.0)
        self.assertEqual(best[1], 600)

    def test_shorter_than_window(self):
        self.assertIsNone(best_average_power(constant_series(200, 100), 300))


class TestNormalizedPower(unittest.TestCase):
    def test_constant_is_average(self):
        np = normalized_power(constant_series(200, 600))
        self.assertAlmostEqual(np, 200.0, places=6)

    def test_oscillating_is_above_average(self):
        watts = ([100.0] * 30 + [300.0] * 30) * 20
        np = normalized_power(PowerSeries(watts=watts))
        self.assertGreater(np, 200.0)
        self.assertLess(np, 300.0)


class TestEstimateFtp(unittest.TestCase):
    def test_best_20min(self):
        candidates = estimate_ftp_candidates(constant_series(200, 1800))
        methods = [c.method for c in candidates]
        self.assertEqual(len(candidates), 1)
        self.assertIn("20-min", methods[0])
        self.assertAlmostEqual(candidates[0].ftp_watts, 190.0)

    def test_60min_effort_adds_candidate(self):
        candidates = estimate_ftp_candidates(constant_series(200, 60 * 60))
        self.assertEqual(len(candidates), 2)
        by_method = {c.method: c for c in candidates}
        self.assertAlmostEqual(by_method["best 60-min power"].ftp_watts, 200.0)
        self.assertAlmostEqual(by_method["best 20-min power x 0.95"].ftp_watts, 190.0)

    def test_recommendation_rounds_to_5(self):
        candidates = estimate_ftp_candidates(constant_series(203, 1800))
        rec = recommend_ftp(candidates)
        self.assertEqual(rec.ftp_watts, 195)
        self.assertEqual(rec.ftp_watts % 5, 0)

    def test_recommendation_empty(self):
        self.assertIsNone(recommend_ftp([]))


class TestRoundTo5(unittest.TestCase):
    def test_rounding(self):
        self.assertEqual(round_to_5(232.4), 230)
        self.assertEqual(round_to_5(233.0), 235)


class TestMatchesMowl(unittest.TestCase):
    def test_name_match(self):
        self.assertEqual(matches_mowl({"name": "MOWL Power 45", "type": "Ride"}, "MOWL"), "name")

    def test_trainer_ride_match(self):
        self.assertEqual(
            matches_mowl({"name": "Spinning", "type": "Ride", "trainer": True}, "MOWL"),
            "indoor ride",
        )

    def test_outdoor_ride_no_match(self):
        self.assertIsNone(
            matches_mowl({"name": "Sunday spin", "type": "Ride", "trainer": False}, "MOWL")
        )

    def test_case_insensitive(self):
        self.assertEqual(matches_mowl({"name": "mowl endurance"}, "MOWL"), "name")


if __name__ == "__main__":
    unittest.main()
