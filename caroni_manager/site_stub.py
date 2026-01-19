#!/usr/bin/env python3

import os
import sys
from random import randrange
import datetime
import base64
import uuid
from time import sleep

import pika

from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.any_pb2 import Any
from google.protobuf.json_format import MessageToDict

from gen.workflow_messages_pb2 import (
    Signature,
    CaroniEnvelope,
    WorkFlowCreate,
    WorkFlowInput)

# django melding magic; look away human
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "caroni.settings")
django.setup()

# ... and now we can do Django!
from caroni.models import (
    Workflow, WorkflowTemplate, WorkflowStep, Job, JobRequest, JobOffer,
    WorkflowDataflow, WorkflowSite)

caroni_exchange = 'caroni_exchange'

u = uuid.uuid4()
agent_id = base64.urlsafe_b64encode(u.bytes).rstrip(b"=").decode()

db = {
    'offers' : {},
    'jobs': {}
}

def get_dest_manager_topic():
    site_count = WorkflowSite.objects.count()
    if site_count == 0:
        this_site = WorkflowSite.objects.create()
    elif site_count == 1:
        this_site = WorkflowSite.objects.all().first()
    else:
        raise RuntimeError(
            "More than one WorkflowSite found; This is unsupported.")

    manager_id = base64.urlsafe_b64encode(
        this_site.uuid.bytes).rstrip(b"=").decode()

    return f"wf.manager.{manager_id}"


def get_agent_topic():
    return f"wf.agent.{agent_id}"

def sign_and_seal(msg):
    # Take an object ('msg') and put it in a CaroniEnvelope.  Return the CE
    any_payload = Any()
    any_payload.Pack(msg)

    ce = CaroniEnvelope(
        signature=Signature(),
        payload=any_payload
    )

    return ce


if 'AMQP_URL' in os.environ:
    amqp_url = os.environ["AMQP_URL"]
    print(f"AMQP_URL is {amqp_url}")
    parameters = pika.URLParameters(amqp_url)
else:
    credentials = pika.PlainCredentials('username', 'password')
    parameters = pika.ConnectionParameters(
        'localhost',
        5672,
        '/',
        credentials)

for attempt in range(1, 5):
    try:
        connection = pika.BlockingConnection(parameters)
    except pika.exceptions.AMQPConnectionError:
        print(f"RabbitMQ not ready (attempt {attempt}/5")
        sleep(2)

channel = connection.channel()
channel.exchange_declare(caroni_exchange, exchange_type="topic")

declare_result = channel.queue_declare(queue="", exclusive=True)
agent_queue_name = declare_result.method.queue

if len(sys.argv) > 1:
    start_value = sys.argv[1]
else:
    start_value = "foomessage"

wf_input = WorkFlowInput(key="start_message", value=start_value)
wf_create = WorkFlowCreate(
    signature=Signature(),
    template_name="test_simple",
    wf_name="test_workflow",
    inputs=[wf_input])

channel.basic_publish(
    exchange=caroni_exchange,
    properties=pika.BasicProperties(reply_to=get_agent_topic()),
    routing_key=get_dest_manager_topic(),
    body=sign_and_seal(wf_create).SerializeToString())


connection.close()