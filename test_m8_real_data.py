import sys, os
from pathlib import Path
import uuid

from app.db.database import SessionLocal, engine
from app.models.models import Base, User, Patient, Case, ImagingStudy, ECGRecord, Explanation

# Create tables
Base.metadata.create_all(bind=engine)

db = SessionLocal()

u = User(email=f"tester_{uuid.uuid4().hex[:4]}@example.com", password_hash="xyz", role="admin")
db.add(u)
p = Patient(anon_code=f"P_{uuid.uuid4().hex[:4]}", age=45, sex="F")
db.add(p)
db.commit()

c = Case(patient_id=p.id, created_by=u.id)
db.add(c)
db.commit()

# Real Data Paths (absolute)
base_path = Path("C:/Users/Vidhaan/OneDrive/Desktop/MediScanX/data")
img_path = base_path / "ChestX-ray14" / "images" / "00000009_000.png"
ecg_path = base_path / "PTB-XL" / "records100" / "records100" / "00000" / "00001_lr.dat"

img = ImagingStudy(case_id=c.id, original_filename="00000009_000.png", file_path=str(img_path), sha256="img_hash")
ecg = ECGRecord(case_id=c.id, original_filename="00001_lr.dat", file_path=str(ecg_path), sha256="ecg_hash", sampling_rate=100.0)
db.add(img)
db.add(ecg)
db.commit()

# Run Analyze
from app.api.analysis import analyze_case
try:
    resp = analyze_case(case_id=c.id, db=db, current_user=u)
    print("SUCCESS")
    print(f"Explanations: {len(resp.explanations) if resp.explanations else 0}")
    print("Messages:", resp.message)
    
    print("\n--- Final Output ---")
    for e in resp.explanations:
        exists = os.path.exists(e.file_path)
        size = os.path.getsize(e.file_path) if exists else 0
        from PIL import Image
        dims = "N/A"
        if exists and size > 0:
            with Image.open(e.file_path) as im:
                dims = f"{im.width}x{im.height}"
        print(f"Modality: {e.modality}")
        print(f"File: {e.file_path}")
        print(f"Readable: {exists and size > 0}")
        print(f"Dimensions: {dims}")
        print("---")
        
    exps = db.query(Explanation).filter_by(prediction_id=e.prediction_id).first()
    print(f"DB Linkage: {'PASS' if exps else 'FAIL'}")

except Exception as e:
    import traceback
    traceback.print_exc()

db.close()
