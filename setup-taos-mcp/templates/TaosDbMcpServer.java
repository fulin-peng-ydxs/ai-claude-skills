package com.gzzn.mcp.taosdb;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class TaosDbMcpServer {
    private static final String PROTOCOL_VERSION = "2024-11-05";
    private static Config config;

    public static void main(String[] args) throws Exception {
        config = Config.fromEnv();
        Class.forName("com.taosdata.jdbc.rs.RestfulDriver");

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
        if (e instanceof SQLException) {
            SQLException sql = (SQLException) e;
            return sql.getClass().getName() + ": " + sql.getMessage()
                    + " [SQLState=" + sql.getSQLState() + ", errorCode=" + sql.getErrorCode() + "]";
        }
        Throwable cause = e.getCause();
        if (cause instanceof SQLException) {
            SQLException sql = (SQLException) cause;
            return e.getClass().getName() + ": " + e.getMessage() + "; caused by "
                    + sql.getClass().getName() + ": " + sql.getMessage()
                    + " [SQLState=" + sql.getSQLState() + ", errorCode=" + sql.getErrorCode() + "]";
        }
        return e.getClass().getName() + ": " + e.getMessage();
    }

    private static Map<String, Object> handle(Object id, String method, Map<String, Object> request) throws Exception {
        if ("initialize".equals(method)) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("protocolVersion", PROTOCOL_VERSION);
            result.put("serverInfo", mapOf("name", "taos-db", "version", "0.1.0"));
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
            try (Connection conn = connection()) {
                return textResult("ok: connected to " + config.host + ":" + config.port + "/" + config.database);
            }
        }
        if ("list_tables".equals(name)) {
            return textResult(Json.stringify(listTables()));
        }
        if ("describe_table".equals(name)) {
            return textResult(Json.stringify(describeTable(required(args, "table"))));
        }
        if ("query_sql".equals(name)) {
            int limit = intValue(args.get("limit"), 200);
            return textResult(Json.stringify(querySql(required(args, "sql"), Math.min(limit, 1000))));
        }
        if ("execute_sql".equals(name)) {
            boolean dryRun = booleanValue(args.get("dry_run"), true);
            return textResult(Json.stringify(executeSql(required(args, "sql"), dryRun)));
        }
        throw new IllegalArgumentException("Unknown tool: " + name);
    }

    private static List<Object> tools() {
        List<Object> tools = new ArrayList<>();
        tools.add(tool("health_check", "Test the TDengine database connection.", mapOf("type", "object", "properties", new LinkedHashMap<String, Object>())));
        tools.add(tool("list_tables", "List tables in the configured database.", mapOf("type", "object", "properties", new LinkedHashMap<String, Object>())));
        tools.add(tool("describe_table", "Describe columns for a table in the configured database.",
                schemaWithProps(mapOf("table", prop("string", "Table name.")), new String[]{"table"})));
        tools.add(tool("query_sql", "Run a read-only SELECT/WITH query against TDengine time-series data. The result is capped.",
                schemaWithProps(mapOf("sql", prop("string", "SELECT or WITH SQL."), "limit", prop("integer", "Max rows, up to 1000.")), new String[]{"sql"})));
        tools.add(tool("execute_sql", "Dry-run or execute INSERT SQL. TDengine time-series data is append-only; UPDATE/DELETE are not supported.",
                schemaWithProps(mapOf("sql", prop("string", "INSERT SQL."), "dry_run", prop("boolean", "Default true. Set false to execute.")), new String[]{"sql"})));
        return tools;
    }

    private static Connection connection() throws Exception {
        String password = System.getenv(config.passwordEnv);
        if (password == null || password.isEmpty()) {
            throw new IllegalStateException("Missing password env var: " + config.passwordEnv);
        }
        String url = "jdbc:TAOS-RS://" + config.host + ":" + config.port + "/" + config.database;
        return DriverManager.getConnection(url, config.user, password);
    }

    private static List<Object> listTables() throws Exception {
        List<Object> rows = new ArrayList<>();
        try (Connection conn = connection(); Statement stmt = conn.createStatement()) {
            try (ResultSet rs = stmt.executeQuery("SHOW TABLES")) {
                ResultSetMetaData meta = rs.getMetaData();
                int count = meta.getColumnCount();
                // find table_name column index (usually column 1)
                int nameCol = 1;
                for (int i = 1; i <= count; i++) {
                    if ("table_name".equalsIgnoreCase(meta.getColumnLabel(i))) {
                        nameCol = i;
                        break;
                    }
                }
                while (rs.next()) {
                    rows.add(mapOf("name", rs.getString(nameCol), "type", "TABLE"));
                }
            }
        }
        return rows;
    }

    private static List<Object> describeTable(String table) throws Exception {
        String tableName = normalizeIdentifier(table);
        List<Object> rows = new ArrayList<>();
        try (Connection conn = connection(); Statement stmt = conn.createStatement()) {
            try (ResultSet rs = stmt.executeQuery("DESCRIBE " + tableName)) {
                ResultSetMetaData meta = rs.getMetaData();
                int count = meta.getColumnCount();
                while (rs.next()) {
                    Map<String, Object> row = new LinkedHashMap<>();
                    for (int i = 1; i <= count; i++) {
                        row.put(meta.getColumnLabel(i).toLowerCase(Locale.ROOT), rs.getObject(i));
                    }
                    rows.add(row);
                }
            }
        }
        return rows;
    }

    private static Object querySql(String sql, int limit) throws Exception {
        String normalized = normalizeSql(sql);
        String upper = normalized.toUpperCase(Locale.ROOT);
        if (!(upper.startsWith("SELECT ") || upper.startsWith("WITH "))) {
            throw new IllegalArgumentException("query_sql only allows SELECT or WITH queries");
        }
        rejectUnsafeSql(normalized, false);
        // TDengine uses LIMIT clause, not ROWNUM
        String limitedSql = normalized + " LIMIT " + limit;
        try (Connection conn = connection(); Statement stmt = conn.createStatement(); ResultSet rs = stmt.executeQuery(limitedSql)) {
            return resultSetToRows(rs);
        }
    }

    private static Object executeSql(String sql, boolean dryRun) throws Exception {
        if (!config.writable) {
            throw new IllegalStateException("This MCP profile is read-only");
        }
        String normalized = normalizeSql(sql);
        String upper = normalized.toUpperCase(Locale.ROOT);
        rejectUnsafeSql(normalized, true);
        // TDengine is append-only time-series; only INSERT is allowed
        if (!upper.startsWith("INSERT ")) {
            throw new IllegalArgumentException("execute_sql only allows INSERT for TDengine time-series data");
        }
        if (dryRun) {
            return mapOf("dry_run", true, "message", "SQL accepted by policy. Re-run with dry_run=false to execute.", "sql", normalized);
        }
        try (Connection conn = connection(); Statement stmt = conn.createStatement()) {
            int affected = stmt.executeUpdate(normalized);
            return mapOf("dry_run", false, "affected_rows", affected);
        }
    }

    private static List<Object> resultSetToRows(ResultSet rs) throws Exception {
        ResultSetMetaData meta = rs.getMetaData();
        int count = meta.getColumnCount();
        List<Object> rows = new ArrayList<>();
        while (rs.next()) {
            Map<String, Object> row = new LinkedHashMap<>();
            for (int i = 1; i <= count; i++) {
                row.put(meta.getColumnLabel(i), rs.getObject(i));
            }
            rows.add(row);
        }
        return rows;
    }

    private static void rejectUnsafeSql(String sql, boolean write) {
        String upper = sql.toUpperCase(Locale.ROOT);
        String[] forbidden = {"CREATE ", "ALTER ", "DROP ", "TRUNCATE ", "GRANT ", "REVOKE ", "MERGE ", "CALL ", "EXEC ", "COMMENT "};
        for (String keyword : forbidden) {
            if (upper.contains(keyword)) {
                throw new IllegalArgumentException("Forbidden SQL keyword: " + keyword.trim());
            }
        }
        if (!write && (upper.contains(" INSERT ") || upper.contains(" UPDATE ") || upper.contains(" DELETE "))) {
            throw new IllegalArgumentException("Read-only query contains write keyword");
        }
    }

    private static String normalizeSql(String sql) {
        String trimmed = sql == null ? "" : sql.trim();
        while (trimmed.endsWith(";")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1).trim();
        }
        if (trimmed.contains(";")) {
            throw new IllegalArgumentException("Multiple statements are not allowed");
        }
        if (trimmed.isEmpty()) {
            throw new IllegalArgumentException("SQL is required");
        }
        return trimmed;
    }

    private static String normalizeIdentifier(String value) {
        String normalized = value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
        if (!normalized.matches("[a-z0-9_]+")) {
            throw new IllegalArgumentException("Invalid table name: " + value);
        }
        return normalized;
    }

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
            return Integer.parseInt(String.valueOf(value));
        }
        return fallback;
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

    private static final class Config {
        final String host;
        final String port;
        final String database;
        final String user;
        final String passwordEnv;
        final boolean writable;

        private Config(String host, String port, String database, String user, String passwordEnv, boolean writable) {
            this.host = host;
            this.port = port;
            this.database = database;
            this.user = user;
            this.passwordEnv = passwordEnv;
            this.writable = writable;
        }

        static Config fromEnv() {
            return new Config(
                    env("TAOS_MCP_HOST", "127.0.0.1"),
                    env("TAOS_MCP_PORT", "6041"),
                    env("TAOS_MCP_DATABASE", "mytest"),
                    env("TAOS_MCP_USER", "root"),
                    env("TAOS_MCP_PASSWORD_ENV", "TAOS_MCP_PASSWORD"),
                    Boolean.parseBoolean(env("TAOS_MCP_WRITABLE", "false")));
        }

        private static String env(String key, String fallback) {
            String value = System.getenv(key);
            return value == null || value.isEmpty() ? fallback : value;
        }
    }

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
            return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
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
            if (c == '{') {
                return parseObject();
            }
            if (c == '[') {
                return parseArray();
            }
            if (c == '"') {
                return parseString();
            }
            if (c == 't' && input.startsWith("true", pos)) {
                pos += 4;
                return true;
            }
            if (c == 'f' && input.startsWith("false", pos)) {
                pos += 5;
                return false;
            }
            if (c == 'n' && input.startsWith("null", pos)) {
                pos += 4;
                return null;
            }
            return parseNumber();
        }

        private Map<String, Object> parseObject() {
            Map<String, Object> map = new LinkedHashMap<>();
            pos++;
            skipWhitespace();
            if (input.charAt(pos) == '}') {
                pos++;
                return map;
            }
            while (true) {
                String key = parseString();
                skipWhitespace();
                expect(':');
                Object value = parseValue();
                map.put(key, value);
                skipWhitespace();
                if (input.charAt(pos) == '}') {
                    pos++;
                    return map;
                }
                expect(',');
                skipWhitespace();
            }
        }

        private List<Object> parseArray() {
            List<Object> list = new ArrayList<>();
            pos++;
            skipWhitespace();
            if (input.charAt(pos) == ']') {
                pos++;
                return list;
            }
            while (true) {
                list.add(parseValue());
                skipWhitespace();
                if (input.charAt(pos) == ']') {
                    pos++;
                    return list;
                }
                expect(',');
            }
        }

        private String parseString() {
            expect('"');
            StringBuilder out = new StringBuilder();
            while (pos < input.length()) {
                char c = input.charAt(pos++);
                if (c == '"') {
                    return out.toString();
                }
                if (c == '\\') {
                    char escaped = input.charAt(pos++);
                    if (escaped == '"' || escaped == '\\' || escaped == '/') {
                        out.append(escaped);
                    } else if (escaped == 'b') {
                        out.append('\b');
                    } else if (escaped == 'f') {
                        out.append('\f');
                    } else if (escaped == 'n') {
                        out.append('\n');
                    } else if (escaped == 'r') {
                        out.append('\r');
                    } else if (escaped == 't') {
                        out.append('\t');
                    } else if (escaped == 'u') {
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
