import uuid

from datetime import datetime, timezone

from django.db import models
from django_fsm import FSMField, transition


class JobType(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=255, default="")
    body = models.TextField(default="")

    def __str__(self):
        return f"{self.name}"

class JobTypeInput(models.Model):
    job_type = models.ForeignKey(
        JobType,
        on_delete=models.CASCADE,
        related_name="inputs")
    name = models.CharField(max_length=255, unique=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job_type", "name"],
                name="unique_input_name_per_job_type",
            )
        ]

    def __str__(self):
        return f"{self.job_type} - {self.name}"

class JobTypeOutput(models.Model):
    job_type = models.ForeignKey(
        JobType,
        on_delete=models.CASCADE,
        related_name="outputs")
    name = models.CharField(max_length=255, unique=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job_type", "name"],
                name="unique_output_name_per_job_type",
            )
        ]

    def __str__(self):
        return f"{self.job_type} - {self.name}"

class JobOffer(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    # Maybe an FK to the JobType instead of 'name' which appears to be not used
    job_type_name = models.CharField(max_length=255, default="")
    expires_at = models.DateTimeField()

class Job(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    reply_to = models.CharField(max_length=255, default="")
    job_type = models.ForeignKey(JobType, on_delete=models.CASCADE, null=True)
    state = FSMField(default="pending", protected=True)
    queued_at = models.DateTimeField(null=True, blank=True)

    @transition(field=state, source="pending", target="queued")
    def queue(self):
        self.queued_at = datetime.now(tz=timezone.utc)

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

    def create_outputs_from_type(self):
        for an_output in self.job_type.outputs.all():
            self.outputs.create(job=self, name=an_output.name)

    def create_inputs_from_type(self):
        for an_input in self.job_type.inputs.all():
            self.inputs.create(job=self, name=an_input.name)

    def deliver_input(self, name="", value=""):
        an_input = self.inputs.get(name=name)
        # Ignore any inputs we already received
        if an_input.state != "available":
            an_input.value=value
            an_input.deliver()
            an_input.save()
            # FIXME For now, we're forcing this right to available, but we need an
            # internal call back, or timer loop to "move" data and confirm it's
            # available.
            an_input.mark_available()
            an_input.save()
        
        # Do we have all the inputs?  If so, go ahead and queue.  This will
        # almost assuredly be more complicated in the future, given the
        # consideration of internal needs like license tokens (yet not the
        # resource itself)
        go_for_queue = True
        for an_input in self.inputs.all():
            if an_input.state not in ["available"]:
                go_for_queue = False

        if go_for_queue:
            self.queue()
            self.save()

    def deliver_output(self, name="", value=""):
        an_output = self.outputs.get(name=name)
        an_output.value=value
        an_output.deliver()
        an_output.save()
        # FIXME For now, we're forcing this right to available, but we need an
        # internal call back, or timer loop to "move" data and confirm it's
        # available.
        an_output.mark_available()
        an_output.save()

    def __str__(self):
        return f"{self.uuid} - {self.state}"

class JobInput(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="inputs")
    name = models.CharField(max_length=255, default="")
    value = models.CharField(max_length=255, default="")
    state = FSMField(default="undelivered", protected=True)

    @transition(field=state, source="undelivered", target="delivered")
    def deliver(self):
        pass

    @transition(field=state, source="delivered", target="available")
    def mark_available(self):
        pass

    def __str__(self):
        return f"{self.job.uuid} {self.job.job_type} {self.name} {self.state}"

class JobOutput(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="outputs")
    name = models.CharField(max_length=255, default="")
    value = models.CharField(max_length=255, default="")
    state = FSMField(default="undelivered", protected=True)

    @transition(field=state, source="undelivered", target="delivered")
    def deliver(self):
        pass

    @transition(field=state, source="delivered", target="available")
    def mark_available(self):
        pass

    def __str__(self):
        return f"{self.job.uuid} {self.job.job_type} {self.name} {self.state}"