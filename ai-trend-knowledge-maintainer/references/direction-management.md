# 方向管理

## 方向总表

方向总表位于：

```text
metadata/direction-registry.json
```

自动化必须读取方向总表，不要在 prompt 中写死固定方向。

## 方向状态

| 状态 | 含义 | 自动化策略 |
| --- | --- | --- |
| `candidate` | 新方向候选 | 只进入候选池 |
| `watching` | 观察中 | 周频检查，重大信息进入候选池 |
| `tracking` | 持续跟踪 | 周频复核，可更新正式文档 |
| `priority` | 重点跟踪 | 日频重点关注，重大事件可触发 event |
| `weakened` | 逻辑削弱 | 降低频率，观察证伪或反转证据 |
| `paused` | 暂停跟踪 | 默认不主动更新 |
| `archived` | 归档 | 仅保留历史 |
| `rejected` | 已证伪 | 不主动更新，除非强反转证据 |

## 新方向处理

当外部信息不属于现有方向，但满足入库标准时：

1. 追加到 `data-source/05_信息候选池/`。
2. `处理结果` 写 `new_direction_candidate`。
3. 如多次出现或来源足够强，在 `metadata/direction-registry.json` 的 `candidate_directions` 中增加候选。
4. 证据进一步增强时，升级为 `directions[]` 中的 `watching`。
5. 形成完整判断链条后，新建正式方向研究文档并升级为 `tracking`。

## 降级和归档

方向可以降级：

- 关键假设被削弱：`tracking` -> `weakened`；
- 多个周期无新增证据：`watching/tracking` -> `paused`；
- 长期不再相关：`paused` -> `archived`；
- 核心逻辑被证伪：任意状态 -> `rejected`。

降级时必须：

- 更新 `metadata/direction-registry.json`；
- 更新对应正式文档中受影响的判断或复盘章节；
- 在文档“更新记录”追加一行；
- 必要时更新观察清单和复盘记录。
