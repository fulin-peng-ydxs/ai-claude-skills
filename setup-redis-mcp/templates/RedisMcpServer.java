package com.gzzn.mcp.redis;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class RedisMcpServer {
    private static final String PROTOCOL_VERSION = "2024-11-05";
    private static Config config;

    public static void main(String[] args) throws Exception {
        config = Config.fromEnv();

        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));
        PrintWriter writer = new PrintWriter(System.out, true);
        String line;
        while ((line = reader.readLine()) != null) {
            if (line.trim().isEmpty()) {
                continue;
            }
            Object id = null;
            try {
                Object parsed = Json.parse(line);
                if (!(parsed instanceof Map)) {
                    continue;
                }
                @SuppressWarnings("unchecked")
                Map<String, Object> request = (Map<String, Object>) parsed;
                id = request.get("id");
                String method = stringValue(request.get("method"));
                if (id == null) {
                    continue;
                }
                writer.println(Json.stringify(handle(id, method, request)));
            } catch (Exception e) {
                writer.println(Json.stringify(error(id, -32603, errorMessage(e))));
            }
        }
    }

    private static String errorMessage(Exception e) {
        return e.getClass().getName() + ": " + e.getMessage();
    }

    private static Map<String, Object> handle(Object id, String method, Map<String, Object> request) throws Exception {
        if ("initialize".equals(method)) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("protocolVersion", PROTOCOL_VERSION);
            result.put("serverInfo", mapOf("name", "redis-mcp", "version", "0.1.0"));
            result.put("capabilities", mapOf("tools", new LinkedHashMap<String, Object>()));
            return response(id, result);
        }
        if ("tools/list".equals(method)) {
            return response(id, mapOf("tools", tools()));
        }
        if ("tools/call".equals(method)) {
            @SuppressWarnings("unchecked")
            Map<String, Object> params = (Map<String, Object>) request.get("params");
            String name = stringValue(params.get("name"));
            @SuppressWarnings("unchecked")
            Map<String, Object> toolArgs = params.get("arguments") instanceof Map
                    ? (Map<String, Object>) params.get("arguments")
                    : new LinkedHashMap<>();
            return response(id, callTool(name, toolArgs));
        }
        if ("ping".equals(method)) {
            return response(id, new LinkedHashMap<String, Object>());
        }
        return error(id, -32601, "Unsupported method: " + method);
    }

    private static Object callTool(String name, Map<String, Object> args) throws Exception {
        if ("health_check".equals(name)) {
            Object reply = exec("PING");
            return textResult("ok: " + reply + " — connected to " + config.host + ":" + config.port + " db=" + config.database);
        }
        if ("keys".equals(name)) {
            String pattern = stringValue(args.get("pattern"));
            if (pattern == null || pattern.isEmpty()) {
                pattern = "*";
            }
            int limit = intValue(args.get("limit"), 200);
            List<Object> allKeys = execList("KEYS", pattern);
            List<Object> limited = allKeys.subList(0, Math.min(limit, allKeys.size()));
            return textResult(Json.stringify(limited) + "\n(total=" + allKeys.size() + ", shown=" + limited.size() + ")");
        }
        if ("get".equals(name)) {
            String key = required(args, "key");
            String type = stringValue(exec("TYPE", key));
            if ("string".equals(type)) {
                Object val = exec("GET", key);
                long ttl = longValue(exec("TTL", key));
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("key", key);
                result.put("type", type);
                result.put("value", val);
                result.put("ttl", ttl);
                return textResult(Json.stringify(result));
            } else if ("hash".equals(type)) {
                List<Object> entries = execList("HGETALL", key);
                Map<String, Object> hash = new LinkedHashMap<>();
                for (int i = 0; i + 1 < entries.size(); i += 2) {
                    hash.put(String.valueOf(entries.get(i)), entries.get(i + 1));
                }
                long ttl = longValue(exec("TTL", key));
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("key", key);
                result.put("type", type);
                result.put("value", hash);
                result.put("ttl", ttl);
                return textResult(Json.stringify(result));
            } else if ("list".equals(type)) {
                List<Object> items = execList("LRANGE", key, "0", "99");
                long ttl = longValue(exec("TTL", key));
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("key", key);
                result.put("type", type);
                result.put("value", items);
                result.put("ttl", ttl);
                return textResult(Json.stringify(result));
            } else if ("set".equals(type)) {
                List<Object> members = execList("SMEMBERS", key);
                long ttl = longValue(exec("TTL", key));
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("key", key);
                result.put("type", type);
                result.put("value", members);
                result.put("ttl", ttl);
                return textResult(Json.stringify(result));
            } else if ("none".equals(type)) {
                return textResult(Json.stringify(mapOf("key", key, "type", "none", "value", null)));
            } else {
                return textResult(Json.stringify(mapOf("key", key, "type", type, "value", "(unsupported type, use execute_command)")));
            }
        }
        if ("set".equals(name)) {
            if (!config.writable) {
                throw new IllegalStateException("This MCP profile is read-only");
            }
            String key = required(args, "key");
            String value = required(args, "value");
            boolean dryRun = booleanValue(args.get("dry_run"), true);
            int ttlSeconds = intValue(args.get("ttl_seconds"), 0);
            if (dryRun) {
                return textResult(Json.stringify(mapOf("dry_run", true, "message", "SET accepted. Re-run with dry_run=false to execute.", "key", key)));
            }
            Object reply;
            if (ttlSeconds > 0) {
                reply = exec("SET", key, value, "EX", String.valueOf(ttlSeconds));
            } else {
                reply = exec("SET", key, value);
            }
            return textResult(Json.stringify(mapOf("ok", true, "reply", reply)));
        }
        if ("del".equals(name)) {
            if (!config.writable) {
                throw new IllegalStateException("This MCP profile is read-only");
            }
            String key = required(args, "key");
            boolean dryRun = booleanValue(args.get("dry_run"), true);
            if (dryRun) {
                return textResult(Json.stringify(mapOf("dry_run", true, "message", "DEL accepted. Re-run with dry_run=false to execute.", "key", key)));
            }
            Object deleted = exec("DEL", key);
            return textResult(Json.stringify(mapOf("deleted", deleted)));
        }
        if ("ttl".equals(name)) {
            String key = required(args, "key");
            long ttl = longValue(exec("TTL", key));
            String meaning = ttl == -1 ? "no expiry" : ttl == -2 ? "key does not exist" : ttl + "s remaining";
            return textResult(Json.stringify(mapOf("key", key, "ttl", ttl, "meaning", meaning)));
        }
        if ("execute_command".equals(name)) {
            String cmd = required(args, "command");
            String[] parts = parseCommand(cmd);
            String upper = parts[0].toUpperCase();
            boolean isWrite = isWriteCommand(upper);
            if (isWrite && !config.writable) {
                throw new IllegalStateException("This MCP profile is read-only; write command rejected: " + upper);
            }
            boolean dryRun = booleanValue(args.get("dry_run"), isWrite);
            if (dryRun && isWrite) {
                return textResult(Json.stringify(mapOf("dry_run", true, "message", "Write command accepted. Re-run with dry_run=false to execute.", "command", cmd)));
            }
            Object result = execParts(parts);
            return textResult(Json.stringify(mapOf("result", result)));
        }
        throw new IllegalArgumentException("Unknown tool: " + name);
    }

    private static List<Object> tools() {
        List<Object> tools = new ArrayList<>();
        tools.add(tool("health_check", "Test the Redis connection with PING.",
                mapOf("type", "object", "properties", new LinkedHashMap<String, Object>())));
        tools.add(tool("keys", "List keys matching a pattern (default *). Results are capped by limit.",
                schemaWithProps(mapOf(
                        "pattern", prop("string", "Redis KEYS pattern, e.g. 'user:*'. Default '*'."),
                        "limit", prop("integer", "Max keys to return, default 200.")),
                        new String[]{})));
        tools.add(tool("get", "Get the value and TTL of a key. Supports string, hash, list, and set types.",
                schemaWithProps(mapOf("key", prop("string", "Redis key.")), new String[]{"key"})));
        tools.add(tool("set", "Set a string key. Dry-run by default.",
                schemaWithProps(mapOf(
                        "key", prop("string", "Redis key."),
                        "value", prop("string", "Value to set."),
                        "ttl_seconds", prop("integer", "Optional TTL in seconds."),
                        "dry_run", prop("boolean", "Default true. Set false to execute.")),
                        new String[]{"key", "value"})));
        tools.add(tool("del", "Delete a key. Dry-run by default.",
                schemaWithProps(mapOf(
                        "key", prop("string", "Redis key to delete."),
                        "dry_run", prop("boolean", "Default true. Set false to execute.")),
                        new String[]{"key"})));
        tools.add(tool("ttl", "Get the TTL of a key. Returns -1 (no expiry) or -2 (not found).",
                schemaWithProps(mapOf("key", prop("string", "Redis key.")), new String[]{"key"})));
        tools.add(tool("execute_command", "Execute any Redis command, e.g. 'INFO server', 'LLEN mylist'. Write commands are dry-run by default.",
                schemaWithProps(mapOf(
                        "command", prop("string", "Full Redis command string, e.g. 'HGET myhash field1'."),
                        "dry_run", prop("boolean", "For write commands defaults to true. Set false to execute.")),
                        new String[]{"command"})));
        return tools;
    }

    // ---- Redis RESP protocol ----

    private static Object exec(String... words) throws Exception {
        try (Socket socket = connect()) {
            OutputStream out = socket.getOutputStream();
            InputStream in = socket.getInputStream();
            if (config.password != null && !config.password.isEmpty()) {
                sendCommand(out, "AUTH", config.password);
                readReply(in);
            }
            if (config.database != 0) {
                sendCommand(out, "SELECT", String.valueOf(config.database));
                readReply(in);
            }
            sendCommand(out, words);
            return readReply(in);
        }
    }

    @SuppressWarnings("unchecked")
    private static List<Object> execList(String... words) throws Exception {
        Object result = exec(words);
        if (result instanceof List) {
            return (List<Object>) result;
        }
        List<Object> list = new ArrayList<>();
        if (result != null) {
            list.add(result);
        }
        return list;
    }

    private static Object execParts(String[] parts) throws Exception {
        return exec(parts);
    }

    private static Socket connect() throws IOException {
        Socket socket = new Socket(config.host, config.port);
        socket.setSoTimeout(10000);
        return socket;
    }

    private static void sendCommand(OutputStream out, String... words) throws IOException {
        StringBuilder sb = new StringBuilder();
        sb.append('*').append(words.length).append("\r\n");
        for (String word : words) {
            byte[] bytes = word.getBytes(StandardCharsets.UTF_8);
            sb.append('$').append(bytes.length).append("\r\n").append(word).append("\r\n");
        }
        out.write(sb.toString().getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    private static Object readReply(InputStream in) throws IOException {
        int b = in.read();
        if (b == -1) {
            throw new IOException("Connection closed by server");
        }
        char type = (char) b;
        String line = readLine(in);
        if (type == '+') {
            return line;
        }
        if (type == '-') {
            throw new IOException("Redis error: " + line);
        }
        if (type == ':') {
            return Long.parseLong(line);
        }
        if (type == '$') {
            int len = Integer.parseInt(line);
            if (len == -1) {
                return null;
            }
            byte[] data = new byte[len];
            int read = 0;
            while (read < len) {
                int n = in.read(data, read, len - read);
                if (n == -1) {
                    throw new IOException("Unexpected end of stream");
                }
                read += n;
            }
            in.read(); // \r
            in.read(); // \n
            return new String(data, StandardCharsets.UTF_8);
        }
        if (type == '*') {
            int count = Integer.parseInt(line);
            if (count == -1) {
                return null;
            }
            List<Object> list = new ArrayList<>();
            for (int i = 0; i < count; i++) {
                list.add(readReply(in));
            }
            return list;
        }
        throw new IOException("Unknown RESP type: " + (char) type);
    }

    private static String readLine(InputStream in) throws IOException {
        StringBuilder sb = new StringBuilder();
        int c;
        while ((c = in.read()) != -1) {
            if (c == '\r') {
                in.read(); // \n
                return sb.toString();
            }
            sb.append((char) c);
        }
        throw new IOException("Unexpected end of stream while reading line");
    }

    private static String[] parseCommand(String cmd) {
        List<String> parts = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        boolean inQuote = false;
        char quoteChar = 0;
        for (int i = 0; i < cmd.length(); i++) {
            char c = cmd.charAt(i);
            if (inQuote) {
                if (c == quoteChar) {
                    inQuote = false;
                } else {
                    cur.append(c);
                }
            } else if (c == '"' || c == '\'') {
                inQuote = true;
                quoteChar = c;
            } else if (c == ' ' || c == '\t') {
                if (cur.length() > 0) {
                    parts.add(cur.toString());
                    cur.setLength(0);
                }
            } else {
                cur.append(c);
            }
        }
        if (cur.length() > 0) {
            parts.add(cur.toString());
        }
        if (parts.isEmpty()) {
            throw new IllegalArgumentException("Empty command");
        }
        return parts.toArray(new String[0]);
    }

    private static final java.util.Set<String> WRITE_COMMANDS = new java.util.HashSet<>(Arrays.asList(
            "SET", "SETNX", "SETEX", "PSETEX", "MSET", "MSETNX",
            "DEL", "UNLINK", "EXPIRE", "PEXPIRE", "EXPIREAT", "PEXPIREAT", "PERSIST",
            "INCR", "INCRBY", "INCRBYFLOAT", "DECR", "DECRBY",
            "APPEND", "SETRANGE", "GETSET", "GETDEL", "GETEX",
            "HSET", "HMSET", "HSETNX", "HINCRBY", "HINCRBYFLOAT", "HDEL",
            "LPUSH", "RPUSH", "LPUSHX", "RPUSHX", "LINSERT", "LSET", "LREM",
            "LPOP", "RPOP", "LMOVE", "RPOPLPUSH",
            "SADD", "SREM", "SMOVE", "SPOP",
            "ZADD", "ZINCRBY", "ZREM", "ZREMRANGEBYRANK", "ZREMRANGEBYSCORE", "ZREMRANGEBYLEX",
            "RENAME", "RENAMENX", "COPY", "MOVE", "SELECT",
            "FLUSHDB", "FLUSHALL", "SWAPDB"
    ));

    private static boolean isWriteCommand(String upper) {
        return WRITE_COMMANDS.contains(upper);
    }

    // ---- MCP helpers ----

    private static Map<String, Object> tool(String name, String description, Object inputSchema) {
        return mapOf("name", name, "description", description, "inputSchema", inputSchema);
    }

    private static Map<String, Object> schemaWithProps(Map<String, Object> props, String[] required) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        schema.put("properties", props);
        List<Object> req = new ArrayList<>();
        for (String item : required) {
            req.add(item);
        }
        schema.put("required", req);
        return schema;
    }

    private static Map<String, Object> prop(String type, String description) {
        return mapOf("type", type, "description", description);
    }

    private static Map<String, Object> textResult(String text) {
        List<Object> content = new ArrayList<>();
        content.add(mapOf("type", "text", "text", text));
        return mapOf("content", content);
    }

    private static Map<String, Object> response(Object id, Object result) {
        return mapOf("jsonrpc", "2.0", "id", id, "result", result);
    }

    private static Map<String, Object> error(Object id, int code, String message) {
        return mapOf("jsonrpc", "2.0", "id", id, "error", mapOf("code", code, "message", message));
    }

    private static String required(Map<String, Object> args, String key) {
        String value = stringValue(args.get(key));
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("Missing required argument: " + key);
        }
        return value;
    }

    private static String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static int intValue(Object value, int fallback) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        if (value != null) {
            try {
                return Integer.parseInt(String.valueOf(value));
            } catch (NumberFormatException ignored) {}
        }
        return fallback;
    }

    private static long longValue(Object value) {
        if (value instanceof Number) {
            return ((Number) value).longValue();
        }
        if (value != null) {
            try {
                return Long.parseLong(String.valueOf(value));
            } catch (NumberFormatException ignored) {}
        }
        return -2;
    }

    private static boolean booleanValue(Object value, boolean fallback) {
        if (value instanceof Boolean) {
            return (Boolean) value;
        }
        if (value != null) {
            return Boolean.parseBoolean(String.valueOf(value));
        }
        return fallback;
    }

    @SafeVarargs
    private static Map<String, Object> mapOf(Object... items) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < items.length; i += 2) {
            map.put(String.valueOf(items[i]), items[i + 1]);
        }
        return map;
    }

    // ---- Config ----

    private static final class Config {
        final String host;
        final int port;
        final int database;
        final String password;
        final boolean writable;

        private Config(String host, int port, int database, String password, boolean writable) {
            this.host = host;
            this.port = port;
            this.database = database;
            this.password = password;
            this.writable = writable;
        }

        static Config fromEnv() {
            String passwordEnvKey = env("REDIS_MCP_PASSWORD_ENV", "REDIS_MCP_PASSWORD");
            String password = System.getenv(passwordEnvKey);
            if (password == null || password.isEmpty()) {
                password = env("REDIS_MCP_PASSWORD", "");
            }
            return new Config(
                    env("REDIS_MCP_HOST", "127.0.0.1"),
                    Integer.parseInt(env("REDIS_MCP_PORT", "6379")),
                    Integer.parseInt(env("REDIS_MCP_DATABASE", "0")),
                    password,
                    Boolean.parseBoolean(env("REDIS_MCP_WRITABLE", "false")));
        }

        private static String env(String key, String fallback) {
            String value = System.getenv(key);
            return value == null || value.isEmpty() ? fallback : value;
        }
    }

    // ---- JSON ----

    private static final class Json {
        static Object parse(String input) {
            return new Parser(input).parseValue();
        }

        static String stringify(Object value) {
            StringBuilder out = new StringBuilder();
            write(out, value);
            return out.toString();
        }

        private static void write(StringBuilder out, Object value) {
            if (value == null) {
                out.append("null");
            } else if (value instanceof String) {
                out.append('"').append(escape((String) value)).append('"');
            } else if (value instanceof Number || value instanceof Boolean) {
                out.append(value);
            } else if (value instanceof Map) {
                out.append('{');
                boolean first = true;
                for (Object entryObj : ((Map<?, ?>) value).entrySet()) {
                    Map.Entry<?, ?> entry = (Map.Entry<?, ?>) entryObj;
                    if (!first) {
                        out.append(',');
                    }
                    first = false;
                    write(out, String.valueOf(entry.getKey()));
                    out.append(':');
                    write(out, entry.getValue());
                }
                out.append('}');
            } else if (value instanceof Iterable) {
                out.append('[');
                boolean first = true;
                for (Object item : (Iterable<?>) value) {
                    if (!first) {
                        out.append(',');
                    }
                    first = false;
                    write(out, item);
                }
                out.append(']');
            } else {
                write(out, String.valueOf(value));
            }
        }

        private static String escape(String value) {
            return value.replace("\\", "\\\\")
                    .replace("\"", "\\\"")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    .replace("\t", "\\t");
        }
    }

    private static final class Parser {
        private final String input;
        private int pos;

        Parser(String input) {
            this.input = input;
        }

        Object parseValue() {
            skipWhitespace();
            if (pos >= input.length()) {
                throw new IllegalArgumentException("Unexpected end of JSON");
            }
            char c = input.charAt(pos);
            if (c == '{') return parseObject();
            if (c == '[') return parseArray();
            if (c == '"') return parseString();
            if (c == 't' && input.startsWith("true", pos)) { pos += 4; return true; }
            if (c == 'f' && input.startsWith("false", pos)) { pos += 5; return false; }
            if (c == 'n' && input.startsWith("null", pos)) { pos += 4; return null; }
            return parseNumber();
        }

        private Map<String, Object> parseObject() {
            Map<String, Object> map = new LinkedHashMap<>();
            pos++;
            skipWhitespace();
            if (input.charAt(pos) == '}') { pos++; return map; }
            while (true) {
                String key = parseString();
                skipWhitespace();
                expect(':');
                Object value = parseValue();
                map.put(key, value);
                skipWhitespace();
                if (input.charAt(pos) == '}') { pos++; return map; }
                expect(',');
                skipWhitespace();
            }
        }

        private List<Object> parseArray() {
            List<Object> list = new ArrayList<>();
            pos++;
            skipWhitespace();
            if (input.charAt(pos) == ']') { pos++; return list; }
            while (true) {
                list.add(parseValue());
                skipWhitespace();
                if (input.charAt(pos) == ']') { pos++; return list; }
                expect(',');
            }
        }

        private String parseString() {
            expect('"');
            StringBuilder out = new StringBuilder();
            while (pos < input.length()) {
                char c = input.charAt(pos++);
                if (c == '"') return out.toString();
                if (c == '\\') {
                    char esc = input.charAt(pos++);
                    if (esc == '"' || esc == '\\' || esc == '/') { out.append(esc); }
                    else if (esc == 'b') { out.append('\b'); }
                    else if (esc == 'f') { out.append('\f'); }
                    else if (esc == 'n') { out.append('\n'); }
                    else if (esc == 'r') { out.append('\r'); }
                    else if (esc == 't') { out.append('\t'); }
                    else if (esc == 'u') {
                        out.append((char) Integer.parseInt(input.substring(pos, pos + 4), 16));
                        pos += 4;
                    }
                } else {
                    out.append(c);
                }
            }
            throw new IllegalArgumentException("Unterminated string");
        }

        private Number parseNumber() {
            int start = pos;
            while (pos < input.length() && "-+0123456789.eE".indexOf(input.charAt(pos)) >= 0) {
                pos++;
            }
            String raw = input.substring(start, pos);
            if (raw.contains(".") || raw.contains("e") || raw.contains("E")) {
                return Double.parseDouble(raw);
            }
            return Long.parseLong(raw);
        }

        private void expect(char expected) {
            if (pos >= input.length() || input.charAt(pos) != expected) {
                throw new IllegalArgumentException("Expected '" + expected + "' at position " + pos);
            }
            pos++;
        }

        private void skipWhitespace() {
            while (pos < input.length() && Character.isWhitespace(input.charAt(pos))) {
                pos++;
            }
        }
    }
}
