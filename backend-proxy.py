#!/usr/bin/env python3
"""
SMART on FHIR Backend Proxy
Solves CORS issues by proxying requests to Cerner FHIR server
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Cerner FHIR endpoints
CERNER_BASE_URL = "https://fhir-ehr-code.cerner.com/r4/ec2458f2-1e24-41c8-b71b-0e701af7583d"

@app.route('/proxy/<path:endpoint>')
def proxy_request(endpoint):
    """Proxy requests to Cerner FHIR server"""
    try:
        # Get the full URL
        url = f"{CERNER_BASE_URL}/{endpoint}"
        
        # Forward query parameters
        query_params = request.args.to_dict()
        
        # Forward headers (excluding host and origin)
        headers = dict(request.headers)
        headers.pop('Host', None)
        headers.pop('Origin', None)
        
        # Make the request to Cerner
        response = requests.get(url, params=query_params, headers=headers)
        
        # Return the response
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "SMART on FHIR Backend Proxy"})

if __name__ == '__main__':
    print("🚀 Starting SMART on FHIR Backend Proxy...")
    print("📡 Proxying requests to Cerner FHIR server")
    print("🌐 CORS enabled for all origins")
    print("🔗 Access at: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
