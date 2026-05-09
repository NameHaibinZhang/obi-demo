# OBI Demo 架构说明

## 调用链（主链）

```
Python(:8081) → NodeJS(:8082) → Go(:8084/HTTP) → .NET(:8085/gRPC) → C++(:8086) → PHP(:8083)
Python(:8081) → Go(:8084/gRPC)
```

## AI 服务调用链

```
Python(:8081) → PythonAI(:8087)  (POST /chat, /embeddings, /tool, /rerank, /mcp)
Python(:8081) → NodeJS(:8082)    (background poll 每10s)
Python(:8081) → PythonAI(:8087)  (background poll AI chat)
```

Python 服务每10秒自动轮询 NodeJS `/api/data` 和 PythonAI `/chat`（使用轮换问题），无需手动触发。

### Python → AI 服务端点

| 端点 | AI服务端点 | 说明 |
|------|-----------|------|
| `/api/ai/chat` | POST `/chat` | OpenAI Chat |
| `/api/ai/embeddings` | POST `/embeddings` | OpenAI Embeddings |
| `/api/ai/tool` | POST `/chat/tool` | Chat with Tool/Agent |
| `/api/ai/rerank` | POST `/rerank` | Rerank |
| `/api/ai/mcp` | POST `/mcp/call` | MCP Tool Call |

## HTTP Side Call（NodeJS/Go/.NET之间的额外HTTP调用）

```
NodeJS → Go(HTTP)        GET /api/health
NodeJS → .NET(HTTP)      GET /api/health  
Go → .NET(HTTP)          GET /api/health
.NET → Go(HTTP)          GET /api/health
.NET → NodeJS(HTTP)      GET /api/health
```

## 数据库调用

| 服务   | 数据库    | 操作                    |
|--------|-----------|-------------------------|
| Python | MySQL     | SELECT users             |
| NodeJS | Redis     | GET cache keys           |
| NodeJS | MongoDB   | FIND customers           |
| Go     | MySQL     | SELECT products          |
| Go     | Redis     | GET cache keys           |
| .NET   | MongoDB   | FIND logs                |
| .NET   | Redis     | GET cache keys           |
| C++    | Redis     | GET/SET cache keys       |
| PHP    | MySQL     | SELECT orders            |
| PHP    | MongoDB   | FIND logs                |

## 错误场景端点

每个服务都提供以下错误端点，用于测试 OBI 异常捕获：

| 端点 | 说明 |
|------|------|
| `/api/error` | 返回500错误 |
| `/api/slow` | 响应延迟5s |
| `/api/timeout-downstream` | 调用下游超时 |
| `/api/notfound-downstream` | 调用下游404 |
| `/api/error-downstream` | 调用下游500 |
| `/api/connection-refused` | 连接被拒绝 |
| `/api/db-error` | 数据库查询错误 |
| `/api/db-slow` | 数据库查询慢 |

## OBI 可观测的协议

| 协议    | 本Demo覆盖情况                                    |
|---------|----------------------------------------------------|
| HTTP    | 所有服务之间的调用 + side calls + AI服务调用       |
| gRPC    | Python → Go, Go → .NET                             |
| MySQL   | Python, Go, PHP                                    |
| Redis   | NodeJS, Go, .NET, C++                              |
| MongoDB | NodeJS, .NET, PHP                                  |

## 端口分配

| 服务       | 端口 | 协议          |
|------------|------|---------------|
| Python     | 8081 | HTTP          |
| NodeJS     | 8082 | HTTP          |
| PHP        | 8083 | HTTP          |
| Go         | 8084 | HTTP + gRPC   |
| .NET       | 8085 | HTTP + gRPC   |
| C++        | 8086 | HTTP          |
| PythonAI   | 8087 | HTTP          |
| MySQL      | 3306 | MySQL         |
| Redis      | 6379 | Redis         |
| MongoDB    | 27017| MongoDB       |

## 快速启动

```bash
docker-compose up --build
curl http://localhost:8081/api/data
curl http://localhost:8081/api/ai/chat
```

## K8s 部署

```bash
./build.sh
./deploy.sh
```