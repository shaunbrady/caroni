import uuid

from django.db import models
from django_fsm import FSMField, transition


class WorkflowSite(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, default="")

    def __str__(self):
        return f"{self.name} - {self.uuid}"

class WorkflowTemplate(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, default="")
    cwl_doc = models.TextField()

    def __str__(self):
        return f"{self.name} - {self.uuid}"

class Workflow(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    template = models.ForeignKey(WorkflowTemplate, on_delete=models.CASCADE)
    cwl_doc = models.TextField()
    state = FSMField(default="created", protected=True)
    workflow_inputs = models.JSONField(default=dict)
    workflow_outputs = models.JSONField(default=dict)

    # created, initalizing, running, stalled, failed, completed
    @transition(field=state, source="created", target="initalizing")
    def initialize(self):
        pass

    @transition(
        field=state,
        source=["stalled", "initalizing"],
        target="running")
    def run(self):
        pass

    @transition(field=state, source=["running", "stalled"], target="stalled")
    def stall(self):
        pass

    @transition(field=state, source="running", target="completed")
    def complete(self):
        pass

    @transition(
        field=state,
        source=["running", "stalled", "initalizing"],
        target="failed")
    def fail(self):
        pass

    def add_step(self, step_name, step, kvs=None):
        """
        Takes a cwltool WorkflowStep and adds a WorkflowStep to this Workflow
        """
        if kvs is None:
            kvs = {}

        # We don't currently support static values, but this is where it would
        # be if ever.  If never, a list makes more sense than a dict.
        inputs = step.tool['run'].get("inputs", [])
        for an_input in inputs:
            if an_input['type'] != "string":
                raise Exception()
            kvs[an_input['id'].split('/')[-1]] = ""
        hints = step.tool['run'].get("hints", [])
        for hint in hints:
            if 'CaroniJobName' in hint:
                job_name = hint['CaroniJobName']
                break
        else:
            raise Exception("CaroniRequirement not found")

        # Add to Workflow
        WorkflowStep.objects.create(
            workflow=self, job_name=job_name, step_name=step_name, job_kvs=kvs
        )

    def uri_helper(self, uri):
        """
        Small helper to break URI in to parts.  Will likely need generalize and
        pull out.
        """
        _, anchor = uri.split("#") # _ is base_uri
        anchor_split = anchor.split("/")
        # If there is no stepname, then we assume it's an input/output from the
        # workflow itself.  Let the caller know.
        if len(anchor_split) == 1:
            from_workflow = True
            step_name = "" # Workflow
            ioput_name = anchor_split[0]
        else:
            from_workflow = False
            step_name = anchor_split[0]
            ioput_name = anchor_split[1] 

        return locals()

    def process_dataflows(self, step_name, step):
        ins = step.tool['in']
        #Create WorkflowDataflow objects from the ins
        
        # 2) Consider how we'll inform of data-ready from $previous_job.  Do we
        # even need to, or just assume that is out of band?
        for an_in in ins:
            this_step = self.uri_helper(an_in['id'])
            source_step = self.uri_helper(an_in['source']) 
            # the step we're operating on won't ever have an input that is from
            # the Workflow
            this_wfstep = WorkflowStep.objects.get(
                workflow=self,
                step_name=this_step["step_name"])
            
            if not source_step["from_workflow"]:
                source_wfstep = WorkflowStep.objects.get(
                    workflow=self,
                    step_name=source_step["step_name"])
            else:
                source_wfstep=None

            WorkflowDataflow.objects.create(
                workflow=self,
                src_output_name=source_step['ioput_name'],
                dst_input_name=this_step['ioput_name'],
                wfstep_src=source_wfstep,
                wfstep_dst=this_wfstep)

    def process_outputs(self, outputs_ast):
        for an_output in outputs_ast:
            source_step = self.uri_helper(an_output['outputSource'])
            wf_out = self.uri_helper(an_output['id'])
            source_wfstep = WorkflowStep.objects.get(
                workflow=self,
                step_name=source_step["step_name"])
            WorkflowDataflow.objects.create(
                workflow=self,
                src_output_name=source_step['ioput_name'],
                dst_input_name=wf_out['ioput_name'],
                wfstep_src=source_wfstep,
                wfstep_dst=None)

    def clear_to_send_dataflows(self):
        """ We only want to send dataflows when all Steps are fulfilled (or
        better).  This could be an internal state, but I didn't think it made
        sense to muddy up the FSM. """
        cts = True
        for step in self.workflow_steps.all():
            if step.state not in ["running", "fulfilled", "completed"]:
                cts  = False
                break
        return cts

    # TODO Generalize this function to update a WF from the state of it's Steps
    def check_complete(self):
        """
        If all steps are complete, complete the Workflow
        """
        complete = True
        for step in self.workflow_steps.all():
            if step.state != "completed":
                complete  = False
                break
        if complete:
            self.complete()
            self.save()

    def __str__(self):
        return f"{self.uuid} - {self.state}"
    
# Job is at a weird place in the file[0], and more importantly sits as a loosely
# held 1:1, even though the database would allow N:1 with WorkflowStep.  This is
# because I'm not yet convinced of the data relationship (what happens if a job
# goes bad, but we want to track it).  Stay tuned...
#
# [0] I'm pedantic about ForeignKey(Foo) vs ForeignKey("Foo"); I'm seen some
# stuff....
class Job(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    state = FSMField(default="pending", protected=True)
    reply_to = models.CharField(max_length=255, default="")

    @transition(field=state, source="pending", target="queued")
    def queue(self):
        pass

    @transition(field=state, source="queued", target="running")
    def run(self):
        pass

    @transition(field=state, source="running", target="completed")
    def complete(self):
        pass

    @transition(field=state,
        source=["running", "queued", "pending"],
        target="failed")
    def fail(self):
        pass

    def __str__(self):
        return f"{self.uuid} - {self.state}"


class WorkflowStep(models.Model):
    workflow = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, related_name="workflow_steps")
    current_job = models.OneToOneField(
        Job, on_delete=models.CASCADE, null=True, related_name="workflow_step")
    state = FSMField(default="created", protected=True)
    step_name = models.CharField(max_length=255, default="")
    job_name = models.CharField(max_length=255, default="")
    job_kvs = models.JSONField(default=dict)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=5)

    def can_fulfill_again(self):
        return self.attempts < self.max_attempts - 1

    # created, fulfilling, fulfilled, running, completed, failed
    @transition(field=state, source="created", target="fulfilling")
    def fulfill(self):
        pass

    @transition(field=state, source="fulfilling", target="fulfilled")
    def mark_fulfilled(self):
        pass

    @transition(field=state,
        source=["fulfilled", "running"],
        target="fulfilling",
        conditions=[can_fulfill_again])
    def fulfill_again(self):
        # TODO switch this to counts of JR if the condition is ===.
        # It could be that we want something more complex.
        self.attempts += 1
        self.save()

    @transition(field=state, source="fulfilled", target="running")
    def run(self):
        pass

    @transition(field=state, source="running", target="completed")
    def complete(self):
        pass

    @transition(
        field=state,
        source=["fulfilling" ,"fulfilled", "running"],
        target="failed")
    def fail(self):
        pass

    def create_job_request(self):

        return self.job_requests.create(workflow_step=self)

    def __str__(self):
        return f"Workflow - {self.workflow.uuid} - {self.job_name} - {self.state}"

class WorkflowDataflow(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE)
    state = FSMField(default="awaiting", protected=True)
    src_output_name = models.CharField(max_length=255, default="")
    dst_input_name = models.CharField(max_length=255, default="")
    value = models.CharField(max_length=255, default="")
    wfstep_src = models.ForeignKey(
        WorkflowStep,
        on_delete=models.CASCADE,
        null=True, # null = Workflow input
        related_name="src_dataflows")
    wfstep_dst = models.ForeignKey(
        WorkflowStep,
        on_delete=models.CASCADE,
        null=True, # null = wf output
        related_name="dst_dataflows")

    # Can be delivered more than once, if Job is refulfilled
    @transition(field=state,
        source=["awaiting", "delivered"],
        target="delivered")
    def deliver(self, value=None):
        if value:
            self.value=value
            self.save()


    def __str__(self):
        if self.wfstep_dst:
            dst_stepname = self.wfstep_dst.step_name
        else:
            dst_stepname = "Workflow"

        if self.wfstep_src:
            src_stepname = self.wfstep_src.step_name
        else:
            src_stepname = "Workflow"

        return f"WfDf {src_stepname}:{self.src_output_name} -> {dst_stepname}:{self.dst_input_name}: {self.state}"


class JobRequest(models.Model):
    workflow_step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.CASCADE,
        related_name="job_requests")
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    state = FSMField(default="created", protected=True)

    # fulfilling, unanswered, fulfilled, refulfilling, expired?
    @transition(field=state, source="created", target="fulfilling")
    def fulfill(self):
        pass

    @transition(field=state, source="fulfilling", target="unanswered")
    def give_up(self):
        pass

    @transition(field=state, source="fulfilling", target="fulfilled")
    def mark_fulfilled(self):
        pass

    # Note: This might be a deadend, more confusing (to the agents) than it's
    # worth.
    @transition(field=state, source="fulfilled", target="fulfilling")
    def fulfill_again(self):
        pass

    # Used for when all offers expire
    @transition(
        field=state,
        source=["fulfilling", "fulfilled"],
        target="expired")
    def expire(self):
        pass

class JobOffer(models.Model):
    job_request = models.ForeignKey(JobRequest, on_delete=models.CASCADE)
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    state = FSMField(default="received", protected=True)
    # TODO Need to track expiration here, and likely another state (expired)

    # received, accepted, declined
    @transition(field=state, source="received", target="accepted")
    def accept(self):
        pass

    @transition(field=state, source="received", target="rejected")
    def reject(self):
        pass