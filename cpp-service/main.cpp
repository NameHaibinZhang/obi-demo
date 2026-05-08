#include <iostream>
#include <string>
#include <cstring>
#include <ctime>
#include <chrono>
#include <thread>
#include <hiredis/hiredis.h>
#include <httplib.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

static std::string REDIS_HOST = std::getenv("REDIS_HOST") ? std::getenv("REDIS_HOST") : "redis";
static int REDIS_PORT = std::getenv("REDIS_PORT") ? std::atoi(std::getenv("REDIS_PORT")) : 6379;
static std::string PHP_SERVICE_URL = std::getenv("PHP_SERVICE_URL") ? std::getenv("PHP_SERVICE_URL") : "http://php-service:8083";
static std::string INVALID_HOST = std::getenv("INVALID_HOST") ? std::getenv("INVALID_HOST") : "http://nonexistent-service:9999";

json query_redis(const std::string& key) {
    redisContext* c = redisConnect(REDIS_HOST.c_str(), REDIS_PORT);
    if (c == nullptr || c->err) {
        if (c) redisFree(c);
        return json{{"error", "redis connection failed"}};
    }
    json result;
    redisReply* reply = (redisReply*)redisCommand(c, "GET %s", key.c_str());
    if (reply && reply->type == REDIS_REPLY_STRING) {
        result[key] = std::string(reply->str, reply->len);
    } else {
        result[key] = nullptr;
    }
    if (reply) freeReplyObject(reply);
    redisFree(c);
    return result;
}

json redis_error() {
    redisContext* c = redisConnect("invalid-redis-host", 9999);
    if (c == nullptr || c->err) {
        if (c) redisFree(c);
        return json{{"error", "redis connection refused"}};
    }
    redisFree(c);
    return json{};
}

json call_service(const std::string& url, int timeout_ms) {
    httplib::Client cli(url);
    cli.set_connection_timeout(std::chrono::milliseconds(timeout_ms));
    cli.set_read_timeout(std::chrono::milliseconds(timeout_ms));
    auto res = cli.Get("/api/data");
    if (res && res->status == 200) {
        try { return json::parse(res->body); }
        catch (...) { return json{{"raw", res->body}}; }
    }
    if (res) return json{{"error", "http error"}, {"status", res->status}};
    return json{{"error", "connection failed"}};
}

int main() {
    httplib::Server svr;

    svr.Get("/api/data", [](const httplib::Request&, httplib::Response& res) {
        json redis_data = query_redis("cache:user:3");
        json php_data = call_service(PHP_SERVICE_URL, 15000);
        json result;
        result["service"] = "cpp";
        result["redis"] = redis_data;
        result["next"] = php_data;
        res.set_content(result.dump(), "application/json");
    });

    svr.Get("/api/slow", [](const httplib::Request&, httplib::Response& res) {
        std::this_thread::sleep_for(std::chrono::seconds(3));
        json redis_data = query_redis("cache:user:3");
        json result;
        result["service"] = "cpp";
        result["scenario"] = "slow";
        result["redis"] = redis_data;
        res.set_content(result.dump(), "application/json");
    });

    svr.Get("/api/error", [](const httplib::Request&, httplib::Response& res) {
        res.status = 500;
        res.set_content(json{{"service", "cpp"}, {"scenario", "error"}, {"message", "internal server error"}}.dump(), "application/json");
    });

    svr.Get("/api/timeout-downstream", [](const httplib::Request&, httplib::Response& res) {
        json php_data = call_service(PHP_SERVICE_URL, 100);
        json result;
        result["service"] = "cpp";
        result["scenario"] = "timeout-downstream";
        result["next"] = php_data;
        res.set_content(result.dump(), "application/json");
    });

    svr.Get("/api/notfound-downstream", [](const httplib::Request&, httplib::Response& res) {
        httplib::Client cli(PHP_SERVICE_URL);
        cli.set_connection_timeout(std::chrono::milliseconds(5000));
        cli.set_read_timeout(std::chrono::milliseconds(5000));
        auto r = cli.Get("/api/nonexistent-path-404");
        json result;
        result["service"] = "cpp";
        result["scenario"] = "notfound-downstream";
        if (r) {
            result["status"] = r->status;
            result["body"] = r->body;
        } else {
            result["error"] = "connection failed";
        }
        res.set_content(result.dump(), "application/json");
    });

    svr.Get("/api/error-downstream", [](const httplib::Request&, httplib::Response& res) {
        httplib::Client cli(PHP_SERVICE_URL);
        cli.set_connection_timeout(std::chrono::milliseconds(5000));
        cli.set_read_timeout(std::chrono::milliseconds(5000));
        auto r = cli.Get("/api/error");
        json result;
        result["service"] = "cpp";
        result["scenario"] = "error-downstream";
        if (r) {
            result["status"] = r->status;
            result["body"] = r->body;
        } else {
            result["error"] = "connection failed";
        }
        res.set_content(result.dump(), "application/json");
    });

    svr.Get("/api/connection-refused", [](const httplib::Request&, httplib::Response& res) {
        httplib::Client cli(INVALID_HOST);
        cli.set_connection_timeout(std::chrono::milliseconds(2000));
        cli.set_read_timeout(std::chrono::milliseconds(2000));
        auto r = cli.Get("/api/data");
        json result;
        result["service"] = "cpp";
        result["scenario"] = "connection-refused";
        if (r) {
            result["status"] = r->status;
        } else {
            result["error"] = "connection refused or timeout";
        }
        res.set_content(result.dump(), "application/json");
    });

    svr.Get("/api/db-error", [](const httplib::Request&, httplib::Response& res) {
        json result = redis_error();
        result["service"] = "cpp";
        result["scenario"] = "db-error";
        res.set_content(result.dump(), "application/json");
    });

    svr.Get("/api/health", [](const httplib::Request&, httplib::Response& res) {
        res.set_content(json{{"status", "ok"}, {"service", "cpp"}}.dump(), "application/json");
    });

    std::cout << "C++ service starting on port 8086" << std::endl;
    svr.listen("0.0.0.0", 8086);
    return 0;
}