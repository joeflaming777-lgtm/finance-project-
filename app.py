import os
from flask import Flask, request, jsonify, send_file
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

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
            'https://openrouter.ai/api/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                'HTTP-Referer': 'https://finbot.app',
                'X-Title': 'FinBot Finance Tracker'
            },
            json={
                'model': 'anthropic/claude-sonnet-4-5',
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