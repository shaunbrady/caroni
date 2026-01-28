# Caroni

Caroni is an asynchronous, distributed workflow management system.

[Jump to Installation](#how)

## What

Caroni currently consists of a manager (concerned with the workflow itself) and
an agent (concerned with the management of a resource). An installation can
have as many managers and agents as desired. Managers and agents aren't really
paired or grouped other than by individual trust.

It is released under [the GPL version 2](LICENSE).

## Why

There are plenty of other workflow systems. The use case of caroni is for
loosely federated resources, that serve multiple sites who each have their own
set of workflows.

When sites don't necessarily know about each other, but have to share a
resource, caroni is there for that.

See our [Design Doc](docs/DESIGN.md)

## How

caroni uses protobuf for managers and agents to communicate.

[Protobuf](https://github.com/protocolbuffers/protobuf/releases/download/v33.2/protoc-33.2-linux-x86_64.zip)
Both the compiler and included .proto files from github release of protobuf are
needed.  Roughly, put the compiler on ones $PATH, and put the .proto files in
something like /usr/local/include/google/protobuf/ (match the zip tree)

The release of protoc-33.2-linux-x86_64.zip was used as of this writing.

From the top of the caroni source tree, run:
```bash
protoc --proto_path=proto/ --python_out=caroni_manager/gen proto/workflow_messages.proto
protoc --proto_path=proto/ --python_out=caroni_agent/gen proto/workflow_messages.proto
```

### Run locally
To run locally each of the manager(s) and agent(s) need their own database, and
they need to share a rabbitmq broker. The installation of these is left up to
the reader, but do see the docker compose file for authentication strings for
both postgres and rabbitmq. The Django ORM (which is used by all of
wf_server.py, wf_agent.py, and each of their respective Django admin
interfaces) will fall back to sqlite if no database authentication is provied.

Build the requirements for each of caroni_agent and caroni_manager. They are
currently identical, but may diverge in the future.
```bash
# From top level
cd caroni_manager
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

# From top level
cd caroni_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

From here, in different terminals execute:
```bash
# The Workflow manager Django process caroni_manager/caroni/
python manage.py migrate # Needed only once and in development
python manage.py runserver 0.0.0.0:8000

# The Workflow manager from caroni_manager/
python wf_server.py

# The Workflow manager Django process caroni_agent/caroni_agent/
python manage.py migrate # Needed only once and in development
python manage.py runserver 0.0.0.0:8001

# The Workflow manager from caroni_manager/
python wf_agent.py
```

For testing purposes, find the database fixtures to load via the Docker and
docker-compose.yaml files.  When all Workflows and JobTypes objects are
created, you can run an example workflow via the command:

```bash
# From caroni_manager/
python site_stub.py
```

### Run via docker
This is your standard docker setup, with the only interesting bit being a
shared network, since we are having the manager bring up the rabbitmq service.

```bash
# From caroni_manager/
docker network create caroni_shared_net
docker compose up -d

# From caroni_agent/
docker compose up -d
```

The administration consoles will be available at the same ports of 8000 and
8001, respectively for the manager and agent. There will be a container
specifically for site_stub.py to kick off an example job.

```bash
# From caroni_manager/
docker compose exec sitestub bash
```

## When
Caroni is currently considered alpha software. Use at one's own peril.
