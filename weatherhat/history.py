import time
from collections import deque

wind_degrees_to_cardinal = {
    0: "North",
    45: "North East",
    90: "East",
    135: "South East",
    180: "South",
    225: "South West",
    270: "West",
    315: "North West"
}

wind_degrees_to_short_cardinal = {
    0: "N",
    45: "NE",
    90: "E",
    135: "SE",
    180: "S",
    225: "SW",
    270: "W",
    315: "NW"
}


class HistoryEntry:
    __slots__ = 'value', 'timestamp'

    def __init__(self, value, timestamp=None):
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.value = value


class History:
    def __init__(self, history_depth=1200):
        # Use deque with maxlen for O(1) append with automatic pruning
        self._history = deque(maxlen=history_depth)
        self.history_depth = history_depth

    def append(self, value, timestamp=None):
        # deque with maxlen automatically prunes oldest entry when full
        self._history.append(HistoryEntry(value, timestamp=timestamp))

    def average(self, sample_over=None):
        history = self.history(sample_over)
        num_samples = len(history)
        if num_samples == 0:
            return 0
        # Use generator expression instead of list comprehension
        return sum(entry.value for entry in history) / float(num_samples)

    def timespan(self):
        return self._history[0].timestamp, self._history[-1].timestamp

    def min(self, sample_over=None):
        return min(self.history(sample_over), key=lambda entry: entry.value)

    def max(self, sample_over=None):
        return max(self.history(sample_over), key=lambda entry: entry.value)

    def median(self, sample_over=None):
        history = self.history(sample_over)
        median = int(len(history) / 2)
        return history[median].value

    def total(self, sample_over=None):
        history = self.history(sample_over)
        # Use generator expression instead of list comprehension
        return sum(entry.value for entry in history)

    def latest(self):
        return self._history[-1]

    def history(self, depth=None):
        if depth is None:
            return self._history
        depth = min(depth, len(self._history))
        # deque doesn't support slicing — convert to list for the slice
        return list(self._history)[-depth:]


class WindSpeedHistory(History):
    def ms_to_kmph(self, ms):
        """Convert meters/second to kilometers/hour."""
        return (ms * 60 * 60) / 1000.0

    def latest_kmph(self):
        return self.ms_to_kmph(self.latest().value)

    def average_kmph(self, sample_over=None):
        return self.ms_to_kmph(self.average(sample_over))

    def gust_kmph(self, seconds=3.0):
        """Wind gust in kilometers/hour."""
        return self.ms_to_kmph(self.gust(seconds))

    def ms_to_mph(self, ms):
        """Convert meters/second to miles/hour."""
        return ((ms * 60 * 60) / 1000.0) * 0.621371

    def latest_mph(self):
        return self.ms_to_mph(self.latest().value)

    def average_mph(self, sample_over=None):
        return self.ms_to_mph(self.average(sample_over))

    def gust_mph(self, seconds=3.0):
        """Wind gust in miles/hour."""
        return self.ms_to_mph(self.gust(seconds))

    def gust(self, seconds=3.0):
        """Wind gust in meters/second."""
        cut_off_time = time.time() - seconds
        # Use generator expression and handle empty case
        samples = (entry.value for entry in self._history if entry.timestamp >= cut_off_time)
        return max(samples, default=0)


class WindDirectionHistory(History):
    def degrees_to_cardinal(self, degrees):
        value, cardinal = min(wind_degrees_to_cardinal.items(), key=lambda item: abs(item[0] - degrees))
        return cardinal

    def degrees_to_short_cardinal(self, degrees):
        value, cardinal = min(wind_degrees_to_short_cardinal.items(), key=lambda item: abs(item[0] - degrees))
        return cardinal

    def average_compass(self, sample_over=None):
        return self.degrees_to_cardinal(self.average(sample_over))

    def average_short_compass(self, sample_over=None):
        return self.degrees_to_short_cardinal(self.average(sample_over))

    def latest_compass(self):
        return self.degrees_to_cardinal(self.latest().value)

    def latest_short_compass(self):
        return self.degrees_to_short_cardinal(self.latest().value)

    def history_compass(self, depth=None):
        return [HistoryEntry(self.degrees_to_cardinal(entry.value), timestamp=entry.timestamp) for entry in self.history(depth)]

    def history_short_compass(self, depth=None):
        return [HistoryEntry(self.degrees_to_short_cardinal(entry.value), timestamp=entry.timestamp) for entry in self.history(depth)]
