using ObiDemo.Services;
using StackExchange.Redis;
using Microsoft.AspNetCore.Server.Kestrel.Core;

var builder = WebApplication.CreateBuilder(args);

builder.WebHost.ConfigureKestrel(options =>
{
    options.ListenAnyIP(8085, listenOptions =>
    {
        listenOptions.Protocols = HttpProtocols.Http1;
    });
    options.ListenAnyIP(9085, listenOptions =>
    {
        listenOptions.Protocols = HttpProtocols.Http2;
    });
});

builder.Services.AddGrpc();
builder.Services.AddSingleton<IConnectionMultiplexer>(
    ConnectionMultiplexer.Connect(Environment.GetEnvironmentVariable("REDIS_ADDR") ?? "redis:6379")
);
builder.Services.AddSingleton<MongoDB.Driver.IMongoClient>(
    new MongoDB.Driver.MongoClient(Environment.GetEnvironmentVariable("MONGO_URL") ?? "mongodb://mongodb:27017")
);
builder.Services.AddSingleton(new HttpClient
{
    Timeout = TimeSpan.FromSeconds(15)
});

var app = builder.Build();

app.MapGrpcService<DemoServiceImpl>();
app.MapGet("/api/health", () => new { status = "ok", service = "dotnet", port = 8085 });
app.MapGet("/api/error", () => Results.Json(new { service = "dotnet", scenario = "error", message = "internal server error" }, statusCode: 500));
app.MapGet("/api/slow", async () =>
{
    await Task.Delay(3000);
    return Results.Json(new { service = "dotnet", scenario = "slow" });
});
app.MapGet("/api/http-data", async (HttpClient httpClient) =>
{
    var cppUrl = Environment.GetEnvironmentVariable("CPP_SERVICE_URL") ?? "http://cpp-service:8086";
    var nodejsUrl = Environment.GetEnvironmentVariable("NODEJS_HTTP_ADDR") ?? "http://nodejs-service:8082";

    string cppData = "{}";
    try
    {
        var cppResp = await httpClient.GetAsync($"{cppUrl}/api/data");
        if (cppResp.IsSuccessStatusCode) cppData = await cppResp.Content.ReadAsStringAsync();
    }
    catch { }

    Dictionary<string, object>? nodejsInfo = null;
    try
    {
        var nodejsResp = await httpClient.GetAsync($"{nodejsUrl}/api/health");
        if (nodejsResp.IsSuccessStatusCode) nodejsInfo = await nodejsResp.Content.ReadFromJsonAsync<Dictionary<string, object>>();
    }
    catch { }

    return Results.Json(new { service = "dotnet", scenario = "http-data", next = cppData, nodejs_http_sidecall = nodejsInfo });
});

app.Run();