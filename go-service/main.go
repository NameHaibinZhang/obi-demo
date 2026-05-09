package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"log"
	"net"
	"net/http"
	"os"
	"time"

	_ "github.com/go-sql-driver/mysql"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "obi-demo/proto"
)

var (
	mysqlDSN       = os.Getenv("MYSQL_DSN")
	redisAddr      = os.Getenv("REDIS_ADDR")
	dotnetAddr     = os.Getenv("DOTNET_GRPC_ADDR")
	dotnetHttpAddr = os.Getenv("DOTNET_HTTP_ADDR")
)

func init() {
	if mysqlDSN == "" { mysqlDSN = "root:demo123@tcp(mysql:3306)/obidemo" }
	if redisAddr == "" { redisAddr = "redis:6379" }
	if dotnetAddr == "" { dotnetAddr = "dotnet-service:9085" }
	if dotnetHttpAddr == "" { dotnetHttpAddr = "http://dotnet-service:8085" }
}

var (
	mysqlDB     *sql.DB
	redisClient *redis.Client
	grpcConn    *grpc.ClientConn
	grpcClient  pb.DemoServiceClient
	httpClient  = &http.Client{Timeout: 5 * time.Second}
)

func initConnections() {
	mysqlDB, _ = sql.Open("mysql", mysqlDSN)
	mysqlDB.SetMaxOpenConns(10)
	redisClient = redis.NewClient(&redis.Options{Addr: redisAddr})
	grpcConn, _ = grpc.NewClient(dotnetAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	grpcClient = pb.NewDemoServiceClient(grpcConn)
}

func queryMySQL(query string) []map[string]interface{} {
	rows, err := mysqlDB.Query(query)
	if err != nil { return []map[string]interface{}{{"error": err.Error()}} }
	defer rows.Close()
	var results []map[string]interface{}
	for rows.Next() {
		var id int; var name, category string; var price float64
		if err := rows.Scan(&id, &name, &price, &category); err != nil { continue }
		results = append(results, map[string]interface{}{"id": id, "name": name, "price": price, "category": category})
	}
	return results
}

func queryRedis(key string) map[string]interface{} {
	val, err := redisClient.Get(context.Background(), key).Result()
	if err != nil { return map[string]interface{}{"error": err.Error()} }
	return map[string]interface{}{key: val}
}

func callDotnetGRPC(ctx context.Context) map[string]interface{} {
	resp, err := grpcClient.GetData(ctx, &pb.DataRequest{RequestId: "go-request"})
	if err != nil {
		st, _ := status.FromError(err)
		return map[string]interface{}{"error": err.Error(), "grpc_code": st.Code().String()}
	}
	var data map[string]interface{}
	json.Unmarshal([]byte(resp.Data), &data)
	return data
}

func callDotnetGRPCError(ctx context.Context) map[string]interface{} {
	resp, err := grpcClient.GetDataError(ctx, &pb.DataRequest{RequestId: "go-error-request"})
	if err != nil {
		st, _ := status.FromError(err)
		return map[string]interface{}{"error": err.Error(), "grpc_code": st.Code().String()}
	}
	return map[string]interface{}{"data": resp.Data, "source": resp.Source}
}

func callServiceHTTP(url string) map[string]interface{} {
	resp, err := httpClient.Get(url)
	if err != nil { return map[string]interface{}{"error": err.Error()} }
	defer resp.Body.Close()
	var data map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&data)
	return data
}

func writeJSON(w http.ResponseWriter, data map[string]interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(data)
}

type goGRPCServer struct {
	pb.UnimplementedDemoServiceServer
}

func (s *goGRPCServer) GetData(ctx context.Context, req *pb.DataRequest) (*pb.DataResponse, error) {
	products := queryMySQL("SELECT id, name, price, category FROM products LIMIT 5")
	redisData := queryRedis("cache:product:1")
	dotnetCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	nextData := callDotnetGRPC(dotnetCtx)
	dotnetHttpInfo := callServiceHTTP(dotnetHttpAddr + "/api/health")
	result := map[string]interface{}{
		"service": "go-grpc", "products": products, "redis": redisData,
		"next": nextData, "dotnet_http_sidecall": dotnetHttpInfo,
	}
	data, _ := json.Marshal(result)
	return &pb.DataResponse{Data: string(data), Source: "go-grpc-server"}, nil
}

func (s *goGRPCServer) GetDataError(ctx context.Context, req *pb.DataRequest) (*pb.DataResponse, error) {
	return nil, status.Error(codes.Internal, "deliberate gRPC error from Go server for OBI demo")
}

func dataHandler(w http.ResponseWriter, r *http.Request) {
	products := queryMySQL("SELECT id, name, price, category FROM products LIMIT 5")
	redisData := queryRedis("cache:product:1")
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	nextData := callDotnetGRPC(ctx)
	dotnetHttpInfo := callServiceHTTP(dotnetHttpAddr + "/api/health")
	writeJSON(w, map[string]interface{}{
		"service": "go", "products": products, "redis": redisData,
		"next": nextData, "dotnet_http_sidecall": dotnetHttpInfo,
	})
}

func slowHandler(w http.ResponseWriter, r *http.Request) {
	time.Sleep(3 * time.Second)
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	nextData := callDotnetGRPC(ctx)
	writeJSON(w, map[string]interface{}{"service": "go", "scenario": "slow", "next": nextData})
}

func errorHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(500)
	writeJSON(w, map[string]interface{}{"service": "go", "scenario": "error", "message": "internal server error"})
}

func grpcTimeoutHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	nextData := callDotnetGRPC(ctx)
	writeJSON(w, map[string]interface{}{"service": "go", "scenario": "grpc-timeout", "next": nextData})
}

func grpcErrorHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	nextData := callDotnetGRPCError(ctx)
	writeJSON(w, map[string]interface{}{"service": "go", "scenario": "grpc-error", "next": nextData})
}

func dbErrorHandler(w http.ResponseWriter, r *http.Request) {
	result := queryMySQL("SELECT * FROM nonexistent_table_xyz")
	redisResult := queryRedis("invalid:key:that:fails")
	writeJSON(w, map[string]interface{}{"service": "go", "scenario": "db-error", "mysql": result, "redis": redisResult})
}

func dbSlowHandler(w http.ResponseWriter, r *http.Request) {
	result := queryMySQL("SELECT SLEEP(3), id, name FROM products LIMIT 1")
	writeJSON(w, map[string]interface{}{"service": "go", "scenario": "db-slow", "result": result})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	result := make(map[string]interface{})
	for k, v := range map[string]string{"status": "ok", "service": "go", "http_port": "8084", "grpc_port": "9084"} {
		result[k] = v
	}
	writeJSON(w, result)
}

func main() {
	initConnections()

	go func() {
		lis, err := net.Listen("tcp", ":9084")
		if err != nil { log.Fatalf("gRPC listen failed: %v", err) }
		grpcServer := grpc.NewServer()
		pb.RegisterDemoServiceServer(grpcServer, &goGRPCServer{})
		log.Println("Go gRPC server starting on :9084")
		grpcServer.Serve(lis)
	}()

	http.HandleFunc("/api/data", dataHandler)
	http.HandleFunc("/api/slow", slowHandler)
	http.HandleFunc("/api/error", errorHandler)
	http.HandleFunc("/api/grpc-timeout", grpcTimeoutHandler)
	http.HandleFunc("/api/grpc-error", grpcErrorHandler)
	http.HandleFunc("/api/db-error", dbErrorHandler)
	http.HandleFunc("/api/db-slow", dbSlowHandler)
	http.HandleFunc("/api/health", healthHandler)

	log.Println("Go HTTP server starting on :8084")
	http.ListenAndServe(":8084", nil)
}