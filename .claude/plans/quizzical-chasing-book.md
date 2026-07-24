# 冷静分析：纯过滤器方案到底站不站得住？

## 核心命题

> "用 9 个通用过滤器的组合，能否覆盖所有表格查询需求？代价是什么？"

## 逐场景推演

### 场景 1：等间隔质量阶梯（原 ladder 场景）

**查询动作**：`mode=query, filter=[range(RT=10~12)]` — 这是唯一的前置过滤。

**然后呢？** 你拿到这个 RT 窗口内所有的 feature rows（大概 20-100 行）。**LLM 自己看这些行找 M, M+Δ, M+2Δ 的等间隔模式。**

**代价分析：**
- 数据传到 LLM context：~20-100 行 × 5 列 = ~700-3500 tokens
- LLM 需要做 pattern matching（"这些 Mass 值之间差 79.966 吗？"）
- **实际代价**：LLM 做数值运算不如代码精确，可能搞错

**但这是真问题吗？** 等间隔识别本质上是算法逻辑——`build_toppic_family` 的 domain 算法本来就是干这个的。所以关键是：
- ✅ `read_table` 处理"取出 RT 窗口内所有行"这部分
- ✅ domain 算法处理"哪些行构成阶梯"这部分
- **代价转移到 domain 层，不是转移到 LLM**

```
之前: expand_family_with_topfd_features(family, stem, ms1_feature_path, ...)
                         ↓ 内部又读文件又算阶梯
现在: domain.family_builder.expand_family(read_table(mode=query, file=ms1_feature, filter=[range(RT)]))
                         ↓ 读文件走 read_table，算阶梯走 domain 算法
```

代价 = 多一次函数调用，零。本来就在 domain 层。

### 场景 2：79/81 Br 同位素

**LLM 调用**：`mode=query, filter=[combine:"or", ppm(Mass, target=79, tol=10), ppm(Mass, target=81, tol=10)]`

同样，返回几行结果，AI 自己看 ratio。或者 `query_mass_spec_data`（MassQL）直接查 isotope pattern。

**代价**：零。这是读取，不是算法。读取结果 raw 还是结构化对后续判断没区别。

### 场景 3：超大文件（60k+ rows msalign）

**代价：** 每次 `read_table(mode=query)` 都要全表扫描做 ppm 计算。

**实际验证：** 60k 行 × 6 列 ≈ 2MB TSV。Python 全读进内存再逐行算 ppm 是 **<50ms**。不是问题。

### 场景 4：LLM 需要自己做表关联（join ms1.feature + ms2.feature）

**之前**：`expand_family` 内部做了 join，返回结构化结果。
**现在**：AI 调两次 `read_table`，各自返回行集。

**代价**：AI context 多几百 tokens 的表数据。LLM 可以自己理解"这些 feature_id 对应的 scan_id 是哪些"。

这是真代价——LLM 做 join 既慢又不准。但这不是方案的问题而是**职责边界问题**：
- join 是 domain 算法该干的，不是 tool 该干的
- `expand_family` 仍然可以作为一个**domain 算法工具**存在，只是它内部的 I/O 改为走 `read_table`

```
之前: expand_family = 读文件 + join + 算阶梯
现在: expand_family(domain 层) = read_table(I/O) + join(domain) + 算阶梯(domain)
     read_table(tool 层)      = 只做 I/O
```

**所以真正的分界清楚了——**

| 该在 read_table 里 | 不该在 read_table 里 |
|---|---|
| 列选择、行过滤 | join 逻辑（domain） |
| 分页、排序 | 阶梯识别（domain） |
| schema 探查 | 同位素模式判断（domain） |
| 文件自动发现 | 综合评分（domain） |
| **ppm 相对容差过滤**（通用数学） | **select_abnormal**（领域判断） |

`ppm` 保留，因为它不是 proteomics 专有——任何有测量误差的科学数据都需要相对容差过滤。它是一个**通用数学谓词**，和 `range` 同级。

## 真正的平衡点

不是"把一切变成通用过滤器"，而是：

```
read_table(tool 层) = 通用的、正交的查询接口
PTM 算法(tool 层)   = 薄调用 read_table + 委托 domain 算法
domain 算法层       = 纯业务逻辑，不知 tool/LLM 的存在
```

`parse_toppic_candidates`、`build_toppic_family` 这些工具**保留入口**，但它们内部"读文件"的部分变成 `read_table(...)` 而不是 `resolve_run_path() + parse_tsv()`。算法部分不动。

这样既没有"AI 自己算阶梯"的危险，也没有"PTM 读表工具碎片化"的问题。**工具入口有意义，但数据读取统一。**

## 最终过滤器清单（定格 10 个）

| 操作符 | 保留理由 |
|--------|---------|
| `eq` `neq` `gt/gte/lt/lte` | 基础 |
| `range` | 基础（闭区间） |
| **`ppm`** | 通用相对容差，任何科学数据 |
| `contains` `regex` `in` | 文本匹配 |
| `is_null` | 数据质量检查 |

不增加：`ladder` `nearest` `isotope`。这些都是组合出来的。
