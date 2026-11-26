"""Contract tests independent of Home Assistant and a real Tauron account."""
import importlib.util
from pathlib import Path
import unittest
from datetime import date

path = Path(__file__).parents[1] / "custom_components/tauron_virtual_meter/profile.py"
spec = importlib.util.spec_from_file_location("profile_model", path)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def response(values):
    return {"success": True, "data": {"values": values}}


class ProfileTests(unittest.TestCase):
    def test_decimal_and_missing_values(self):
        parsed = model.parse_day(date(2026, 11, 20), response(["0.1", None, "0,2"] + [0] * 21))
        self.assertEqual(len(parsed), 23)
        stats = model.cumulative_statistics({"day": parsed})
        self.assertEqual(stats[-1]["sum"], 0.3)

    def test_corrections_recalculate_later_sums(self):
        first = model.parse_day(date(2026, 11, 20), response([1] * 24))
        second = model.parse_day(date(2026, 11, 21), response([2] * 24))
        profiles = {"first": first, "second": second}
        self.assertEqual(model.cumulative_statistics(profiles)[-1]["sum"], 72)
        first[next(iter(first))] = "3"
        self.assertEqual(model.cumulative_statistics(profiles)[-1]["sum"], 74)
        self.assertEqual(model.cumulative_statistics(profiles), model.cumulative_statistics(profiles))

    def test_spring_dst_23_hours(self):
        parsed = model.parse_day(date(2026, 3, 29), response([1] * 23))
        self.assertEqual(len(parsed), 23)
        self.assertEqual(len(set(parsed)), 23)

    def test_autumn_dst_25_hours(self):
        parsed = model.parse_day(date(2026, 10, 25), response([1] * 25))
        self.assertEqual(len(parsed), 25)
        self.assertEqual(len(set(parsed)), 25)

    def test_ambiguous_dst_is_not_guessed(self):
        for day in (date(2026, 3, 29), date(2026, 10, 25)):
            with self.assertRaises(model.ProfileError):
                model.parse_day(day, response([1] * 24))

    def test_sparse_rows_keep_actual_hours(self):
        parsed = model.parse_day(date(2026, 11, 20), {"data": {"allData": [
            {"Hour": 1, "EC": "1"}, {"Hour": 5, "EC": "2"}
        ]}})
        stamps = list(parsed)
        self.assertEqual((model.datetime.fromisoformat(stamps[1]) - model.datetime.fromisoformat(stamps[0])).total_seconds(), 14400)

    def test_duplicates_are_rejected(self):
        with self.assertRaises(model.ProfileError):
            model.parse_day(date(2026, 11, 20), {"data": {"allData": [
                {"Hour": 1, "EC": "1"}, {"Hour": 1, "EC": "2"}
            ]}})

    def test_values_fallback_when_all_data_is_empty(self):
        parsed = model.parse_day(date(2026, 11, 20), {"data": {"allData": [], "values": [1] * 24}})
        self.assertEqual(len(parsed), 24)

    def test_null_status_is_not_fabricated_energy(self):
        parsed = model.parse_day(date(2026, 11, 20), {"data": {"allData": [
            {"Hour": 1, "EC": "1", "Status": None},
            {"Hour": 2, "EC": "2", "Status": "0"},
        ]}})
        self.assertEqual(len(parsed), 1)

    def test_dst_explicit_wall_hours_keep_both_autumn_intervals(self):
        day = date(2026, 10, 25)
        hours = model.day_hours(day)
        rows = [{"Hour": stamp.astimezone(model.WARSAW).hour + 1, "EC": "1"} for stamp in hours]
        self.assertEqual(len(model.parse_day(day, {"data": {"allData": rows}})), 25)

    def test_invalid_energy_is_not_zero(self):
        for raw in ("NaN", "Infinity", "-1", "abc"):
            with self.assertRaises(model.ProfileError):
                model.energy(raw)

    def test_quarter_hour_profile_is_preserved_for_later_support(self):
        with self.assertRaises(model.ProfileError):
            model.parse_day(date(2026, 11, 20), response([1] * 96))


if __name__ == "__main__":
    unittest.main()
