import requests

try:
    response = requests.post(
        'http://127.0.0.1:5000/api/chat',
        json={'messages': [
            {'role': 'system', 'content': 'You are FinBot...'},
            {'role': 'user', 'content': 'what is my balance?'}
        ]}
    )
    print("Status:", response.status_code)
    print("Response:", response.text)
except Exception as e:
    print("Error:", e)
