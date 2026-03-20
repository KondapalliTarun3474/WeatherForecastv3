#!/bin/bash

# Exit on error
set -e

echo "Pointing shell to Minikube's Docker daemon..."
eval $(minikube docker-env)

echo "Building Auth Service Image..."
docker build -f mlops-llm4ts/model-service/auth-service/Dockerfile.auth -t weather-auth:v1 mlops-llm4ts/model-service/auth-service/

echo "Building Inference Service Image..."
docker build -f mlops-llm4ts/model-service/inference-service/Dockerfile.param -t weather-inference:v1 mlops-llm4ts/model-service/inference-service/

echo "Building Frontend Image..."
docker build -t weather-frontend:v1 frontend-new/

echo "Building DB Service Image..."
docker build -f db-service/Dockerfile.db -t weather-db:v1 db-service/

echo "Building Retrainer Image..."
docker build -f MLOps-automation-service/Dockerfile.retrainer -t weather-retrainer:v1 MLOps-automation-service/

echo "Applying Kubernetes Manifests..."
kubectl apply -f k8s/

echo "Deployment Complete!"
echo "Access the app at: http://$(minikube ip):30080"
echo "Services:"
echo "  Auth: NodePort 30000"
echo "  T2M:  NodePort 30001"
echo "  RH2M: NodePort 30002"
echo "  WS2M: NodePort 30003"
