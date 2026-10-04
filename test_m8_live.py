import requests, os

def run():
    # Create user & get token
    requests.post('http://127.0.0.1:8002/api/auth/register', json={'username': 'm8_test_user_v3', 'password': 'password123'})
    token = requests.post('http://127.0.0.1:8002/api/auth/login', data={'username': 'm8_test_user_v3', 'password': 'password123'}).json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    # Create patient & case
    pat_id = requests.post('http://127.0.0.1:8002/api/patients/', json={'age': 50, 'sex': 'M'}, headers=headers).json()['id']
    case_id = requests.post('http://127.0.0.1:8002/api/cases', json={'patient_id': pat_id}, headers=headers).json()['id']

    # Upload mock image
    with open('test_img.png', 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x80\x00\x00\x00\x80\x08\x02\x00\x00\x00\x06\x1e\x83\x80\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\x0c\x83\xa3\x12\x00\x00\x00\x00IEND\xaeB`\x82')
    requests.post(f'http://127.0.0.1:8002/api/cases/{case_id}/upload-image', files={'file': ('test_img.png', open('test_img.png', 'rb'), 'image/png')}, headers=headers)

    # Upload mock ECG
    ecg_csv = 'time,I,II,III,aVR,aVL,aVF,V1,V2,V3,V4,V5,V6\n' + '\n'.join([','.join(['0.0']*13) for _ in range(1000)])
    with open('test_ecg.csv', 'w') as f:
        f.write(ecg_csv)
    requests.post(f'http://127.0.0.1:8002/api/cases/{case_id}/upload-ecg', files={'file': ('test_ecg.csv', open('test_ecg.csv', 'rb'), 'text/csv')}, headers=headers)

    # Analyze
    r = requests.post(f'http://127.0.0.1:8002/api/cases/{case_id}/analyze', headers=headers)
    print('Analysis Status Code:', r.status_code)
    res = r.json()
    print('Explanations Count:', len(res.get('explanations', [])) if res.get('explanations') else 0)
    for exp in res.get('explanations', []):
        exists = os.path.exists(exp['file_path'])
        print(f"- {exp['explanation_type']} for {exp['modality']} (target: {exp['target_class']}) exists: {exists}")

if __name__ == '__main__':
    run()
