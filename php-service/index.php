<?php
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);

$MYSQL_HOST = getenv('MYSQL_HOST') ?: 'mysql';
$MYSQL_USER = getenv('MYSQL_USER') ?: 'root';
$MYSQL_PASSWORD = getenv('MYSQL_PASSWORD') ?: 'demo123';
$MYSQL_DB = getenv('MYSQL_DB') ?: 'obidemo';
$MONGO_URL = getenv('MONGO_URL') ?: 'mongodb://mongodb:27017';
$SLOW_DELAY = intval(getenv('SLOW_DELAY') ?: '3');

header('Content-Type: application/json');

if ($path === '/api/health') {
    echo json_encode(['status' => 'ok', 'service' => 'php']);
    exit;
}

if ($path === '/api/error') {
    http_response_code(500);
    echo json_encode(['service' => 'php', 'scenario' => 'error', 'message' => 'internal server error']);
    exit;
}

if ($path === '/api/slow') {
    sleep($SLOW_DELAY);
    $orders = [];
    try {
        $mysql = new mysqli($MYSQL_HOST, $MYSQL_USER, $MYSQL_PASSWORD, $MYSQL_DB);
        if (!$mysql->connect_error) {
            $result = $mysql->query("SELECT id, user_id, product_id, quantity, total, status FROM orders LIMIT 5");
            while ($row = $result->fetch_assoc()) { $orders[] = $row; }
            $mysql->close();
        }
    } catch (Exception $e) { $orders = [['error' => $e->getMessage()]]; }
    echo json_encode(['service' => 'php', 'scenario' => 'slow', 'orders' => $orders]);
    exit;
}

if ($path === '/api/db-error') {
    $result = [];
    try {
        $mysql = new mysqli($MYSQL_HOST, $MYSQL_USER, $MYSQL_PASSWORD, $MYSQL_DB);
        if (!$mysql->connect_error) {
            $mysql->query("SELECT * FROM nonexistent_table_xyz");
            $result = ['mysql_error' => $mysql->error];
            $mysql->close();
        } else {
            $result = ['mysql_error' => $mysql->connect_error];
        }
    } catch (Exception $e) { $result = ['error' => $e->getMessage()]; }
    echo json_encode(['service' => 'php', 'scenario' => 'db-error', 'result' => $result]);
    exit;
}

if ($path === '/api/db-slow') {
    $result = [];
    try {
        $mysql = new mysqli($MYSQL_HOST, $MYSQL_USER, $MYSQL_PASSWORD, $MYSQL_DB);
        if (!$mysql->connect_error) {
            $mysql->query("SELECT SLEEP(3), id, name FROM orders LIMIT 1");
            $result = ['slow_query' => 'completed after 3s'];
            $mysql->close();
        }
    } catch (Exception $e) { $result = ['error' => $e->getMessage()]; }
    echo json_encode(['service' => 'php', 'scenario' => 'db-slow', 'result' => $result]);
    exit;
}

if ($path === '/api/data') {
    $orders = [];
    $logs = [];

    try {
        $mysql = new mysqli($MYSQL_HOST, $MYSQL_USER, $MYSQL_PASSWORD, $MYSQL_DB);
        if (!$mysql->connect_error) {
            $result = $mysql->query("SELECT id, user_id, product_id, quantity, total, status FROM orders LIMIT 5");
            while ($row = $result->fetch_assoc()) { $orders[] = $row; }
            $mysql->close();
        } else { $orders = [['error' => $mysql->connect_error]]; }
    } catch (Exception $e) { $orders = [['error' => $e->getMessage()]]; }

    try {
        $manager = new MongoDB\Driver\Manager($MONGO_URL);
        $query = new MongoDB\Driver\Query([], ['limit' => 5]);
        $cursor = $manager->executeQuery("obidemo.logs", $query);
        foreach ($cursor as $doc) { $logs[] = (array)$doc; }
    } catch (Exception $e) { $logs = [['error' => $e->getMessage()]]; }

    echo json_encode(['service' => 'php', 'orders' => $orders, 'mongodb' => $logs]);
    exit;
}

http_response_code(404);
echo json_encode(['error' => 'not found', 'path' => $path]);
?>