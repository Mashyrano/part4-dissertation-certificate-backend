from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from .models import PendingInstitution  # Or whatever your model is
from .serializers import PendingInstitutionSerializer
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime
import json
from .models import PendingInstitution, Certificate
from django.shortcuts import get_object_or_404
from django.core.files.storage import default_storage
from concurrent.futures import ThreadPoolExecutor
import tempfile, os, json, csv, hashlib

from .helper import generate_certificate_pdf_local, process_single_entry
from .helper import upload_to_pinata, download_pdf_from_ipfs, merge_overlay, create_overlay

@csrf_exempt
def register_institution_request(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        description = request.POST.get('description')
        eth_address = request.POST.get('ethereum_address')
        logo = request.FILES.get('logo')

        # Check for duplicate request
        if PendingInstitution.objects.filter(name__iexact=name).exists():
            return JsonResponse({"error": "An institution with this name has already requested registration."}, status=400)
        
        if PendingInstitution.objects.filter(email__iexact=email).exists():
            return JsonResponse({"error": "This email has already been used to request registration."}, status=400)


        # Save to model (example assumes you have a model named InstitutionRequest)
        req = PendingInstitution.objects.create(
            name=name,
            email=email,
            description=description,
            ethereum_address=eth_address,
            logo=logo
        )

        return JsonResponse({"message": "Request submitted successfully."}, status=201)
    
    return JsonResponse({"error": "Invalid request method."}, status=400)

@api_view(['GET'])
def institution_requests(request):
    pending = PendingInstitution.objects.filter(approved=False)
    serializer = PendingInstitutionSerializer(pending, many=True)
    return Response(serializer.data)

@api_view(['POST'])
def approve_institution(request, institution_id):
    try:
        institution = PendingInstitution.objects.get(id=institution_id)
        institution.approved = True
        institution.save()
        return Response({'message': 'Institution approved'}, status=status.HTTP_200_OK)
    except PendingInstitution.DoesNotExist:
        return Response({'error': 'Institution not found'}, status=status.HTTP_404_NOT_FOUND)
    
@api_view(['GET'])
def approved_institutions(request):
    institutions = PendingInstitution.objects.filter(approved=True, revoked=False)
    serializer = PendingInstitutionSerializer(institutions, many=True)
    return Response(serializer.data)

@api_view(["POST"])
def revoke_institution(request, institution_id):
    try:
        institution = PendingInstitution.objects.get(id=institution_id)
        institution.revoked = True
        institution.save()
        return Response({'message': 'Institution approved'}, status=status.HTTP_200_OK)
    except PendingInstitution.DoesNotExist:
        return Response({'error': 'Institution not found'}, status=status.HTTP_404_NOT_FOUND)
    
@api_view(['GET'])
def get_institution_by_address(request):
    eth_address = request.GET.get("address")
    if not eth_address:
        return Response({"error": "Ethereum address is required"}, status=400)

    try:
        institution = get_object_or_404(PendingInstitution, ethereum_address__iexact=eth_address, approved=True, revoked=False)
        return Response({
            "id": institution.id,
            "name": institution.name,
        })
    except:
        return Response({"error": "Institution not found"}, status=404)

@csrf_exempt
def issue_certificate(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    if not request.body:
        return JsonResponse({"error": "Request body is empty"}, status=400)

    data = json.loads(request.body)

    name = data["student_name"]
    surname = data["student_surname"]
    reg_number = data["reg_number"]
    course = data["course"]
    degree_class = data["degree_class"]
    institution_id = data["institution_id"]
    date_issued = datetime.now().strftime("%Y-%m-%d")

    # 🔍 Fetch institution
    institution = get_object_or_404(PendingInstitution, id=institution_id)
    institution_name = institution.name
    institution_logo_path = institution.logo.path if institution.logo else None

    # 📄 Filename
    filename = f"{name}_{surname}_{course}.pdf".replace(" ", "_")
    pdf_path = os.path.join(tempfile.gettempdir(), filename)

    # 🧪 Step 1: Generate the clean certificate (no CID, no QR)
    generate_certificate_pdf_local(
        pdf_path,
        f"{name} {surname} {course}",
        course,
        degree_class,
        institution_name,
        institution_logo_path,
        verification_url=None,
        date_issued=date_issued,
        qr_mode="dummy",
    )

    # ☁️ Step 3: Upload clean file (preserves CID)
    uploaded_url = upload_to_pinata(pdf_path)

    # 💾 Step 4: Save certificate record
    Certificate.objects.create(
        student_name=name,
        student_surname=surname,
        student_regNumber=reg_number,
        course=course,
        degree_class=degree_class,
    )

    return JsonResponse({
        "message": "Certificate issued",
        "ipfs_url": uploaded_url,
    })

@csrf_exempt
def update_certificate_with_cid(request):
    data = json.loads(request.body)
    new_cid = data["new_cid"]

    # 1. Download original PDF
    pdf_path = download_pdf_from_ipfs(new_cid)

    # 2. Create overlay with new CID
    new_verification_url = f"https://gateway.pinata.cloud/ipfs/{new_cid}"
    overlay_buffer = create_overlay(new_verification_url, new_cid)

    # 3. Merge and return updated PDF
    final_pdf_path = merge_overlay(pdf_path, overlay_buffer)
    return FileResponse(open(final_pdf_path, "rb"), as_attachment=True, filename=f"updated_certificate.pdf")

#### mass upload
@csrf_exempt
def batch_upload_certificates(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    if not request.FILES.get("file") or not request.POST.get("institution_id"):
        return JsonResponse({"error": "CSV file and institution ID required"}, status=400)

    csv_file = request.FILES["file"]
    institution_id = request.POST["institution_id"]
    institution = PendingInstitution.objects.get(id=institution_id)

    decoded_file = csv_file.read().decode("utf-8").splitlines()
    reader = csv.DictReader(decoded_file)
    student_data = list(reader)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda entry: process_single_entry(entry, institution), student_data))

    return JsonResponse({"results": results}, safe=False)
