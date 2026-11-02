"""gunicorn's access log, which run.sh points gunicorn at; the rest of its settings are there.

One line per request: the method, the path, the status, the bytes sent, the time taken and the
user agent, which is what tells apart whatever wakes the suspended machine. No client address and
no query string. absolved/access_log.py escapes control characters, so a request stays one line.
"""

accesslog = "-"
access_log_format = '%(m)s %(U)s %(s)s %(b)s %(M)sms "%(a)s"'
logger_class = "absolved.access_log.AccessLogger"
