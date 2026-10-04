import sys, os
from pathlib import Path
import uuid
import numpy as np

from app.db.database import SessionLocal, engine
from app.models.models import Base, User, Patient, Case, ImagingStudy, ECGRecord, Explanation

# Create tables
Base.metadata.create_all(bind=engine)

# Get session
db = SessionLocal()

# Setup test data
u = User(email=f"tester_{uuid.uuid4().hex[:4]}@example.com", password_hash="xyz", role="admin")
db.add(u)
p = Patient(anon_code=f"P_{uuid.uuid4().hex[:4]}", age=45, sex="F")
db.add(p)
db.commit()

c = Case(patient_id=p.id, created_by=u.id)
db.add(c)
db.commit()

# Create dummy files
img_path = Path("test_real_img.png")
if not img_path.exists():
    import cv2
    cv2.imwrite("test_real_img.png", np.zeros((224, 224, 3), dtype=np.uint8))

ecg_path = Path("test_real_ecg.csv")
if not ecg_path.exists():
    ecg_csv = 'I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6\n' + '\n'.join([','.join(['0.0']*12) for _ in range(1000)])
    ecg_path.write_text(ecg_csv)

img = ImagingStudy(case_id=c.id, original_filename="test.png", file_path="test_real_img.png", sha256="hash1")
ecg = ECGRecord(case_id=c.id, original_filename="test.csv", file_path="test_real_ecg.csv", sha256="hash2", sampling_rate=100.0)
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
    for e in resp.explanations:
        exists = os.path.exists(e.file_path)
        print(f"  {e.modality} - {e.explanation_type} - {e.target_class}: {exists} ({e.file_path})")
    
    # Check DB
    exps = db.query(Explanation).all()
    print(f"DB Explanation rows: {len(exps)}")

except Exception as e:
    import traceback
    traceback.print_exc()

db.close()
