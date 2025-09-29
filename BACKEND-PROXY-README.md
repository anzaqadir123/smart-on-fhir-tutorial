# SMART on FHIR Backend Proxy Solution

This solution solves CORS issues when working with Cerner's FHIR server by using a backend proxy pattern.

## Why This Works

The [itissismail GitHub repository](https://github.com/itissismail/itissismail.github.io) works without CORS issues because they use a **backend proxy pattern**:

1. **Frontend** (GitHub Pages) → **Backend API** (Python Flask)
2. **Backend API** → **Cerner FHIR Server**

This eliminates CORS issues because:
- ✅ Frontend makes requests to same-origin backend
- ✅ Backend handles CORS headers properly
- ✅ Backend proxies requests to Cerner
- ✅ No browser CORS restrictions

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the Backend Proxy

```bash
python backend-proxy.py
```

You should see:
```
🚀 Starting SMART on FHIR Backend Proxy...
📡 Proxying requests to Cerner FHIR server
🌐 CORS enabled for all origins
🔗 Access at: http://localhost:5000
```

### 3. Test the Proxy

Open: `http://localhost:5000/health`

Should return:
```json
{
  "status": "healthy",
  "service": "SMART on FHIR Backend Proxy"
}
```

### 4. Use the Proxy Version of Your App

Instead of using the regular launch files, use:
- `launch-proxy.html` - Launch page with proxy
- `index-proxy.html` - Main app with proxy

## How It Works

### Regular Flow (CORS Issues):
```
Browser → Cerner FHIR Server ❌ CORS Error
```

### Proxy Flow (No CORS Issues):
```
Browser → Backend Proxy → Cerner FHIR Server ✅ Success
```

## Files Created

- `backend-proxy.py` - Flask backend proxy server
- `requirements.txt` - Python dependencies
- `launch-proxy.html` - Launch page using proxy
- `index-proxy.html` - Main app using proxy
- `src/js/example-smart-app-proxy.js` - JavaScript with proxy support

## Testing

1. **Start the proxy**: `python backend-proxy.py`
2. **Open**: `http://localhost:5000/health` (should show healthy)
3. **Launch your app**: Use `launch-proxy.html`
4. **Check console**: Should show "Backend proxy is running"

## Production Deployment

For production, deploy the backend proxy to a cloud service like:
- Heroku
- AWS
- Google Cloud
- Azure

Then update the `PROXY_BASE_URL` in the JavaScript files to point to your deployed proxy.

## Benefits

- ✅ **Solves CORS issues** completely
- ✅ **Works with any FHIR server** (Cerner, Epic, etc.)
- ✅ **Maintains security** (tokens handled server-side)
- ✅ **Easy to deploy** (standard Python Flask app)
- ✅ **Scalable** (can handle multiple frontend apps)

## Troubleshooting

### Backend Not Running
```
❌ Backend proxy not running
```
**Solution**: Start the proxy with `python backend-proxy.py`

### Port Already in Use
```
Address already in use
```
**Solution**: Change port in `backend-proxy.py` or kill existing process

### CORS Still Issues
**Solution**: Make sure you're using the proxy version files (`*-proxy.html`)

## Next Steps

1. Test with the proxy version
2. Deploy backend to cloud service
3. Update frontend to use deployed proxy URL
4. Enjoy CORS-free SMART on FHIR development! 🎉
