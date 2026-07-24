---
purpose: "Performance review: latency, throughput, resource usage, bottlenecks. Use when changes impact performance or when profiling."
---

# Review Criteria

1. **Query efficiency**: N+1 queries? Missing indexes? Large result sets without pagination or projection?
2. **Resource usage**: Excessive allocations on hot paths? Memory leaks? Connection pool exhaustion?
3. **Concurrency**: Blocking calls in async context? Lock contention? Thread pool starvation?
4. **Caching**: Is caching appropriate for this data? Is cache invalidation correct? Cache stampede risk?
5. **Bundle/client**: Oversized frontend bundle? Large assets loaded unconditionally?

# Quality Gates

- [ ] No N+1 queries (verify with query counter or ORM logging)
- [ ] No synchronous I/O in async code paths
- [ ] Pagination is used for all list endpoints with configurable page size
- [ ] No `SELECT *` when only a subset of fields is needed
- [ ] All hot-path operations have a cache layer or are O(n) or better
- [ ] No connection leaks — DB clients, HTTP clients are reused, not created per-request
- [ ] Frontend: no large dependencies in the main bundle chunk
- [ ] Batch operations use bulk APIs, not per-item loops
