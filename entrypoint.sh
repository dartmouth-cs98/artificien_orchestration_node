#!/bin/bash
exec gunicorn --bind 0.0.0.0:5001  "src.wsgi:app" "$@"
