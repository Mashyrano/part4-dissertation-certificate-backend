from django.urls import path
from . import views

from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('register-institution-request/', views.register_institution_request, name='register-institution-request'),
    path('institution-requests/', views.institution_requests, name='institution-requests'),
    path('approve-institution/<int:institution_id>/', views.approve_institution),
    path('approved-institutions/', views.approved_institutions),
    path('revoke-institution/<int:institution_id>/', views.revoke_institution, name='revoke-institution'),
    path('get-institution-by-address/', views.get_institution_by_address, name='get-institution-by-address'),
    path('issue-certificate/', views.issue_certificate, name="issue_certificate"),
    path('update-certificate/', views.update_certificate_with_cid),
    path('batch-upload/', views.batch_upload_certificates),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

