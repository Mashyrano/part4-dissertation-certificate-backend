import io, os, qrcode, requests
import time
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import black, blue
from reportlab.lib.utils import ImageReader
import os
import tempfile
from PyPDF2 import PdfReader, PdfWriter, PageObject
from .models import Certificate
from datetime import datetime
import json
PINATA_JWT = os.getenv("PINATA_JWT")

def upload_to_pinata(file_path):
    print("PINATA_JWT loaded:", PINATA_JWT)  # 🔍 TEMPORARY DEBUG
    if not PINATA_JWT:
        raise Exception("Pinata JWT not found in environment variables")
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {
        "Authorization": f"{PINATA_JWT}",
    }
    with open(file_path, "rb") as f:
        files = {'file': (os.path.basename(file_path), f)}
        response = requests.post(url, headers=headers, files=files)

    if response.status_code == 200:
        return f"https://gateway.pinata.cloud/ipfs/{response.json()['IpfsHash']}"
    else:
        raise Exception(f"Pinata upload failed: {response.text}")

def generate_certificate_pdf_local(pdf_path, student_name, course_name, degree_class,
                                   institution_name, institution_logo, verification_url,
                                   date_issued, qr_mode="real"):
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    pdf.setTitle("Certificate of Achievement")
    pdf.setStrokeColor(black)
    pdf.setLineWidth(4)
    pdf.rect(30, 30, width - 60, height - 60)

    pdf.setFont("Helvetica-Bold", 28)
    pdf.setFillColor(blue)
    pdf.drawCentredString(width / 2, height - 120, "Certificate of Achievement")

    pdf.setFont("Helvetica", 16)
    pdf.setFillColor(black)
    pdf.drawCentredString(width / 2, height - 160, "This certificate is proudly presented to:")

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(width / 2, height - 200, student_name)

    pdf.setFont("Helvetica", 18)
    pdf.drawCentredString(width / 2, height - 240, f"For successfully completing the course: {course_name}")

    pdf.setFont("Helvetica-Bold", 18)
    pdf.setFillColor(blue)
    pdf.drawCentredString(width / 2, height - 270, f"Degree Classification: {degree_class}")

    pdf.setFont("Helvetica-Oblique", 16)
    pdf.setFillColor(black)
    pdf.drawCentredString(width / 2, height - 310, f"Issued by: {institution_name}")

    # 🔲 QR Code Area
    if qr_mode == "real" and verification_url:
        cid = verification_url.split("/")[-1]
        pdf.setFont("Courier", 12)
        pdf.drawCentredString(width / 2, height - 340, f"ipfs-CID: {cid}")
        qr = qrcode.make(verification_url)
        qr_path = "temp_qr.png"
        qr.save(qr_path)
        pdf.drawInlineImage(qr_path, width - 180, 50, width=100, height=100)
        os.remove(qr_path)
    elif qr_mode == "dummy":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            qrcode.make("DUMMY").save(tmp.name)
            pdf.drawInlineImage(tmp.name, width - 180, 50, width=100, height=100)
        os.remove(tmp.name)

    # 🖋 Date + Signature
    pdf.setFont("Helvetica", 12)
    pdf.drawString(100, 130, f"Date Issued: {date_issued}")
    pdf.setLineWidth(1)
    pdf.line(100, 100, 300, 100)
    pdf.drawString(150, 80, "Authorized Signature")

    if institution_logo:
        try:
            pdf.drawImage(ImageReader(institution_logo), 50, height - 150, width=100, height=100, mask='auto')
        except Exception as e:
            print("Logo load error:", e)

    pdf.save()
    buffer.seek(0)

    with open(pdf_path, "wb") as f:
        f.write(buffer.getvalue())

# new metadata
def generate_metadata_dict(name, surname, reg_number, course, degree_class, institution_name, date_issued):
    return {
        "student_name": name,
        "student_surname": surname,
        "registration_number": reg_number,
        "course": course,
        "degree_class": degree_class,
        "institution": institution_name,
        "date_issued": date_issued,
    }

def upload_json_to_pinata(metadata: dict) -> str:
    url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    headers = {
        "Authorization": PINATA_JWT,         
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, data=json.dumps(metadata))
    if response.status_code == 200:
        return f"https://gateway.pinata.cloud/ipfs/{response.json()['IpfsHash']}"
    else:
        raise Exception(f"Pinata JSON upload failed: {response.text}")

def download_pdf_from_ipfs(cid):
    gateways = [
        f"https://ipfs.io/ipfs/{cid}",
        f"https://cloudflare-ipfs.com/ipfs/{cid}",
        f"https://gateway.pinata.cloud/ipfs/{cid}",
        f"https://{cid}.ipfs.dweb.link",
    ]

    for url in gateways:
        try:
            print(f"⏳ Trying PDF gateway: {url}")
            response = requests.get(url, timeout=15)
            response.raise_for_status()

            temp_path = os.path.join(tempfile.gettempdir(), f"{cid}.pdf")
            with open(temp_path, "wb") as f:
                f.write(response.content)

            print(f"✅ Fetched PDF from: {url}")
            return temp_path

        except Exception as e:
            print(f"❌ Gateway {url} failed: {e}")
            continue

    raise Exception("All IPFS gateways failed to retrieve the PDF.")


def create_overlay(cid, reg_number):
    # Build a verification URL that points to your frontend (with query params)
    qr_url = (
        "https://dissertationtest-cw6eyx69o-marshalls-projects-57ca710a.vercel.app"
        f"/verify-certificate?reg_number={reg_number}&cid={cid}"
    )

    # Create an in-memory PDF (single page) containing the QR + text
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Courier", 12)
    # c.drawCentredString(300, 450, f"IPFS CID: {cid}")
    # c.drawCentredString(300, 430, f"Reg Number: {reg_number}")

    # Generate and embed the QR code
    qr = qrcode.make(qr_url)
    tmp_qr_path = os.path.join(tempfile.gettempdir(), "qr_temp.png")
    qr.save(tmp_qr_path)
    c.drawInlineImage(tmp_qr_path, 450, 50, width=100, height=100)
    os.remove(tmp_qr_path)

    c.save()
    buffer.seek(0)
    return buffer


def merge_overlay(original_pdf_path, overlay_buffer):
    reader = PdfReader(original_pdf_path)
    overlay_reader = PdfReader(overlay_buffer)  # this reads from BytesIO
    writer = PdfWriter()

    for i, page in enumerate(reader.pages):
        if i == 0:
            # Merge overlay only onto page 1
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    output_path = original_pdf_path.replace(".pdf", "_updated.pdf")
    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path

def process_single_entry(entry, institution):
    start = time.time()
    try:
        name = entry["student_name"]
        surname = entry["student_surname"]
        reg_number = entry["reg_number"]
        course = entry["course"]
        degree_class = entry["degree_class"]
        date_issued = datetime.now().strftime("%Y-%m-%d")

        filename = f"{name}_{surname}_{course}.pdf".replace(" ", "_")
        pdf_path = os.path.join(tempfile.gettempdir(), filename)

        generate_certificate_pdf_local(
            pdf_path,
            f"{name} {surname} {course}",
            course,
            degree_class,
            institution.name,
            institution.logo.path if institution.logo else None,
            verification_url=None,
            date_issued=date_issued,
            qr_mode="dummy",
        )

        # Upload PDF to IPFS
        pdf_ipfs_url = upload_to_pinata(pdf_path)

        # Create metadata
        metadata = {
            "student_name": name,
            "student_surname": surname,
            "reg_number": reg_number,
            "course": course,
            "degree_class": degree_class,
            "institution": institution.name,
            "date_issued": date_issued,
            "pdf_ipfs_url": pdf_ipfs_url,
        }

        # Upload metadata to IPFS
        metadata_ipfs_url = upload_json_to_pinata(metadata)

        # Save to DB (optional)
        Certificate.objects.create(
            student_name=name,
            student_surname=surname,
            student_regNumber=reg_number,
            course=course,
            degree_class=degree_class,
        )

        print(f"⏱️ Processed {reg_number} in {time.time() - start:.2f}s")
        return {
            "reg_number": reg_number,
            "cid": metadata_ipfs_url.split("/")[-1],
            "status": "success"
        }

    except Exception as e:
        return {
            "reg_number": entry.get("reg_number", "N/A"),
            "status": f"error: {str(e)}"
        }
