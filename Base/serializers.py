from rest_framework import serializers
from .models import PendingInstitution

class PendingInstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingInstitution
        fields = '__all__'
