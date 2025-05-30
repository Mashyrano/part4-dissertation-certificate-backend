from django.contrib import admin
from .models import PendingInstitution, Certificate

admin.site.register(PendingInstitution)
admin.site.register(Certificate)
