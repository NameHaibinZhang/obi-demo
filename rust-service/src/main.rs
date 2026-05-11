use actix_web::{web, App, HttpServer, HttpResponse, middleware};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::env;
use std::time::Duration;

#[derive(Clone)]
struct AppState {
    client: Client,
    nodejs_service_url: String,
    invalid_host: String,
}

#[derive(Serialize, Deserialize)]
struct HealthResponse {
    status: String,
    service: String,
    port: u16,
}

async fn call_service(client: &Client, url: &str, timeout_ms: u64) -> (Value, u16) {
    let result = client
        .get(url)
        .timeout(Duration::from_millis(timeout_ms))
        .send()
        .await;

    match result {
        Ok(resp) => {
            let status = resp.status().as_u16();
            match resp.json::<Value>().await {
                Ok(body) => (body, status),
                Err(e) => (serde_json::json!({"error": e.to_string()}), status),
            }
        }
        Err(e) => {
            if e.is_timeout() {
                (serde_json::json!({"error": "timeout"}), 0)
            } else if e.is_connect() {
                (serde_json::json!({"error": "connection_refused"}), 0)
            } else {
                (serde_json::json!({"error": e.to_string()}), 0)
            }
        }
    }
}

async fn get_data(state: web::Data<AppState>) -> HttpResponse {
    let url = format!("{}/api/data", state.nodejs_service_url);
    let (nodejs_data, _) = call_service(&state.client, &url, 15000).await;

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "nodejs": nodejs_data,
    }))
}

async fn health() -> HttpResponse {
    HttpResponse::Ok().json(HealthResponse {
        status: "ok".to_string(),
        service: "rust".to_string(),
        port: 8088,
    })
}

async fn slow(state: web::Data<AppState>) -> HttpResponse {
    tokio::time::sleep(Duration::from_secs(3)).await;
    let url = format!("{}/api/data", state.nodejs_service_url);
    let (nodejs_data, _) = call_service(&state.client, &url, 15000).await;

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "scenario": "slow",
        "nodejs": nodejs_data,
    }))
}

async fn error() -> HttpResponse {
    HttpResponse::InternalServerError().json(serde_json::json!({
        "service": "rust",
        "scenario": "error",
        "message": "internal server error",
    }))
}

async fn timeout_downstream(state: web::Data<AppState>) -> HttpResponse {
    let url = format!("{}/api/data", state.nodejs_service_url);
    let (data, status) = call_service(&state.client, &url, 100).await;

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "scenario": "timeout-downstream",
        "nodejs": data,
        "status": status,
    }))
}

async fn notfound_downstream(state: web::Data<AppState>) -> HttpResponse {
    let url = format!("{}/api/nonexistent-path-404", state.nodejs_service_url);
    let (data, status) = call_service(&state.client, &url, 5000).await;

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "scenario": "notfound-downstream",
        "nodejs": data,
        "status": status,
    }))
}

async fn error_downstream(state: web::Data<AppState>) -> HttpResponse {
    let url = format!("{}/api/error", state.nodejs_service_url);
    let (data, status) = call_service(&state.client, &url, 5000).await;

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "scenario": "error-downstream",
        "nodejs": data,
        "status": status,
    }))
}

async fn connection_refused(state: web::Data<AppState>) -> HttpResponse {
    let url = format!("{}/api/data", state.invalid_host);
    let (data, status) = call_service(&state.client, &url, 2000).await;

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "scenario": "connection-refused",
        "result": data,
        "status": status,
    }))
}

/// 重试风暴: 调用 nodejs /api/error，失败后重试3次，展示请求放大效应
async fn retry_storm(state: web::Data<AppState>) -> HttpResponse {
    let url = format!("{}/api/error", state.nodejs_service_url);
    let max_retries = 3;
    let mut attempts = Vec::new();

    for i in 0..=max_retries {
        let (data, status) = call_service(&state.client, &url, 5000).await;
        attempts.push(serde_json::json!({
            "attempt": i + 1,
            "status": status,
            "response": data,
        }));
        if status == 200 {
            break;
        }
        if i < max_retries {
            tokio::time::sleep(Duration::from_millis(200)).await;
        }
    }

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "scenario": "retry-storm",
        "total_attempts": attempts.len(),
        "attempts": attempts,
    }))
}

/// 级联失败: rust 用较短 timeout 调用 nodejs /api/slow (nodejs sleep 3s)
/// 模拟 python(15s) → rust(2s timeout) → nodejs(sleep 3s) 的超时传播
async fn cascade(state: web::Data<AppState>) -> HttpResponse {
    let url = format!("{}/api/slow", state.nodejs_service_url);
    let (data, status) = call_service(&state.client, &url, 2000).await;

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "scenario": "cascade",
        "message": "called nodejs /api/slow with 2s timeout, nodejs sleeps 3s",
        "nodejs": data,
        "status": status,
    }))
}

/// CPU 密集: 计算斐波那契数列（递归），模拟 CPU spike
async fn cpu_intensive() -> HttpResponse {
    let n = 42u64;
    let start = std::time::Instant::now();
    let result = tokio::task::spawn_blocking(move || fibonacci(n)).await.unwrap();
    let elapsed_ms = start.elapsed().as_millis();

    HttpResponse::Ok().json(serde_json::json!({
        "service": "rust",
        "scenario": "cpu-intensive",
        "fibonacci_n": n,
        "result": result,
        "elapsed_ms": elapsed_ms,
    }))
}

fn fibonacci(n: u64) -> u64 {
    if n <= 1 {
        return n;
    }
    fibonacci(n - 1) + fibonacci(n - 2)
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let nodejs_service_url = env::var("NODEJS_SERVICE_URL")
        .unwrap_or_else(|_| "http://nodejs-service:8082".to_string());
    let invalid_host = env::var("INVALID_HOST")
        .unwrap_or_else(|_| "http://nonexistent-service:9999".to_string());

    let client = Client::new();
    let state = AppState {
        client,
        nodejs_service_url,
        invalid_host,
    };

    env_logger::init_from_env(env_logger::Env::default().default_filter_or("info"));
    log::info!("Rust service running on port 8088");

    HttpServer::new(move || {
        App::new()
            .wrap(middleware::Logger::new("%a \"%r\" %s %b %Dms"))
            .app_data(web::Data::new(state.clone()))
            .route("/api/data", web::get().to(get_data))
            .route("/api/health", web::get().to(health))
            .route("/api/slow", web::get().to(slow))
            .route("/api/error", web::get().to(error))
            .route("/api/timeout-downstream", web::get().to(timeout_downstream))
            .route("/api/notfound-downstream", web::get().to(notfound_downstream))
            .route("/api/error-downstream", web::get().to(error_downstream))
            .route("/api/connection-refused", web::get().to(connection_refused))
            .route("/api/retry-storm", web::get().to(retry_storm))
            .route("/api/cascade", web::get().to(cascade))
            .route("/api/cpu-intensive", web::get().to(cpu_intensive))
    })
    .bind("0.0.0.0:8088")?
    .run()
    .await
}
