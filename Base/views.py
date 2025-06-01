from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
import requests
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
from django.http import HttpResponse

from .helper import generate_certificate_pdf_local, process_single_entry
from .helper import upload_to_pinata, download_pdf_from_ipfs, merge_overlay, create_overlay
from .helper import upload_json_to_pinata

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

@csrf_exempt
@api_view(['GET'])
def institution_requests(request):
    pending = PendingInstitution.objects.filter(approved=False)
    serializer = PendingInstitutionSerializer(pending, many=True)
    return Response(serializer.data)

@csrf_exempt
@api_view(['POST'])
def approve_institution(request, institution_id):
    try:
        institution = PendingInstitution.objects.get(id=institution_id)
        institution.approved = True
        institution.save()
        return Response({'message': 'Institution approved'}, status=status.HTTP_200_OK)
    except PendingInstitution.DoesNotExist:
        return Response({'error': 'Institution not found'}, status=status.HTTP_404_NOT_FOUND)

@csrf_exempt   
@api_view(['GET'])
def approved_institutions(request):
    institutions = PendingInstitution.objects.filter(approved=True, revoked=False)
    serializer = PendingInstitutionSerializer(institutions, many=True)
    return Response(serializer.data)

@csrf_exempt
@api_view(["POST"])
def revoke_institution(request, institution_id):
    try:
        institution = PendingInstitution.objects.get(id=institution_id)
        institution.revoked = True
        institution.save()
        return Response({'message': 'Institution approved'}, status=status.HTTP_200_OK)
    except PendingInstitution.DoesNotExist:
        return Response({'error': 'Institution not found'}, status=status.HTTP_404_NOT_FOUND)

@csrf_exempt 
@api_view(['GET'])
def get_institution_by_address(request):
    eth_address = request.GET.get("address")
    if not eth_address:
        return Response({"error": "Ethereum address is required"}, status=400)

    try:
        institution = PendingInstitution.objects.get(
            ethereum_address__iexact=eth_address,
            approved=True,
            revoked=False
        )
        return Response({
            "id": institution.id,
            "name": institution.name,
        })
    except PendingInstitution.DoesNotExist:
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

    # 🧪 Step 1: Generate PDF with dummy QR code (no IPFS CID yet)
    generate_certificate_pdf_local(
        pdf_path,
        f"{name} {surname}",
        course,
        degree_class,
        institution_name,
        institution_logo_path,
        verification_url=None,
        date_issued=date_issued,
        qr_mode="dummy",
    )

    # ☁️ Step 2: Upload the PDF to IPFS
    pdf_ipfs_url = upload_to_pinata(pdf_path)

    # 🧾 Step 3: Create metadata JSON
    metadata = {
        "student_name": name,
        "student_surname": surname,
        "reg_number": reg_number,
        "course": course,
        "degree_class": degree_class,
        "institution": institution_name,
        "date_issued": date_issued,
        "pdf_ipfs_url": pdf_ipfs_url,
    }

    # ☁️ Step 4: Upload metadata JSON to IPFS
    metadata_ipfs_url = upload_json_to_pinata(metadata)

    # 💾 Step 5: Save the certificate to the database (optional)
    Certificate.objects.create(
        student_name=name,
        student_surname=surname,
        student_regNumber=reg_number,
        course=course,
        degree_class=degree_class,
    )

    return JsonResponse({
        "message": "Certificate issued",
        "ipfs_url": metadata_ipfs_url,  # This is the CID to store on-chain
        "pdf_url": pdf_ipfs_url,
    })

@csrf_exempt
def update_certificate_with_cid(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    try:
        data = json.loads(request.body)
        new_cid = data["new_cid"]

        # Step 1: Download original certificate PDF from IPFS
        pdf_path = download_pdf_from_ipfs(new_cid)

        # Step 2: Fetch metadata from IPFS to get reg number
        json_url = f"https://gateway.pinata.cloud/ipfs/{new_cid}"
        response = requests.get(json_url)
        if response.status_code != 200:
            raise Exception("Could not fetch metadata JSON")
        reg_number = response.json().get("reg_number")
        if not reg_number:
            raise Exception("Missing reg_number in metadata")

        # Step 3: Create overlay with QR code
        overlay_buffer = create_overlay(new_cid, reg_number)

        # Step 4: Merge and return final certificate
        final_pdf_path = merge_overlay(pdf_path, overlay_buffer)

        return FileResponse(open(final_pdf_path, "rb"), as_attachment=True, filename="updated_certificate.pdf")

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

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

    # ✅ Prepare downloadable CSV with IPFS CIDs
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="batch_upload_results.csv"'

    writer = csv.writer(response)
    writer.writerow(["student_name", "student_surname", "reg_number", "course", "degree_class", "ipfs_cid", "status"])

    for r in results:
        entry = next((e for e in student_data if e["reg_number"] == r["reg_number"]), {})
        writer.writerow([
            entry.get("student_name", ""),
            entry.get("student_surname", ""),
            entry.get("reg_number", ""),
            entry.get("course", ""),
            entry.get("degree_class", ""),
            r.get("cid", ""),
            r.get("status", "")
        ])

    return response

