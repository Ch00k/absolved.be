#!/bin/sh
set -e

python manage.py migrate --noinput
# Sessions that expired without a logout stay in the database until something removes them.
python manage.py clearsessions

# One worker: the rate limits count in its memory, which a second process would not share. Its
# threads serve requests side by side. gunicorn.conf.py holds the access log, which keeps no client
# address.
exec gunicorn config.wsgi:application --config gunicorn.conf.py --bind [::]:8080 --workers 1 --threads 4 --timeout 30
