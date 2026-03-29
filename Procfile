release: python manage.py collectstatic --noinput && python manage.py migrate --noinput
web: gunicorn edutrack.wsgi --log-file -