#!/usr/bin/env python3

import os
import pika
import uuid
import base64
import textwrap
from time import sleep
from urllib.parse import urljoin

from google.protobuf.any_pb2 import Any

from cwltool.load_tool import load_tool
from cwltool.workflow import default_make_tool # just needs to be imported?
from cwltool.context import LoadingContext

from schema_salad.fetcher import Fetcher

from gen.workflow_messages_pb2 import (
    JobStatus, JobFulfillmentRequest, Signature, JobParameter,
    JobFulfillmentDecline, JobFulfillmentOffer, JobFulfillmentOfferAccept,
    JobFulfillmentOfferReject, CaroniEnvelope, JobQueued, JobStatusUpdate,
    JobStatusRequest, WorkFlowCreate, JobDataReady)


# django melding magic; look away human
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "caroni.settings")
django.setup()

# ... and now we can do Django!
from caroni.models import (
    Workflow, WorkflowTemplate, WorkflowStep, Job, JobRequest, JobOffer,
    WorkflowDataflow)

from django.db import transaction


class InMemoryFetcher(Fetcher):
    def __init__(self, cache, session):
        self.store = store

    def supported_schemes(self):
        return ["mem", "https", "http"]

    def fetch_text(self, url, content_types=None, **kwargs):
        if url.startswith("mem://"):
            return self.store[url]
        return super().fetch_text(url, **kwargs)

    def check_exists(self, url):
        if "caroni" in url:
            return True
        return url in self.store

    def urljoin(self, base, ref):
        return urljoin(base, ref)

store = {
    "records.yml": textwrap.dedent("""\
        ---
        $schema: https://json-schema.org/draft/2019-09/schema
        $graph:
          - name: Stage1Record
              type: record
              fields:
              - name: input_text
                  type: string

          - name: Stage2Record
              type: record
              fields:
              - name: processed_text
                  type: string
              - name: word_count
                  type: int

          - name: Stage3Record
              type: record
              fields:
              - name: summary
                  type: string
              - name: score
                  type: float
""")
}

def mem_resolver(loader, uri):
    # Accept mem:// URIs as-is
    return uri

caroni_exchange = "caroni_exchange"

u = uuid.uuid4()
manager_id = base64.urlsafe_b64encode(u.bytes).rstrip(b"=").decode()

db = {
    'requests' : {},
    'jobs': {}
}

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

def get_manager_topic():
    #return f"wf.manager.{manager_id}"
    return f"wf.manager.uuid4you"

### Split in to common TODO
def sign_and_seal(msg):
    # Take an object ('msg') and put it in a CaroniEnvelope.  Return the CE
    any_payload = Any()
    any_payload.Pack(msg)

    ce = CaroniEnvelope(
        signature=Signature(),
        payload=any_payload
    )

    return ce

def to_uuid_obj(uuid_bytes):
    return uuid.UUID(bytes=uuid_bytes)

def enum_given_fsm(fsm_value):
    return JobStatus.Value("JOB_STATUS_" + fsm_value.upper())

def fsm_given_enum(enum_value):
    return JobStatus.Name(enum_value).split("_")[2] # JOB_STATUS_RUNNING
### End common

def workflow_kvs_to_proto_parameters(kvs=None):
    if not type(kvs) == dict:
        raise Exception()

    ret = []
    for k,v in kvs.items():
        ret.append(JobParameter(key=k, value=v))

    return ret

def send_job_data_ready(
    jp_key=None, jp_value=None, job_uuid=None, job_routing_key=None):
    # TODO could make a multi-send version as JobDataReady takes parameters as a
    # list.
    jp = JobParameter(
        key=jp_key,
        value=jp_value)
    jdr = JobDataReady(
        signature=Signature(),
        job_uuid=job_uuid,
        parameters=[jp])
    channel.basic_publish(
        exchange=caroni_exchange,
        properties=pika.BasicProperties(reply_to=get_manager_topic()),
        routing_key=job_routing_key,
        body=sign_and_seal(jdr).SerializeToString())

def jfr_decline_process(jfd, method=None, properties=None):
    # TODO This should not kill the JFR, but maybe it has a max_declines?
    print(f" [x] Received JobFulfillmentDecline for : {uuid.UUID(bytes=jfd.request_uuid)}")

def jfr_offer_process(jfo, method=None, properties=None):
    # Accepting first offer. We'll make this more intelligent when metrics
    # reveal themselves.

    # Have we already fulfilled?
    accept = False
    with transaction.atomic():
        jr = JobRequest.objects.get(uuid=uuid.UUID(bytes=jfo.request_uuid))
        if jr.state == "fulfilling":
            # Accept
            jr.mark_fulfilled()
            jr.save()
            accept = True
        # TODO Probably need to safety check other states here and Exception;
        # maybe out of the transaction.

    jo = JobOffer.objects.create(
        uuid=uuid.UUID(bytes=jfo.offer_uuid),
        job_request=jr)
    if(accept):
        jo.accept()
        jfoa = JobFulfillmentOfferAccept(
            signature=Signature(),
            request_uuid=jfo.request_uuid,
            offer_uuid=jfo.offer_uuid,
            accept_message="offer accepted")

        channel.basic_publish(
            exchange=caroni_exchange,
            properties=pika.BasicProperties(reply_to=get_manager_topic()),
            routing_key=properties.reply_to,
            body=sign_and_seal(jfoa).SerializeToString())

        print(f"Sent JobFulfillmentOfferAccept to request {uuid.UUID(bytes=jfo.request_uuid)}")
    else: # Reject
        jo.reject()
        jfor = JobFulfillmentOfferReject(
            signature=Signature(),
            request_uuid=jfo.request_uuid,
            offer_uuid=jfo.offer_uuid,
            reject_message="offer rejected")

        channel.basic_publish(
            exchange=caroni_exchange,
            properties=pika.BasicProperties(reply_to=get_manager_topic()),
            routing_key=properties.reply_to,
            body=sign_and_seal(jfor).SerializeToString())

        print(f"Sent JobFulfillmentOfferReject to request {uuid.UUID(bytes=jfo.request_uuid)}")
    jo.save()


def job_queued_process(job_queued, method=None, properties=None):
    print(f" [x] Received JobQueued for : {uuid.UUID(bytes=job_queued.job_uuid)}")

    jo = JobOffer.objects.get(uuid=uuid.UUID(bytes=job_queued.offer_uuid))
    wf_step = jo.job_request.workflow_step
    job = Job.objects.create(
        uuid=uuid.UUID(bytes=job_queued.job_uuid),
        reply_to=properties.reply_to)
    wf_step.current_job = job
    wf_step.mark_fulfilled()
    wf_step.save()

    # should this be scheduled for later?
    jsr = JobStatusRequest(
        signature=Signature(),
        job_uuid=job_queued.job_uuid)

    channel.basic_publish(
        exchange=caroni_exchange,
        properties=pika.BasicProperties(reply_to=get_manager_topic()),
        routing_key=properties.reply_to,
        body=sign_and_seal(jsr).SerializeToString())

    if wf_step.workflow.clear_to_send_dataflows():
        # We should be on the last job being accepted. The Workflow as a whole
        # should be good to go; send Dataflow messages.
        print("We're ready to send dataflows")
        wf_dfs = WorkflowDataflow.objects.filter(
            workflow=wf_step.workflow, wfstep_src=None)
        for df in wf_dfs:

            jp_key = df.dst_input_name
            jp_value = wf_step.workflow.workflow_inputs[df.src_output_name]
            job_uuid = df.wfstep_dst.current_job.uuid.bytes
            job_routing_key = df.wfstep_dst.current_job.reply_to

            send_job_data_ready(
                jp_key=jp_key, jp_value=jp_value, job_uuid=job_uuid,
                job_routing_key=job_routing_key)

            df.deliver()
            df.save()

def job_status_update_process(job_status_update, method=None, properties=None):
    print(f" [x] Received JobStatusUpdate for : {uuid.UUID(bytes=job_status_update.job_uuid)}")

    job = Job.objects.get(uuid=to_uuid_obj(job_status_update.job_uuid))
    if(job_status_update.job_status == JobStatus.JOB_STATUS_QUEUED):
        job.queue()
        job.save()
    elif(job_status_update.job_status == JobStatus.JOB_STATUS_RUNNING):
        job.run()
        job.save()
        # Match workflow
        wfs = WorkflowStep.objects.get(current_job=job)
        wfs.run()
        wfs.save()
        wf = wfs.workflow
        if wf.state == "initalizing":
            wf.run()
            wf.save()
    elif(job_status_update.job_status == JobStatus.JOB_STATUS_COMPLETED):
        job.complete()
        job.save()
        # Match workflow
        wfs = WorkflowStep.objects.get(current_job=job)
        wfs.complete()
        wfs.save()
        wf = wfs.workflow
        if wf.state == "running":
            wf.check_complete()
    elif(job_status_update.job_status == JobStatus.JOB_STATUS_FAILED):
        job.fail()
        job.save()
    elif(job_status_update.job_status == JobStatus.JOB_STATUS_PENDING):
        pass #NOOP as we should already be in pending (or beyond)
    else:
        print(f"JobStatusUpdate send unknown status {job_status_update.job_status}")

def workflow_create(wfc, method=None, properties=None):
    print(f" [x] Received WorkFlowCreate for : {wfc.template_name}")

    wft = WorkflowTemplate.objects.get(name = wfc.template_name)
    store['mem://workflow.cwl'] = wft.cwl_doc
    workflow_inputs = {_.key: _.value for _ in wfc.inputs}
    wf = Workflow.objects.create(
        template=wft, cwl_doc=wft.cwl_doc, workflow_inputs=workflow_inputs)
    ctx = LoadingContext()
    ctx.fetcher_constructor = InMemoryFetcher
    ctx.resolver = mem_resolver
    ctx.construct_tool_object = default_make_tool
    workflow_ast = load_tool("mem://workflow.cwl", loadingContext=ctx)
    # TODO, this is how to get the outputs of the workflow
    #print("OUTPUTS")
    #print(list(workflow_ast.tool['outputs']))

    for step in workflow_ast.steps:
        step_name = step.id.split("#")[1] # 0 is namespace
        try:
            wf.add_step(step_name, step)
        except Exception as e:
            print(e)

    # Go around again to get dataflows.  Need to make sure all the steps existed
    # first (previous for)
    for step in workflow_ast.steps:
        try:
            wf.process_dataflows(step_name, step)
        except Exception as e:
            print(e)

    # Turn any outputs into dataflows
    wf.process_outputs(workflow_ast.tool['outputs'])

    # Some what arbitrary doing this here, versus before scanning the AST above,
    # but we should do it before we kick off JobRequests.
    wf.initialize()
    wf.save()

    # Third go around but we use the WorkflowStep models now.  We fire off requests
    # after we know DAG (we'll have the opportunity to calculate a time estimate at
    # this point, which I speculate we'll need in the future).
    for step in WorkflowStep.objects.filter(workflow=wf):
        jr = step.create_job_request() # TODO default state is fulfilling?
        jr.fulfill()
        jr.save() # TODO Do we have the JR update the WFS?
        step.fulfill()
        step.save()

        jfr = JobFulfillmentRequest(
            signature=Signature(),
            request_uuid=jr.uuid.bytes,
            job_type_name=step.job_name,
            parameters=workflow_kvs_to_proto_parameters(step.job_kvs))

        print("Sending to wf.agent.fulfillment")
        channel.basic_publish(
            exchange=caroni_exchange,
            properties=pika.BasicProperties(reply_to=get_manager_topic()),
            routing_key='wf.agent.fulfillment',
            body=sign_and_seal(jfr).SerializeToString())

def job_data_ready_process(jdr, method=None, properties=None):
    print(f" [x] Received JobDataReady for : {to_uuid_obj(jdr.job_uuid)}")
    uuid_obj=to_uuid_obj(jdr.job_uuid)

    params_recv = {}
    for param in jdr.parameters:
        params_recv[param.key] = param.value

    # It will come FROM the source job
    src_job = Job.objects.get(uuid=uuid_obj)
    wfstep_src = src_job.workflow_step
    for df in WorkflowDataflow.objects.filter(wfstep_src=wfstep_src):

        # Do we have the right input/output pair
        if df.src_output_name in params_recv.keys():
            if df.wfstep_dst: # a job to be notified
                jp_key = df.dst_input_name
                jp_value = params_recv[df.src_output_name]
                job_uuid = df.wfstep_dst.current_job.uuid.bytes
                job_routing_key = df.wfstep_dst.current_job.reply_to

                send_job_data_ready(
                    jp_key=jp_key, jp_value=jp_value, job_uuid=job_uuid,
                    job_routing_key=job_routing_key)
            else: # Workflow itself
                with transaction.atomic():
                    wfouts = wfstep_src.workflow.workflow_outputs
                    wfouts[df.dst_input_name] = params_recv[df.src_output_name]
                    wfstep_src.workflow.workflow_outputs = wfouts
                    wfstep_src.workflow.save()

            df.deliver()
            df.save()


callback_routes = {
    JobFulfillmentDecline: jfr_decline_process,
    JobFulfillmentOffer: jfr_offer_process,
    JobQueued: job_queued_process,
    JobStatusUpdate: job_status_update_process,
    WorkFlowCreate: workflow_create,
    JobDataReady: job_data_ready_process,
}

def callback(ch, method, properties, body):
    envelope = CaroniEnvelope()
    envelope.ParseFromString(body)

    any_payload = envelope.payload

    for msg_type, handler in callback_routes.items():
        if any_payload.Is(msg_type.DESCRIPTOR):
            # Unpack into the correct type
            unpacked = msg_type()
            any_payload.Unpack(unpacked)
            handler(unpacked, method=method, properties=properties)
            break
    else:
        print(f"Unknown routing key: {method.routing_key}")


declare_result = channel.queue_declare(queue="", exclusive=True)
wf_server_queue_name = declare_result.method.queue


channel.queue_bind(
    exchange=caroni_exchange,
    queue=wf_server_queue_name,
    routing_key=get_manager_topic()
)

print(f"Bound to queue with topic: {get_manager_topic()}")

# Set up queue to listen for fulfillment decline response
channel.basic_consume(
    queue=wf_server_queue_name,
    auto_ack=True,
    on_message_callback=callback)


try:
    channel.start_consuming()
except KeyboardInterrupt:
    connection.close()