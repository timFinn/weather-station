"""Tests for the History data aggregation classes."""
import time

from weatherhat.history import History, HistoryEntry, WindDirectionHistory, WindSpeedHistory, wind_degrees_to_cardinal, wind_degrees_to_short_cardinal


class TestHistoryEntry:
    def test_stores_value_and_timestamp(self):
        entry = HistoryEntry(42.0, timestamp=1000.0)
        assert entry.value == 42.0
        assert entry.timestamp == 1000.0

    def test_auto_timestamp(self):
        before = time.time()
        entry = HistoryEntry(10.0)
        after = time.time()
        assert before <= entry.timestamp <= after


class TestHistory:
    def test_append_and_latest(self):
        h = History()
        h.append(1.0)
        h.append(2.0)
        assert h.latest().value == 2.0

    def test_average(self):
        h = History()
        for v in [10.0, 20.0, 30.0]:
            h.append(v)
        assert h.average() == 20.0

    def test_average_empty(self):
        h = History()
        assert h.average() == 0

    def test_min_max(self):
        h = History()
        for v in [5.0, 1.0, 9.0, 3.0]:
            h.append(v)
        assert h.min().value == 1.0
        assert h.max().value == 9.0

    def test_median(self):
        h = History()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            h.append(v)
        assert h.median() == 3.0

    def test_total(self):
        h = History()
        for v in [1.0, 2.0, 3.0]:
            h.append(v)
        assert h.total() == 6.0

    def test_history_depth_limit(self):
        h = History(history_depth=3)
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            h.append(v)
        values = [e.value for e in h.history()]
        assert values == [3.0, 4.0, 5.0]

    def test_history_with_sample_depth(self):
        h = History()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            h.append(v)
        last_two = h.history(2)
        assert [e.value for e in last_two] == [4.0, 5.0]

    def test_average_with_sample_over(self):
        h = History()
        for v in [10.0, 20.0, 30.0, 40.0]:
            h.append(v)
        assert h.average(2) == 35.0  # avg of last 2: (30+40)/2

    def test_timespan(self):
        h = History()
        h.append(1.0, timestamp=100.0)
        h.append(2.0, timestamp=200.0)
        start, end = h.timespan()
        assert start == 100.0
        assert end == 200.0


class TestWindSpeedHistory:
    def test_ms_to_kmph(self):
        h = WindSpeedHistory()
        assert h.ms_to_kmph(1.0) == 3.6

    def test_ms_to_mph(self):
        h = WindSpeedHistory()
        result = h.ms_to_mph(1.0)
        assert abs(result - 2.236936) < 0.001

    def test_latest_kmph(self):
        h = WindSpeedHistory()
        h.append(10.0)
        assert h.latest_kmph() == 36.0

    def test_latest_mph(self):
        h = WindSpeedHistory()
        h.append(10.0)
        assert abs(h.latest_mph() - 22.36936) < 0.01

    def test_average_kmph(self):
        h = WindSpeedHistory()
        h.append(5.0)
        h.append(15.0)
        assert h.average_kmph() == 36.0  # avg 10 m/s = 36 km/h

    def test_average_mph(self):
        h = WindSpeedHistory()
        h.append(5.0)
        h.append(15.0)
        assert abs(h.average_mph() - 22.36936) < 0.01

    def test_gust(self):
        h = WindSpeedHistory()
        now = time.time()
        h.append(5.0, timestamp=now - 10)  # old, outside 3s window
        h.append(20.0, timestamp=now - 1)  # within 3s
        h.append(8.0, timestamp=now)       # within 3s
        assert h.gust(seconds=3.0) == 20.0

    def test_gust_empty(self):
        h = WindSpeedHistory()
        assert h.gust() == 0

    def test_gust_kmph(self):
        h = WindSpeedHistory()
        now = time.time()
        h.append(10.0, timestamp=now)
        assert h.gust_kmph(seconds=3.0) == 36.0

    def test_gust_mph(self):
        h = WindSpeedHistory()
        now = time.time()
        h.append(10.0, timestamp=now)
        assert abs(h.gust_mph(seconds=3.0) - 22.36936) < 0.01


class TestWindDirectionHistory:
    def test_degrees_to_cardinal(self):
        h = WindDirectionHistory()
        assert h.degrees_to_cardinal(0) == "North"
        assert h.degrees_to_cardinal(90) == "East"
        assert h.degrees_to_cardinal(180) == "South"
        assert h.degrees_to_cardinal(270) == "West"

    def test_degrees_to_short_cardinal(self):
        h = WindDirectionHistory()
        assert h.degrees_to_short_cardinal(0) == "N"
        assert h.degrees_to_short_cardinal(45) == "NE"
        assert h.degrees_to_short_cardinal(180) == "S"

    def test_average_compass(self):
        h = WindDirectionHistory()
        h.append(0)
        h.append(90)
        assert h.average_compass() == "North East"

    def test_average_short_compass(self):
        h = WindDirectionHistory()
        h.append(0)
        h.append(90)
        assert h.average_short_compass() == "NE"

    def test_latest_compass(self):
        h = WindDirectionHistory()
        h.append(180)
        assert h.latest_compass() == "South"

    def test_latest_short_compass(self):
        h = WindDirectionHistory()
        h.append(270)
        assert h.latest_short_compass() == "W"

    def test_history_compass(self):
        h = WindDirectionHistory()
        h.append(0)
        h.append(90)
        result = h.history_compass()
        assert [e.value for e in result] == ["North", "East"]

    def test_history_short_compass(self):
        h = WindDirectionHistory()
        h.append(0)
        h.append(90)
        result = h.history_short_compass()
        assert [e.value for e in result] == ["N", "E"]


class TestCardinalMappings:
    def test_cardinal_has_eight_directions(self):
        assert len(wind_degrees_to_cardinal) == 8

    def test_short_cardinal_has_eight_directions(self):
        assert len(wind_degrees_to_short_cardinal) == 8

    def test_all_degrees_covered(self):
        expected = {0, 45, 90, 135, 180, 225, 270, 315}
        assert set(wind_degrees_to_cardinal.keys()) == expected
        assert set(wind_degrees_to_short_cardinal.keys()) == expected
