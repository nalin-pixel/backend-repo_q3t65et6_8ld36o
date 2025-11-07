import os
import base64
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Student, Payment, Test, Certificate

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "EPIC Test Backend Running"}

# Student registration with payment proof upload
@app.post("/registrations")
async def create_registration(
    npm: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    payment_proof: Optional[UploadFile] = File(None),
):
    if not npm or not name or not email:
        raise HTTPException(status_code=400, detail="Data tidak lengkap")

    # upsert student minimal info
    existing = db["student"].find_one({"npm": npm})
    if not existing:
        create_document("student", Student(npm=npm, name=name, email=email))
    else:
        db["student"].update_one({"npm": npm}, {"$set": {"name": name, "email": email, "updated_at": datetime.now(timezone.utc)}})

    file_name = None
    file_mime = None
    file_b64 = None

    if payment_proof is not None:
        file_mime = payment_proof.content_type or "application/octet-stream"
        if file_mime not in ["image/jpeg", "image/png", "application/pdf"]:
            raise HTTPException(status_code=400, detail="Format file tidak didukung. Gunakan JPG/PNG/PDF")
        raw = await payment_proof.read()
        # store as base64 string for demo. In production, use object storage.
        file_b64 = base64.b64encode(raw).decode("utf-8")
        file_name = payment_proof.filename

    pay = Payment(
        npm=npm,
        name=name,
        email=email,
        file_name=file_name,
        file_mime=file_mime,
        file_data_b64=file_b64,
        status='pending'
    )
    pid = create_document("payment", pay)

    return {"message": "Registrasi tersimpan", "payment_id": pid}

# Admin: list pending payments
@app.get("/admin/pending")
def list_pending():
    payments = get_documents("payment", {"status": "pending"})
    # map simple info and downloadable data link
    out = []
    for p in payments:
        p["_id"] = str(p.get("_id"))
        file_url = None
        if p.get("file_data_b64") and p.get("file_mime"):
            file_url = f"data:{p['file_mime']};base64,{p['file_data_b64']}"
        out.append({
            "_id": p["_id"],
            "npm": p.get("npm"),
            "name": p.get("name"),
            "email": p.get("email"),
            "file_url": file_url,
        })
    return {"payments": out}

class VerifyBody(BaseModel):
    status: str

# Admin: verify payment
@app.post("/admin/verify/{payment_id}")
def verify_payment(payment_id: str, body: VerifyBody):
    if body.status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status tidak valid")
    res = db["payment"].update_one(
        {"_id": __import__("bson").ObjectId(payment_id)},
        {"$set": {"status": body.status, "verified_at": datetime.now(timezone.utc)}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Payment tidak ditemukan")
    return {"ok": True}

class ResultBody(BaseModel):
    npm: str
    attempt: int
    score: float
    status: str

# Admin: submit test result; if pass, create certificate pseudo URL
@app.post("/admin/result")
def submit_result(body: ResultBody):
    if body.status not in ["pass", "fail"]:
        raise HTTPException(status_code=400, detail="Status hasil tidak valid")

    create_document("test", Test(npm=body.npm, attempt=body.attempt, score=body.score, status=body.status, taken_at=datetime.now(timezone.utc)))

    cert_url = None
    if body.status == "pass":
        # Simple PDF data URL as placeholder certificate; real app would generate a PDF file
        pdf_content = f"SERTIFIKAT EPIC\nNPM: {body.npm}\nAttempt: {body.attempt}\nSkor: {body.score}\nTanggal: {datetime.now().strftime('%d-%m-%Y')}\n".encode("utf-8")
        b64 = base64.b64encode(pdf_content).decode("utf-8")
        cert_url = f"data:application/pdf;base64,{b64}"
        create_document("certificate", Certificate(npm=body.npm, attempt=body.attempt, issued_at=datetime.now(timezone.utc)))

    return {"ok": True, "certificate_url": cert_url}

# Student history endpoint
@app.get("/students/{npm}/history")
def student_history(npm: str):
    tests = get_documents("test", {"npm": npm})
    # sort by attempt
    tests_sorted = sorted(tests, key=lambda x: x.get("attempt", 0))

    out = []
    for t in tests_sorted:
        t_id = str(t.get("_id"))
        status = t.get("status")
        cert = db["certificate"].find_one({"npm": npm, "attempt": t.get("attempt")})
        cert_url = None
        if status == "pass" and cert:
            # regenerate a very simple PDF content link (stateless)
            pdf_content = f"SERTIFIKAT EPIC\nNPM: {npm}\nAttempt: {t.get('attempt')}\nSkor: {t.get('score')}\nTanggal: {datetime.now().strftime('%d-%m-%Y')}\n".encode("utf-8")
            b64 = base64.b64encode(pdf_content).decode("utf-8")
            cert_url = f"data:application/pdf;base64,{b64}"
        out.append({
            "id": t_id,
            "attempt": t.get("attempt"),
            "score": t.get("score"),
            "status": status,
            "taken_at": t.get("taken_at"),
            "certificate_url": cert_url,
        })
    return {"tests": out}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            collections = db.list_collection_names()
            response["collections"] = collections[:10]
            response["database"] = "✅ Connected & Working"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
