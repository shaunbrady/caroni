# Workflow wf_agent
FROM python:3.12-slim AS caroniagent-wf_agent
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
RUN apt-get update && apt-get install -y jq
CMD ["./wait_for_db.sh", "python", "wf_agent.py"]

# Webserver
FROM python:3.12-slim AS caroniagent-django
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["./db_init_run_server.sh"]