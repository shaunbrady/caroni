# Workflow wf_server
FROM python:3.12-slim AS caroniwf-wf_server
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["./wait_for_db.sh", "python", "wf_server.py"]

# Webserver
FROM python:3.12-slim AS caroniwf-django
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["./db_init_run_server.sh"]

# Site stub; to be execed in to
FROM python:3.12-slim AS caroniwf-sitestub
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["sleep", "infinity"]