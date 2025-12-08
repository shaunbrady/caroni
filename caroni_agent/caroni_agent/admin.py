from django.contrib import admin

from caroni_agent.models import (
    JobType, JobTypeInput, JobTypeOutput, Job, JobOffer, JobInput, JobOutput)

@admin.register(JobType)
class JobTypeAdmin(admin.ModelAdmin):
    pass

@admin.register(JobTypeInput)
class JobTypeInputAdmin(admin.ModelAdmin):
    pass

@admin.register(JobTypeOutput)
class JobTypeOutputAdmin(admin.ModelAdmin):
    pass

@admin.register(JobOffer)
class JobOfferAdmin(admin.ModelAdmin):
    pass

@admin.register(JobInput)
class JobInputAdmin(admin.ModelAdmin):
    pass

@admin.register(JobOutput)
class JobOutputAdmin(admin.ModelAdmin):
    pass

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    pass