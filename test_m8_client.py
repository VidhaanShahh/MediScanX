from fastapi.testclient import TestClient
import os

# Set up test DB environment
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.main import app
from app.models.models import Base
from app.db.database import engine, SessionLocal

# Create tables
Base.metadata.create_all(bind=engine)

client = TestClient(app)

def run():
    import uuid
    username = f"user_{uuid.uuid4().hex[:8]}"
    r_reg = client.post('/api/auth/register', json={'username': username, 'password': 'password123'})
    print("Register:", r_reg.text)
    r_log = client.post('/api/auth/login', data={'username': username, 'password': 'password123'})
    print("Login:", r_log.text)
    token = r_log.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    # Patient & case
    pat_id = client.post('/api/patients/', json={'age': 50, 'sex': 'M'}, headers=headers).json()['id']
    case_id = client.post('/api/cases', json={'patient_id': pat_id}, headers=headers).json()['id']

    # Upload mock image
    with open('test_img.png', 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x80\x00\x00\x00\x80\x08\x02\x00\x00\x00\x06\x1e\x83\x80\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\x0c\x83\xa3\x12\x00\x00\x00\x00IEND\xaeB`\x82')
    with open('test_img.png', 'rb') as f:
        client.post(f'/api/cases/{case_id}/upload-image', files={'file': ('test_img.png', f, 'image/png')}, headers=headers)

    # Upload mock ECG
    ecg_csv = 'time,I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6\n' + '\n'.join([','.join(['0.0']*13) for _ in range(1000)])
    with open('test_ecg.csv', 'w') as f:
        f.write(ecg_csv)
    with open('test_ecg.csv', 'rb') as f:
        client.post(f'/api/cases/{case_id}/upload-ecg', files={'file': ('test_ecg.csv', f, 'text/csv')}, headers=headers)

    # Analyze
    r = client.post(f'/api/cases/{case_id}/analyze', headers=headers)
    print('Analysis Status Code:', r.status_code)
    res = r.json()
    print('Explanations Count:', len(res.get('explanations', [])) if res.get('explanations') else 0)
    for exp in res.get('explanations', []):
        exists = os.path.exists(exp['file_path'])
        print(f"- {exp['explanation_type']} for {exp['modality']} (target: {exp['target_class']}) exists: {exists}")

if __name__ == '__main__':
    run()
