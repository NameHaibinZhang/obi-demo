#!/bin/bash
set -e

REGISTRY="${DOCKER_REGISTRY:-}"
TAG="${IMAGE_TAG:-latest}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

SERVICES=(
    "python-service"
    "python-ai-service"
    "nodejs-service"
    "go-service"
    "dotnet-service"
    "cpp-service"
    "php-service"
)

IMAGE_NAMES=(
    "registry.cn-hangzhou.aliyuncs.com/private-mesh/obi:python-service"
    "registry.cn-hangzhou.aliyuncs.com/private-mesh/obi:python-ai-service"
    "registry.cn-hangzhou.aliyuncs.com/private-mesh/obi:nodejs-service"
    "registry.cn-hangzhou.aliyuncs.com/private-mesh/obi:go-service"
    "registry.cn-hangzhou.aliyuncs.com/private-mesh/obi:dotnet-service"
    "registry.cn-hangzhou.aliyuncs.com/private-mesh/obi:cpp-service"
    "registry.cn-hangzhou.aliyuncs.com/private-mesh/obi:php-service"
)

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -r, --registry REGISTRY   Docker registry prefix (e.g. harbor.example.com/library)"
    echo "                            Default: empty (local build only)"
    echo "  -t, --tag TAG             Image tag (default: latest)"
    echo "  -p, --push                Push images to registry after build"
    echo "  -s, --service SERVICE     Build single service only (python-service|nodejs-service|go-service|dotnet-service|cpp-service|php-service)"
    echo "  -n, --no-cache            Build without Docker cache"
    echo "  -h, --help                Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                                   # Build all images locally"
    echo "  $0 -r harbor.example.com/library -t v1.0 -p  # Build, tag and push all"
    echo "  $0 -s go-service                     # Build only Go service"
    echo "  $0 -n                                 # Build all without cache"
    echo ""
    echo "Built images:"
    for i in "${!SERVICES[@]}"; do
        echo "  ${IMAGE_NAMES[$i]}  ←  ${SERVICES[$i]}/"
    done
}

PUSH=false
NO_CACHE=""
TARGET_SERVICE=""
PLATFORM=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--registry) REGISTRY="$2"; shift 2 ;;
        -t|--tag)      TAG="$2"; shift 2 ;;
        -p|--push)     PUSH=true; shift ;;
        -s|--service)  TARGET_SERVICE="$2"; shift 2 ;;
        -n|--no-cache) NO_CACHE="--no-cache"; shift ;;
        --platform)    PLATFORM="$2"; shift 2 ;;
        -h|--help)     usage; exit 0 ;;
        *)             echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

PLATFORM_FLAG=""
if [ -n "$PLATFORM" ]; then
    PLATFORM_FLAG="--platform $PLATFORM"
fi

build_service() {
    local service="$1"
    local image_name="$2"
    local full_image="${REGISTRY}${image_name}:${TAG}"

    echo ""
    echo "============================================"
    echo " Building: ${service} → ${full_image}"
    echo "============================================"

    if [ -n "$NO_CACHE" ]; then
        echo "  [no-cache mode]"
    fi

    docker build ${PLATFORM_FLAG} ${NO_CACHE} -t "${full_image}" "${PROJECT_DIR}/${service}"

    if [ "$PUSH" = true ] && [ -n "$REGISTRY" ]; then
        echo "  Pushing: ${full_image}"
        docker push "${full_image}"
    fi

    echo "  ✓ Done: ${full_image}"
}

echo "=== OBI Demo - Build Images ==="
echo "  Registry : ${REGISTRY:-<local>}"
echo "  Tag      : ${TAG}"
echo "  Push     : ${PUSH}"
echo ""

if [ -n "$TARGET_SERVICE" ]; then
    found=false
    for i in "${!SERVICES[@]}"; do
        if [ "${SERVICES[$i]}" = "$TARGET_SERVICE" ]; then
            build_service "${SERVICES[$i]}" "${IMAGE_NAMES[$i]}"
            found=true
            break
        fi
    done
    if [ "$found" = false ]; then
        echo "Error: unknown service '${TARGET_SERVICE}'"
        echo "Valid services: ${SERVICES[*]}"
        exit 1
    fi
else
    for i in "${!SERVICES[@]}"; do
        build_service "${SERVICES[$i]}" "${IMAGE_NAMES[$i]}"
    done
fi

echo ""
echo "=== Build Summary ==="
echo ""
if [ -n "$TARGET_SERVICE" ]; then
    for i in "${!SERVICES[@]}"; do
        if [ "${SERVICES[$i]}" = "$TARGET_SERVICE" ]; then
            echo "  ${REGISTRY}${IMAGE_NAMES[$i]}"
        fi
    done
else
    for i in "${!SERVICES[@]}"; do
        echo "  ${REGISTRY}${IMAGE_NAMES[$i]}"
    done
fi
echo ""
echo "To deploy to K8s, update image names in k8s/deployment.yaml files and run:"
echo "  ./deploy.sh"
echo ""
echo "To test locally:"
echo "  docker compose up"