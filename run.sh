#!/bin/sh
set -e

python manage.py migrate --noinput
# Sessions that expired without a logout stay in the database until something removes them.
python manage.py clearsessions

# One worker: the rate limits count in its memory, which a second process would not share. Its
# threads serve requests side by side. No access log is written, so no client address is kept.
exec gunicorn config.wsgi:application --bind [::]:8080 --workers 1 --threads 4 --timeout 30
