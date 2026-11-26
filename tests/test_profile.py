"""Contract tests independent of Home Assistant and a real Tauron account."""
import importlib.util
import json
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
    def test_empty_month_summary_requires_daily_null_slots(self):
        for count in (29, 30):
            raw = {"success": True, "data": {"values": [None]*count, "sum": 0, "allData": []}}
            self.assertEqual(model.month_summary_status(date(2024, 9, 1), raw), "empty")

    def test_zero_measurements_are_available_not_empty(self):
        raw = {"success": True, "data": {"values": [0]*30, "sum": 0}}
        self.assertEqual(model.month_summary_status(date(2024, 9, 1), raw), "available")

    def test_month_sum_zero_alone_does_not_prove_absence(self):
        for values in ([], [None]*24, [False]*30, None):
            raw = {"success": True, "data": {"values": values, "sum": 0}}
            self.assertEqual(model.month_summary_status(date(2024, 9, 1), raw), "unknown")

    def test_month_positive_sum_contradicts_empty_array(self):
        raw = {"success": True, "data": {"values": [None]*30, "sum": 2.5}}
        self.assertEqual(model.month_summary_status(date(2024, 9, 1), raw), "unknown")

    def test_failed_or_unrecognized_month_response_is_not_empty(self):
        for raw in ({"success": False}, {"success": True, "data": []}, [],
                    {"success": True, "data": {"values": [None]*30, "allData": {}}}):
            self.assertEqual(model.month_summary_status(date(2024, 9, 1), raw), "unknown")

    def test_monthly_rows_with_zero_energy_prevent_skipping(self):
        raw = {"success": True, "data": {"values": [None]*30, "sum": 0, "allData": [{"EC": "0"}]}}
        self.assertEqual(model.month_summary_status(date(2024, 9, 1), raw), "available")

    def test_leap_february_month_summary(self):
        raw = {"success": True, "data": {"values": [None]*29}}
        self.assertEqual(model.month_summary_status(date(2024, 2, 1), raw), "empty")

    def test_tauron_empty_day_with_23_nulls_and_24_labels_is_missing_not_zero(self):
        raw = json.loads((Path(__file__).parent / "fixtures/empty_profile.json").read_text())
        parsed = model.parse_day(date(2024, 9, 7), raw)
        self.assertEqual(parsed, {})
        self.assertEqual(model.cumulative_statistics({"2024-09-07": parsed}), [])

    def test_23_values_with_a_real_reading_on_normal_day_still_need_resolution(self):
        raw = response([None]*22 + ["0.1"])
        with self.assertRaises(model.ProfileError):
            model.parse_day(date(2024, 9, 7), raw)

    def test_daily_request_date_takes_precedence_over_tauron_row_date(self):
        day = date(2026, 11, 20)
        for source_date in ("20.11.2026", "2026-11-20 00:00:00", "1999-01-01", ""):
            raw = {"data": {"allData": [{"Date": source_date, "Hour": "1", "EC": "0.45", "Status": "0"}]}}
            parsed = model.parse_day(day, raw)
            self.assertEqual(parsed, {model.day_hours(day)[0].isoformat(): "0.45"})
            self.assertEqual(raw["data"]["allData"][0]["Date"], source_date)

    def test_correcting_row_date_does_not_weaken_hour_validation(self):
        raw = {"data": {"allData": [
            {"Date": "1999-01-01", "Hour": "1", "EC": "0.45"},
            {"Date": "1999-01-01", "Hour": "1", "EC": "0.45"},
        ]}}
        with self.assertRaises(model.ProfileError):
            model.parse_day(date(2026, 11, 20), raw)

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
