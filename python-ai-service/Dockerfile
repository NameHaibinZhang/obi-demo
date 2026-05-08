FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV OPENAI_API_KEY=""
ENV OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
ENV OPENAI_MODEL="qwen-plus"
ENV MCP_SERVER_URL=""
ENV AI_SERVICE_PORT="8087"

EXPOSE 8087

CMD ["python", "app.py"]