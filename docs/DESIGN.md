# Caroni Design Document

This document is a rough collection of some of the design goals of Caroni. It
can cover design pillars, ideal use cases, and technical drivers.

## What is caroni?

Caroni is a workflow service. It consists workflow managers and agents (these
may be renamed to "resource managers"). A series of (Protobuf/AMQP) messages
coordinates workflow steps to agents.

Using (a subset of) the Common Workflow Language, workflows are defined by a
YAML standard (CWL). The workflow manager breaks this workflow down in to steps,
creating a DAG from the inputs and outputs of the different steps.

A workflow step (eventually) has a job associated with it. Jobs are requested of
the agent by the workflow managers, and happens in a fulfillment style, in that
the agents listen for jobs they can service and respond indicating their
fulfillment (a handshake to establish two way confirmation is performed)

Job status is monitored by the agent, and communicated back to the owning
workflow manager. Inputs and outputs connect workflow steps, and thus jobs. Both
workflow managers (for each step in a workflow) and agents (for jobs specific to
them) marshal connecting dataflows (Input/output tuple) between each other.
Jobs do not start until all of their data inputs are available to them, and this
is tracked by the agent.

#### What is caroni not?

These are things caroni does not try to do:

* An intelligent queue manager or load balancer: Caroni currently does very dumb FIFO queuing. The idea would be either that a more intelligent resource manager like slurm or pbs are used to actually queue for a hardware resource, or that jobs are so short/obvious to schedule that a very dumb FIFO suffices. The only thing in regards to scheduling is tracking that all data inputs have arrived and are processed before fully scheduling the resource (we never ever want the resource to wait).

* Something that will inherently monitor system resources, like Kubernetes. This can be a deciding factor of if an agent accepts a job or not, but a hook/plugin interface would need to be made for this. We don't include this as we make very little assumption about what the hardware resource is or how it is utilized.

* Data management or transfer agent. We will be making an interface for caroni to deal with various data transfer and preprocessing services, but it itself does not do this.
 
## What are use cases?

Several use cases exist, and they each compound upon one another:

* An entity has access to several (hardware) resources. This is almost a non-use case as something like slurm alone would serve better here.

* These resources may be involved in workflows from several origination points (workflow managers), instead of from a single point. Caroni starts to shine; a single manger is an assumption made by several competing workflow systems.

* Workflow steps (job) have inputs requirements and provide outputs to other jobs, BUT by technical constraint or by policy, the job (agent) can not know about the rest of the workflow. Additionally, compartmentalization is just good practice for re-usable steps.

* Recovery and redundancy of jobs. Should a job fail, and the failure is either temporary or another agent is capable of servicing the same job, caroni will recover a workflow step by re-fulfilling the job.

* Agents are in weird, disparate, and/or semi-offline locations. Given the message based approach of caroni, as long as a message can be routed to and then received from a remote system (agent or manager) caroni will operate. This allows for network transparency. Additionally, because caroni uses messages and not synchronous communication (like HTTP), temporal outages are quickly glazed over, or routed around (using other agents to fulfill the job).

## What drives caroni towards the above use cases

AMQP and protobuf are central technologies to caroni. AMQP could be traded out for other messaging protocols that utilize a broker and have topic routing. Protobuf is important due to it's standardization of message types, as well as being protocol agnostic. There are a few JSON sub-standard that control and maintain message structure, but protobuf worked out of the gate.

X.509 is not implemented, but will be the methodology for agent and manager authentication and validation. Being "offline" this allows different ends of a communication to be at radically different locations.

[The sequence of messages](https://github.com/shaunbrady/caroni-demo?#sequence-diagrams) (which personally reminds me of TCP) lets the manager indicate their need, and resource mangers accept these (or decline). This is how resources can easily go offline on their own schedules, and the managers will look elsewhere for fulfillment. 

Each side (manager and agent) has an individual Django web application that
shares an ORM with the central AMQP process. Django is mostly meant to be a drop
in "management/administration/debug" console. Ideally this Django application
will turn into an installable Django app (versus an entire project/site).
Additionally an SPA would be nice to include providing an end-user with a nice
dashboard.

Only workflow template and job definition are done via Django web interfaces
(manager and agent respectively). The rest of the workflow, from workflow
submission on is done via AMQP; the only involvement Django has is the ORM.
