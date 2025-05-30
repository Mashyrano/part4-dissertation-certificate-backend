from django.db import models

class PendingInstitution(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    description = models.TextField()
    logo = models.ImageField(upload_to="logos/")
    ethereum_address = models.CharField(max_length=42, blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)
    revoked = models.BooleanField(default=False) 

    def __str__(self):
        return self.name



class Certificate(models.Model):
    student_name = models.CharField(max_length=100)
    student_regNumber = models.CharField(max_length=20)
    student_surname = models.CharField(max_length=100)
    course = models.CharField(max_length=200)
    degree_class = models.CharField(max_length=100)
    date_issued = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student_name} {self.student_surname} - {self.course}"