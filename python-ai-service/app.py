import asyncio
import json
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "qwen-plus")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
RERANK_MODEL = os.getenv("RERANK_MODEL", "gte-rerank-v2")
RERANK_URL = os.getenv("RERANK_URL", "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "")
AI_SERVICE_PORT = int(os.getenv("AI_SERVICE_PORT", "8087"))

app = FastAPI()
mcp_session = None


def new_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)


async def mcp_list_tools() -> list[dict]:
    if mcp_session is None:
        raise RuntimeError("MCP not connected")
    result = await mcp_session.list_tools()
    tools = []
    for t in result.tools:
        tools.append({
            "name": t.name,
            "description": t.description or "",
            "inputSchema": t.inputSchema if hasattr(t, 'inputSchema') else {"type": "object", "properties": {}},
        })
    return tools


async def mcp_call_tool(name: str, arguments: dict) -> str:
    if mcp_session is None:
        raise RuntimeError("MCP not connected")
    result = await mcp_session.call_tool(name, arguments)
    parts = [c.text for c in result.content if hasattr(c, 'text')]
    return "\n".join(parts) if parts else "(no text content)"


def mcp_tools_to_openai_functions(mcp_tools: list[dict]) -> list[dict]:
    tools = []
    for t in mcp_tools:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
            },
        })
    return tools


async def init_mcp_with_retry():
    global mcp_session
    if not MCP_SERVER_URL:
        logger.info("MCP_SERVER_URL not set, MCP features unavailable")
        return
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    max_retries = 30
    for i in range(1, max_retries + 1):
        try:
            async with streamablehttp_client(MCP_SERVER_URL) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    mcp_session = session
                    logger.info(f"MCP client connected: {MCP_SERVER_URL}")
                    while True:
                        await asyncio.sleep(60)
        except Exception as e:
            logger.warning(f"MCP init attempt {i}/{max_retries} failed: {e}")
            mcp_session = None
            await asyncio.sleep(3)
    logger.error(f"MCP init failed after {max_retries} attempts")


@app.post("/chat")
async def handle_chat(request: Request):
    body = await request.json()
    message = body.get("message", "")
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)
    model = body.get("model") or OPENAI_MODEL
    client = new_openai_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": message},
        ],
    )
    if not resp.choices:
        return JSONResponse({"error": "no choices"}, status_code=500)
    return JSONResponse({"content": resp.choices[0].message.content, "model": resp.model})


@app.post("/chat/stream")
async def handle_chat_stream(request: Request):
    body = await request.json()
    message = body.get("message", "")
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)
    model = body.get("model") or OPENAI_MODEL

    async def event_generator():
        client = new_openai_client()
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": message},
            ],
            stream=True,
        )
        async for chunk in stream:
            for choice in chunk.choices:
                if choice.delta and choice.delta.content:
                    yield f"data: {choice.delta.content}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/chat/agent")
async def handle_chat_agent(request: Request):
    body = await request.json()
    message = body.get("message", "")
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)
    model = body.get("model") or OPENAI_MODEL

    async def agent_loop():
        client = new_openai_client()
        tools = []
        if mcp_session is not None:
            try:
                mcp_tools = await mcp_list_tools()
                tools = mcp_tools_to_openai_functions(mcp_tools)
            except Exception as e:
                logger.warning(f"list tools failed: {e}")

        messages = [
            {"role": "system", "content": "You are a helpful assistant. Use the provided tools when needed."},
            {"role": "user", "content": message},
        ]

        kwargs = {"model": model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools

        stream = await client.chat.completions.create(**kwargs)
        tool_calls_acc: dict[int, dict] = {}

        async for chunk in stream:
            for choice in chunk.choices:
                delta = choice.delta
                if delta and delta.content:
                    yield f"data: {delta.content}\n\n"
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc.function.arguments

        if not tool_calls_acc:
            yield "data: [DONE]\n\n"
            return

        assistant_tool_calls = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            assistant_tool_calls.append({
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            })
        messages.append({"role": "assistant", "tool_calls": assistant_tool_calls})

        for tc_info in assistant_tool_calls:
            fn_name = tc_info["function"]["name"]
            try:
                fn_args = json.loads(tc_info["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}
            yield f"event: tool_call\ndata: {json.dumps({'tool': fn_name, 'args': fn_args}, ensure_ascii=False)}\n\n"
            try:
                tool_result = await mcp_call_tool(fn_name, fn_args)
            except Exception as e:
                tool_result = f"tool error: {e}"
            yield f"event: tool_result\ndata: {json.dumps({'tool': fn_name, 'result': tool_result}, ensure_ascii=False)}\n\n"
            messages.append({"role": "tool", "tool_call_id": tc_info["id"], "content": tool_result})

        stream2 = await client.chat.completions.create(model=model, messages=messages, stream=True)
        async for chunk in stream2:
            for choice in chunk.choices:
                if choice.delta and choice.delta.content:
                    yield f"data: {choice.delta.content}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(agent_loop(), media_type="text/event-stream")


@app.post("/embeddings")
async def handle_embeddings(request: Request):
    body = await request.json()
    input_texts = body.get("input", [])
    if not input_texts:
        return JSONResponse({"error": "input required"}, status_code=400)
    if isinstance(input_texts, str):
        input_texts = [input_texts]
    model = body.get("model") or EMBEDDING_MODEL
    include_embedding = body.get("include_embedding", True)
    dimensions = body.get("dimensions")
    client = new_openai_client()
    kwargs = {"model": model, "input": input_texts}
    if dimensions:
        kwargs["dimensions"] = dimensions
    resp = await client.embeddings.create(**kwargs)
    logger.info(f"[Embeddings] model={resp.model} input_tokens={resp.usage.prompt_tokens} total_tokens={resp.usage.total_tokens}")
    embeddings = []
    for item in resp.data:
        entry = {"index": item.index, "dimensions": len(item.embedding)}
        if include_embedding:
            entry["embedding"] = item.embedding
        embeddings.append(entry)
    return JSONResponse({
        "model": resp.model,
        "embeddings": embeddings,
        "usage": {"prompt_tokens": resp.usage.prompt_tokens, "total_tokens": resp.usage.total_tokens},
    })


@app.post("/chat/tool")
async def handle_chat_tool(request: Request):
    body = await request.json()
    message = body.get("message", "")
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)
    model = body.get("model") or OPENAI_MODEL
    client = new_openai_client()
    tools = [
        {"type": "function", "function": {"name": "get_weather", "description": "获取指定城市的天气信息", "parameters": {"type": "object", "properties": {"city": {"type": "string", "description": "城市名称"}}, "required": ["city"]}}},
        {"type": "function", "function": {"name": "get_current_time", "description": "获取当前时间", "parameters": {"type": "object", "properties": {"timezone": {"type": "string", "description": "时区，如 Asia/Shanghai"}}}}},
    ]
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Use the provided tools when needed."},
        {"role": "user", "content": message},
    ]
    resp = await client.chat.completions.create(model=model, messages=messages, tools=tools, tool_choice="auto")
    result = {"content": resp.choices[0].message.content, "tool_calls": None}
    if resp.choices[0].message.tool_calls:
        result["tool_calls"] = []
        for tc in resp.choices[0].message.tool_calls:
            result["tool_calls"].append({"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}})
    return JSONResponse(result)


@app.post("/rerank")
async def handle_rerank(request: Request):
    body = await request.json()
    query = body.get("query", "")
    documents = body.get("documents", [])
    if not query or not documents:
        return JSONResponse({"error": "query and documents required"}, status_code=400)
    model = body.get("model") or RERANK_MODEL
    top_n = body.get("top_n", len(documents))
    return_documents = body.get("return_documents", False)
    dashscope_key = os.getenv("DASHSCOPE_API_KEY") or OPENAI_API_KEY

    import httpx
    async with httpx.AsyncClient() as http_client:
        req_body = {
            "model": model,
            "input": {"query": query, "documents": documents},
            "parameters": {"top_n": top_n, "return_documents": return_documents},
        }
        resp = await http_client.post(
            RERANK_URL,
            headers={"Authorization": f"Bearer {dashscope_key}", "Content-Type": "application/json"},
            json=req_body,
            timeout=30.0,
        )
        data = resp.json()

    if "code" in data and data["code"] != "Success":
        logger.warning("rerank failed model=%s: %s", model, data.get("message"))
        return JSONResponse({"error": data.get("message", "rerank failed"), "details": data}, status_code=500)
    return JSONResponse(data)


@app.get("/mcp/tools")
async def handle_mcp_tools():
    if mcp_session is None:
        return JSONResponse({"error": "MCP not connected", "mcp_server_url": MCP_SERVER_URL}, status_code=503)
    try:
        tools = await mcp_list_tools()
        return JSONResponse({"tools": tools})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/mcp/call")
async def handle_mcp_call(request: Request):
    body = await request.json()
    tool_name = body.get("tool_name", "")
    args = body.get("args", {})
    if not tool_name:
        return JSONResponse({"error": "tool_name required"}, status_code=400)
    if mcp_session is None:
        return JSONResponse({"error": "MCP not connected"}, status_code=503)
    try:
        result = await mcp_call_tool(tool_name, args)
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def handle_health():
    return JSONResponse({
        "status": "ok",
        "timestamp": int(time.time()),
        "service": "python-ai",
        "port": AI_SERVICE_PORT,
        "mcp_connected": mcp_session is not None,
        "openai_base": OPENAI_BASE_URL,
        "openai_model": OPENAI_MODEL,
    })


@app.on_event("startup")
async def on_startup():
    logger.info(f"=== Python AI Service starting on port {AI_SERVICE_PORT} ===")
    logger.info("  POST /chat         - OpenAI chat (non-stream)")
    logger.info("  POST /chat/stream  - OpenAI chat (SSE stream)")
    logger.info("  POST /chat/agent   - Agent Loop + MCP tool calling")
    logger.info("  POST /embeddings   - OpenAI embeddings")
    logger.info("  POST /chat/tool    - OpenAI native tool calling")
    logger.info("  POST /rerank       - Rerank")
    logger.info("  GET  /mcp/tools    - List MCP tools")
    logger.info("  POST /mcp/call     - Call MCP tool")
    logger.info("  GET  /health       - Health check")
    if MCP_SERVER_URL:
        asyncio.create_task(init_mcp_with_retry())


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=AI_SERVICE_PORT, log_level="info")