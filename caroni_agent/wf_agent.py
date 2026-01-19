#!/usr/bin/env python3

from random import uniform, choices
from datetime import datetime, timezone, timedelta
import base64
import json
import uuid
import os
import subprocess
from time import sleep

from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.any_pb2 import Any

from gen.workflow_messages_pb2 import (
    JobStatus, JobFulfillmentRequest, JobFulfillmentDecline,
    JobFulfillmentOffer, Signature, Site, CaroniEnvelope,
    JobFulfillmentOfferAccept, JobQueued, JobStatusUpdate, JobStatusRequest,
    JobDataReady, JobParameter, JobDataReady)

import pika


import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "caroni_agent.settings")
django.setup()

# ... and now we can do Django!
from caroni_agent.models import JobType, JobOffer, Job, JobInput, JobOutput

caroni_exchange = 'caroni_exchange'

u = uuid.uuid4()
agent_id = base64.urlsafe_b64encode(u.bytes).rstrip(b"=").decode()

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

def enum_given_fsm(fsm_value):
    return JobStatus.Value("JOB_STATUS_" + fsm_value.upper())

def fsm_given_enum(enum_value):
    return JobStatus.Name(enum_value).split("_")[2] # JOB_STATUS_RUNNING

def report_job_status(
        job,
        status_info="This job is doing something different now."):
    # Takes ORM Job and sends JobStatusUpdate
    job_status_update = JobStatusUpdate(
        signature=Signature(),
        job_uuid=job.uuid.bytes,
        job_status=enum_given_fsm(job.state),
        status_info=status_info)

    channel.basic_publish(
        exchange=caroni_exchange,
        properties=pika.BasicProperties(reply_to=get_agent_topic()),
        routing_key=job.reply_to,
        body=sign_and_seal(job_status_update).SerializeToString())

def jfr_process(jfr, method=None, properties=None):
    # For now we decline or offer based purely on if we have an exactly name job
    # and an equal set of parameter keys.  In the future we can consider keys
    # and (statically sent) values, and even advanced conditions based on those
    # bits of info.  This will likely result in a plugin system or call backs.

    job_found = False

    job_types_with_name = JobType.objects.filter(name=jfr.job_type_name)
    for job_type_with_name in job_types_with_name:
        input_names = [_.name for _ in job_type_with_name.inputs.all()]
        key_names = [_.key for _ in jfr.parameters]

        if set(input_names) == set(key_names):
            job_found = True
            break

    if(job_found):
        expiration_seconds = int((datetime.now() + timedelta(hours=5)).timestamp())
        epoch_obj = datetime.fromtimestamp(expiration_seconds, tz=timezone.utc)

        jo = JobOffer.objects.create(
            job_type_name=jfr.job_type_name,
            expires_at=epoch_obj)

        jfo = JobFulfillmentOffer(
            signature=Signature(),
            request_uuid=jfr.request_uuid,
            offer_uuid=jo.uuid.bytes,
            site=Site(),
            offer_message=f"Offering for {jfr.job_type_name}",
            expiration=Timestamp(seconds=expiration_seconds)
            )

        channel.basic_publish(
            exchange=caroni_exchange,
            properties=pika.BasicProperties(reply_to=get_agent_topic()),
            routing_key=properties.reply_to,
            body=sign_and_seal(jfo).SerializeToString())
        print(f"Sent JobFulfillmentOffer of {jo.uuid} to request {uuid.UUID(bytes=jfr.request_uuid)}")
    else:
        jfd = JobFulfillmentDecline(
            signature=Signature(),
            request_uuid=jfr.request_uuid,
            site=Site(),
            decline_message=f"No jobtype of {jfr.job_type_name}")

        channel.basic_publish(
            exchange=caroni_exchange,
            properties=pika.BasicProperties(reply_to=get_agent_topic()),
            routing_key=properties.reply_to,
            body=sign_and_seal(jfd).SerializeToString())
        print(f"Sent JobFulfillmentDecline to request {uuid.UUID(bytes=jfr.request_uuid)}")

def jfoa_process(jfoa, method=None, properties=None):
    # Move the offer to the job with the new ID
    jo = JobOffer.objects.get(uuid=uuid.UUID(bytes=jfoa.offer_uuid))
    job_type = JobType.objects.get(name=jo.job_type_name)
    job = Job.objects.create(
        reply_to=properties.reply_to,
        job_type=job_type,
        state="pending")
    job.create_inputs_from_type()
    job.create_outputs_from_type()
    jo.delete()
    
    job_queued = JobQueued(
        signature=Signature(),
        job_uuid=job.uuid.bytes,
        offer_uuid=jfoa.offer_uuid)

    channel.basic_publish(
        exchange=caroni_exchange,
        properties=pika.BasicProperties(reply_to=get_agent_topic()),
        routing_key=properties.reply_to,
        body=sign_and_seal(job_queued).SerializeToString())

    print(f"Sent JobQueued of {job.uuid} to offer {uuid.UUID(bytes=jfoa.offer_uuid)}")

def jsr_process(jsr, method=None, properties=None):
    job = Job.objects.get(uuid=uuid.UUID(bytes=jsr.job_uuid))
    job_status_update = JobStatusUpdate(
        signature=Signature(),
        job_uuid=jsr.job_uuid,
        job_status=enum_given_fsm(job.state),
        status_info="This job is now in doing something different")

    channel.basic_publish(
        exchange=caroni_exchange,
        properties=pika.BasicProperties(reply_to=get_agent_topic()),
        routing_key=properties.reply_to,
        body=sign_and_seal(job_status_update).SerializeToString())

def jdr_process(jdr, method=None, properties=None):
    print(f"In JobDataReady!")
    job = Job.objects.get(uuid=uuid.UUID(bytes=jdr.job_uuid))

    for param in jdr.parameters:
        job.deliver_input(name=param.key, value=param.value)

    if job.state == "queued": # We've gotten all of our inputs
        report_job_status(job)

def callback(ch, method, properties, body):
    envelope = CaroniEnvelope()
    envelope.ParseFromString(body)

    any_payload = envelope.payload
    if any_payload.Is(JobFulfillmentRequest.DESCRIPTOR):
        jfr = JobFulfillmentRequest()
        any_payload.Unpack(jfr)
        jfr_process(jfr, method=method, properties=properties)
    elif any_payload.Is(JobFulfillmentOfferAccept.DESCRIPTOR):
        jfoa = JobFulfillmentOfferAccept()
        any_payload.Unpack(jfoa)
        jfoa_process(jfoa, method=method, properties=properties)
    elif any_payload.Is(JobStatusRequest.DESCRIPTOR):
        jsr = JobStatusRequest()
        any_payload.Unpack(jsr)
        jsr_process(jsr, method=method, properties=properties)
    elif any_payload.Is(JobDataReady.DESCRIPTOR):
        jdr = JobDataReady()
        any_payload.Unpack(jdr)
        jdr_process(jdr, method=method, properties=properties)
    else:
        print("Unknown routing key")



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

connection = pika.BlockingConnection(parameters)
channel = connection.channel()
channel.exchange_declare(caroni_exchange, exchange_type="topic")

declare_result = channel.queue_declare(queue="", exclusive=True)
agent_queue_name = declare_result.method.queue

# Our personal binding
channel.queue_bind(
    exchange=caroni_exchange,
    queue=agent_queue_name,
    routing_key=get_agent_topic()
)

# Where open requests come in to
channel.queue_bind(
    exchange=caroni_exchange,
    queue=agent_queue_name,
    routing_key='wf.agent.fulfillment'
)

channel.basic_consume(
    queue=agent_queue_name,
    auto_ack=True,
    on_message_callback=callback)

print(' [*] Waiting for messages. To exit press CTRL+C')

while True:
    connection.process_data_events(time_limit=1.0)

    # Get the first queued job if any
    first_job = Job.objects.filter(state="queued").order_by("queued_at").first()

    if first_job:
        first_job.run()
        first_job.save()

        new_env = {}
        for ji in JobInput.objects.filter(job=first_job):
            new_env["CARONI_ENV_" +ji.name] = ji.value

        report_job_status(first_job)

        result = subprocess.run(
            ["bash", "-c", first_job.job_type.body],
            capture_output=True,
            text=True,
            env=new_env
        )

        try:
            job_outs = json.loads(result.stdout)
        except Exception as e:
            # We could send a fail status here
            sleep(uniform(6, 10))
            print("JSON failed")
            print(f"STDOUT is: {result.stdout}" )
            print(f"STDERR is: {result.stderr}" )
            job_outs = {}

        for k, v in job_outs.items():
            first_job.deliver_output(name=k, value=v)

        first_job.complete()
        first_job.save()
        report_job_status(first_job)

        print(f"Job {first_job.uuid} finished!")

        for output in first_job.outputs.all():
            # Check here for output.available else fail?
            jp = JobParameter(
                key=output.name,
                value=output.value)
            jdr = JobDataReady(
                signature=Signature(),
                job_uuid=first_job.uuid.bytes,
                parameters=[jp]) # TODO could collect and then send
            channel.basic_publish(
                exchange=caroni_exchange,
                properties=pika.BasicProperties(reply_to=get_agent_topic()),
                routing_key=first_job.reply_to,
                body=sign_and_seal(jdr).SerializeToString())
