using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;
using System.Text.Json;
using Grpc.Core;
using ObiDemo;
using MongoDB.Driver;
using StackExchange.Redis;

namespace ObiDemo.Services;

public class DemoServiceImpl : DemoService.DemoServiceBase
{
    private readonly IMongoClient _mongoClient;
    private readonly IConnectionMultiplexer _redis;
    private readonly HttpClient _httpClient;
    private readonly string _cppServiceUrl;
    private readonly string _goHttpUrl;
    private readonly string _nodejsHttpUrl;

    public DemoServiceImpl(IMongoClient mongoClient, IConnectionMultiplexer redis, HttpClient httpClient)
    {
        _mongoClient = mongoClient;
        _redis = redis;
        _httpClient = httpClient;
        _cppServiceUrl = Environment.GetEnvironmentVariable("CPP_SERVICE_URL") ?? "http://cpp-service:8086";
        _goHttpUrl = Environment.GetEnvironmentVariable("GO_HTTP_ADDR") ?? "http://go-service:8084";
        _nodejsHttpUrl = Environment.GetEnvironmentVariable("NODEJS_HTTP_ADDR") ?? "http://nodejs-service:8082";
    }

    public override async Task<DataResponse> GetData(DataRequest request, ServerCallContext context)
    {
        var database = _mongoClient.GetDatabase("obidemo");

        var customers = await database
            .GetCollection<MongoDB.Bson.BsonDocument>("customers")
            .Find(new MongoDB.Bson.BsonDocument())
            .Limit(5)
            .ToListAsync();

        var db = _redis.GetDatabase();
        var cachedProduct = await db.StringGetAsync("cache:product:2");

        string cppData = "{}";
        try
        {
            var cppResponse = await _httpClient.GetAsync($"{_cppServiceUrl}/api/data");
            if (cppResponse.IsSuccessStatusCode)
            {
                cppData = await cppResponse.Content.ReadAsStringAsync();
            }
        }
        catch { }

        Dictionary<string, object>? goHttpInfo = null;
        try
        {
            var goResp = await _httpClient.GetAsync($"{_goHttpUrl}/api/health");
            if (goResp.IsSuccessStatusCode)
            {
                goHttpInfo = await goResp.Content.ReadFromJsonAsync<Dictionary<string, object>>();
            }
        }
        catch { }

        Dictionary<string, object>? nodejsHttpInfo = null;
        try
        {
            var nodejsResp = await _httpClient.GetAsync($"{_nodejsHttpUrl}/api/health");
            if (nodejsResp.IsSuccessStatusCode)
            {
                nodejsHttpInfo = await nodejsResp.Content.ReadFromJsonAsync<Dictionary<string, object>>();
            }
        }
        catch { }

        var result = new Dictionary<string, object>
        {
            ["service"] = "dotnet",
            ["mongodb"] = customers.Select(c => c.ToDictionary()).ToList(),
            ["redis"] = cachedProduct.HasValue ? cachedProduct.ToString() : null,
            ["next"] = cppData,
            ["go_http_sidecall"] = goHttpInfo,
            ["nodejs_http_sidecall"] = nodejsHttpInfo
        };

        return new DataResponse
        {
            Data = JsonSerializer.Serialize(result),
            Source = "dotnet"
        };
    }

    public override async Task<DataResponse> GetDataError(DataRequest request, ServerCallContext context)
    {
        throw new RpcException(new Status(StatusCode.Internal, "deliberate gRPC error from .NET for OBI demo"));
    }
}