#!/bin/bash
./wait_for_db.sh python manage.py migrate
python manage.py loaddata demo_data.json
python manage.py runserver 0.0.0.0:8000