"""Model time as people read it: elapsed hours, or the date and time.

ANUGA stores each timestep's time in seconds from the ``starttime`` global
attribute, which is seconds since 1970-01-01 UTC, and names the time zone
results are reported in with the ``timezone`` attribute.  Most runs leave
``starttime`` at 0, and their times are shown as time elapsed; a run whose
``starttime`` is a real date is also shown with the date and time.
"""

import datetime

# A starttime later than this (1973-03-03) is taken to be a date; smaller
# ones are offsets that happen to be non-zero.
DATED_AFTER = 1e8

# Runs no longer than this (s) are labelled in seconds, and charted in
# seconds; up to HOURS_AFTER in minutes; longer ones in hours.
SECONDS_UP_TO = 600.0
HOURS_AFTER = 3 * 3600.0


def _text(value):
    if isinstance(value, bytes):
        value = value.decode()
    return str(value).strip() if value is not None else ''


def _zone(name):
    """A tzinfo for a timezone attribute: an IANA name ("Europe/Rome"), "UTC",
    or a fixed offset ("+10:00", "UTC+10"); UTC when it cannot be read."""
    name = name or 'UTC'
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        pass
    offset = name.upper().replace('UTC', '').replace('GMT', '').strip()
    if offset:
        try:
            sign = -1 if offset[0] == '-' else 1
            hours, _, minutes = offset.lstrip('+-').partition(':')
            delta = datetime.timedelta(hours=int(hours), minutes=int(minutes or 0))
            return datetime.timezone(sign * delta, name)
        except ValueError:
            pass
    return datetime.timezone.utc


def elapsed(seconds, end):
    """Time since the start, in a style that suits a run lasting end s."""
    if end <= SECONDS_UP_TO:
        return '%.1f s' % seconds
    # Hours run past 24, to match hydrographs plotted in hours.
    seconds = int(round(seconds))
    return '%d:%02d:%02d' % (seconds // 3600, seconds % 3600 // 60, seconds % 60)


class Clock(object):
    """Labels and chart axes for the times of an .sww file."""

    def __init__(self, times, attrs):
        self.times = times
        self.end = float(times[-1]) if len(times) else 0.0
        try:
            self.starttime = float(attrs.get('starttime', 0.0))
        except (TypeError, ValueError):
            self.starttime = 0.0
        self.dated = self.starttime > DATED_AFTER
        self.zone = _zone(_text(attrs.get('timezone')))

    def datetime(self, index):
        """The date and time of a timestep, in the file's time zone, or None."""
        if not self.dated:
            return None
        seconds = self.starttime + float(self.times[index])
        return datetime.datetime.fromtimestamp(seconds, self.zone)

    def label(self, index):
        """e.g. "38:00:00", or "2024-05-17 16:00:00 CEST (+38:00:00)"."""
        since = elapsed(float(self.times[index]), self.end)
        when = self.datetime(index)
        if when is None:
            return since
        return '%s (+%s)' % (when.strftime('%Y-%m-%d %H:%M:%S %Z').strip(), since)

    def axis(self):
        """(values, title) for a chart's time axis: dates and times when the
        run is dated, else elapsed time in seconds, minutes or hours."""
        if self.dated:
            # As text, which plotly reads as dates and which goes as JSON.
            values = [self.datetime(i).strftime('%Y-%m-%d %H:%M:%S')
                      for i in range(len(self.times))]
            name = self.datetime(0).strftime('%Z') if len(self.times) else ''
            return values, 'Time (%s)' % name if name else 'Time'
        if self.end <= SECONDS_UP_TO:
            return list(self.times), 'Time (s)'
        if self.end <= HOURS_AFTER:
            return [t / 60.0 for t in self.times], 'Time (min)'
        return [t / 3600.0 for t in self.times], 'Time (h)'

    def axis_value(self, index):
        """The chart axis value of a timestep."""
        return self.axis()[0][index]
