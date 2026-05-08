#!/bin/bash
set -e

echo "=== OBI Demo - Kubernetes Deployment ==="

NS="obi-demo"

echo "[1/3] Creating namespace..."
kubectl apply -f infra/k8s/namespace.yaml

echo "[2/3] Deploying infrastructure (MySQL, Redis, MongoDB)..."
kubectl apply -f infra/k8s/mysql.yaml
kubectl apply -f infra/k8s/redis.yaml
kubectl apply -f infra/k8s/mongodb.yaml

echo "Waiting for infrastructure to be ready..."
kubectl wait --for=condition=available --timeout=120s deployment/mysql -n $NS || true
kubectl wait --for=condition=available --timeout=60s deployment/redis -n $NS || true
kubectl wait --for=condition=available --timeout=120s deployment/mongodb -n $NS || true

echo "Seeding Redis data..."
kubectl apply -f infra/k8s/redis-seed.yaml

echo "[3/3] Deploying application services..."
kubectl apply -f php-service/k8s/deployment.yaml
kubectl apply -f cpp-service/k8s/deployment.yaml
kubectl apply -f dotnet-service/k8s/deployment.yaml
kubectl apply -f go-service/k8s/deployment.yaml
kubectl apply -f nodejs-service/k8s/deployment.yaml
kubectl apply -f python-ai-service/k8s/deployment.yaml
kubectl apply -f python-service/k8s/deployment.yaml

echo "Waiting for services to be ready..."
kubectl wait --for=condition=available --timeout=120s deployment/php-service -n $NS || true
kubectl wait --for=condition=available --timeout=120s deployment/cpp-service -n $NS || true
kubectl wait --for=condition=available --timeout=120s deployment/dotnet-service -n $NS || true
kubectl wait --for=condition=available --timeout=120s deployment/go-service -n $NS || true
kubectl wait --for=condition=available --timeout=120s deployment/nodejs-service -n $NS || true
kubectl wait --for=condition=available --timeout=120s deployment/python-ai-service -n $NS || true
kubectl wait --for=condition=available --timeout=120s deployment/python-service -n $NS || true

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Test normal chain:"
echo "  kubectl port-forward svc/python-service 8081:8081 -n $NS"
echo "  curl http://localhost:8081/api/data"
echo ""
echo "Test error scenarios:"
echo "  curl http://localhost:8081/api/error              # HTTP 500"
echo "  curl http://localhost:8081/api/timeout-downstream # upstream timeout"
echo "  curl http://localhost:8081/api/notfound-downstream # 404 upstream"
echo "  curl http://localhost:8081/api/error-downstream    # upstream 500"
echo "  curl http://localhost:8081/api/connection-refused  # DNS/connection failure"
echo "  curl http://localhost:8081/api/db-error            # database error"
echo "  curl http://localhost:8081/api/db-slow             # slow database query"
echo "  curl http://localhost:8081/api/slow               # slow server response"