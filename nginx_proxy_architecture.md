# Nginx Reverse Proxy Architecture for Kubernetes

## The Problem
In a standard Kubernetes deployment, your Frontend (React) code runs in the **User's Browser**, not inside the cluster.
- The Browser cannot resolve internal K8s DNS names like `http://auth-service`.
- The Browser cannot access Pod IPs directly.
- Using `localhost` only works if you manually set up `kubectl port-forward` tunnels for every single service.

## The Solution: Nginx Reverse Proxy
We configure the Nginx server (which serves the Frontend files) to act as a Gateway.

### 1. Unified Entry Point
We expose **only** the Frontend Service to the outside world (via NodePort, LoadBalancer, or Ingress).

### 2. Traffic Flow
1.  **Browser Request**: The React app makes a call to a relative path: `fetch('/api/auth/login')`.
2.  **Frontend Pod**: The request hits Nginx running inside the K8s cluster.
3.  **Nginx Routing**: Nginx sees the `/api/auth` prefix and proxies the request to the actual internal service: `http://auth-service.default.svc.cluster.local:5000`.
4.  **Response**: The Auth Service replies to Nginx, which forwards the response back to your Browser.

### 3. Implementation Details

**nginx.conf** (Inside Frontend Pod)
```nginx
server {
    listen 80;
    
    # Proxy Auth Requests
    location /api/auth/ {
        rewrite ^/api/auth/(.*) /$1 break;
        proxy_pass http://auth-service:5000;
    }

    # Proxy Inference Requests
    location /api/t2m/ {
        rewrite ^/api/t2m/(.*) /$1 break;
        proxy_pass http://inference-t2m-service:5001;
    }
}
```

**Frontend Code** (React)
```javascript
// No more localhost or port numbers!
fetch('/api/auth/login', { ... })
```

This pattern decouples your code from specific ports and URLs, making it "Cloud Native" and ready for production.
