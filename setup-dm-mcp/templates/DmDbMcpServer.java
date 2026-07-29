package com.gzzn.mcp.dmdb;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

public class DmDbMcpServer {
    private static final String PROTOCOL_VERSION = "2024-11-05";
    private static final List<String> SUPPORTED_QUERY_TYPES = Arrays.asList("SELECT", "WITH");
    private static final List<String> SUPPORTED_WRITE_TYPES = Arrays.asList("INSERT", "UPDATE", "DELETE");
    private static Config config;

    public static void main(String[] args) throws Exception {
        config = Config.fromEnv();
        Class.forName("dm.jdbc.driver.DmDriver");

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
            result.put("serverInfo", mapOf("name", "dm-db", "version", "0.1.0"));
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
            Map<String, Object> args = params.get("arguments") instanceof Map
                    ? (Map<String, Object>) params.get("arguments")
                    : new LinkedHashMap<>();
            return response(id, callTool(name, args));
        }
        if ("ping".equals(method)) {
            return response(id, new LinkedHashMap<String, Object>());
        }
        return error(id, -32601, "Unsupported method: " + method);
    }

    private static Object callTool(String name, Map<String, Object> args) throws Exception {
        if ("health_check".equals(name)) {
            try (Connection conn = rawConnection()) {
                try {
                    setSchema(conn);
                    return textResult("ok: connected to " + config.host + ":" + config.port + "/" + config.schema);
                } catch (SQLException schemaError) {
                    return textResult("connected, but SET SCHEMA failed: " + errorMessage(schemaError));
                }
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
            int effectiveLimit = Math.min(Math.max(limit, 1), config.maxQueryRows);
            return textResult(Json.stringify(querySql(required(args, "sql"), effectiveLimit)));
        }
        if ("execute_sql".equals(name)) {
            boolean dryRun = booleanValue(args.get("dry_run"), true);
            return textResult(Json.stringify(executeSql(required(args, "sql"), dryRun)));
        }
        throw new IllegalArgumentException("Unknown tool: " + name);
    }

    private static List<Object> tools() {
        List<Object> tools = new ArrayList<>();
        tools.add(tool("health_check", "Test the DM database connection.", mapOf("type", "object", "properties", new LinkedHashMap<String, Object>())));
        tools.add(tool("list_tables", "List tables in the configured schema.", mapOf("type", "object", "properties", new LinkedHashMap<String, Object>())));
        tools.add(tool("describe_table", "Describe columns for a table in the configured schema.",
                schemaWithProps(mapOf("table", prop("string", "Table name, without schema.")), new String[]{"table"})));
        tools.add(tool("query_sql", "Run an allowed read-only query. Allowed statement types: "
                        + String.join(", ", config.allowedQueryTypes) + "; result limit: " + config.maxQueryRows + ".",
                schemaWithProps(mapOf("sql", prop("string", "Read-only SQL allowed by the configured profile policy."),
                        "limit", prop("integer", "Requested rows; clamped to the configured profile limit.")), new String[]{"sql"})));
        tools.add(tool("execute_sql", "Dry-run or execute SQL allowed by the profile policy. Allowed write statement types: "
                        + String.join(", ", config.allowedWriteTypes) + "; forbidden keywords: "
                        + String.join(", ", config.forbiddenSqlKeywords) + ".",
                schemaWithProps(mapOf("sql", prop("string", "Write SQL allowed by the configured profile policy."),
                        "dry_run", prop("boolean", "Default true. Set false to execute.")), new String[]{"sql"})));
        return tools;
    }

    private static Connection connection() throws Exception {
        String password = System.getenv(config.passwordEnv);
        if (password == null || password.isEmpty()) {
            throw new IllegalStateException("Missing password env var: " + config.passwordEnv);
        }
        String url = "jdbc:dm://" + config.host + ":" + config.port;
        Connection conn = rawConnection();
        setSchema(conn);
        return conn;
    }

    private static Connection rawConnection() throws Exception {
        String password = System.getenv(config.passwordEnv);
        if (password == null || password.isEmpty()) {
            throw new IllegalStateException("Missing password env var: " + config.passwordEnv);
        }
        String url = "jdbc:dm://" + config.host + ":" + config.port;
        return DriverManager.getConnection(url, config.user, password);
    }

    private static void setSchema(Connection conn) throws SQLException {
        try (Statement stmt = conn.createStatement()) {
            stmt.execute("SET SCHEMA " + config.schema);
        }
    }

    private static List<Object> listTables() throws Exception {
        List<Object> rows = new ArrayList<>();
        try (Connection conn = connection()) {
            DatabaseMetaData meta = conn.getMetaData();
            try (ResultSet rs = meta.getTables(null, config.schema, "%", new String[]{"TABLE", "VIEW"})) {
                while (rs.next()) {
                    rows.add(mapOf("name", rs.getString("TABLE_NAME"), "type", rs.getString("TABLE_TYPE")));
                }
            }
        }
        return rows;
    }

    private static List<Object> describeTable(String table) throws Exception {
        String tableName = normalizeIdentifier(table);
        List<Object> rows = new ArrayList<>();
        try (Connection conn = connection()) {
            DatabaseMetaData meta = conn.getMetaData();
            try (ResultSet rs = meta.getColumns(null, config.schema, tableName, "%")) {
                while (rs.next()) {
                    rows.add(mapOf(
                            "name", rs.getString("COLUMN_NAME"),
                            "type", rs.getString("TYPE_NAME"),
                            "size", rs.getInt("COLUMN_SIZE"),
                            "nullable", rs.getInt("NULLABLE") == DatabaseMetaData.columnNullable,
                            "remarks", rs.getString("REMARKS")));
                }
            }
        }
        return rows;
    }

    private static Object querySql(String sql, int limit) throws Exception {
        String normalized = normalizeSql(sql);
        String type = statementType(normalized);
        if (!config.allowedQueryTypes.contains(type)) {
            throw new IllegalArgumentException("query_sql rejects statement type " + type
                    + "; allowed types: " + String.join(", ", config.allowedQueryTypes));
        }
        rejectUnsafeSql(normalized, false);
        String limitedSql = "SELECT * FROM (" + normalized + ") WHERE ROWNUM <= " + limit;
        try (Connection conn = connection(); PreparedStatement stmt = conn.prepareStatement(limitedSql); ResultSet rs = stmt.executeQuery()) {
            return resultSetToRows(rs);
        }
    }

    private static Object executeSql(String sql, boolean dryRun) throws Exception {
        if (!config.writable) {
            throw new IllegalStateException("This MCP profile is read-only");
        }
        String normalized = normalizeSql(sql);
        String type = statementType(normalized);
        rejectUnsafeSql(normalized, true);
        if (!config.allowedWriteTypes.contains(type)) {
            throw new IllegalArgumentException("execute_sql rejects statement type " + type
                    + "; allowed types: " + String.join(", ", config.allowedWriteTypes));
        }
        boolean updateOrDelete = "UPDATE".equals(type) || "DELETE".equals(type);
        if (config.requireWhere && updateOrDelete
                && !containsSqlKeyword(sqlForPolicyCheck(normalized), "WHERE")) {
            throw new IllegalArgumentException("UPDATE/DELETE must include a WHERE clause");
        }
        if (dryRun) {
            return mapOf("dry_run", true, "message", "SQL accepted by policy. Re-run with dry_run=false to execute.", "sql", normalized);
        }
        try (Connection conn = connection(); Statement stmt = conn.createStatement()) {
            conn.setAutoCommit(false);
            int affected = stmt.executeUpdate(normalized);
            if (updateOrDelete && affected > config.maxAffectedRows) {
                conn.rollback();
                throw new IllegalStateException("Affected rows " + affected + " exceeds max " + config.maxAffectedRows + "; rolled back");
            }
            conn.commit();
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
        String policySql = sqlForPolicyCheck(sql);
        for (String keyword : config.forbiddenSqlKeywords) {
            if (containsSqlKeyword(policySql, keyword)) {
                throw new IllegalArgumentException("Forbidden SQL keyword: " + keyword);
            }
        }
        if (!write) {
            for (String keyword : SUPPORTED_WRITE_TYPES) {
                if (containsSqlKeyword(policySql, keyword)) {
                    throw new IllegalArgumentException("Read-only query contains write keyword: " + keyword);
                }
            }
        }
    }

    /**
     * 移除字符串、双引号标识符和注释中的内容，仅保留真正参与语句结构的字符。
     * 返回值只用于安全策略判断，数据库实际执行的仍是规范化后的原始 SQL。
     */
    private static String sqlForPolicyCheck(String sql) {
        StringBuilder out = new StringBuilder(sql.length());
        boolean singleQuoted = false;
        boolean doubleQuoted = false;
        boolean lineComment = false;
        boolean blockComment = false;
        for (int i = 0; i < sql.length(); i++) {
            char current = sql.charAt(i);
            char next = i + 1 < sql.length() ? sql.charAt(i + 1) : '\0';
            if (lineComment) {
                if (current == '\n' || current == '\r') {
                    lineComment = false;
                    out.append(' ');
                }
                continue;
            }
            if (blockComment) {
                if (current == '*' && next == '/') {
                    blockComment = false;
                    i++;
                }
                out.append(' ');
                continue;
            }
            if (singleQuoted) {
                if (current == '\'' && next == '\'') {
                    i++;
                } else if (current == '\'') {
                    singleQuoted = false;
                }
                out.append(' ');
                continue;
            }
            if (doubleQuoted) {
                if (current == '"' && next == '"') {
                    i++;
                } else if (current == '"') {
                    doubleQuoted = false;
                }
                out.append(' ');
                continue;
            }
            if (current == '-' && next == '-') {
                lineComment = true;
                i++;
                out.append(' ');
            } else if (current == '/' && next == '*') {
                blockComment = true;
                i++;
                out.append(' ');
            } else if (current == '\'') {
                singleQuoted = true;
                out.append(' ');
            } else if (current == '"') {
                doubleQuoted = true;
                out.append(' ');
            } else {
                out.append(Character.toUpperCase(current));
            }
        }
        return out.toString();
    }

    /**
     * 按完整 SQL 单词匹配已经清洗的策略文本，避免表名或字段名包含短字符串时被误判。
     */
    private static boolean containsSqlKeyword(String policySql, String keyword) {
        String regex = "(^|[^A-Z0-9_])" + Pattern.quote(keyword) + "([^A-Z0-9_]|$)";
        return Pattern.compile(regex).matcher(policySql).find();
    }

    /**
     * 提取首个 SQL 操作关键字作为语句类型；不接受以注释或其他特殊字符开头的隐式语句。
     */
    private static String statementType(String sql) {
        String upper = sql.trim().toUpperCase(Locale.ROOT);
        int end = 0;
        while (end < upper.length() && Character.isLetter(upper.charAt(end))) {
            end++;
        }
        if (end == 0) {
            throw new IllegalArgumentException("Unable to determine SQL statement type");
        }
        return upper.substring(0, end);
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
        String normalized = value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z0-9_]+")) {
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
        final String schema;
        final String user;
        final String passwordEnv;
        final boolean writable;
        final int maxAffectedRows;
        final int maxQueryRows;
        final boolean requireWhere;
        final List<String> allowedQueryTypes;
        final List<String> allowedWriteTypes;
        final List<String> forbiddenSqlKeywords;

        private Config(String host, String port, String schema, String user, String passwordEnv,
                       boolean writable, int maxAffectedRows, int maxQueryRows, boolean requireWhere,
                       List<String> allowedQueryTypes, List<String> allowedWriteTypes,
                       List<String> forbiddenSqlKeywords) {
            this.host = host;
            this.port = port;
            this.schema = schema.toUpperCase(Locale.ROOT);
            this.user = user;
            this.passwordEnv = passwordEnv;
            this.writable = writable;
            this.maxAffectedRows = maxAffectedRows;
            this.maxQueryRows = maxQueryRows;
            this.requireWhere = requireWhere;
            this.allowedQueryTypes = allowedQueryTypes;
            this.allowedWriteTypes = allowedWriteTypes;
            this.forbiddenSqlKeywords = forbiddenSqlKeywords;
        }

        static Config fromEnv() {
            return new Config(
                    env("DM_MCP_HOST", "127.0.0.1"),
                    env("DM_MCP_PORT", "5236"),
                    env("DM_MCP_SCHEMA", "DM_SCHEMA"),
                    env("DM_MCP_USER", "DM_USER"),
                    env("DM_MCP_PASSWORD_ENV", "DM_PASSWORD"),
                    booleanEnv("DM_MCP_WRITABLE", false),
                    positiveIntEnv("DM_MCP_MAX_AFFECTED_ROWS", 1000),
                    positiveIntEnv("DM_MCP_MAX_QUERY_ROWS", 1000),
                    booleanEnv("DM_MCP_REQUIRE_WHERE", true),
                    allowedSqlTypes("DM_MCP_ALLOWED_QUERY_TYPES", "SELECT,WITH", SUPPORTED_QUERY_TYPES),
                    allowedSqlTypes("DM_MCP_ALLOWED_WRITE_TYPES", "INSERT,UPDATE,DELETE", SUPPORTED_WRITE_TYPES),
                    csvEnv("DM_MCP_FORBIDDEN_SQL_KEYWORDS",
                            "CREATE,ALTER,DROP,TRUNCATE,GRANT,REVOKE,MERGE,CALL,EXEC,COMMENT"));
        }

        private static boolean booleanEnv(String key, boolean fallback) {
            String value = env(key, String.valueOf(fallback)).trim().toLowerCase(Locale.ROOT);
            if (!"true".equals(value) && !"false".equals(value)) {
                throw new IllegalArgumentException(key + " must be true or false");
            }
            return Boolean.parseBoolean(value);
        }

        private static int positiveIntEnv(String key, int fallback) {
            int value = Integer.parseInt(env(key, String.valueOf(fallback)));
            if (value <= 0) {
                throw new IllegalArgumentException(key + " must be greater than zero");
            }
            return value;
        }

        private static List<String> allowedSqlTypes(String key, String fallback, List<String> supported) {
            List<String> configured = csvEnv(key, fallback);
            for (String value : configured) {
                if (!supported.contains(value)) {
                    throw new IllegalArgumentException(key + " contains unsupported SQL type: " + value);
                }
            }
            return configured;
        }

        private static List<String> csvEnv(String key, String fallback) {
            List<String> values = new ArrayList<>();
            for (String item : env(key, fallback).split(",")) {
                String value = item.trim().toUpperCase(Locale.ROOT);
                if (!value.matches("[A-Z_]+")) {
                    throw new IllegalArgumentException(key + " contains an invalid value: " + item);
                }
                if (!values.contains(value)) {
                    values.add(value);
                }
            }
            if (values.isEmpty()) {
                throw new IllegalArgumentException(key + " must not be empty");
            }
            return values;
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
