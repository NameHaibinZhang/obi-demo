import os
import time
import json
import logging
import threading
import mysql.connector
import requests
from flask import Flask, jsonify

app = Flask(__name__)

MYSQL_HOST = os.environ.get('MYSQL_HOST', 'mysql')
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'demo123')
MYSQL_DB = os.environ.get('MYSQL_DB', 'obidemo')
NEXT_SERVICE_URL = os.environ.get('NEXT_SERVICE_URL', 'http://nodejs-service:8082')
AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL', 'http://python-ai-service:8087')
PHP_SERVICE_URL = os.environ.get('PHP_SERVICE_URL', 'http://php-service:8083')
INVALID_HOST = os.environ.get('INVALID_HOST', 'http://nonexistent-service:9999')
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '10'))

log = logging.getLogger('obi-demo-python')


def query_mysql(query="SELECT id, name, email, age FROM users LIMIT 5"):
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST, user=MYSQL_USER,
            password=MYSQL_PASSWORD, database=MYSQL_DB
        )
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        return [{"error": str(e)}]


def call_service(url, timeout=15):
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.json(), resp.status_code
    except requests.exceptions.Timeout:
        return {"error": "timeout"}, 0
    except requests.exceptions.ConnectionError:
        return {"error": "connection_refused"}, 0
    except Exception as e:
        return {"error": str(e)}, 0


def post_service(url, payload, timeout=15):
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        return resp.json(), resp.status_code
    except requests.exceptions.Timeout:
        return {"error": "timeout"}, 0
    except requests.exceptions.ConnectionError:
        return {"error": "connection_refused"}, 0
    except Exception as e:
        return {"error": str(e)}, 0


@app.route('/api/data')
def get_data():
    users = query_mysql()
    next_data, _ = call_service(f"{NEXT_SERVICE_URL}/api/data")
    php_data, _ = call_service(f"{PHP_SERVICE_URL}/api/data")
    ai_health, _ = call_service(f"{AI_SERVICE_URL}/health")
    return jsonify({
        "service": "python",
        "users": users,
        "ai_status": ai_health,
        "php": php_data,
        "next": next_data,
    })


@app.route('/api/ai/chat')
def ai_chat():
    data, status = post_service(f"{AI_SERVICE_URL}/chat", {"message": "hello from obi-demo"})
    return jsonify({"service": "python", "ai_chat": data, "status": status})


@app.route('/api/ai/embeddings')
def ai_embeddings():
    data, status = post_service(
        f"{AI_SERVICE_URL}/embeddings",
        {"input": ["OBI demo test embedding"], "include_embedding": False},
    )
    return jsonify({"service": "python", "ai_embeddings": data, "status": status})


@app.route('/api/ai/tool')
def ai_tool():
    data, status = post_service(f"{AI_SERVICE_URL}/chat/tool", {"message": "What is the weather in Beijing?"})
    return jsonify({"service": "python", "ai_tool": data, "status": status})


@app.route('/api/ai/rerank')
def ai_rerank():
    data, status = post_service(
        f"{AI_SERVICE_URL}/rerank",
        {"query": "OpenTelemetry", "documents": ["eBPF monitoring", "distributed tracing", "cloud native", "observability platform"]},
    )
    return jsonify({"service": "python", "ai_rerank": data, "status": status})


@app.route('/api/ai/mcp')
def ai_mcp():
    data, status = call_service(f"{AI_SERVICE_URL}/mcp/tools")
    return jsonify({"service": "python", "ai_mcp_tools": data, "status": status})


@app.route('/api/php/data')
def php_data():
    data, status = call_service(f"{PHP_SERVICE_URL}/api/data")
    return jsonify({"service": "python", "php": data, "status": status})


@app.route('/api/php/slow')
def php_slow():
    data, status = call_service(f"{PHP_SERVICE_URL}/api/slow")
    return jsonify({"service": "python", "scenario": "php-slow", "php": data, "status": status})


@app.route('/api/php/error')
def php_error():
    data, status = call_service(f"{PHP_SERVICE_URL}/api/error")
    return jsonify({"service": "python", "scenario": "php-error", "php": data, "status": status})


@app.route('/api/php/db-error')
def php_db_error():
    data, status = call_service(f"{PHP_SERVICE_URL}/api/db-error")
    return jsonify({"service": "python", "scenario": "php-db-error", "php": data, "status": status})


@app.route('/api/php/db-slow')
def php_db_slow():
    data, status = call_service(f"{PHP_SERVICE_URL}/api/db-slow")
    return jsonify({"service": "python", "scenario": "php-db-slow", "php": data, "status": status})


@app.route('/api/slow')
def slow():
    time.sleep(3)
    users = query_mysql()
    next_data, _ = call_service(f"{NEXT_SERVICE_URL}/api/data")
    return jsonify({"service": "python", "scenario": "slow", "users": users, "next": next_data})


@app.route('/api/error')
def error():
    return jsonify({"service": "python", "scenario": "error", "message": "internal server error"}), 500


@app.route('/api/timeout-downstream')
def timeout_downstream():
    next_data, status = call_service(f"{NEXT_SERVICE_URL}/api/data", timeout=0.1)
    return jsonify({"service": "python", "scenario": "timeout-downstream", "next": next_data, "status": status})


@app.route('/api/notfound-downstream')
def notfound_downstream():
    next_data, status = call_service(f"{NEXT_SERVICE_URL}/api/nonexistent-path-404")
    return jsonify({"service": "python", "scenario": "notfound-downstream", "next": next_data, "status": status})


@app.route('/api/error-downstream')
def error_downstream():
    next_data, status = call_service(f"{NEXT_SERVICE_URL}/api/error")
    return jsonify({"service": "python", "scenario": "error-downstream", "next": next_data, "status": status})


@app.route('/api/connection-refused')
def connection_refused():
    data, status = call_service(f"{INVALID_HOST}/api/data", timeout=2)
    return jsonify({"service": "python", "scenario": "connection-refused", "result": data, "status": status})


@app.route('/api/db-error')
def db_error():
    result = query_mysql("SELECT * FROM nonexistent_table_xyz")
    return jsonify({"service": "python", "scenario": "db-error", "result": result})


@app.route('/api/db-slow')
def db_slow():
    result = query_mysql("SELECT SLEEP(3), id, name FROM users LIMIT 1")
    return jsonify({"service": "python", "scenario": "db-slow", "result": result})


@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "service": "python"})


AI_POLL_MESSAGES = [
    "What is OpenTelemetry?",
    "Explain eBPF monitoring",
    "How does distributed tracing work?",
    "What is observability?",
    "Describe cloud native architecture",
    "What are microservices?",
    "How does HTTP/2 work?",
    "Explain gRPC protocol",
]


def background_poll():
    time.sleep(8)
    idx = 0
    while True:
        try:
            resp = requests.get(f"{NEXT_SERVICE_URL}/api/data", timeout=10)
            log.info("poll nodejs: status=%s body_len=%d", resp.status_code, len(resp.text))
        except Exception as e:
            log.warning("poll nodejs failed: %s", e)

        try:
            msg = AI_POLL_MESSAGES[idx % len(AI_POLL_MESSAGES)]
            resp = requests.post(f"{AI_SERVICE_URL}/chat", json={"message": msg}, timeout=30)
            log.info("poll ai chat: status=%s", resp.status_code)
        except Exception as e:
            log.warning("poll ai chat failed: %s", e)

        idx += 1
        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    t = threading.Thread(target=background_poll, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=8081)