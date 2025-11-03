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
import logging
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        logger.info("✅ Loaded encrypted private key successfully")
    except Exception as exc:
        raise ValueError(
            f"Failed to load encrypted private key. Ensure CERNER_PRIVATE_KEY_PASSPHRASE is correct. Error: {exc}"
        )

# Log configuration at startup (without exposing sensitive data)
logger.info("=" * 60)
logger.info("🔧 CERNER BACKEND SERVICES CONFIGURATION")
logger.info("=" * 60)
logger.info(f"📋 Client ID: {CERNER_CLIENT_ID[:20]}...")
logger.info(f"🔗 Token URL: {CERNER_TOKEN_URL}")
logger.info(f"🏥 FHIR Base: {CERNER_FHIR_BASE}")
logger.info(f"🔑 Key ID (KID): {KID}")
logger.info(f"🔐 Private Key Loaded: {'✅ Yes' if PRIVATE_KEY else '❌ No'}")
logger.info(f"🔐 Private Key Type: {'Encrypted (PEM object)' if PRIVATE_KEY_OBJ else 'Plain text (PEM string)'}")
logger.info("=" * 60)

# Verify key pair matches JWKS (if jwcrypto available)
try:
    from jwcrypto import jwk
    import json as jwcrypto_json
    
    # Derive public key from private to verify
    if PRIVATE_KEY_OBJ:
        # For encrypted keys, we need to export and re-import
        from cryptography.hazmat.primitives import serialization
        pem_bytes = PRIVATE_KEY_OBJ.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        jwk_key = jwk.JWK.from_pem(pem_bytes, password=None)
    else:
        jwk_key = jwk.JWK.from_pem(PRIVATE_KEY.encode("utf-8"), password=None if not PASSPHRASE else PASSPHRASE.encode("utf-8"))
    
    pub_key_json = jwcrypto_json.loads(jwk_key.export_public())
    pub_kid = pub_key_json.get("kid") or "N/A"
    pub_alg = pub_key_json.get("alg") or "N/A"
    pub_n_prefix = pub_key_json.get("n", "")[:50] if pub_key_json.get("n") else "N/A"
    
    logger.info("🔍 Key Pair Verification:")
    logger.info(f"   📌 Derived Public Key KID: {pub_kid}")
    logger.info(f"   📌 Derived Public Key ALG: {pub_alg}")
    logger.info(f"   📌 Derived Public Key N (first 50 chars): {pub_n_prefix}...")
    logger.info(f"   ⚠️  JWT Header KID (from config): {KID}")
    if pub_kid != "N/A" and pub_kid != KID:
        logger.warning(f"   ⚠️  KID MISMATCH! Derived KID ({pub_kid}) != Config KID ({KID})")
    logger.info("=" * 60)
except Exception as e:
    logger.warning(f"⚠️  Could not verify key pair (jwcrypto may not be installed): {e}")

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
        logger.info(f"[token] ✅ Using cached token (expires in {int(_token_cache['expires_at'] - time.time())}s)")
        return _token_cache["token"]
    
    logger.info("=" * 60)
    logger.info("[token] 🔐 Requesting new access token...")
    logger.info(f"   Scope: {scope}")
    logger.info(f"   Token URL: {CERNER_TOKEN_URL}")
    logger.info("=" * 60)
    
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
    
    logger.info("📝 JWT Payload:")
    logger.info(f"   iss (issuer): {payload['iss']}")
    logger.info(f"   sub (subject): {payload['sub']}")
    logger.info(f"   aud (audience): {payload['aud']}")
    logger.info(f"   exp (expires): {payload['exp']} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(payload['exp']))})")
    logger.info(f"   iat (issued at): {payload['iat']} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(payload['iat']))})")
    logger.info(f"   jti (token ID): {payload['jti']}")
    
    logger.info("📝 JWT Header:")
    logger.info(f"   alg: {header['alg']}")
    logger.info(f"   typ: {header['typ']}")
    logger.info(f"   kid: {header['kid']}")
    logger.info(f"   ⚠️  KID Verification: Header KID ({header['kid']}) must match a key in your JWKS")
    
    try:
        # Sign JWT with private key using RS384 algorithm
        signing_key = PRIVATE_KEY_OBJ if PRIVATE_KEY_OBJ is not None else PRIVATE_KEY
        key_type = "Encrypted key object" if PRIVATE_KEY_OBJ else "Plain PEM string"
        
        logger.info(f"✍️  Signing JWT with RS384 algorithm...")
        logger.info(f"   Using: {key_type}")
        
        client_assertion = jwt.encode(
            payload,
            signing_key,
            algorithm="RS384",
            headers=header
        )
        
        # Decode JWT to show structure (without verification)
        decoded_header = jwt.get_unverified_header(client_assertion)
        decoded_payload = jwt.decode(client_assertion, options={"verify_signature": False})
        
        logger.info(f"✅ JWT Created Successfully")
        logger.info(f"   JWT Length: {len(client_assertion)} characters")
        logger.info(f"   JWT Preview: {client_assertion[:80]}...")
        logger.info(f"   Decoded Header: {json.dumps(decoded_header, indent=2)}")
        logger.info(f"   Decoded Payload: {json.dumps(decoded_payload, indent=2)}")
        
    except Exception as e:
        logger.error(f"❌ Failed to create JWT: {str(e)}")
        logger.error(f"   Error type: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create JWT: {str(e)}"
        )
    
    # Exchange JWT for access token
    logger.info("=" * 60)
    logger.info("🌐 Exchanging JWT for Access Token...")
    logger.info(f"   POST {CERNER_TOKEN_URL}")
    
    try:
        token_request_data = {
            "grant_type": "client_credentials",
            "scope": scope,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": client_assertion
        }
        
        logger.info("📤 Token Request Data:")
        logger.info(f"   grant_type: {token_request_data['grant_type']}")
        logger.info(f"   scope: {token_request_data['scope']}")
        logger.info(f"   client_assertion_type: {token_request_data['client_assertion_type']}")
        logger.info(f"   client_assertion (first 80 chars): {token_request_data['client_assertion'][:80]}...")
        
        response = requests.post(
            CERNER_TOKEN_URL,
            data=token_request_data,
            timeout=10
        )
        
        logger.info(f"📥 Token Response:")
        logger.info(f"   Status Code: {response.status_code}")
        logger.info(f"   Headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            error_detail = response.text
            logger.error(f"❌ Token request FAILED!")
            logger.error(f"   Status: {response.status_code}")
            logger.error(f"   Response: {error_detail}")
            
            # Try to parse error JSON for better details
            try:
                error_json = response.json()
                logger.error(f"   Error JSON: {json.dumps(error_json, indent=2)}")
                if "error_uri" in error_json:
                    logger.error(f"   Error URI: {error_json['error_uri']}")
                    logger.error(f"   💡 Check this URL for detailed error explanation")
            except:
                pass
            
            raise HTTPException(
                status_code=500,
                detail=f"Token request failed: {error_detail}"
            )
        
        token_data = response.json()
        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        
        logger.info(f"✅ Token Obtained Successfully!")
        logger.info(f"   Access Token (first 50 chars): {access_token[:50]}...")
        logger.info(f"   Expires In: {expires_in} seconds ({expires_in // 60} minutes)")
        if "token_type" in token_data:
            logger.info(f"   Token Type: {token_data['token_type']}")
        if "scope" in token_data:
            logger.info(f"   Granted Scope: {token_data['scope']}")
        
        # Cache token
        _token_cache["token"] = access_token
        _token_cache["expires_at"] = time.time() + expires_in
        _token_cache["scope"] = scope
        
        logger.info("=" * 60)
        return access_token
        
    except requests.RequestException as e:
        logger.error(f"❌ Token endpoint unreachable: {str(e)}")
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


@app.get("/debug/key-info")
def debug_key_info():
    """Diagnostic endpoint to verify key configuration"""
    try:
        from jwcrypto import jwk
        import json as jwcrypto_json
        
        # Derive public key from private
        if PRIVATE_KEY_OBJ:
            from cryptography.hazmat.primitives import serialization
            pem_bytes = PRIVATE_KEY_OBJ.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            jwk_key = jwk.JWK.from_pem(pem_bytes, password=None)
        else:
            jwk_key = jwk.JWK.from_pem(PRIVATE_KEY.encode("utf-8"), password=None if not PASSPHRASE else PASSPHRASE.encode("utf-8"))
        
        pub_key_json = jwcrypto_json.loads(jwk_key.export_public())
        derived_kid = pub_key_json.get("kid") or "N/A"
        
        # Fetch JWKS from GitHub Pages
        jwks_url = "https://anzaqadir123.github.io/smart-on-fhir-tutorial/.well-known/jwks.json"
        try:
            jwks_response = requests.get(jwks_url, timeout=5)
            published_jwks = jwks_response.json() if jwks_response.status_code == 200 else None
        except:
            published_jwks = None
        
        return {
            "config": {
                "client_id": CERNER_CLIENT_ID,
                "token_url": CERNER_TOKEN_URL,
                "fhir_base": CERNER_FHIR_BASE,
                "configured_kid": KID,
            },
            "private_key": {
                "loaded": bool(PRIVATE_KEY or PRIVATE_KEY_OBJ),
                "type": "encrypted_object" if PRIVATE_KEY_OBJ else "plain_pem",
                "has_passphrase": bool(PASSPHRASE),
            },
            "derived_public_key": {
                "kid": derived_kid,
                "kty": pub_key_json.get("kty"),
                "alg": pub_key_json.get("alg"),
                "n_length": len(pub_key_json.get("n", "")),
                "n_prefix": pub_key_json.get("n", "")[:50] + "..." if pub_key_json.get("n") else None,
                "e": pub_key_json.get("e"),
            },
            "kid_match": {
                "configured_kid": KID,
                "derived_kid": derived_kid,
                "matches": derived_kid == KID or derived_kid == "N/A",
                "warning": "KID mismatch! Your JWT header uses configured KID, but derived KID is different" if (derived_kid != "N/A" and derived_kid != KID) else None
            },
            "published_jwks": {
                "url": jwks_url,
                "accessible": published_jwks is not None,
                "keys_count": len(published_jwks.get("keys", [])) if published_jwks else 0,
                "published_kids": [k.get("kid") for k in published_jwks.get("keys", [])] if published_jwks else None,
                "configured_kid_in_jwks": KID in [k.get("kid") for k in published_jwks.get("keys", [])] if published_jwks else None,
            },
            "recommendations": []
        }
    except Exception as e:
        return {
            "error": str(e),
            "note": "Install jwcrypto: pip install jwcrypto"
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
    logger.info("=" * 60)
    logger.info(f"[api] 👤 Fetching Patient/{patient_id} from Cerner")
    logger.info(f"   FHIR Base: {CERNER_FHIR_BASE}")
    
    try:
        # Get access token (will create JWT and exchange if needed)
        logger.info("   Getting access token...")
        token = get_access_token("system/Patient.read")
        
        # Build FHIR URL
        url = f"{CERNER_FHIR_BASE}/Patient/{patient_id}"
        
        headers = {
            "Authorization": f"Bearer {token[:20]}...",
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json"
        }
        
        logger.info(f"   📤 GET {url}")
        logger.info(f"   Headers: {headers}")
        
        response = requests.get(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json"
        }, timeout=20)
        
        logger.info(f"   📥 Response Status: {response.status_code}")
        
        if response.status_code != 200:
            error_detail = response.text
            logger.error(f"   ❌ Request failed: {response.status_code}")
            logger.error(f"   Error: {error_detail}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Cerner API error: {error_detail}"
            )
        
        patient_data = response.json()
        logger.info(f"   ✅ Patient retrieved: {patient_data.get('id')}")
        if 'name' in patient_data and patient_data.get('name'):
            name = patient_data['name'][0]
            given = ' '.join(name.get('given', []))
            family = name.get('family', '')
            logger.info(f"   Patient Name: {given} {family}")
        logger.info("=" * 60)
        
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

