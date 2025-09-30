#!/usr/bin/env python3
"""
SMART on FHIR Backend Proxy
Solves CORS issues by proxying requests to Cerner FHIR server
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json
import time

app = Flask(__name__)
# Allow Authorization header in CORS preflight so the browser will send it
CORS(app, resources={r"/proxy/*": {"origins": "*", "allow_headers": ["Authorization", "Content-Type"], "expose_headers": ["Authorization"]}})

# Cerner FHIR endpoints
# Default Cerner base; proxy can also target other allowed FHIR bases (e.g., SMART Health IT)
CERNER_BASE_URL = "https://fhir-ehr-code.cerner.com/r4/ec2458f2-1e24-41c8-b71b-0e701af7583d"
ALLOWED_BASES = {
    CERNER_BASE_URL,
    # SMART Health IT R4 sandbox base
    "https://launch.smarthealthit.org/v/r4/fhir"
}

@app.route('/proxy/<path:endpoint>')
def proxy_request(endpoint):
    """Proxy requests to Cerner FHIR server"""
    try:
        # Choose upstream base: default Cerner, or `base` query override if allowed
        upstream_base = request.args.get('base', CERNER_BASE_URL)
        if upstream_base not in ALLOWED_BASES:
            upstream_base = CERNER_BASE_URL
        # Build full upstream URL
        url = f"{upstream_base}/{endpoint}"
        
        # Forward query parameters
        query_params = request.args.to_dict()
        # Remove internal-only controls not meant for upstream
        query_params.pop('base', None)
        
        # Forward only necessary headers
        incoming = dict(request.headers)
        headers = {
            'Authorization': incoming.get('Authorization', ''),
            'Accept': incoming.get('Accept', 'application/fhir+json')
        }
        
        # Debug log to verify Authorization header presence
        auth_present = bool(headers.get('Authorization'))
        print(f"[proxy] -> upstream {url} | Authorization header present: {auth_present}")
        
        # Make the request to Cerner with simple retries on transient 5xx
        attempts = 0
        last_exc = None
        while attempts < 3:
            attempts += 1
            try:
                response = requests.get(url, params=query_params, headers=headers, timeout=20)
                print(f"[proxy] upstream status: {response.status_code}")
                if response.status_code in (502, 503, 504):
                    time.sleep(1.5 * attempts)
                    continue
                break
            except requests.RequestException as e:
                last_exc = e
                print(f"[proxy] upstream exception: {e}")
                time.sleep(1.0 * attempts)
        
        if 'response' not in locals():
            return jsonify({"error": "upstream_unreachable", "details": str(last_exc)}), 502
        
        # Return upstream body and status verbatim (helpful to see 403 details)
        return Response(response.content, status=response.status_code, content_type=response.headers.get('Content-Type', 'application/json'))
        
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
