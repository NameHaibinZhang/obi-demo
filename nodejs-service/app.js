const express = require('express');
const redis = require('redis');
const { MongoClient } = require('mongodb');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');

const app = express();

const REDIS_URL = process.env.REDIS_URL || 'redis://redis:6379';
const MONGO_URL = process.env.MONGO_URL || 'mongodb://mongodb:27017/obidemo';
const NEXT_SERVICE_URL = process.env.NEXT_SERVICE_URL || 'http://go-service:8084';
const GO_GRPC_ADDR = process.env.GO_GRPC_ADDR || 'go-service:9084';
const GO_HTTP_ADDR = process.env.GO_HTTP_ADDR || 'http://go-service:8084';
const DOTNET_HTTP_ADDR = process.env.DOTNET_HTTP_ADDR || 'http://dotnet-service:8085';
const INVALID_HOST = process.env.INVALID_HOST || 'http://nonexistent-service:9999';
const SLOW_DELAY = parseInt(process.env.SLOW_DELAY || '3') * 1000;

const packageDefinition = protoLoader.loadSync(__dirname + '/proto/demo.proto', {
    keepCase: true, longs: String, enums: String, defaults: true, oneofs: true
});
const obiDemoProto = grpc.loadPackageDefinition(packageDefinition).obidemo;
const goGrpcClient = new obiDemoProto.DemoService(GO_GRPC_ADDR, grpc.credentials.createInsecure());

async function queryRedis(keys) {
    try {
        const client = redis.createClient({ url: REDIS_URL });
        await client.connect();
        const result = {};
        for (const key of keys) { result[key] = await client.get(key); }
        await client.disconnect();
        return result;
    } catch (e) { return { error: e.message }; }
}

async function queryMongoDB(collectionName, query, limit) {
    try {
        const client = new MongoClient(MONGO_URL);
        await client.connect();
        const db = client.db('obidemo');
        const data = await db.collection(collectionName).find(query).limit(limit).toArray();
        await client.close();
        return data;
    } catch (e) { return [{ error: e.message }]; }
}

function callGoGrpc(method = 'GetData', requestId = 'nodejs-request', timeoutMs = 15000) {
    return new Promise((resolve) => {
        const deadline = new Date(Date.now() + timeoutMs);
        const callMethod = method === 'GetDataError' ? 'GetDataError' : 'GetData';
        goGrpcClient[callMethod]({ request_id: requestId }, { deadline }, (err, response) => {
            if (err) {
                resolve({ error: err.message, grpc_code: err.code });
            } else {
                try { resolve(JSON.parse(response.data)); }
                catch { resolve({ data: response.data, source: response.source }); }
            }
        });
    });
}

async function callServiceHttp(url, timeoutMs = 15000) {
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        const response = await fetch(url, { signal: controller.signal });
        clearTimeout(timer);
        const data = await response.json();
        return { data, status: response.status };
    } catch (e) {
        if (e.name === 'AbortError') return { data: { error: 'timeout' }, status: 0 };
        return { data: { error: e.message }, status: 0 };
    }
}

app.get('/api/data', async (req, res) => {
    const redisData = await queryRedis(['cache:user:1', 'cache:product:1']);
    const mongoData = await queryMongoDB('customers', {}, 5);
    const nextData = await callGoGrpc('GetData', 'nodejs-data-request');
    const goHttpInfo = await callServiceHttp(`${GO_HTTP_ADDR}/api/health`, 5000);
    const dotnetHttpInfo = await callServiceHttp(`${DOTNET_HTTP_ADDR}/api/health`, 5000);
    res.json({
        service: 'nodejs', redis: redisData, mongodb: mongoData,
        next: nextData,
        go_http_sidecall: goHttpInfo.data,
        dotnet_http_sidecall: dotnetHttpInfo.data
    });
});

app.get('/api/http-chain', async (req, res) => {
    const redisData = await queryRedis(['cache:user:1']);
    const { data: goData } = await callServiceHttp(`${GO_HTTP_ADDR}/api/data`, 15000);
    res.json({ service: 'nodejs', scenario: 'http-chain', redis: redisData, next: goData });
});

app.get('/api/slow', async (req, res) => {
    await new Promise(r => setTimeout(r, SLOW_DELAY));
    const nextData = await callGoGrpc('GetData', 'nodejs-slow-request');
    res.json({ service: 'nodejs', scenario: 'slow', next: nextData });
});

app.get('/api/error', (req, res) => {
    res.status(500).json({ service: 'nodejs', scenario: 'error', message: 'internal server error' });
});

app.get('/api/grpc-timeout-downstream', async (req, res) => {
    const result = await callGoGrpc('GetData', 'timeout-request', 100);
    res.json({ service: 'nodejs', scenario: 'grpc-timeout-downstream', result });
});

app.get('/api/grpc-error-downstream', async (req, res) => {
    const result = await callGoGrpc('GetDataError', 'error-request', 5000);
    res.json({ service: 'nodejs', scenario: 'grpc-error-downstream', result });
});

app.get('/api/timeout-downstream', async (req, res) => {
    const result = await callServiceHttp(`${GO_HTTP_ADDR}/api/data`, 100);
    res.json({ service: 'nodejs', scenario: 'timeout-downstream', result });
});

app.get('/api/notfound-downstream', async (req, res) => {
    const result = await callServiceHttp(`${GO_HTTP_ADDR}/api/nonexistent-path-404`, 5000);
    res.json({ service: 'nodejs', scenario: 'notfound-downstream', result });
});

app.get('/api/error-downstream', async (req, res) => {
    const result = await callServiceHttp(`${GO_HTTP_ADDR}/api/error`, 5000);
    res.json({ service: 'nodejs', scenario: 'error-downstream', result });
});

app.get('/api/connection-refused', async (req, res) => {
    const result = await callServiceHttp(`${INVALID_HOST}/api/data`, 2000);
    res.json({ service: 'nodejs', scenario: 'connection-refused', result });
});

app.get('/api/db-error', async (req, res) => {
    const redisResult = await queryRedis(['invalid:key:that:fails']);
    const mongoResult = await queryMongoDB('nonexistent_collection_xyz', {}, 5);
    res.json({ service: 'nodejs', scenario: 'db-error', redis: redisResult, mongodb: mongoResult });
});

app.get('/api/db-slow', async (req, res) => {
    const redisData = await queryRedis(['cache:user:1']);
    await new Promise(r => setTimeout(r, SLOW_DELAY));
    res.json({ service: 'nodejs', scenario: 'db-slow', redis: redisData });
});

app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', service: 'nodejs', port: 8082 });
});

app.listen(8082, '0.0.0.0', () => {
    console.log('NodeJS service running on port 8082');
});