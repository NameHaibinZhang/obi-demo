db = db.getSiblingDB('obidemo');

db.customers.insertMany([
    { name: "Alice", email: "alice@example.com", address: "123 Main St", tier: "gold" },
    { name: "Bob", email: "bob@example.com", address: "456 Oak Ave", tier: "silver" },
    { name: "Charlie", email: "charlie@example.com", address: "789 Pine Rd", tier: "bronze" },
    { name: "Diana", email: "diana@example.com", address: "321 Elm Blvd", tier: "gold" },
    { name: "Eve", email: "eve@example.com", address: "654 Maple Dr", tier: "silver" }
]);

db.logs.insertMany([
    { service: "python", level: "info", message: "Service started", timestamp: new Date() },
    { service: "nodejs", level: "info", message: "Cache initialized", timestamp: new Date() },
    { service: "go", level: "info", message: "Database connected", timestamp: new Date() },
    { service: "dotnet", level: "info", message: "gRPC server ready", timestamp: new Date() },
    { service: "cpp", level: "info", message: "Redis connected", timestamp: new Date() },
    { service: "php", level: "info", message: "Request processed", timestamp: new Date() }
]);

db.sessions.insertMany([
    { sessionId: "sess-001", userId: 1, data: { cart: ["Widget"], preferences: { theme: "dark" } } },
    { sessionId: "sess-002", userId: 2, data: { cart: ["Gadget", "Doohickey"], preferences: { theme: "light" } } }
]);