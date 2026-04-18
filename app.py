import os
from flask import Flask, request, jsonify, send_file
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def index():
    return send_file("finance-chatbot (4).html")

@app.route('/api/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json
        if not data:
            return jsonify({"error": {"message": "Invalid request payload"}}), 400

        messages = data.get("messages", [])
        
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {GROQ_API_KEY}'
            },
            json={
                'model': 'llama-3.1-8b-instant',
                'max_tokens': 1000,
                'messages': messages
            }
        )
        
        return jsonify(response.json()), response.status_code

    except Exception as e:
        print(f"Error handling chat request: {e}")
        return jsonify({"error": {"message": "Internal server error"}}), 500

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)