# Memory Risk Checklist

This reference supports `backend-memory-risk-analysis`.

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
- hot paths repeatedly creating large objects or converting the same payload through multiple in-memory forms
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

## 3. Suggested Search Patterns

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
- `new HashMap`
- `new ArrayList`
- `newFixedThreadPool`
- `newCachedThreadPool`
- `EasyExcel`
- `subList`

## 4. Report Contract

Use [the rating rules](../SKILL.md#第四步分级与判定) for risk levels and [SKILL.md](../SKILL.md) for evidence requirements, progress states, baseline handling and the output path. Read [the report template](output-template.md#内存风险报告) when generating the report; keep evidence, trigger conditions, impact, treatment and runtime verification together for each finding. This checklist defines risk patterns, not a second report or storage contract.
