# Memory Risk Checklist

This reference supports `backend-memory-risk-report`.

Use it when inspecting a backend codebase for potential OOM, memory leak, or abnormal memory growth risks.

## 1. Baseline Questions

Before reporting any risk, answer these:

1. What runtime is this backend using?
2. Which components live for the whole process lifetime?
3. Which code paths handle large datasets, large files, or high-frequency traffic?
4. Which components can accumulate data over time?

## 2. High-Risk Java/Spring Patterns

Prioritize these patterns in JVM services:

### 2.1 Static Or Singleton Retention

Check for:

- static `Map`, `List`, `Set`, array, cache holder
- singleton service fields storing request data
- unbounded local registries or subscription containers
- ever-growing session or device maps

Typical risk:

- Objects remain strongly reachable for the whole JVM lifetime.

### 2.2 Cache Growth

Check for:

- in-memory caches without size limit
- maps keyed by device id, session id, request id, or area id without eviction
- duplicate caches for the same data
- cached large objects, JSON blobs, or DTO trees

Typical risk:

- Heap keeps growing under real traffic and never returns to baseline.

### 2.3 ThreadLocal Leaks

Check for:

- `ThreadLocal` values set but not removed
- MDC-like data stored in thread locals
- thread pools reusing threads while old values remain attached

Typical risk:

- Long-lived pooled threads retain request-scoped data.

### 2.4 Scheduler And Async Accumulation

Check for:

- `@Scheduled` tasks appending to long-lived collections
- retry queues without eviction
- delayed tasks or executor queues without backpressure
- background tasks producing results faster than they are consumed

Typical risk:

- Heap growth is gradual and may only appear after long uptime.

### 2.5 Listener / MQ / MQTT / WebSocket Retention

Check for:

- listeners added but never removed
- consumer registries or callback maps that grow over time
- MQTT topic subscriptions tied to objects that remain referenced
- websocket/session managers with stale sessions

Typical risk:

- Connection-scoped objects remain retained after disconnect or re-register.

### 2.6 Large Query Or Aggregation Loads

Check for:

- loading full tables into memory
- large `List` creation before pagination or filtering
- repeated `collect(Collectors.toList())`
- nested loops materializing large intermediate collections
- export logic assembling huge datasets before writing

Typical risk:

- Short-lived spikes cause OOM even without a strict leak.

### 2.7 Large Buffer / Serialization Paths

Check for:

- `ByteArrayOutputStream`
- in-memory Excel or CSV generation
- large JSON serialization and repeated object copying
- image, stream, binary, or telemetry payload buffering

Typical risk:

- A single request or batch task can allocate huge contiguous memory.

### 2.8 Resource Leaks

Check for:

- streams not closed
- HTTP responses or bodies not released
- DB or driver resources retained longer than necessary
- file-processing logic without bounded buffering

Typical risk:

- Retained native or heap-backed resources increase memory pressure over time.

## 3. Risk Rating Guidance

Use this scale:

### High Risk

- Strong evidence of unbounded retention or guaranteed long-lived references.

### Medium Risk

- Clear growth pattern exists, but cleanup logic or triggering conditions are uncertain.

### Low Risk

- Pattern is suspicious but current evidence is weak.

### Needs Runtime Evidence

- Code suggests risk, but proof needs heap dump, profiler, GC log, allocation flame graph, or production metrics.

## 4. Suggested Search Patterns

Useful search patterns for Java/Spring projects:

- `static `
- `ThreadLocal`
- `ConcurrentHashMap`
- `HashMap<`
- `ArrayList<`
- `@Scheduled`
- `ExecutorService`
- `ScheduledExecutorService`
- `BlockingQueue`
- `addListener`
- `register`
- `subscribe`
- `cache`
- `mqtt`
- `websocket`
- `ByteArrayOutputStream`
- `InputStream`
- `OutputStream`
- `collect(Collectors.toList())`
- `stream().map`
- `findAll`

## 5. Report Writing Rules

For every finding, always include:

1. Severity
2. Code location
3. Risk type
4. Progress status
4. Trigger condition
5. Evidence
6. Impact
7. Fix recommendation

If a finding cannot be proven from code alone, explicitly say what runtime evidence is still needed.

Use one of these progress statuses:

1. `已处理`
2. `未处理`
3. `业务需要`
4. `不重要`
5. `需运行时验证`

Write the final report to:

- `doc/check/memory/{日期}.md`

Use `YYYY-MM-DD` for `{日期}` by default.

Before generating the current report, first locate the latest existing report under `doc/check/memory` and use it as the baseline.

When using the baseline report:

1. Update the status of previously recorded risks based on the current code.
2. Update severity, evidence, impact, and recommendations if the current code changed.
3. Append newly discovered risks that did not exist in the latest report.

If the report for the same date already exists, continue updating that file instead of replacing valid prior content blindly.
