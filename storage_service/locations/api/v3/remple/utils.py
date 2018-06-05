import unicodedata
import datetime


def normalize(unistr):
    """Return a unistr using canonical decompositional normalization (NFD)."""
    try:
        return unicodedata.normalize('NFD', unistr)
    except TypeError:
        return unicodedata.normalize('NFD', unistr.decode('utf8'))
    except UnicodeDecodeError:
        return unistr


def round_datetime(dt):
    """Round a datetime to the nearest second."""
    discard = datetime.timedelta(microseconds=dt.microsecond)
    dt -= discard
    if discard >= datetime.timedelta(microseconds=500000):
        dt += datetime.timedelta(seconds=1)
    return dt


def datetime_string2datetime(datetime_string):
    """Parse an ISO 8601-formatted datetime into a Python datetime object.
    Cf. http://stackoverflow.com/questions/531157/\
        parsing-datetime-strings-with-microseconds
    """
    try:
        parts = datetime_string.split('.')
        years_to_seconds_string = parts[0]
        datetime_object = datetime.datetime.strptime(
            years_to_seconds_string, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    try:
        microseconds = int(parts[1])
        datetime_object = datetime_object.replace(microsecond=microseconds)
    except (IndexError, ValueError, OverflowError):
        pass
    return datetime_object


def date_string2date(date_string):
    try:
        return datetime.datetime.strptime(date_string, "%Y-%m-%d").date()
    except ValueError:
        return None
