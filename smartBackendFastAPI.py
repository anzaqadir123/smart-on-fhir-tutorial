#!/usr/bin/env python3
"""
Cerner Backend Services API (FastAPI)
Performs client credentials flow using JWT assertions to authenticate with Cerner FHIR.
This is the production-ready backend service that keeps private keys secure.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import requests
import jwt
import json
import time
import os
from typing import Optional
from pathlib import Path
import base64
import uuid
from typing import Union
try:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
except Exception:
    load_pem_private_key = None  # cryptography optional; required for encrypted PEMs
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    # dotenv is optional; if unavailable, env vars can still be set by the shell
    pass

app = FastAPI(title="Cerner Backend Services API")

# Enable CORS for all origins (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# CERNER BACKEND SERVICES CONFIGURATION
# ============================================================================
# Update these values to match your Cerner app registration

CERNER_CLIENT_ID = os.getenv("CERNER_CLIENT_ID", "cbebea6b-836f-4121-82dc-bbd0c712dd81")
CERNER_TOKEN_URL = os.getenv(
    "CERNER_TOKEN_URL",
    "https://authorization.cerner.com/tenants/ec2458f2-1e24-41c8-b71b-0e701af7583d/protocols/oauth2/profiles/smart-v1/token"
)
CERNER_FHIR_BASE = os.getenv(
    "CERNER_FHIR_BASE",
    "https://fhir-ehr-code.cerner.com/r4/ec2458f2-1e24-41c8-b71b-0e701af7583d"
)

# Key ID (KID) - must match the key registered with Cerner
KID = os.getenv("CERNER_KID", "1EBx0b3f8kKtQAW7NdbiA7Tx17yuyxWa")

# Private key: prefer env var (CERNER_PRIVATE_KEY). If missing, try file path.
PRIVATE_KEY: Union[str, None] = os.getenv("CERNER_PRIVATE_KEY")
PRIVATE_KEY_OBJ = None  # When using encrypted PEMs, hold a key object

# Allow base64-encoded private key as alternative
if not PRIVATE_KEY:
    PRIVATE_KEY_B64 = os.getenv("CERNER_PRIVATE_KEY_B64")
    if PRIVATE_KEY_B64:
        try:
            PRIVATE_KEY = base64.b64decode(PRIVATE_KEY_B64).decode("utf-8")
        except Exception as exc:
            raise ValueError(f"Failed to decode CERNER_PRIVATE_KEY_B64: {exc}")

# Fallback to file path (absolute or relative)
if not PRIVATE_KEY:
    PRIVATE_KEY_PATH = os.getenv("CERNER_PRIVATE_KEY_PATH", "private_key.pem")
    candidate_path = Path(PRIVATE_KEY_PATH)
    if not candidate_path.is_file():
        # try relative to project root (file location)
        project_root = Path(__file__).resolve().parent
        alt_path = project_root / PRIVATE_KEY_PATH
        if alt_path.is_file():
            candidate_path = alt_path
    if not candidate_path.is_file():
        raise ValueError(
            "Private key not provided. Set one of: "
            "CERNER_PRIVATE_KEY (PEM contents), "
            "CERNER_PRIVATE_KEY_B64 (base64 PEM), or "
            f"CERNER_PRIVATE_KEY_PATH (file path, tried '{PRIVATE_KEY_PATH}')."
        )
    PRIVATE_KEY = candidate_path.read_text()

# If the key appears to be encrypted, or a passphrase is provided, try to load with cryptography
PASSPHRASE = os.getenv("CERNER_PRIVATE_KEY_PASSPHRASE")
if (PASSPHRASE or (PRIVATE_KEY and "ENCRYPTED" in PRIVATE_KEY)) and load_pem_private_key is not None:
    try:
        PRIVATE_KEY_OBJ = load_pem_private_key(
            PRIVATE_KEY.encode("utf-8"),
            password=None if not PASSPHRASE else PASSPHRASE.encode("utf-8")
        )
    except Exception as exc:
        raise ValueError(
            f"Failed to load encrypted private key. Ensure CERNER_PRIVATE_KEY_PASSPHRASE is correct. Error: {exc}"
        )

# ============================================================================
# TOKEN CACHE
# ============================================================================
# Cache access tokens to avoid unnecessary token requests
_token_cache = {
    "token": None,
    "expires_at": 0,
    "scope": None
}


def get_access_token(scope: str = "system/Patient.read system/Observation.read") -> str:
    """
    Get or refresh access token using client credentials flow.
    
    Args:
        scope: Space-separated list of system/* scopes (e.g., "system/Patient.read")
    
    Returns:
        Access token string
    """
    # Return cached token if still valid (with 60 second buffer)
    if (
        _token_cache["token"] 
        and time.time() < _token_cache["expires_at"] - 60
        and _token_cache["scope"] == scope
    ):
        print(f"[token] Using cached token (expires in {int(_token_cache['expires_at'] - time.time())}s)")
        return _token_cache["token"]
    
    print("[token] Requesting new access token...")
    
    # Create JWT client assertion
    now = int(time.time())
    payload = {
        "iss": CERNER_CLIENT_ID,      # Issuer = client_id
        "sub": CERNER_CLIENT_ID,      # Subject = client_id
        "aud": CERNER_TOKEN_URL,       # Audience = token endpoint
        "exp": now + 300,              # Expires in 5 minutes
        "iat": now,                    # Issued at
        "jti": str(uuid.uuid4())       # Unique token ID
    }
    
    header = {
        "alg": "RS384",
        "typ": "JWT",
        "kid": KID  # Key ID registered with Cerner
    }
    
    try:
        # Sign JWT with private key using RS384 algorithm
        client_assertion = jwt.encode(
            payload,
            PRIVATE_KEY_OBJ if PRIVATE_KEY_OBJ is not None else PRIVATE_KEY,
            algorithm="RS384",
            headers=header
        )
        
        print(f"[token] JWT created: {client_assertion[:50]}...")
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create JWT: {str(e)}"
        )
    
    # Exchange JWT for access token
    try:
        response = requests.post(
            CERNER_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "scope": scope,
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": client_assertion
            },
            timeout=10
        )
        
        if response.status_code != 200:
            error_detail = response.text
            print(f"[token] Token request failed: {response.status_code} - {error_detail}")
            raise HTTPException(
                status_code=500,
                detail=f"Token request failed: {error_detail}"
            )
        
        token_data = response.json()
        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        
        # Cache token
        _token_cache["token"] = access_token
        _token_cache["expires_at"] = time.time() + expires_in
        _token_cache["scope"] = scope
        
        print(f"[token] ✅ Token obtained (expires in {expires_in}s)")
        return access_token
        
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Token endpoint unreachable: {str(e)}"
        )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/health")
def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Cerner Backend Services API",
        "client_id": CERNER_CLIENT_ID[:8] + "..." if CERNER_CLIENT_ID else None
    }


@app.get("/cerner/patient/{patient_id}")
def get_patient_from_cerner(patient_id: str):
    """
    Fetch a Patient resource from Cerner using backend services authentication.
    
    Args:
        patient_id: FHIR Patient resource ID
    
    Returns:
        Patient resource (FHIR JSON)
    """
    print(f"[api] Fetching Patient/{patient_id} from Cerner")
    
    try:
        # Get access token (will create JWT and exchange if needed)
        token = get_access_token("system/Patient.read")
        
        # Build FHIR URL
        url = f"{CERNER_FHIR_BASE}/Patient/{patient_id}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json"
        }
        
        print(f"[api] GET {url}")
        
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code != 200:
            error_detail = response.text
            print(f"[api] Request failed: {response.status_code} - {error_detail}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Cerner API error: {error_detail}"
            )
        
        patient_data = response.json()
        print(f"[api] ✅ Patient retrieved: {patient_data.get('id')}")
        
        return patient_data
        
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cerner FHIR server unreachable: {str(e)}"
        )


@app.get("/cerner/patient/{patient_id}/observations")
def get_patient_observations(patient_id: str):
    """
    Fetch Observation resources for a patient from Cerner.
    
    Args:
        patient_id: FHIR Patient resource ID
    
    Returns:
        Bundle containing Observation resources
    """
    print(f"[api] Fetching Observations for Patient/{patient_id}")
    
    try:
        token = get_access_token("system/Patient.read system/Observation.read")
        
        url = f"{CERNER_FHIR_BASE}/Observation"
        params = {"subject": f"Patient/{patient_id}"}
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json"
        }
        
        print(f"[api] GET {url}?{params}")
        
        response = requests.get(url, params=params, headers=headers, timeout=20)
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Cerner API error: {response.text}"
            )
        
        observations = response.json()
        print(f"[api] ✅ Retrieved {observations.get('total', 0)} observations")
        
        return observations
        
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cerner FHIR server unreachable: {str(e)}"
        )


@app.post("/cerner/condition")
async def create_condition(request: Request):
    """
    Create a Condition resource on Cerner.
    
    Request body should be a FHIR Condition resource.
    
    Returns:
        Created Condition resource
    """
    print("[api] Creating Condition on Cerner")
    
    try:
        condition_data = await request.json()
        token = get_access_token("system/Condition.write")
        
        url = f"{CERNER_FHIR_BASE}/Condition"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json"
        }
        
        print(f"[api] POST {url}")
        
        response = requests.post(url, headers=headers, json=condition_data, timeout=20)
        
        if response.status_code not in [200, 201]:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Cerner API error: {response.text}"
            )
        
        created_condition = response.json()
        print(f"[api] ✅ Condition created: {created_condition.get('id')}")
        
        return created_condition
        
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cerner FHIR server unreachable: {str(e)}"
        )


@app.get("/cerner/documentreference/{doc_id}")
def get_document_reference(doc_id: str):
    """Fetch a DocumentReference resource from Cerner"""
    print(f"[api] Fetching DocumentReference/{doc_id}")
    
    try:
        token = get_access_token("system/DocumentReference.read system/Binary.read")
        url = f"{CERNER_FHIR_BASE}/DocumentReference/{doc_id}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json"
        }
        
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Cerner API error: {response.text}"
            )
        
        return response.json()
        
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cerner FHIR server unreachable: {str(e)}"
        )


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 Cerner Backend Services API")
    print("=" * 60)
    print(f"📋 Client ID: {CERNER_CLIENT_ID[:20]}...")
    print(f"🔗 Token URL: {CERNER_TOKEN_URL}")
    print(f"🏥 FHIR Base: {CERNER_FHIR_BASE}")
    print(f"🔑 Key ID: {KID}")
    print("=" * 60)
    print("🌐 API available at: http://localhost:8000")
    print("📚 API docs at: http://localhost:8000/docs")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

