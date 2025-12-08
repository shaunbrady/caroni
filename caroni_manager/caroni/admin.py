from django.contrib import admin

from caroni.models import (
    Workflow, WorkflowTemplate, WorkflowStep, WorkflowDataflow, Job)


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    pass

@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    pass

@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    pass

@admin.register(WorkflowDataflow)
class WorkflowDataflowAdmin(admin.ModelAdmin):
    pass

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    pass