# llm-poker-arena 设计文档 v2.1.1

| Meta | |
|---|---|
| **项目名** | llm-poker-arena |
| **版本** | 2.1.1 |
| **日期** | 2026-04-23 |
| **状态** | Draft — v2.1.1 integrates third-round doc alignment, ready for Phase 1 planning |
| **前身版本** | [v1](2026-04-23-llm-poker-arena-design.md)（SUPERSEDED） |
| **Review 历史** | v1→v2（round 1 架构重构）；v2→v2.1（round 2 设计一致性）；v2.1→v2.1.1（round 3 文档/伪代码对齐 + MVP 顺序纳入 §16） |

---

## 0. Review Response Matrix

v2 是对 v1 review 的完整回应。以下表格列出每个 issue 的定位和 resolution，**不依赖 v1 行号**（行号会随编辑漂移），用 issue ID 追溯。

### 阻断级（B 类，12 项）

| ID | 问题概述 | v1 位置 | v2 处理位置 | Resolution |
|---|---|---|---|---|
| B-01 | "完整捕获原生思考链"跨 provider 不可实现（OpenAI 不暴露 raw reasoning，Anthropic 可能 redacted/encrypted） | §0, §4.3 | §0, §4.3, §4.6 | Tier 3 改为 **provider reasoning artifact matrix**，列出每家可得产出形态（raw / summary / encrypted / unavailable），不再作跨家一致性假设 |
| B-02 | "最后一步强制 action tool"措辞误导 | §4.2 | §4.2 | 澄清机制是**缩小 tool 列表**，provider 均支持；真正风险是**模型仍可能不调任何 tool**，fallback 必须扎实 |
| B-03 | 非法时默认 fold 在"无下注"场景本身非法 | §4.2 | §3.3, §4.2 | 引入 `default_safe_action(view)`：`check if to_call == 0 else fold`；所有 fallback 路径走它 |
| B-04 | `all_in` 总是暴露 + short all-in reopening 未建模 | §3.3 | §3.3 | reopening 逻辑 **完全交由 PokerKit** 计算；我们的 `compute_legal_tool_set` 从 PokerKit 的 `min_bet` / `min_raise_to` API 读取，不自己算 |
| B-05 | 1000 手无 rebuy 会变 freezeout | §0, §3 | §3.5 | 显式 **auto-rebuy**：每手开始前 `stack_i = starting_stack`（"table stakes with automatic topup"），模拟独立重复现金局 |
| B-06 | PokerKit automations 漏项 | §3.2 | §3.2 | 补齐 `BET_COLLECTION` / `HAND_KILLING` / `CHIPS_PUSHING` / `CHIPS_PULLING` |
| B-07 | 双 TableState 没定 canonical | §2.2, §3.2 | §3.1, §3.2 | **PokerKit.State 是唯一 canonical**；我们的 `PlayerView` / `PublicView` 是 **read-only 投影**，每 turn 重算，从不持久化状态 |
| B-08 | 模型 ID 可能不存在 | §15.2-3 | §15 | Spec 层使用 **runtime-pinned placeholder**（`<opus_tier_frontier>` 等占位），实际 ID 在 `config.yaml` 运行时 pin |
| B-09 | Reproducibility 承诺过强 | §11 | §11 | 分层：**Engine + Prompt = 严格复现**；**LLM 决策 = best-effort**（provider capability table 明示每家 seed / determinism 实际支持） |
| B-10 | Cost estimate $342 偏低 | §15.4 | §15.5 | 重算并给 **assumption-transparent range**：$500–$3,000（视 model mix 和 ReAct 深度）；附拆解 |
| B-11 | 1000 手 + 固定座位不适合 winrate 比较 | §15, §17 | §15.4 | **Across-session seat permutation**（balanced Latin-square-like 设计）作为 Phase 4 硬性要求；1000 手仅作 action distribution / tool use / CoT 分析，winrate 需 ≥10k 手并在报告中声明 CI |
| B-12 | API 超时默认 fold 混淆 infra 与策略 | §17 | §15.6 | 引入 `hand_outcome: invalid_api_error`，excluded from winrate 统计；同 state 可 replay；提供 censored stats |

### 高风险（H 类，16 项）

| ID | 问题概述 | v2 处理位置 | Resolution |
|---|---|---|---|
| H-01 | Range parser 正则不可靠 | §5.2.1 | 专门的 `RangeNotationParser` 类，显式 rank / suit 枚举 + 语法验证，拒绝具体牌面 |
| H-02 | treys/eval7 锁死实现 | §5.2.2 | `EquityBackend` 抽象接口；实现可插拔（初版 eval7，fallback treys） |
| H-03 | Monte Carlo 无 RNG 无 CI | §5.2.2 | 强制 `seed` 参数 + 返回 `EquityResult{estimate, ci_low, ci_high, n_samples}` |
| H-04 | 只支持 heads-up | §5.2.2 | 新 API `hand_equity_vs_ranges(range_by_seat: dict[SeatId, str])`；HU 是单元素特例；旧 HU-only API 作为 alias，多路场景调用旧 API 返回 `ToolUsageError` |
| H-05 | hands.jsonl 含全部 hole cards，UI 层分不开 | §7.1, §7.2 | **三层日志**：`canonical_private.jsonl`（engine 内部真相）/ `public_replay.jsonl`（UI/spectator 可见）/ `agent_view_snapshots.jsonl`（每 turn 每 seat 的 PlayerView 快照） |
| H-06 | `"QsJs"` 应为 `["Qs", "Js"]` | §7.3 | 修正所有 schema 示例，牌始终是 `list[str]` of 2-char tokens |
| H-07 | VPIP SQL 按 turn 平均错误 | §8.3 | 正确 SQL：按 hand 去重 + 排除强制盲注位置 |
| H-08 | Red-team 只测 hole cards | §12.5 | 扩展至：opponent label / stats field 注入、prompt injection、WebSocket 私有事件串台、log 层级访问控制 |
| H-09 | Python grep 非安全边界 | §2.2 P2, §14 | **包边界**：`engine/_internal/` 不对外导出；`prompt_builder` 接受 **serialized DTO (dict)**，不拿 PlayerView 对象；入口 ABI 用 Pydantic 校验 |
| H-10 | 每行 fsync 拖慢长 session | §8.1 | **Batch flush**：每 10 条 event 或 200ms 强制 flush；关机/SIGTERM 时 drain；crash recovery 至最近 checkpoint |
| H-11 | f-string SQL 注入 | §8.2 | DuckDB 参数化（`con.sql("... FROM read_json_auto(?)", [path])`）或 shlex 转义 |
| H-12 | "native vs stated similarity" 分析不成立 | §15.3 | 替换为 **reasoning artifact coverage report**：统计每 provider 的 native availability 分布，stated reasoning 长度/信息量对比 |
| H-13 | v1/v2 只变 HUD 但都注入 stats 混淆变量 | §15.2 | **4 组基线**（random / rule-based / LLM-no-tools / LLM-math-tools）作为 main；HUD-vs-autoinject 移到后续 ablation backlog |
| H-14 | 强制"reasoning-first"非中性 | §6.1 | `rationale_required: bool` 配置项；默认 `true`，但作为 ablation 轴可 `false` 对比 |
| H-15 | Timebank 不应后置 | §15.7 | Phase 2 就纳入设计：per-turn timeout（默认 120s）+ per-iteration timeout + retry with backoff；每 provider 的延迟/失败率记录为 metric |
| H-16 | Phase 1 1 周风险高 | §16 | 扩到 **~2 周**（NLHE edge case、side pot、min-raise、reopen、PokerKit 适配都需单独验证） |

### 建议（S 类，5 项）

| ID | 建议 | v2 处理 |
|---|---|---|
| S-01 | Reasoning artifact matrix 替代 "complete native CoT" | 已通过 B-01 采纳 |
| S-02 | Phase 1 不自写合法动作，PokerKit 单权威 + property/differential tests | 已通过 B-04, B-07 采纳；§12.2 新增 differential tests |
| S-03 | 4 组 baseline + seat permutation + 多 seed | 已通过 H-13, B-11 采纳 |
| S-04 | 3 层日志 | 已通过 H-05 采纳 |
| S-05 | PHH 标准 | **内部 JSONL + PHH exporter**；exporter 作为测试项（§7.7 + §12.4） |

---

## 0bis. v2 → v2.1 Review Response Addendum

v2 提出后第二轮设计级 review，定位 7 个阻断级 + 7 个高风险一致性/正确性问题。v2.1 逐条修正：

### v2.1 阻断级（BR2 类，7 项）

| ID | 问题 | v2.1 处理位置 | Resolution |
|---|---|---|---|
| BR2-01 | API 二次失败仍返回 `final_action=default_safe_action(view)`，与 §15 "不把 API 错误当 fold" 矛盾 | §4.1, §4.2 | `TurnDecisionResult.final_action: Action \| None`；api_error 时 `final_action=None`，Session 层检测到后**直接 censor hand，不进入 state transition**；绝不 apply fallback |
| BR2-02 | `default_safe_action` 使用 PlayerView 未定义字段（`current_bet_to_match` / `my_invested_this_round` / `opponent_seats_in_hand` / `turn_seed` / `view.config`） | §3.2, §3.3 | PlayerView 补全缺失字段；`config` 改为显式嵌入 view 的 `immutable_session_params: SessionParamsView`（只读副本），不引用 config 对象 |
| BR2-03 | Chip audit 在 hand 结算前后口径不同，混用会双计 `paid_out` | §2.2 P7 | 拆成 `audit_pre_settlement` / `audit_post_settlement`，engine 按 hand 状态调不同函数 |
| BR2-04 | `CanonicalState` 签名在 §3.1 (`config, deck_seed`) 与 §3.5 (`config, deck_seed, button_seat, pending_stacks`) 不一致；deterministic deck 注入 PokerKit 的机制未明示 | §3.1 | 统一签名为 `CanonicalState(config, hand_context: HandContext)`（`HandContext = {deck_seed, button_seat, initial_stacks, hand_id}`）；明示 **deterministic deck 注入**通过禁用 `HOLE_DEALING`/`BOARD_DEALING` automations + 用 seeded RNG 预洗牌 + 手动 `state.deal_hole/deal_board` |
| BR2-05 | 单 `retry_count` 混合多种 retry 语义（provider transient、no-tool、illegal action、final-step utility） | §4.1, §4.2 | 拆成 `api_retry_count` / `illegal_action_retry_count` / `no_tool_retry_count` / `tool_usage_error_count`；各类独立限额，不互相挤占 |
| BR2-06 | `total_turn_timeout_sec` 定义了但 loop 里没 enforcement | §4.2 | 外层 `asyncio.wait_for(total_turn_timeout_sec)` 包整个 decide() 体；内层 per-iteration timeout 保留；总超时 → `api_retry_count` 判断后进 censor 路径 |
| BR2-07 | Anthropic extended thinking + tool use 强制要求 thinking blocks 原样回传，v2 抽象丢失这个语义 | §4.4, §12.5 | Provider 接口新增 `serialize_assistant_turn(response) -> list[ContentBlock]`，Anthropic 实现**必须保留原始 thinking/redacted/encrypted/tool_use block 及其 signatures**；round-trip 测试保证 mock 响应的所有 block 字段在后续 turn 中 byte-identical 出现 |

### v2.1 高风险（HR2 类，7 项）

| ID | 问题 | v2.1 处理位置 | Resolution |
|---|---|---|---|
| HR2-01 | 成本估算矛盾（§0 写 $500–$3,000，§15.5 写 $15k–$30k）；pricing 硬编码 $15/$75 是 Opus 4.1/4 旧价，Opus 4.7 是 $5/$25 | §0b, §15.5 | 移除 TL;DR 中的硬编码金额；§15.5 引入 **runtime pricing matrix**（`config.pricing_per_provider: dict`）；实际估算交给 session 启动脚本按当前 pricing 算；spec 只给公式与 per-turn token 假设 |
| HR2-02 | VPIP SQL 仍不可执行（`WHERE seat = seat` 是 tautology；`is_mandatory_blind_post()` 非标准 SQL） | §7.4, §8.3 | 在 `agent_view_snapshots.jsonl` schema 中加 `is_forced_blind: bool` 字段（写入时预计算）；VPIP SQL 仅用标准 DuckDB 函数，不依赖 UDF |
| HR2-03 | Provider capability 表过于静态（Anthropic thinking 受 temp/top_k/tool_choice 限制；OpenAI 应优先 Responses API 不是 Chat seed；Gemini seed 状态待核实） | §4.6 | 表改标 "representative observed behavior — **probed at session start**"；新增 `ProviderCapability.probe(sample_prompt) -> ObservedCapability` 方法；probe 结果写入 `meta.json.provider_capabilities`；spec 仅给 observed defaults，不承诺稳态 |
| HR2-04 | B3/B4 都开 (β) stats memory，"LLM-no-tools" 不是纯 baseline | §15.2 | 扩为 **5 组 baseline**：`random / rule_based / llm_pure (no tools, no memory) / llm_math (math tools, no memory) / llm_math_stats (math tools + stats memory)`；B3→B4 孤立 tool 效应，B4→B5 孤立 stats 效应；stats-only 变种（no tools + stats）移 ablation backlog |
| HR2-05 | Seat permutation 示例仅改 seat → agent 映射，未包含 initial button permutation；若 hands 不是 6 倍数有偏差 | §15.4 | 显式正交轴：`seat_assignment × initial_button`；规定 `config.num_hands` 必须为 6 的倍数（强制 validation）；跨 session 聚合时保证"每模型 × 每绝对座位 × 每 initial button" 三元组的观测次数相等（要求 ≥ 6 session 才完整平衡） |
| HR2-06 | `LogReader` assert `canonical_private` 存在，违背 "public_replay 可独立发布" 目标 | §7.5 | `PublicLogReader` 无 private 文件依赖，可 standalone 工作；`PrivateLogReader` 才需要 private 文件 + access token |
| HR2-07 | WebSocket token 在 URL query 会进日志 | §9.2 | Token 改走 **WebSocket subprotocol header** 或 **first-message auth handshake**（客户端连接后第一条 message 发 auth 对象；服务器验证通过前不接受其他 message，验证失败即关闭连接） |

---

## 0ter. v2.1 → v2.1.1 文档对齐 Addendum（7 项）

v2.1 提出后的第三轮 review 定位 7 处伪代码/文档口径未跟上架构变更。v2.1.1 patch 修正：

| ID | 问题 | v2.1.1 处理 |
|---|---|---|
| PP-01 | §3.1 禁用 HOLE_DEALING / BOARD_DEALING 但保留 `CARD_BURNING`，同时 §3.1 手动 `burn_card()` → double burn、breaks card conservation | automations 里移除 `CARD_BURNING`；所有 burn 由 `CanonicalState._next_card()` 从预洗牌堆取 |
| PP-02 | `raw_blinds_or_straddles=(sb, bb, 0...)` 硬绑 SB/BB 在 seat 0/1，`HandContext.button_seat` 没进 PokerKit 状态 → seat × initial_button permutation 是假的 | CanonicalState 构造时**按 button_seat 旋转 blinds tuple**，使 SB 位于 `(button_seat + 1) % num_players`，BB 位于 `(button_seat + 2) % num_players`；并给 worked example |
| PP-03 | §3.6 生命周期文案仍写 "PokerKit 自动 post blinds / deal holes" | 改为 "PokerKit 自动 post blinds；CanonicalState 手动 deterministic deal hole/board cards 从预洗牌堆取" |
| PP-04 | §3.6 伪代码 `apply_action(actor, decision.final_action)` 没体现 `final_action is None` → censor 路径 | 同步 §4.1 的 session_orchestrator 检测：`if decision.final_action is None: mark_hand_censored(...); break` |
| PP-05 | §5.3 `build_tool_set` 仍用 `config.enable_math_tools` / `config.enable_hud_tool`；v2.1 已把 `config` 从 view 下线 | 改为 `view.immutable_session_params.enable_math_tools` / `view.immutable_session_params.enable_hud_tool` |
| PP-06 | §15.7 Timebank 段 "api_error + default_safe_action(view)" 与 BR2-01 矛盾 | 改为 "api_error + `final_action=None` + Session 层 censor hand，绝不 apply fallback" |
| PP-07 | §8.2 DuckDB 同时展示 parameterized path 和 `safe_json_source` 两种方案 | 实施阶段只保留 `safe_json_source`（runs/ 白名单 + path escape），加专项测试 `test_safe_json_source_rejects_outside_runs` |

### MVP 实施顺序（纳入 §16 作为权威 Phase 1 路线）

用户 review 给出的 12 步 MVP 顺序：见 §16.1。**关键路径**：PokerKit deterministic hand → random/rule-based engine → logs/analysis → mock ReAct → real providers。**不要先做 UI 或真实 LLM**。

---

## 0b. TL;DR (v2)

**一句话**：搭建一个可严谨复现（engine+prompt 层）、防作弊的 6-max NLHE cash game 仿真平台；让多个 LLM 作为独立席位同桌博弈；**provider-aware** 地捕获各家可得的推理产出（raw / summary / encrypted / unavailable）+ 表述推理 + 工具调用轨迹 + 最终动作。用于多智能体博弈观察与潜在论文产出。

**核心设计调整（相比 v1，含 v2.1 修订）**：

| 维度 | v1 | v2.1 |
|---|---|---|
| 推理捕获 | "Tier 3 双通道（native + stated）" | **Provider reasoning artifact matrix**（承认不均匀）+ **runtime probe** 每 session 实测 |
| Engine 状态 | 我们自建 TableState + PokerKit State 双存 | **PokerKit.State 单 canonical**，我们的层仅为 read-only 投影 |
| 非法动作 fallback | 默认 fold | **Context-aware**（check if legal，else fold） |
| Cash game | 没说 rebuy | **Auto-rebuy** 到 starting stack |
| 合法动作重开逻辑 | 自己算 | **完全委托 PokerKit** |
| 复现性 | "Session 级别全复现" | **Engine+Prompt 严复现；LLM 决策 best-effort**（provider capability probe 结果写入 meta） |
| 实验矩阵 | Main v1 (ii+β) / v2 (iii+β) | **5 组基线**（random / rule_based / llm_pure / llm_math / llm_math_stats）；tools × memory 正交 ablation |
| 座位 | 固定 | **Across-session 正交 balanced permutation**（seat × initial_button） + `num_hands` 强制 6 的倍数 |
| 日志 | 单 `hands.jsonl` | **3 层**（canonical_private / public_replay / agent_view_snapshots）；`PublicLogReader` 可独立工作 |
| Equity 工具 | HU only、无 CI、无 seed | **Multi-way via range_by_seat**，seeded MC，返回 CI |
| 错误处理 | "单次 retry" | **四类独立 retry counter**（api / illegal_action / no_tool / tool_usage_error）；API 错误 → `final_action=None` censor hand，**绝不 apply fallback** |
| Hand history 格式 | 自定义 only | **自定义内部 + PHH exporter**（测试项） |
| Chip audit | 单一 formula | **pre_settlement / post_settlement 两套**（避免双计 payout） |
| CanonicalState | 签名不一致 | 统一 `CanonicalState(config, HandContext)`；**deterministic deck 注入**明示（禁用 HOLE_DEALING/BOARD_DEALING + 预洗牌 + 手动 deal） |
| Anthropic thinking | 未规定回传 | **thinking blocks 必须原样 byte-identical 回传**（`serialize_assistant_turn`） |
| WebSocket auth | token 进 URL | **first-message handshake**，token 不进 URL |
| Phase 1 时间 | ~1 周 | **~2 周**（NLHE edge case 验证） |
| Cost 估算 | 硬编码 $342 | **Runtime pricing matrix**（§15.5）。spec 只给 per-turn token assumption 和公式；金额由 session 启动脚本按当前 pricing 算；spec 内**绝不**硬编码价格 |

---

## 1. 项目目的与成功标准

### 1.1 Primary Purpose

观察多个前沿 LLM 在 6-max NLHE 博弈中的行为差异，**在 provider 能给出的边界内**收集每一步决策的推理产物 + 工具调用轨迹 + 最终动作。用于：
- 纯研究好奇
- 潜在论文素材（LLM 博弈论推理、工具使用、多智能体策略涌现；且在公开 LLM reasoning 透明度约束下的"可见部分"分析）
- 保留未来接入人类玩家的入口

### 1.2 非目的

- 不训练自定义模型
- 不追求击败人类或 solver
- 不构建真钱产品
- **非 NLHE 变体延后**
- 不做分布式
- **不承诺 LLM 决策字节级可复现**（provider 限制，见 §11）

### 1.3 成功标准

**Phase 1（~2 周，engine + 防作弊 + 测试，无 LLM）**
- [ ] PokerKit 适配层跑 50,000+ random 动作序列无 audit failure
- [ ] PlayerView / PublicView DTO **序列化后** 不含其他 seat 的私有信息（不靠 grep，靠单元测试 + 结构化 DTO schema）
- [ ] Property-based 测试覆盖筹码守恒、52 张牌守恒、side pot 结构、min-raise reopening
- [ ] Differential test：我们适配层输出的"合法动作集" == PokerKit `State.can_*()` 结果
- [ ] Fuzz：range parser + tool input 输入 10,000 随机 byte 串无 crash，全部正确 accept/reject
- [ ] Red-team 测试集（§12.5，6+ 场景）通过

**Phase 2（~2 周，LLM agent + ReAct + 基础 session）**
- [ ] 至少 2 个 provider（Anthropic + OpenAI）跑通 Bounded ReAct，其他 provider 为 stub
- [ ] 每家 provider 的 reasoning artifact 类别**从 probe 结果实测**（见 §4.6）写入 `meta.json.provider_capabilities`
- [ ] Anthropic 的 thinking blocks 在 multi-turn tool use 中 byte-identical 回传（round-trip 测试）
- [ ] Pilot session（100 手，6 × same-model 镜像）完整跑完，无 crash
- [ ] Iteration schema 完整写入 `agent_view_snapshots.jsonl`，reasoning artifact kind 全部标注
- [ ] 4 类 retry 计数器（`api_retry_count` / `illegal_action_retry_count` / `no_tool_retry_count` / `tool_usage_error_count`）分别统计
- [ ] API 错误的 hand 标 `hand_outcome: invalid_api_error`、**不** apply fallback action，与 "normal" hand 日志区分
- [ ] Per-iteration + per-turn 两级 timeout 生效（`asyncio.wait_for` 外层包住 decide）
- [ ] 可用 DuckDB 查"每 agent 的 VPIP"（**正确** SQL，用 `is_forced_blind` 字段，不依赖 UDF）

**Phase 3（~1.5 周，Web UI + 事件）**
- [ ] Spectator 模式不泄漏 private info（WebSocket 通道测试）
- [ ] Replay 模式可回放任意 session
- [ ] Reasoning panel 显示各 iteration + 各 provider 的 artifact 类别标签

**Phase 4（~1.5 周，主实验 + 分析）**
- [ ] 5 组主线基线跑完（random / rule_based / llm_pure / llm_math / llm_math_stats，HR2-04 重构后）
- [ ] 每组至少 2 session，seat permutation 达到 balanced
- [ ] Reasoning artifact coverage report 产出
- [ ] 分析图表 ≥ 5 张（§15.3）
- [ ] PHH exporter 通过 round-trip 测试

---

## 2. 威胁模型与防作弊架构

**第一优先架构约束**。防作弊不靠事后 review，必须 architect 进去 + 主动验证。

### 2.1 威胁分类

| 类别 | 攻击面 | 严重度 |
|---|---|---|
| 信息泄漏 | LLM 看到他人 hole cards / 未发公共牌 / 牌堆 | ★★★★★ |
| 时间线泄漏 | LLM 看到后续 street 信息 | ★★★★★ |
| 跨玩家污染 | 多 LLM 实例共享 context → 合谋 | ★★★★ |
| 状态声明篡改 | LLM 在 reasoning 中"改写"事实 | ★★★★ |
| 工具反推 | Utility tool 参数探测私有信息 | ★★★ |
| Prompt injection | 对手 label / stats 注入控制指令 | ★★★ |
| 日志串台 | UI / log reader 错误访问 private 层 | ★★★ |
| 非法动作强推 | 利用 retry 试错非法参数 | ★★ |

### 2.2 防御原则（7 条强制约束）

#### P1. 单一权威源：PokerKit.State

- **PokerKit.State 是唯一 canonical 游戏状态**
- 我们的 `TableProjection`、`PlayerView`、`PublicView` 都是 **read-only 投影**，每次从 PokerKit 重新计算
- 不持久化我们自己的 state；无"双 state 同步" bug 源

```
    ┌───────────────────────────────────────────┐
    │  PokerKit.State (ground truth)            │
    │  └── 完整 deck / hole cards / pot /        │
    │       sidepots / betting / actor / ...    │
    └───────────────────────────────────────────┘
              ↓ 每 turn 重新投影
    ┌───────────────────────────────────────────┐
    │  PlayerView[i]  PublicView   AgentSnap[i] │
    │  (read-only DTO, 无法回写)                 │
    └───────────────────────────────────────────┘
              ↓ 序列化 (Pydantic)
    ┌───────────────────────────────────────────┐
    │  Agent i (untrusted)                      │
    │  收到 dict / JSON，不持有对象引用            │
    └───────────────────────────────────────────┘
```

#### P2. 模块边界 + DTO 序列化作为物理信息墙

Python 的 "不导出" 不是安全边界，需强制：

**目录结构级**
```
src/llm_poker_arena/engine/
├── _internal/                 # 下划线前缀：非公开
│   ├── poker_state.py        # 包装 PokerKit.State
│   ├── audit.py
│   └── transition.py
├── projections.py             # 对外：Project PokerKit → DTO
├── views.py                   # 对外：PlayerView / PublicView Pydantic 模型
└── __init__.py                # 导出白名单
```

**运行时级**
- `PlayerView` / `PublicView` 是 `pydantic.BaseModel` 类，带 schema 验证
- `prompt_builder(view_dto: dict)` 接受 **serialized dict**，不接受 view 对象
- 序列化路径：`PlayerView → .model_dump() → dict → prompt_builder`
- 序列化时 drop 掉任何 key 不在 whitelist 的字段（防意外字段泄漏）

**CI 级**
- Pre-commit hook：`grep -r "from llm_poker_arena.engine._internal" src/ | grep -v engine/_internal` → 必须为空
- 单元测试：构造 `TableState`，调 `PlayerView[i].model_dump_json()`，断言 seat j (j≠i) 的任何私有信息字段都不在结果里

#### P3. 工具参数净化（强白名单）

- `pot_odds()` / `spr()`：零参数
- `hand_equity_vs_ranges(range_by_seat: dict[SeatId, str])`：
  - key 必须是**当前仍在手的对手 seat** 集合（校验）
  - value 必须是**合法 poker range notation**（走 `RangeNotationParser`）
  - 任何具体卡面字符串（`Ah`, `AhKh`, `7c 2d`）→ `ToolInputError`
  - 多余 seat（已 fold/不在手）→ `ToolInputError`
- `get_opponent_stats(seat, detail_level)`：seat 必须 ≠ self.seat；detail_level 限定枚举

所有 `ToolInputError` 在 `ToolRunner` 层被捕获，返回 `{"error": str, "invalid_input": True}` 给 agent；计入 `tool_usage_error_count`（BR2-05 四类计数器之一，独立于 `illegal_action_retry_count`）。

#### P4. Opponent stats 源头污染防护

- Stats 只来自 **canonical_private.jsonl** 的已完成 hand 记录
- 只统计**已结束** hand；进行中 hand 不进 stats
- 若未来接入 self-notes，笔记**不进入** stats（保持对称）

#### P5. 跨玩家强制隔离

- 每 Agent 独立 `provider_client`（构造时注入）
- 每 Agent 独立 `conversation_state`
- `Session.agents: list[Agent]`，无跨席位访问 API
- **默认跨 hand 清空 conversation**（保留 system prompt），避免"前一手的 reasoning 作为 side-channel 影响这手"

#### P6. 动作权威性：tool_call > reasoning

- `tool_call` 决定动作；reasoning 仅存档
- 不一致（"我 raise 500" vs `raise_to(300)`）按 tool_call 执行，差异作为研究数据

#### P7. 守恒审计（按 hand 状态区分的两套 assertion）

**BR2-03** 澄清：hand 进行中与结算后筹码口径不同，必须分两套，不混用。

```python
# engine/_internal/audit.py

def audit_pre_settlement(state: PokerKitState, config: SessionConfig) -> None:
    """
    Hand 进行中（任一 betting street 内）。
    此时 pot 尚未 push 给赢家；bets 已从 stacks 扣除。
    守恒公式：stacks_remaining + pot + bets_still_in_round == starting_total
    """
    starting_total = config.starting_stack * config.num_players
    total_live_stacks = sum(state.stacks)                       # 当前剩余筹码
    total_pot_collected = state.pot_total                       # 前几街已收入 pot 的
    total_bets_in_flight = sum(state.bets)                      # 本街尚未收入 pot 的下注
    
    conserved = total_live_stacks + total_pot_collected + total_bets_in_flight
    assert conserved == starting_total, (
        f"pre-settlement chip conservation: "
        f"{conserved} (stacks={total_live_stacks} + pot={total_pot_collected} "
        f"+ in_flight={total_bets_in_flight}) != expected {starting_total}"
    )

def audit_post_settlement(state: PokerKitState, config: SessionConfig) -> None:
    """
    Hand 结算完毕（showdown + payout + muck 都完成后）。
    此时 pot 已被 push，所有筹码都回到 stacks；不应再累加 pot/bets/payouts。
    守恒公式：stacks_final == starting_total
    """
    starting_total = config.starting_stack * config.num_players
    total_stacks = sum(state.stacks)
    
    assert total_stacks == starting_total, (
        f"post-settlement chip conservation: stacks sum {total_stacks} != expected {starting_total}. "
        f"Payouts may be incomplete or double-counted."
    )
    # 结算后 pot 应该清空
    assert state.pot_total == 0, f"post-settlement pot should be 0, got {state.pot_total}"
    # 所有 bets 都已 collect
    assert sum(state.bets) == 0, f"post-settlement bets should be 0"

def audit_cards_invariant(state: PokerKitState) -> None:
    """
    牌守恒在 hand 全程都适用。
    """
    all_known = (
        state.deck_remaining +
        state.burn_cards +
        state.community +
        [c for hc in state.hole_cards.values() for c in hc] +
        state.mucked_cards
    )
    assert len(all_known) == 52
    assert len(set(all_known)) == 52, "duplicate cards detected"
    
    # Hole cards 互斥
    for i, j in combinations(range(state.num_players), 2):
        assert not (set(state.hole_cards[i]) & set(state.hole_cards[j]))

# engine 层的调度入口
def audit_invariants(state: PokerKitState, config: SessionConfig, phase: HandPhase) -> None:
    """
    phase ∈ {PRE_SETTLEMENT, POST_SETTLEMENT}。
    engine 的 state transition wrapper 根据当前 hand 阶段调用正确的 audit。
    """
    audit_cards_invariant(state)
    if phase == HandPhase.POST_SETTLEMENT:
        audit_post_settlement(state, config)
    else:
        audit_pre_settlement(state, config)
    assert state.is_valid()  # PokerKit 自身一致性
```

### 2.3 测试策略对应表

| 威胁 | 防御 | 测试（§12） |
|---|---|---|
| 信息泄漏 | PlayerView DTO | 单元：构造全 state，序列化 PlayerView[i]，断言 seat j private fields 不出现 |
| 时间线泄漏 | PokerKit 只揭示已发公共牌 | 单元：preflop 的 PlayerView.community == [] |
| 跨玩家污染 | 独立 client | 单元：Mock 两个 agent，断言它们收到的 prompt 对象 id 不同；conversation 状态独立 |
| 状态声明 | tool_call > reasoning | 单元：Mock agent 返回 "我 fold" + tool_call "raise_to(100)"，断言 engine 执行后者 |
| 工具反推 | 白名单 + Range parser | Fuzz + Red-team：§12.5 扩展 |
| Prompt injection | Label / stats 字段消毒 | Red-team：§12.5 扩展 |
| 日志串台 | 3 层 log + access control | 单元：构造 PublicReplayReader 读 canonical_private.jsonl 必须 raise |
| Conservation | `audit_invariants` | Property-based：§12.3 |

---

## 3. 核心域：Engine、PokerKit 适配、投影

### 3.1 PokerKit 作为唯一 canonical

**BR2-04** 澄清：签名统一；deterministic deck 注入机制显式定义。

**签名约定**：

```python
@dataclass(frozen=True)
class HandContext:
    """每手起始上下文；engine orchestrator 在 start_new_hand 时构造。"""
    hand_id: int
    deck_seed: int                           # 派生自 config.rng_seed + hand_id
    button_seat: int
    initial_stacks: tuple[int, ...]          # 本手开始时每 seat 的 stack（含 auto-rebuy）
```

**Deterministic deck 注入机制**：

PokerKit 的 `HOLE_DEALING` / `BOARD_DEALING` automations 会内部调用 deck 的 `pop()`。PokerKit 的 `State.deck` 接受**预排序的 `Deck`** 对象。我们禁用这两个 automation，改为：
1. 用 `seeded_rng = random.Random(hand_context.deck_seed)` 预洗一副牌（`deterministic_deck_order(seeded_rng) -> list[Card]`）
2. 创建 `State` 时传入这个 `Deck`
3. 手动调用 `state.deal_hole(cards_pair, seat)` / `state.deal_board(cards_triplet/single)`，每次从**我们维护的**预排序牌堆顶部取卡

这样 `hand_id + config.rng_seed` 决定了整手牌的 deck 顺序，完全 deterministic。

```python
# engine/_internal/poker_state.py
from pokerkit import NoLimitTexasHoldem, Automation, State, Deck, Card

def build_deterministic_deck(deck_seed: int) -> list[Card]:
    """用 seeded RNG 洗出一副 52 张牌的确定顺序。"""
    full_deck = list(Deck.STANDARD)
    rng = random.Random(deck_seed)
    rng.shuffle(full_deck)
    return full_deck

class CanonicalState:
    """
    Wraps pokerkit.State. 唯一持有 game state 的对象。
    不暴露 pokerkit.State 给上层；通过方法返回只读数据。
    """
    def __init__(self, config: SessionConfig, hand_context: HandContext):
        self._config = config
        self._ctx = hand_context
        self._deck_order = build_deterministic_deck(hand_context.deck_seed)
        self._deck_cursor = 0
        
        # PP-02: 按 button_seat 旋转 blinds tuple，让 PokerKit 正确识别 SB/BB 位置。
        # 约定：PokerKit 的 raw_blinds_or_straddles[i] 是 seat i 的 forced post。
        #   SB 位于 (button_seat + 1) % num_players
        #   BB 位于 (button_seat + 2) % num_players
        # 其他 seats 为 0。
        # 举例（6-max，button_seat=3）：
        #   raw_blinds_or_straddles = (0, 0, 0, 0, sb, bb)
        #   → seat 4 post SB, seat 5 post BB, seat 0 = UTG (first to act preflop)
        blinds = [0] * config.num_players
        sb_seat = (hand_context.button_seat + 1) % config.num_players
        bb_seat = (hand_context.button_seat + 2) % config.num_players
        blinds[sb_seat] = config.sb
        blinds[bb_seat] = config.bb
        
        self._state: State = NoLimitTexasHoldem.create_state(
            automations=(
                Automation.ANTE_POSTING,
                Automation.BET_COLLECTION,
                Automation.BLIND_OR_STRADDLE_POSTING,
                # PP-01: CARD_BURNING 禁用，因 deterministic manual deal 路径下
                #        我们从预洗牌堆显式 burn（见 deal_community），
                #        保留 automation 会 double-burn 并破坏牌守恒
                # ---- HOLE_DEALING / BOARD_DEALING / CARD_BURNING 三者都禁用 ----
                # 所有 card movement 由 CanonicalState._next_card() 从预洗牌堆取
                Automation.HAND_KILLING,
                Automation.CHIPS_PUSHING,
                Automation.CHIPS_PULLING,
                Automation.RUNOUT_COUNT_SELECTION,
            ),
            ante_trimming_status=True,
            raw_antes=(0,) * config.num_players,
            raw_blinds_or_straddles=tuple(blinds),  # PP-02: rotated
            min_bet=config.bb,
            raw_starting_stacks=hand_context.initial_stacks,
            player_count=config.num_players,
        )
        # Hole cards 手动发（PokerKit 自动 post blinds 在上面的 BLIND_OR_STRADDLE_POSTING automation 里完成）
        self._deal_hole_cards_deterministic()
    
    def _next_card(self) -> Card:
        card = self._deck_order[self._deck_cursor]
        self._deck_cursor += 1
        return card
    
    def _deal_hole_cards_deterministic(self) -> None:
        """
        从预洗牌堆发 hole cards，遵循标准 NLHE 发牌顺序：
        从 SB 开始 clockwise，每 seat 发一张，连发两轮。
        """
        sb_seat = (self._ctx.button_seat + 1) % self._config.num_players
        for round_idx in range(2):
            for offset in range(self._config.num_players):
                seat = (sb_seat + offset) % self._config.num_players
                self._state.deal_hole((self._next_card(),))
    
    def deal_community(self, street: Street) -> None:
        """
        外部 orchestrator 在进入新 street 时调用。
        标准 NLHE 每街先烧一张，然后发公共牌。
        PP-01: CARD_BURNING automation 已禁用，burn 完全由本方法控制，从预洗牌堆取。
        """
        count = {"flop": 3, "turn": 1, "river": 1}[street.name]
        self._state.burn_card(self._next_card())
        cards = tuple(self._next_card() for _ in range(count))
        self._state.deal_board(cards)
    
    # -- read-only 投影方法 --
    
    def build_player_view(self, seat: SeatId) -> "PlayerView":
        """从 canonical 投影，构造 seat 视角。"""
        ...
    
    def build_public_view(self) -> "PublicView":
        """构造无 private 信息的公共视图（供 UI spectator / public log）。"""
        ...
    
    def build_agent_snapshot(self, seat: SeatId) -> "AgentSnapshot":
        """构造 serialization-ready 快照，用于存入 agent_view_snapshots.jsonl。"""
        ...
    
    # -- 合法动作查询（委托给 PokerKit） --
    
    def legal_actions(self, seat: SeatId) -> "LegalActionSet":
        """查询当前合法动作集。reopening 等逻辑完全由 PokerKit 决定。"""
        pk = self._state
        out: list[ActionToolSpec] = []
        
        can_fold = pk.can_fold()
        can_check = pk.can_check_or_call() and self._to_call_amount(seat) == 0
        can_call = pk.can_check_or_call() and self._to_call_amount(seat) > 0
        can_complete_bet_raise_to = pk.can_complete_bet_or_raise_to()
        
        if can_fold: out.append(FOLD_SPEC)
        if can_check: out.append(CHECK_SPEC)
        if can_call: out.append(CALL_SPEC)
        if can_complete_bet_raise_to:
            min_amt = pk.min_completion_betting_or_raising_to_amount
            max_amt = pk.max_completion_betting_or_raising_to_amount
            # 名称区分：如果是 opening（无人下注），叫 bet；否则 raise_to
            if self._to_call_amount(seat) == 0:
                out.append(BET_SPEC(min=min_amt, max=max_amt))
            else:
                out.append(RAISE_TO_SPEC(min=min_amt, max=max_amt))
        
        # all_in 作为便捷 tool，仅在栈 > 0 时
        if self._state.stacks[seat] > 0 and (can_call or can_complete_bet_raise_to):
            out.append(ALL_IN_SPEC)
        
        return LegalActionSet(tools=out)
    
    # -- 状态变更（唯一入口） --
    
    def apply_action(self, seat: SeatId, action: Action) -> TransitionResult:
        """
        验证 action 合法 → 委托 PokerKit 执行 → audit_invariants → 返回结果。
        任何非法输入在这里被拦截。
        """
        ...
```

### 3.2 PlayerView / PublicView / AgentSnapshot DTO

```python
# engine/views.py
from pydantic import BaseModel, Field

class PlayerView(BaseModel):
    """Seat i 能看到的完整信息。Pydantic 模型确保 serialization 边界。"""
    my_seat: int
    my_hole_cards: list[str]        # e.g. ["As", "Kd"]
    community: list[str]            # 仅已揭示
    pot: int
    sidepots: list[SidePotInfo]
    my_stack: int
    my_invested_this_hand: int                # 本手累计投入（所有 street 之和）
    my_invested_this_round: int               # ← BR2-02：本街已投入（用于算 to_call）
    current_bet_to_match: int                 # ← BR2-02：本街最高下注（任何 seat 的）
    seats_public: list[SeatPublicInfo]
    opponent_seats_in_hand: list[int]         # ← BR2-02：当前仍在手的对手 seat 列表
    action_order_this_street: list[int]
    already_acted_this_street: list[ActionRecord]
    hand_history: list[StreetHistory]
    legal_actions: LegalActionSet
    opponent_stats: dict[int, OpponentStatsOrInsufficient]  # key = seat
    hand_id: int
    street: str
    button_seat: int
    turn_seed: int                            # ← BR2-02：每 turn deterministic 派生 (rng_seed, hand_id, street, seat) 的种子，供 utility 工具（如 equity MC）复现
    immutable_session_params: "SessionParamsView"  # ← BR2-02：只读副本，替代 view.config

class SessionParamsView(BaseModel):
    """SessionConfig 的只读子集；view 需要知道的参数全复制进来，避免 agent/tool 摸到完整 config。"""
    num_players: int
    sb: int
    bb: int
    starting_stack: int
    max_utility_calls: int
    rationale_required: bool
    enable_math_tools: bool
    enable_hud_tool: bool
    opponent_stats_min_samples: int

class PublicView(BaseModel):
    """无 private 信息，给 UI spectator 和 public_replay.jsonl 用。"""
    hand_id: int
    street: str
    pot: int
    sidepots: list[SidePotInfo]
    community: list[str]
    seats_public: list[SeatPublicInfo]
    # 注意：没有任何 hole_cards 字段；没有 deck；没有单 seat 的 PlayerView

class AgentSnapshot(BaseModel):
    """进 agent_view_snapshots.jsonl 的快照。是 PlayerView + 元数据。"""
    timestamp: str
    seat: int
    hand_id: int
    turn_id: str
    view: PlayerView
```

### 3.3 合法动作集与 fallback

```python
# engine/legal_actions.py

def default_safe_action(view: PlayerView) -> Action:
    """
    非法或超时等 fallback 路径使用。
    规则：
      - 无人下注（to_call == 0）→ check
      - 有人下注 → fold
    这样保证 fallback 本身合法。
    """
    to_call = view.current_bet_to_match - view.my_invested_this_round
    if to_call == 0:
        return Action(tool_name="check")
    else:
        return Action(tool_name="fold")
```

所有需要 fallback 的路径（API timeout、二次非法、模型最终 step 不调 tool）**都走 `default_safe_action(view)`，不直接写死 fold**。

### 3.4 Short all-in 与 reopening

完全委托 PokerKit。具体：
- `pk.can_complete_bet_or_raise_to()` 返回 `True` 当且仅当 PokerKit 判断 raise 权利未被取消
- Short all-in（不足 full raise）之后，对已行动玩家 `can_complete_bet_or_raise_to()` 会返回 `False`
- 我们不自建 reopening 判断逻辑，全走 PokerKit API

### 3.5 Cash game rules：Auto-rebuy

```python
# engine/_internal/rebuy.py

def start_new_hand(session: Session) -> CanonicalState:
    """
    每手开始前的"table stakes + auto topup"规则：
    所有 seat 的 stack 重置为 config.starting_stack（100BB）。
    模拟"独立重复现金局"——避免变成 freezeout。
    
    影响：
    - 每手都是对称起点（减少位置方差）
    - 所有 agent 参与所有 hand（最大样本量）
    - P&L 指标 = 全程 (win - loss) 之和；每手独立结算
    """
    config = session.config
    hand_id = session.current_hand_id
    
    initial_stacks = tuple(config.starting_stack for _ in range(config.num_players))
    deck_seed = derive_deck_seed(config.rng_seed, hand_id)
    button_seat = session.next_button_seat()  # 正常 button rotation
    
    ctx = HandContext(
        hand_id=hand_id,
        deck_seed=deck_seed,
        button_seat=button_seat,
        initial_stacks=initial_stacks,
    )
    return CanonicalState(config, ctx)
```

**Rationale**：
- 研究目标不是 freezeout 比拼，是独立重复 cash scenarios
- 每手对称起点 → 减少方差，样本密度最大化
- 分析时 P&L 按手累加，符合 cash stats 习惯（$/手）

### 3.6 Hand 生命周期

PP-03 + PP-04：与 §3.1 手动 deterministic deal 路径 + §4.1 api_error censor 路径同步。

```
hand_start →
  apply_button_rotation (session 层：next_button_seat())
  reset_stacks (auto-rebuy 到 config.starting_stack) →
  construct HandContext(hand_id, deck_seed, button_seat, initial_stacks) →
  construct CanonicalState(config, hand_ctx):
    - PokerKit 自动 post blinds（BLIND_OR_STRADDLE_POSTING automation）
    - CanonicalState 手动 deterministic deal hole cards 从预洗牌堆
  →
  audit_invariants(phase=PRE_SETTLEMENT) →
  
  while PokerKit.is_actor_required():
    actor = PokerKit.get_actor()
    view = build_player_view(actor)
    tool_runner = ToolRunner(view, view.legal_actions, equity_backend)
    
    decision = await agents[actor].decide(view, tool_runner)
    
    # PP-04: BR2-01 censor 路径 —— api_error 或 final_action is None 时不进入 state transition
    if decision.api_error is not None or decision.final_action is None:
      mark_hand_censored(hand_id, reason="invalid_api_error", seat=actor, error=decision.api_error)
      emit_event(HandEnded{status: "invalid_api_error", ...})
      break  # 跳出 hand 主 loop，session 继续下一 hand
    
    apply_action(actor, decision.final_action)
    audit_invariants(phase=PRE_SETTLEMENT)
    emit_events(ActionCommitted, ...)
    
    # 若 PokerKit 需要发下一街 board card（CARD_BURNING/BOARD_DEALING 都禁用了，由 CanonicalState 手动）
    if PokerKit.needs_community(street):
      canonical_state.deal_community(street)
      audit_cards_invariant()
      emit_event(CommunityRevealed, ...)
  
  # 达到 showdown 或所有人 fold
  PokerKit 自动 showdown / HAND_KILLING / CHIPS_PUSHING / CHIPS_PULLING →
  audit_invariants(phase=POST_SETTLEMENT) →
  emit_event(HandEnded{status: "normal", winners: ...})
hand_end
```

**关键口径对齐**：
- PP-03: 不再说"PokerKit 自动 deal holes"；改为"PokerKit 自动 post blinds；CanonicalState 手动 deterministic deal hole/board"
- PP-04: `final_action is None`（来自 api_error 或 total_turn_timeout 触发的 censor path，见 §4.2）进入 `mark_hand_censored`，不调 `apply_action`，当前 hand 直接终止且不计入 winrate 统计

---

## 4. Agent 接口与 Bounded ReAct 循环

### 4.1 Agent 抽象

```python
# agents/base.py
from abc import ABC, abstractmethod

class Agent(ABC):
    @abstractmethod
    async def decide(
        self,
        view: PlayerView,
        tool_runner: ToolRunner,
    ) -> TurnDecisionResult:
        """
        Agent 接收 PlayerView + 可用 ToolRunner，返回完整决策记录。
        
        tool_runner 暴露：
          - run_utility(name, args) -> Any | ErrorDict
          - validate_action(name, args) -> ValidationResult
        
        Agent 不持有 engine 引用；所有世界交互经由 (view, tool_runner)。
        """
        ...
    
    @abstractmethod
    def provider_id(self) -> str: ...

@dataclass
class TurnDecisionResult:
    iterations: list[IterationRecord]
    final_action: Action | None          # ← BR2-01: None = api_error，Session 不 apply 任何动作，censor 整手
    total_tokens: TokenCounts
    wall_time_ms: int
    
    # ← BR2-05: 拆分四类 retry 计数器，各自独立限额，互不挤占
    api_retry_count: int                 # provider transient error / timeout 触发的 retry
    illegal_action_retry_count: int      # 模型提交的 action 不在 legal set / amount 越界
    no_tool_retry_count: int             # 模型没调任何 tool（content-only 响应）
    tool_usage_error_count: int          # utility tool 调用语法错（非法 range、mismatched seats 等）
    
    default_action_fallback: bool        # True = final_action 走了 default_safe_action
    api_error: ApiErrorInfo | None       # 非 None → final_action 必须为 None
    turn_timeout_exceeded: bool          # ← BR2-06: 总 turn timeout 触发
```

**Session 层处理语义**（§3.6 hand 生命周期补充）：

```python
# engine/session_orchestrator.py
async def run_turn(session, actor) -> HandOutcome | None:
    view = build_player_view(actor)
    tool_runner = ToolRunner(view, view.legal_actions, session.equity_backend)
    
    decision = await agents[actor].decide(view, tool_runner)
    
    # BR2-01: api_error 或 final_action is None 时，不 apply 任何动作
    if decision.api_error is not None or decision.final_action is None:
        session.mark_hand_censored(
            reason="invalid_api_error",
            error=decision.api_error,
            seat=actor,
        )
        # 中断当前 hand；session 继续下一 hand
        return HandOutcome(status="invalid_api_error", ...)
    
    # 正常路径
    result = apply_action(session.canonical_state, actor, decision.final_action)
    audit_invariants(session.canonical_state, session.config, phase=HandPhase.PRE_SETTLEMENT)
    emit_events(...)
    return None  # 继续下一 turn
```

### 4.2 LLM Agent Bounded ReAct（v2 版）

```python
# agents/llm_agent.py

class LLMAgent(Agent):
    """
    Bounded ReAct：K 次 utility tool 调用 + 1 次强制 action 步。
    最后一步通过 **缩小 tool list 到 action-only** 施压。
    但 provider **不保证** 一定调 tool——fallback 必须扎实。
    """
    
    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        version: str,
        prompt_profile: PromptProfile,
        max_utility_calls: int = 5,
        temperature: float = 0.7,
        seed: int | None = None,
        per_iteration_timeout_sec: float = 60.0,
        total_turn_timeout_sec: float = 180.0,
        label: str = "",
    ):
        ...  # 保存参数
    
    async def decide(self, view, tool_runner) -> TurnDecisionResult:
        """
        BR2-06: 用 asyncio.wait_for 包住整个 decide 体，保证 total_turn_timeout_sec 生效。
        超时触发则回 api_error（与 provider transient timeout 同路径）。
        """
        try:
            return await asyncio.wait_for(
                self._decide_inner(view, tool_runner),
                timeout=self.total_turn_timeout_sec,
            )
        except asyncio.TimeoutError:
            return TurnDecisionResult(
                iterations=[],
                final_action=None,  # BR2-01: api/timeout 错误 → None，不 apply
                total_tokens=TokenCounts.zero(),
                wall_time_ms=int(self.total_turn_timeout_sec * 1000),
                api_retry_count=0,
                illegal_action_retry_count=0,
                no_tool_retry_count=0,
                tool_usage_error_count=0,
                default_action_fallback=False,
                api_error=ApiErrorInfo(type="TotalTurnTimeout", detail=f"exceeded {self.total_turn_timeout_sec}s"),
                turn_timeout_exceeded=True,
            )
    
    async def _decide_inner(self, view, tool_runner) -> TurnDecisionResult:
        K = self.max_utility_calls
        full_tools = build_tool_specs(view, include_utility=True)
        action_only_tools = build_tool_specs(view, include_utility=False)
        
        messages = self._build_messages(view)
        iterations: list[IterationRecord] = []
        
        # BR2-05: 四类独立 retry 计数器
        api_retry_count = 0
        illegal_action_retry_count = 0
        no_tool_retry_count = 0
        tool_usage_error_count = 0
        
        MAX_API_RETRY = 1           # provider transient → 最多 retry 1 次
        MAX_ILLEGAL_RETRY = 1       # illegal action → 最多 retry 1 次
        MAX_NO_TOOL_RETRY = 1       # 没调 tool → 最多 retry 1 次
        # tool_usage_error 不消耗"retry 配额"：agent 可以在同 step 重试不同 tool 参数
        # 但总 step 数仍受 K+1 bound 限制
        
        utility_count = 0
        turn_start = time.monotonic()
        
        step = 0
        while step < K + 1:
            is_final_step = (step == K) or (utility_count >= K)
            tools_this_step = action_only_tools if is_final_step else full_tools
            
            # Provider 调用 + per-iteration timeout
            try:
                response = await asyncio.wait_for(
                    self.provider.complete(
                        messages=messages,
                        tools=tools_this_step,
                        temperature=self.temperature,
                        seed=self.seed,
                    ),
                    timeout=self.per_iteration_timeout_sec,
                )
            except (asyncio.TimeoutError, ProviderTransientError) as e:
                if api_retry_count < MAX_API_RETRY:
                    api_retry_count += 1
                    await asyncio.sleep(1.0 + random.random())
                    continue  # 不推进 step；重试同一步
                # 超出 API retry 预算 → censor hand，final_action=None
                return TurnDecisionResult(
                    iterations=iterations,
                    final_action=None,  # BR2-01: 明确不 fallback
                    total_tokens=sum_tokens(iterations),
                    wall_time_ms=int((time.monotonic() - turn_start) * 1000),
                    api_retry_count=api_retry_count,
                    illegal_action_retry_count=illegal_action_retry_count,
                    no_tool_retry_count=no_tool_retry_count,
                    tool_usage_error_count=tool_usage_error_count,
                    default_action_fallback=False,
                    api_error=ApiErrorInfo(type=type(e).__name__, detail=str(e)),
                    turn_timeout_exceeded=False,
                )
            
            iter_record = self._extract_iteration(response, step=step + 1)
            iterations.append(iter_record)
            
            if iter_record.tool_call is None:
                # 模型没调任何 tool
                if no_tool_retry_count < MAX_NO_TOOL_RETRY:
                    no_tool_retry_count += 1
                    # BR2-07: 保留 Anthropic thinking blocks 等原样
                    messages.append(self.provider.serialize_assistant_turn(response))
                    messages.append(self._error_message("You must call an action tool."))
                    step += 1
                    continue
                # 超出额度 → default_safe_action
                return TurnDecisionResult(
                    iterations=iterations,
                    final_action=default_safe_action(view),
                    total_tokens=sum_tokens(iterations),
                    wall_time_ms=int((time.monotonic() - turn_start) * 1000),
                    api_retry_count=api_retry_count,
                    illegal_action_retry_count=illegal_action_retry_count,
                    no_tool_retry_count=no_tool_retry_count,
                    tool_usage_error_count=tool_usage_error_count,
                    default_action_fallback=True,
                    api_error=None,
                    turn_timeout_exceeded=False,
                )
            
            tc = iter_record.tool_call
            
            if tc.name in ACTION_TOOL_NAMES:
                action = self._to_action(tc)
                validation = tool_runner.validate_action(action.tool_name, action.args)
                if validation.is_valid:
                    return TurnDecisionResult(
                        iterations=iterations,
                        final_action=action,
                        total_tokens=sum_tokens(iterations),
                        wall_time_ms=int((time.monotonic() - turn_start) * 1000),
                        api_retry_count=api_retry_count,
                        illegal_action_retry_count=illegal_action_retry_count,
                        no_tool_retry_count=no_tool_retry_count,
                        tool_usage_error_count=tool_usage_error_count,
                        default_action_fallback=False,
                        api_error=None,
                        turn_timeout_exceeded=False,
                    )
                # 非法 action
                if illegal_action_retry_count < MAX_ILLEGAL_RETRY:
                    illegal_action_retry_count += 1
                    messages.append(self.provider.serialize_assistant_turn(response))
                    messages.append(self._error_message(
                        f"Illegal action: {validation.reason}. "
                        f"Legal set: {[t.name for t in view.legal_actions.tools]}."
                    ))
                    step += 1
                    continue
                # 超出额度 → default_safe_action
                return TurnDecisionResult(
                    iterations=iterations,
                    final_action=default_safe_action(view),
                    total_tokens=sum_tokens(iterations),
                    wall_time_ms=int((time.monotonic() - turn_start) * 1000),
                    api_retry_count=api_retry_count,
                    illegal_action_retry_count=illegal_action_retry_count,
                    no_tool_retry_count=no_tool_retry_count,
                    tool_usage_error_count=tool_usage_error_count,
                    default_action_fallback=True,
                    api_error=None,
                    turn_timeout_exceeded=False,
                )
            
            elif tc.name in UTILITY_TOOL_NAMES:
                if is_final_step:
                    # 最后一步仍调 utility（理论上不应发生——action_only_tools 不含 utility）
                    if no_tool_retry_count < MAX_NO_TOOL_RETRY:
                        no_tool_retry_count += 1
                        messages.append(self.provider.serialize_assistant_turn(response))
                        messages.append(self._error_message(
                            "You have exhausted utility calls. Call an action tool now."
                        ))
                        step += 1
                        continue
                    return TurnDecisionResult(
                        iterations=iterations,
                        final_action=default_safe_action(view),
                        total_tokens=sum_tokens(iterations),
                        wall_time_ms=int((time.monotonic() - turn_start) * 1000),
                        api_retry_count=api_retry_count,
                        illegal_action_retry_count=illegal_action_retry_count,
                        no_tool_retry_count=no_tool_retry_count,
                        tool_usage_error_count=tool_usage_error_count,
                        default_action_fallback=True,
                        api_error=None,
                        turn_timeout_exceeded=False,
                    )
                
                utility_count += 1
                result = tool_runner.run_utility(tc.name, tc.args)
                # 若 utility 返回 invalid_input（如 range 字符串不合法），计入 tool_usage_error_count
                if isinstance(result, dict) and result.get("invalid_input"):
                    tool_usage_error_count += 1
                messages.append(self.provider.serialize_assistant_turn(response))
                messages.append(self._to_tool_result_message(tc, result))
                step += 1
                continue
            
            else:
                # 未知 tool name
                if illegal_action_retry_count < MAX_ILLEGAL_RETRY:
                    illegal_action_retry_count += 1
                    messages.append(self.provider.serialize_assistant_turn(response))
                    messages.append(self._error_message(f"Unknown tool: {tc.name}."))
                    step += 1
                    continue
                return TurnDecisionResult(
                    iterations=iterations,
                    final_action=default_safe_action(view),
                    total_tokens=sum_tokens(iterations),
                    wall_time_ms=int((time.monotonic() - turn_start) * 1000),
                    api_retry_count=api_retry_count,
                    illegal_action_retry_count=illegal_action_retry_count,
                    no_tool_retry_count=no_tool_retry_count,
                    tool_usage_error_count=tool_usage_error_count,
                    default_action_fallback=True,
                    api_error=None,
                    turn_timeout_exceeded=False,
                )
        
        # 走完全部 iterations 仍未 commit
        return TurnDecisionResult(
            iterations=iterations,
            final_action=default_safe_action(view),
            total_tokens=sum_tokens(iterations),
            wall_time_ms=int((time.monotonic() - turn_start) * 1000),
            api_retry_count=api_retry_count,
            illegal_action_retry_count=illegal_action_retry_count,
            no_tool_retry_count=no_tool_retry_count,
            tool_usage_error_count=tool_usage_error_count,
            default_action_fallback=True,
            api_error=None,
            turn_timeout_exceeded=False,
        )
```

**BR2-07: Anthropic thinking block 回传**

`self.provider.serialize_assistant_turn(response)` 是 Provider 接口方法，返回**原样保留**的 assistant turn content blocks（list[ContentBlock]）。对 Anthropic 实现：

- `thinking` block（明文）→ 保留 `type`/`thinking`/`signature` 字段
- `redacted_thinking` block → 保留 `type`/`data` 字段原样
- `tool_use` block → 保留 `type`/`id`/`name`/`input`
- `text` block → 保留 `type`/`text`

**不做**任何重构、合并、裁剪；一旦修改会破坏 Anthropic extended thinking + tool use 的协议要求（Anthropic 文档明确要求 multi-turn 时这些 block 必须 byte-identical 回传）。

对不使用 thinking block 的 provider（OpenAI / DeepSeek 等），`serialize_assistant_turn` 返回 provider 约定的 assistant message 结构即可。

### 4.3 Iteration 记录 Schema（v2）

```python
@dataclass
class IterationRecord:
    step: int
    reasoning_artifact: ReasoningArtifact    # ← §4.6 定义
    reasoning_stated: str                     # content field
    tool_call: ToolCall | None                # None = 模型没调任何 tool
    tool_result: Any                          # 对 utility 是结果；对 action 是 None
    tokens: TokenCounts
    wall_time_ms: int
    raw_response: dict                        # forensic debug
```

### 4.4 Provider 适配

直连优先：先 Anthropic + OpenAI，LiteLLM 作为 fallback。理由：
- 直连对各家特有 reasoning 通道抽取最可控
- LiteLLM 常抹平差异，丢掉我们需要的 provider-specific 信息

```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self, messages, tools, temperature, seed
    ) -> LLMResponse: ...
    
    @abstractmethod
    def extract_reasoning_artifact(self, response) -> ReasoningArtifact: ...
    
    @abstractmethod
    def serialize_assistant_turn(self, response) -> AssistantTurn:
        """
        BR2-07: 将 provider response 序列化为可回传到下一轮的 assistant message。
        
        **关键约束（Anthropic）**：若启用 extended thinking，thinking/redacted_thinking/
        encrypted 等 block 必须**原样（byte-identical）** 保留；不得重构、合并或裁剪。
        否则下一轮 API 会拒绝请求或行为退化。
        
        其他 provider：按各自 SDK 约定重构 assistant message 即可。
        """
        ...
    
    @abstractmethod
    async def probe(self) -> ObservedCapability:
        """
        HR2-03: 在 session 启动时用一个最小 sample prompt 实探 provider 能力。
        返回运行时实测结果（而非静态假设）。
        
        探测内容：
          - 实际返回的 reasoning artifact kind
          - seed 参数是否被接受（不保证 determinism，但接受性 = 该接口没退役）
          - tool_use + thinking 是否兼容（在 thinking=true 时调 tool_choice=any 跑通）
          - system_fingerprint 是否返回（OpenAI 系）
        """
        ...
    
    @abstractmethod
    def static_capability(self) -> ProviderCapability:
        """静态声明（不需要网络）；仅供 fallback 或离线配置参考。运行时以 probe() 为准。"""
        ...
```

```python
class AssistantTurn(BaseModel):
    """BR2-07: 保留原始 content blocks 结构，不做抽象。"""
    provider: str
    blocks: list[dict]                      # 原样保留 provider 的 content block list
    role: Literal["assistant"] = "assistant"

class ObservedCapability(BaseModel):
    """HR2-03: 启动 probe 产出。"""
    provider: str
    probed_at: str                          # ISO timestamp
    reasoning_kinds: list[ReasoningArtifactKind]  # 实测可见的形态
    seed_accepted: bool                     # API 接受 seed 参数（不保证 determinism）
    tool_use_with_thinking_ok: bool         # 若相关
    extra_flags: dict                       # 额外 flags（如 OpenAI system_fingerprint 是否存在）
```

### 4.5 Rationale Required 开关（新，H-14）

`rationale_required: bool`（默认 `true`）
- `true`：system prompt 要求"先写 reasoning 再调 action tool"；content 为空时视为退化（触发 retry）
- `false`：允许模型直接调 tool 不写 content；用于测"强制推理是否改变策略"

作为 ablation 轴进入实验配置（见 §15.2）。

### 4.6 Provider Reasoning Artifact Matrix（新，B-01 / S-01）

**不再承诺 "Tier 3 双通道"。**  改为显式记录每家 provider 能给出的 reasoning artifact 类别：

```python
class ReasoningArtifactKind(str, Enum):
    RAW = "raw"              # e.g. DeepSeek R1 reasoning_content（原生思考链）
    SUMMARY = "summary"      # e.g. OpenAI reasoning.summary（摘要）
    THINKING_BLOCK = "thinking_block"  # e.g. Anthropic extended thinking 的明文部分
    ENCRYPTED = "encrypted"  # e.g. Anthropic encrypted thinking block
    REDACTED = "redacted"    # e.g. Anthropic redacted_thinking
    UNAVAILABLE = "unavailable"  # provider 不暴露任何 reasoning artifact

class ReasoningArtifact(BaseModel):
    kind: ReasoningArtifactKind
    content: str | None       # kind=RAW/SUMMARY/THINKING_BLOCK 时为文本；
                              # kind=ENCRYPTED 时为 base64/opaque 字符串；
                              # 其他时为 None
    provider_raw_index: int | None  # raw response 里这部分的位置（forensic）
```

**Provider capability 表（representative observed — probed at session start）**

HR2-03 澄清：下表为写 spec 时的**代表性观察**，**非稳定约定**。实际值由 `Provider.probe()` 在每 session 启动时实探，结果写入 `meta.json.provider_capabilities`。Spec 不承诺表内值的时间稳定性。

| Provider | 已观察到的 reasoning 产出形态 | seed 参数接受 | tool_use + thinking 限制（需 probe） |
|---|---|---|---|
| Anthropic (Opus/Sonnet) | `thinking_block` / `encrypted_thinking` / `redacted_thinking` | 否 | temperature/top_k/tool_choice 在 thinking 开启时受限；thinking blocks 必须原样回传（BR2-07） |
| OpenAI (reasoning-tier, o-series) | `summary` 或 `unavailable`（取决于 model）；推荐走 Responses API 而不是 Chat API 的 seed | best-effort（Chat API `seed` 字段标 deprecated） | Responses API 更新接口语义不同，probe 必须区分 |
| Gemini 2.5 thinking | `summary` 或 `thinking_block`（取决于 flag） | 视版本 —— probe 决定 | 视版本 |
| DeepSeek R1 | `raw` (`reasoning_content`) | 接受（开源/兼容接口） | 接受 |
| DeepSeek V3 | `unavailable` | 接受 | 接受 |
| Kimi K2 | `unavailable`（未明示） | 未明示 | 需 probe |
| Grok 4 | `unavailable`（未明示） | 未明示 | 需 probe |

Session 启动时对每个 agent provider 调 `probe()`，将 `ObservedCapability` 写入 `meta.json`。实验分析以 **probe 结果** 为 grouping 维度，不用此表硬约定。

分析时以 `ReasoningArtifactKind` 为数据分组维度，不强求同构比较。

---

## 5. 工具系统

### 5.1 Action Tools

| Tool | args | 合法性（委托 PokerKit） |
|---|---|---|
| `fold` | {} | `pk.can_fold()` |
| `check` | {} | `pk.can_check_or_call() and to_call == 0` |
| `call` | {} | `pk.can_check_or_call() and to_call > 0` |
| `bet` | {amount: int, min/max} | `pk.can_complete_bet_or_raise_to() and to_call == 0` |
| `raise_to` | {amount: int, min/max} | `pk.can_complete_bet_or_raise_to() and to_call > 0` |
| `all_in` | {} | 栈 > 0（便捷 tool，server 端转换到 pk 合法入口） |

### 5.2 Utility Tools（v2 重做）

#### 5.2.1 Range Notation Parser（H-01）

```python
# tools/range_parser.py

RANK_CHARS = "AKQJT98765432"
SUIT_CHARS = "shdc"

class RangeNotationParser:
    """
    严格解析 poker range notation。
    支持语法（示例）：
      - 对子：22, 55, TT, 22+, 88+
      - 非对子：AK, AKs, AKo, AKs+, AKo-ATo
      - 组合：22+,AT+,KQ
      - 特定组合枚举：AKs（表示 AK 同花 4 种）
    
    **拒绝**：具体 5-card string、单张 card string、suited 具体组合。
    """
    
    def parse(self, notation: str) -> list[HoleCardCombo]:
        """返回 range 展开后的所有 2-card combo。"""
        # 1. 硬拒绝任何具体 suit-card 格式
        if re.search(r'\b[AKQJT98765432][shdc]\b', notation):
            raise ToolInputError(
                f"Range notation must not contain concrete cards (e.g. 'Ah'). "
                f"Use abstract notation like 'AKs' instead. Got: {notation!r}"
            )
        
        # 2. 分割 comma-separated 段
        segments = [s.strip() for s in notation.split(',')]
        if not all(segments):
            raise ToolInputError(f"Empty segment in range: {notation!r}")
        
        # 3. 每段严格语法解析
        combos = []
        for seg in segments:
            combos.extend(self._parse_segment(seg))
        
        return combos
    
    def _parse_segment(self, seg: str) -> list[HoleCardCombo]:
        # 单对子：22
        if re.fullmatch(r'[AKQJT98765432]{2}', seg) and seg[0] == seg[1]:
            return pair_combos(seg[0])
        
        # 对子以上：22+
        if re.fullmatch(r'[AKQJT98765432]{2}\+', seg[:-1] + seg[-1]):
            ...
        
        # 同花/非同花：AKs, AKo
        if re.fullmatch(r'[AKQJT98765432]{2}[so]', seg):
            ...
        
        # 区间：AKs-ATs
        if re.fullmatch(r'[AKQJT98765432]{2}[so]-[AKQJT98765432]{2}[so]', seg):
            ...
        
        raise ToolInputError(f"Unrecognized range segment: {seg!r}")
```

#### 5.2.2 Equity Backend 抽象（H-02）

```python
# tools/equity_backend.py

class EquityBackend(ABC):
    @abstractmethod
    def evaluate_range_equity(
        self,
        hero_cards: list[Card],
        community: list[Card],
        villain_ranges: dict[SeatId, list[HoleCardCombo]],
        n_samples: int,
        seed: int,
    ) -> EquityResult: ...

class EquityResult(BaseModel):
    hero_equity: float          # 估计胜率（含 tie 0.5 权重）
    ci_low: float               # 95% CI 下界
    ci_high: float              # 95% CI 上界
    n_samples: int
    seed: int
    backend: str                # 实现标识

# 默认实现：eval7Backend
# Fallback：TreysBackend
# 未来可替换：cubicBackend、pokerkit-native etc.
```

#### 5.2.3 Utility Tool 实现

```python
# tools/utility_tools.py

def pot_odds(view: PlayerView) -> float:
    """零参数，纯 view 计算。"""
    ...

def spr(view: PlayerView) -> float:
    """零参数。"""
    ...

def hand_equity_vs_ranges(
    view: PlayerView,
    range_by_seat: dict[int, str],
    backend: EquityBackend,
    n_samples: int = 5000,
    seed_override: int | None = None,
) -> EquityResult:
    """
    多人底池 equity 估计。
    
    range_by_seat 的 keys 必须严格等于 view.opponent_seats_in_hand。
    返回 hero_equity + CI。
    """
    live_opponents = set(view.opponent_seats_in_hand)
    provided = set(range_by_seat.keys())
    
    if provided != live_opponents:
        raise ToolInputError(
            f"range_by_seat keys {provided} must equal live opponent seats "
            f"{live_opponents}. Missing: {live_opponents - provided}, "
            f"extra: {provided - live_opponents}."
        )
    
    parser = RangeNotationParser()
    parsed_ranges = {
        seat: parser.parse(notation)
        for seat, notation in range_by_seat.items()
    }
    
    # deterministic seed: 来自 turn context，或 override
    seed = seed_override if seed_override is not None else view.turn_seed
    
    return backend.evaluate_range_equity(
        hero_cards=view.my_hole_cards,
        community=view.community,
        villain_ranges=parsed_ranges,
        n_samples=n_samples,
        seed=seed,
    )

def hand_equity_vs_range(
    view: PlayerView,
    villain_range: str,
    backend: EquityBackend,
    n_samples: int = 5000,
    seed_override: int | None = None,
) -> EquityResult:
    """
    HU-only alias。多人底池场景 raise ToolUsageError 引导 agent 用新 API。
    """
    live_opponents = view.opponent_seats_in_hand
    if len(live_opponents) != 1:
        raise ToolUsageError(
            f"hand_equity_vs_range is heads-up only (got {len(live_opponents)} live opponents). "
            f"Use hand_equity_vs_ranges(range_by_seat={{seat: range}}) for multi-way."
        )
    return hand_equity_vs_ranges(
        view, {live_opponents[0]: villain_range}, backend, n_samples, seed_override
    )

def get_opponent_stats(
    view: PlayerView,
    seat: int,
    detail_level: str = "summary",
) -> dict:
    ...
```

### 5.3 Tool Registry

```python
def build_tool_specs(
    view: PlayerView,
    include_utility: bool = True,
) -> list[ToolSpec]:
    specs = []
    specs.extend(view.legal_actions.to_tool_specs())
    
    if include_utility:
        # PP-05: 从 view 的只读 session params 副本取开关，不经 config 对象
        params = view.immutable_session_params
        if params.enable_math_tools:
            specs.append(POT_ODDS_SPEC)
            specs.append(SPR_SPEC)
            specs.append(HAND_EQUITY_VS_RANGES_SPEC)
            # HU alias 不在 default 集里，避免 agent 误用；留作 docs 例子
        if params.enable_hud_tool:
            specs.append(OPPONENT_STATS_SPEC)
    
    return specs
```

### 5.4 ToolRunner

```python
class ToolRunner:
    """
    Agent 与工具/校验的唯一交互面。
    持有 PlayerView + 预算出的 LegalActionSet + EquityBackend。
    **不持有 CanonicalState。**
    **不持有完整 SessionConfig** —— session params 走 view.immutable_session_params（只读副本）。
    """
    def __init__(
        self,
        view: PlayerView,
        legal_actions: LegalActionSet,
        equity_backend: EquityBackend,
    ):
        self._view = view
        self._legal = legal_actions
        self._equity = equity_backend
    
    def run_utility(self, name: str, args: dict) -> Any:
        try:
            if name == "pot_odds":
                return {"value": pot_odds(self._view)}
            elif name == "spr":
                return {"value": spr(self._view)}
            elif name == "hand_equity_vs_ranges":
                result = hand_equity_vs_ranges(
                    self._view, args["range_by_seat"], self._equity,
                    seed_override=None,
                )
                return result.model_dump()
            elif name == "get_opponent_stats":
                # PP-05: 从 view 的 session params 只读副本读开关
                if not self._view.immutable_session_params.enable_hud_tool:
                    return {"error": "get_opponent_stats disabled"}
                return get_opponent_stats(self._view, **args)
            else:
                return {"error": f"Unknown tool: {name}"}
        except (ToolInputError, ToolUsageError) as e:
            return {"error": str(e), "invalid_input": True}
    
    def validate_action(self, name: str, args: dict) -> ValidationResult:
        legal_names = [t.name for t in self._legal.tools]
        if name not in legal_names:
            return ValidationResult.invalid(
                f"Action '{name}' not in legal set {legal_names}"
            )
        spec = next(t for t in self._legal.tools if t.name == name)
        if name in ("bet", "raise_to"):
            amt = args.get("amount")
            if not isinstance(amt, int):
                return ValidationResult.invalid(f"{name} requires integer 'amount'")
            mn, mx = spec.args["amount"]["min"], spec.args["amount"]["max"]
            if not (mn <= amt <= mx):
                return ValidationResult.invalid(
                    f"{name} amount {amt} out of range [{mn}, {mx}]"
                )
        return ValidationResult.valid()
```

---

## 6. Prompt 设计

### 6.1 System Prompt（cached per session）

核心不变，但加入 `rationale_required` 条件：

```jinja
You are a player in a No-Limit Texas Hold'em 6-max cash game simulation.

SESSION PARAMETERS
- Variant: NLHE, 6 players
- Starting stack: {{ starting_stack }} chips ({{ starting_stack // bb }} BB at {{ sb }}/{{ bb }})
- Auto-rebuy: each hand starts with stacks reset to starting_stack
- Rake: none
- Rotation: dealer button moves clockwise

YOUR ROLE
- Fixed seat for entire session.
- See only your hole cards.

YOUR OBJECTIVE
- Maximize chip EV over all hands.
- Decisions final once submitted (action tool_call).

HOW TO ACT
- Receive state + subset of legal action tools each turn.
{%- if rationale_required %}
- First write reasoning in your response content.
- Then call exactly one action tool.
{%- else %}
- Call exactly one action tool. You may optionally write brief reasoning, but it is not required.
{%- endif %}
- You may call utility tools (pot_odds, etc.) up to {{ K }} times before committing.
- Tools not in the list are not legal this turn.

{%- if rationale_required %}

WHEN THINKING, CONSIDER
- Hand strength (current and future equity)
- Opponents' likely ranges given their actions and stats
- Pot odds and implied odds
- Your position and stack depth
{%- endif %}

Respond in English.
```

### 6.2 User Prompt Template

基本同 v1，修正：
- 去掉"insufficient 样本"的片段结构（改为显式 if/else 见 v1 自查修正）
- 增加 action order + button 显式标注
- Hole cards 格式固定为空格分隔的 2-char tokens

### 6.3 Prompt Profile

```yaml
# prompts/default-v2.yaml
prompt_profile:
  name: "default-v2"
  language: "en"
  persona: null
  reasoning_prompt: "light"
  rationale_required: true          # ← H-14
  stats_min_samples: 30
  card_format: "Ah Kh"
  player_label_format: "Player_{seat}"
  position_label_format: "{short} ({full})"
```

---

## 7. 数据 Schema（v2 三层日志）

### 7.1 目录结构（per-session）

```
runs/
└── session_2026-04-23_17-30-45_a8f3b2/
    ├── config.yaml
    ├── meta.json
    ├── canonical_private.jsonl        # engine 真相，含所有 hole cards（access control 限制）
    ├── public_replay.jsonl            # UI / spectator 可见（无 hidden info）
    ├── agent_view_snapshots.jsonl     # 每 turn 每 agent 的 PlayerView 快照
    ├── phh/                           # PHH exporter 产出（§7.7）
    │   └── hand_0001.phh, hand_0002.phh, ...
    ├── prompts/
    │   └── ... (snapshot)
    └── crash.json (optional)
```

### 7.2 Layer 1: canonical_private.jsonl

完整 hand 记录。**仅 engine 内部 / 分析工具可读**；UI 永远不读这个。

```json
{
  "hand_id": 127,
  "started_at": "2026-04-23T18:12:33.123Z",
  "ended_at": "2026-04-23T18:13:05.456Z",
  "button_seat": 4,
  "sb_seat": 5,
  "bb_seat": 6,
  "deck_seed": 42127,
  "starting_stacks": {"1": 10000, "2": 10000, "3": 10000, "4": 10000, "5": 10000, "6": 10000},
  "hole_cards": {
    "1": ["Ah", "Kh"],
    "2": ["7s", "7c"],
    "3": ["2d", "2h"],
    "4": ["Qs", "Js"],
    "5": ["3c", "8d"],
    "6": ["Tc", "Th"]
  },
  "community": ["7c", "2d", "5s", "9h", "Ah"],
  "actions": [/* 按时间序全部 action，含 street / seat / amount / legal_ctx */],
  "result": {
    "showdown": true,
    "winners": [{"seat": 2, "winnings": 2450, "best_hand_desc": "Set of 7s"}],
    "side_pots": [],
    "final_invested": {"1": 1200, "2": 1200, ...},
    "net_pnl": {"1": -1200, "2": 1250, ...}
  }
}
```

### 7.3 Layer 2: public_replay.jsonl

**不含任何隐藏信息**。可安全推给 UI 观战、发布为开放数据集。

```json
{
  "hand_id": 127,
  "street_events": [
    {"type": "hand_started", "button_seat": 4, "blinds": {"sb": 50, "bb": 100}},
    {"type": "hole_dealt"},
    {"type": "action", "seat": 1, "street": "preflop", "action": {"type": "raise_to", "amount": 300}},
    ...
    {"type": "flop", "community": ["7c", "2d", "5s"]},
    ...
    {"type": "showdown", "revealed": {"1": ["Ah", "Kh"], "3": ["2d", "2h"]}},
    {"type": "hand_ended", "winnings": {"1": -1200, "2": 1250, ...}}
  ]
}
```

**规则**：showdown 才揭示参与 showdown 的 hole cards；弃牌 muck 的不出现在 public_replay。

### 7.4 Layer 3: agent_view_snapshots.jsonl（一行一 turn 一 agent）

```json
{
  "hand_id": 127,
  "turn_id": "127-flop-3",
  "session_id": "session_...",
  "seat": 3,
  "street": "flop",
  "timestamp": "2026-04-23T18:12:55.789Z",
  
  "view_at_turn_start": {
    /* 完整 PlayerView[seat=3] Pydantic dump */
  },
  
  "iterations": [
    {
      "step": 1,
      "reasoning_artifact": {"kind": "thinking_block", "content": "Let me check pot odds..."},
      "reasoning_stated": "I'll check the pot odds.",
      "tool_call": {"name": "pot_odds", "args": {}},
      "tool_result": {"value": 0.297},
      "tokens": {"prompt": 1432, "completion": 45, "reasoning": 210, "total": 1687},
      "wall_time_ms": 842
    },
    {
      "step": 2,
      "reasoning_artifact": {"kind": "thinking_block", "content": "..."},
      "reasoning_stated": "Equity vs TT+ looks good.",
      "tool_call": {
        "name": "hand_equity_vs_ranges",
        "args": {"range_by_seat": {"1": "TT+,AKs,AKo"}}
      },
      "tool_result": {
        "hero_equity": 0.847,
        "ci_low": 0.834, "ci_high": 0.860,
        "n_samples": 5000, "seed": 127003,
        "backend": "eval7"
      },
      "tokens": {...},
      "wall_time_ms": 1203
    },
    {
      "step": 3,
      "reasoning_artifact": {"kind": "thinking_block", "content": "..."},
      "reasoning_stated": "Set of 2s is very strong. Raise for value.",
      "tool_call": {"name": "raise_to", "args": {"amount": 725}},
      "tool_result": null,
      "tokens": {...},
      "wall_time_ms": 1567
    }
  ],
  
  "final_action": {"type": "raise_to", "amount": 725},
  "is_forced_blind": false,               // ← HR2-02: 写入时预计算。true 仅当本 action 是 SB/BB 的强制 post（不算 voluntary）
  "total_utility_calls": 2,
  "api_retry_count": 0,                   // ← BR2-05: 四类独立计数器
  "illegal_action_retry_count": 0,
  "no_tool_retry_count": 0,
  "tool_usage_error_count": 0,
  "default_action_fallback": false,
  "api_error": null,
  "turn_timeout_exceeded": false,         // ← BR2-06
  "total_tokens": {},
  "wall_time_ms": 3612,
  "agent": {
    "provider": "anthropic",
    "model": "<opus_tier_frontier>",      // runtime-pinned at config load
    "version": "<pinned_by_config>",
    "temperature": 0.7,
    "seed": null                          // Anthropic doesn't support seed
  }
}
```

**`is_forced_blind` 预计算规则**：`true` 当且仅当 `(street == "preflop") AND (seat == sb_seat OR seat == bb_seat) AND (final_action 是 blind auto-post；即 agent 根本没被 ask 做选择)`。PokerKit 的 BLIND_OR_STRADDLE_POSTING automation 处理的是 blind post，这部分**不调 agent**——所以实际上 agent_view_snapshots 本就不会记录 blind post 作为 turn。但为避免歧义，仍在 schema 里加此字段，所有 agent 产生的 turn 记录 `is_forced_blind=false`。HR2-02 的 VPIP SQL 靠这字段做过滤。

### 7.5 Access Control

```python
# storage/access_control.py

class PublicLogReader:
    """
    HR2-06: 公共读取器，无任何 private 文件依赖。
    可独立用于"已发布的开放数据集"场景——仅 public_replay.jsonl 存在即可。
    """
    def __init__(self, session_dir: Path):
        self._public_path = session_dir / "public_replay.jsonl"
        if not self._public_path.exists():
            raise FileNotFoundError(
                f"Public replay not found at {self._public_path}. "
                f"This reader only requires public_replay.jsonl; canonical_private is not needed."
            )
    
    def iter_events(self) -> Iterator[dict]:
        with open(self._public_path) as f:
            for line in f:
                yield json.loads(line)

class PrivateLogReader:
    """
    带 access token 的读取器，可读 canonical_private + agent_view_snapshots + public_replay。
    只应在 analysis notebook / admin tool 里使用。
    不继承 PublicLogReader（避免因"要求 private 文件存在"间接破坏 public 路径）。
    """
    def __init__(self, session_dir: Path, access_token: str):
        require_private_access(access_token)
        self._session_dir = session_dir
        self._private_path = session_dir / "canonical_private.jsonl"
        self._snapshots_path = session_dir / "agent_view_snapshots.jsonl"
        self._public_path = session_dir / "public_replay.jsonl"
        for p in (self._private_path, self._snapshots_path):
            if not p.exists():
                raise FileNotFoundError(f"Private session file missing: {p}")
    
    def iter_private_hands(self) -> Iterator[dict]:
        with open(self._private_path) as f:
            for line in f:
                yield json.loads(line)
    
    def iter_snapshots(self) -> Iterator[dict]:
        with open(self._snapshots_path) as f:
            for line in f:
                yield json.loads(line)
    
    def public_reader(self) -> PublicLogReader:
        return PublicLogReader(self._session_dir)
```

### 7.6 meta.json

```json
{
  "session_id": "session_...",
  "version": 2,
  "schema_version": "v2.0",
  "started_at": "...",
  "ended_at": "...",
  "total_hands_played": 1000,
  "planned_hands": 1000,
  "git_commit": "abc123...",
  "prompt_profile_version": "default-v2",
  "provider_capabilities": {
    "1": {"reasoning_kinds_observed": ["thinking_block", "encrypted"], "seed_supported": false},
    "2": {"reasoning_kinds_observed": ["summary"], "seed_supported": true},
    ...
  },
  "chip_pnl": {"1": -1460, "2": 1200, "3": 310, "4": -520, "5": 890, "6": -420},
  "retry_summary_per_seat": {              // ← BR2-05: 四类独立计数
    "1": {
      "total_turns": 1543,
      "api_retry_count": 4,
      "illegal_action_retry_count": 12,
      "no_tool_retry_count": 3,
      "tool_usage_error_count": 7,
      "default_action_fallback_count": 1,
      "turn_timeout_exceeded_count": 0
    }
  },
  "tool_usage_summary": {
    "1": {
      "total_utility_calls": 3201,
      "avg_per_turn": 2.07,
      "calls_by_name": {"pot_odds": 1543, "hand_equity_vs_ranges": 1234, "spr": 424}
    }
  },
  "censored_hands_count": 3,               // ← BR2-01: API error 导致的 invalid hands 数（final_action=None 的）
  "censored_hand_ids": [218, 537, 891],    // 明示哪些 hand 被 censor
  "total_tokens": {"1": {"prompt": 4500000, "completion": 1200000, "reasoning": 800000}},
  "estimated_cost_breakdown": {            // ← HR2-01: 按 pricing matrix 实算
    "1": {"input_usd": 15.40, "output_usd": 85.20, "total_usd": 100.60, "pricing_snapshot_id": "pricing_v1"}
  },
  "session_wall_time_sec": 19843,
  "seat_assignment": {"1": "Claude_A", "2": "GPT_A", "3": "Gemini_A", "4": "Claude_B", "5": "GPT_B", "6": "Gemini_B"},
  "initial_button_seat": 3,                // ← HR2-05: 本 session 的 initial button
  "seat_permutation_id": "balanced_6session_row_3"   // 6-session balanced set 中本 session 的 id
}
```

### 7.7 PHH Exporter（新，S-05）

```python
# storage/phh_exporter.py

from pathlib import Path

def export_session_to_phh(session_dir: Path, out_dir: Path) -> None:
    """
    Convert canonical_private.jsonl → 一个 .phh 文件每手。
    
    PHH (Poker Hand History) 是标准化格式 (phh.readthedocs.io)。
    Exporter 仅包含纯 poker hand history——不含 LLM iterations / reasoning / tool calls。
    那部分 metadata 保留在 agent_view_snapshots.jsonl。
    
    作为测试项：round-trip test 确保 export 后再 parse 得到一致 hand state。
    """
    ...
```

---

## 8. 存储层

### 8.1 写路径：Batch flush（H-10）

```python
# storage/jsonl_writer.py

class BatchedJsonlWriter:
    """
    内存 buffer + 定期 flush。
    保证：
      - 每 BATCH_SIZE 条 event 或 FLUSH_INTERVAL_MS 后 fsync
      - SIGTERM / atexit 时 drain buffer 并 fsync
      - crash 最多丢最近一个 batch（<= BATCH_SIZE 条）
    """
    BATCH_SIZE = 10
    FLUSH_INTERVAL_MS = 200
    
    def __init__(self, path: Path):
        self._path = path
        self._buffer: list[str] = []
        self._f = open(path, "a")
        self._last_flush = time.monotonic_ns()
        atexit.register(self._drain)
        signal.signal(signal.SIGTERM, lambda *a: self._drain())
    
    def write(self, record: dict) -> None:
        self._buffer.append(json.dumps(record))
        if len(self._buffer) >= self.BATCH_SIZE:
            self._flush()
        else:
            self._maybe_time_flush()
    
    def _flush(self) -> None:
        if not self._buffer: return
        self._f.write("\n".join(self._buffer) + "\n")
        self._f.flush()
        os.fsync(self._f.fileno())
        self._buffer.clear()
        self._last_flush = time.monotonic_ns()
    
    def _drain(self) -> None:
        self._flush()
        self._f.close()
```

**重要 checkpoint**：每手结束（`hand_ended` event）时强制 `flush()`，保证 hand 级粒度的 durability。

### 8.2 查询路径：DuckDB 白名单路径 + SQL literal escaping（H-11 / PP-07）

**PP-07 澄清**：DuckDB 的 `read_json_auto(...)` table function 的路径参数**不是标准 SQL 参数化绑定点**（DuckDB 的 prepared statement 不支持把 table function 的字符串参数替换为 `?` placeholder）。实施阶段只保留**单一**方案：**白名单路径 + SQL literal escaping**。

```python
# storage/duckdb_query.py

RUNS_ROOT = Path("runs").resolve()

def safe_json_source(path: Path) -> str:
    """
    返回安全嵌入 DuckDB SQL 的字符串字面量（含引号和 escape）。
    
    防御两条：
      1. 白名单：path 必须在受信 runs_root 子树内（resolve 后前缀校验 + 边界判断）
      2. Escape：DuckDB 字符串字面量用 '...', 内部单引号 double 成 ''
    """
    abs_path = path.resolve()
    try:
        abs_path.relative_to(RUNS_ROOT)  # 抛 ValueError 如果不在 runs_root 子树
    except ValueError:
        raise ValueError(f"Path {abs_path} not under trusted runs root {RUNS_ROOT}")
    
    # DuckDB 字符串 literal 约定：单引号包围，内部单引号 double
    p = str(abs_path).replace("'", "''")
    return f"'{p}'"

def open_session(session_dir: Path, access_token: str | None = None):
    con = duckdb.connect(":memory:")
    public_src = safe_json_source(session_dir / "public_replay.jsonl")
    con.sql(f"CREATE VIEW public_events AS SELECT * FROM read_json_auto({public_src});")
    
    if access_token and is_private_access_ok(access_token):
        private_src = safe_json_source(session_dir / "canonical_private.jsonl")
        snapshots_src = safe_json_source(session_dir / "agent_view_snapshots.jsonl")
        con.sql(f"CREATE VIEW hands AS SELECT * FROM read_json_auto({private_src});")
        con.sql(f"CREATE VIEW actions AS SELECT * FROM read_json_auto({snapshots_src});")
    
    return con
```

**专项测试**（§12.1 加入 unit 层）：

```python
# tests/unit/test_safe_json_source.py

def test_accepts_paths_under_runs_root(tmp_path, monkeypatch):
    monkeypatch.setattr("storage.duckdb_query.RUNS_ROOT", tmp_path)
    session_dir = tmp_path / "session_2026-04-23_a8f3b2"
    session_dir.mkdir()
    p = session_dir / "public_replay.jsonl"
    p.touch()
    result = safe_json_source(p)
    assert str(p) in result
    assert result.startswith("'") and result.endswith("'")

def test_rejects_paths_outside_runs_root(tmp_path, monkeypatch):
    monkeypatch.setattr("storage.duckdb_query.RUNS_ROOT", tmp_path / "runs")
    outside = tmp_path / "elsewhere" / "evil.jsonl"
    outside.parent.mkdir(parents=True)
    outside.touch()
    with pytest.raises(ValueError, match="not under trusted runs root"):
        safe_json_source(outside)

def test_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr("storage.duckdb_query.RUNS_ROOT", tmp_path / "runs")
    traversal = tmp_path / "runs" / ".." / "etc" / "passwd"
    with pytest.raises(ValueError):
        safe_json_source(traversal)

def test_escapes_single_quotes_in_path(tmp_path, monkeypatch):
    monkeypatch.setattr("storage.duckdb_query.RUNS_ROOT", tmp_path)
    weird = tmp_path / "session_o'malley" / "public.jsonl"
    weird.parent.mkdir()
    weird.touch()
    result = safe_json_source(weird)
    # 单引号被 double，但字符串整体用外层单引号包住
    assert "''" in result
```

### 8.3 Corrected VPIP SQL（H-07 / HR2-02）

依赖字段（都在 `agent_view_snapshots.jsonl` 一行一 turn 的 schema 里）：
- `seat: int`
- `hand_id: int`
- `street: str`
- `final_action: {type: str, amount: int?}`
- `is_forced_blind: bool`  ← 写入时预计算，无 SQL UDF 依赖

```sql
-- VPIP: per-seat fraction of hands where player voluntarily put money in pot preflop.
-- "Voluntary" 排除强制盲注自动 post 的 case。
-- 同一 hand 同一 seat 若有多次 preflop action，只算一次（DISTINCT hand_id）。

WITH voluntary_preflop AS (
    SELECT DISTINCT seat, hand_id
    FROM actions
    WHERE street = 'preflop'
      AND is_forced_blind = false
      AND final_action.type IN ('call', 'raise_to', 'bet', 'all_in')
),
hands_played_per_seat AS (
    SELECT seat, COUNT(DISTINCT hand_id) AS n_hands
    FROM actions
    GROUP BY seat
)
SELECT
    h.seat,
    h.n_hands,
    COUNT(v.hand_id) * 1.0 / h.n_hands AS vpip_rate
FROM hands_played_per_seat h
LEFT JOIN voluntary_preflop v ON h.seat = v.seat
GROUP BY h.seat, h.n_hands
ORDER BY h.seat;
```

所用函数（`COUNT`, `COUNT(DISTINCT ...)`, `LEFT JOIN`）全部是标准 SQL/DuckDB 内置；**无 UDF 依赖**。

其他衍生指标（PFR、3bet%、AF、WTSD%）可按同模式在 `is_forced_blind` + `street` + `final_action.type` 的组合上派生；具体 SQL 在 `analysis/derived_metrics.sql` 中给出。

---

## 9. Event System

### 9.1 EventBus with channel control

```python
class EventBus:
    def __init__(self):
        self._public_subs: list[Callable] = []
        self._private_subs: list[Callable] = []  # 需要 access control
    
    async def publish_public(self, event: PublicEvent) -> None:
        for s in self._public_subs: await s(event)
    
    async def publish_private(self, event: PrivateEvent) -> None:
        for s in self._private_subs: await s(event)
    
    def subscribe_public(self, cb, token: str | None = None) -> None:
        self._public_subs.append(cb)
    
    def subscribe_private(self, cb, token: str) -> None:
        require_private_access(token)
        self._private_subs.append(cb)
```

Engine 发布 event 时**必须**按可见性分类：
- Hole card 相关 → `publish_private`
- Action / 公共牌 → `publish_public`

### 9.2 WebSocket Protocol

**HR2-07**：token **不走 URL query string**（会进 server log、浏览器历史、日志聚合系统），改为 first-message auth handshake。

**URL**：`/ws/session/{session_id}?mode=<spectator|replay|player>&seat=<n>`
（无 token，无任何 secret 字段）

**Handshake 协议**：

```
Client → Server (TCP/WS established) → 
  Client 发第一条 message，必须是 auth 对象：
    {"type": "auth", "mode": "replay", "token": "<opaque>", "seat": null}
  
Server:
  - mode=spectator: 忽略 token 字段（可 null），即刻 accept，开始推 public events
  - mode=player&seat=N: 验证 token；合法则订阅 public + seat=N 的 private；否则关闭连接
  - mode=replay: 验证 token（若提供）；合法 → private 可读；无效/缺失 → 仅 public
  
  验证结果通过 server → client 的 ack message 传达：
    {"type": "auth_ok", "channels": ["public", "seat_3_private"], "session_started_at": "..."}
    或
    {"type": "auth_error", "reason": "invalid_token"} + close(1008)
  
  auth_ok 之前，server 不推送任何其他 message。
```

**Token 放到 subprotocol header** 作为 fallback 方案（WebSocket 握手 `Sec-WebSocket-Protocol: <token>`），但 first-message handshake 是推荐主路径。

- `spectator`：只 public channel，无需 token
- `replay`：首条 auth message 带 token，验证后可访问 private
- `player&seat=N`：首条 auth message 带 token + seat 断言；public + 仅 seat N 的 private events

**绝不**在 URL query 里接收 token。Server 端对 URL query 里的 `token` 参数应记 warning 并拒绝连接，告知"使用 first-message auth"。

---

## 10. Web UI

（技术栈与 v1 相同：React + Vite + Tailwind + shadcn/ui + TanStack Query）

关键变化：
- 默认从 `public_replay.jsonl` / public WebSocket 读；**不读** canonical_private
- Replay 模式有"揭秘模式"开关，需本地 token 才能看全部 hole cards（仅 admin/analyst 用）
- Reasoning panel 显示每 iteration 的 `reasoning_artifact.kind` 标签（`raw`/`summary`/`thinking_block`/`encrypted`/`redacted`/`unavailable`），让观察者明白数据的 provenance

---

## 11. 可复现性（v2 分层承诺）

### 11.1 严格可复现（Engine + Prompt 层）

- **Deck shuffle**：`rng_seed` 100% 控制，`derive_deck_seed(rng_seed, hand_id)`
- **Button rotation**：deterministic
- **Auto-rebuy**：deterministic
- **Legal action computation**：deterministic（PokerKit 是 pure function）
- **Prompt 构造**：给定 prompt_profile + view，字符串输出 deterministic
- **Tool 调用**：utility tool 给定输入和 seed 输出 deterministic（equity 有 seed）

### 11.2 Best-effort 可复现（LLM 决策层）

| Provider | seed 支持现状 |
|---|---|
| Anthropic | 不支持 seed |
| OpenAI | `seed` 参数存在但标 **best-effort**（fingerprint 返回），Chat 某些 param 已 deprecated |
| Gemini | 部分模型支持，未文档化稳定 |
| DeepSeek | 支持 seed（OpenAI 兼容接口） |

**实际做法**：
- 支持 seed 的 provider：传入 per-agent seed
- 不支持的：`seed=null` 记录
- 不承诺"重跑 session 复现 LLM 决策"，只承诺 "重跑可得到**同一 prompt 的**一次 API 调用，其分布与原始 session 来自同一 provider"

### 11.3 Session 自证（Artifact Chain）

每 session 保存：
- `config.yaml`（全部配置，含 model versions、prompt_profile、seeds）
- `prompts/`（实际使用的 prompt 文件）
- `meta.json.git_commit`
- `meta.json.provider_capabilities`（记录每家当时观测到的 reasoning_kinds 分布 + seed 是否真生效）

复现脚本：
```bash
# 严格复现 engine + prompt：
git checkout <commit>
python -m llm_poker_arena.replay_deterministic --session-dir runs/session_.../

# 重跑 LLM 决策（不保证结果一致）：
python -m llm_poker_arena.rerun_llm --session-dir runs/session_.../ --n-repeats 3
```

---

## 12. 测试策略

### 12.1 测试分层

| 层 | 工具 | 目的 |
|---|---|---|
| Unit | pytest | 单函数 / 单类 |
| Property | Hypothesis | 不变量（筹码 / 牌 / side pot / reopen） |
| Differential | pytest | 我们的适配层输出 vs PokerKit 直接查询 一致 |
| Fuzz | atheris + custom | range parser / tool input 鲁棒性 |
| Red-team | 手工 + 自动化 | 防作弊、prompt injection、log access control |
| Integration | pytest-asyncio + mock LLM | 端到端 session |
| PHH export | pytest | Round-trip |
| Live pilot | 真实 API | 校准 |

### 12.2 Differential Tests（新，S-02）

对 legal action computation 做差分：

```python
@given(random_hand_state())
def test_legal_action_set_matches_pokerkit_directly(state):
    our_legal = CanonicalState(...)._to_legal_action_set(state)
    pokerkit_can = {
        "fold": state.can_fold(),
        "check_or_call": state.can_check_or_call(),
        "complete_bet_or_raise_to": state.can_complete_bet_or_raise_to(),
    }
    # 我们的 tool set 映射回 PokerKit 的 can_* 应一致
    assert map_our_tools_to_pokerkit_predicates(our_legal) == pokerkit_can
```

### 12.3 Property Tests（扩充）

- 筹码守恒（含 side pots）
- 52 牌守恒（dealt + deck + burn + muck = 52）
- Hole cards 互斥
- **Min-raise reopening**：短 all-in 后，已行动玩家 `can_complete_bet_or_raise_to()` 必须 False
- **Auto-rebuy**：每手开始 stack == starting_stack
- **PlayerView 投影纯粹性**：同一 canonical state 投影两次结果相同（无副作用）

### 12.4 PHH Exporter Test

```python
def test_phh_roundtrip():
    # 1. 从 canonical_private 导 PHH
    export_session_to_phh(test_session_dir, tmp_phh_dir)
    
    # 2. 读 PHH，reconstruct hand
    for phh_file in tmp_phh_dir.iterdir():
        reconstructed = parse_phh(phh_file)
        original = load_canonical_hand(phh_file.stem, test_session_dir)
        
        # 3. 公共字段应完全一致（hole cards、actions、showdown、pnl）
        assert_equivalent_hands(reconstructed, original)
```

### 12.5 Red-team Suite（扩充，H-08）

**传统信息泄漏**：
- `test_playerview_dto_dump_excludes_other_hole_cards`：序列化后字节级扫描
- `test_future_community_not_in_preflop_view`

**Prompt injection**：
- `test_prompt_injection_via_opponent_label` — label 字段含 "Ignore all prior instructions"
- `test_prompt_injection_via_stats_render` — stats 某字段含 control sequence
- `test_prompt_injection_does_not_cause_info_leak` — injection agent 的回答里不含他人私有信息

**Tool 反推**：
- `test_hand_equity_rejects_concrete_cards`
- `test_hand_equity_rejects_mismatched_seat_keys`
- `test_get_opponent_stats_rejects_self_seat`

**Log 访问控制**：
- `test_public_log_reader_cannot_open_canonical_private` — `PublicReplayReader` 试图打开 private 文件应 raise
- `test_websocket_spectator_does_not_receive_private_events`
- `test_websocket_player_seat_3_receives_only_seat_3_private_events`

**状态声明篡改**：
- `test_reasoning_claim_ignored_when_tool_call_differs`

**BR2-07: Anthropic thinking block 回传**（provider-specific 测试）：
- `test_anthropic_thinking_block_byte_identical_on_next_turn`：
  1. Mock Anthropic response 含 `thinking` + `redacted_thinking` + `tool_use` 三类 block
  2. 过一遍 `AnthropicProvider.serialize_assistant_turn(response)`
  3. 断言返回的 `blocks` 列表的每个 dict 与原始 response 对应 block **字段完全一致**（`json.dumps(sort_keys=True)` 比较）
  4. 断言 `signature` / `data` / 任何 opaque 字段未被修改
- `test_openai_reasoning_summary_passthrough`：OpenAI 的 reasoning summary 字段在 serialize 后仍能被下一次请求正确引用（provider 要求相应 handling）

**BR2-01: API error hand censoring**：
- `test_api_error_does_not_apply_fallback_action`：Mock provider raise timeout 两次；断言 `decision.final_action is None`；断言 Session 没调 `apply_action`；断言 hand 被标 `invalid_api_error`
- `test_total_turn_timeout_enforced`：Mock provider 每次 `await asyncio.sleep(200)`；断言 `total_turn_timeout_sec=180` 触发后 `decision.turn_timeout_exceeded is True` 且 hand 被 censor

**BR2-05: 四类 retry counter 独立性**：
- `test_api_retry_does_not_consume_illegal_budget`：先让 provider timeout 一次（消耗 api_retry），然后正常返回非法 action 两次（消耗 illegal_action_retry 两次）；断言流程未因"总 retry 超限"早退；api_retry_count=1, illegal_action_retry_count=1 (capped at MAX), default_fallback=True

### 12.6 Mock LLM Integration Test

端到端 session 用 `MockLLMProvider`（scripted responses）跑 10 手完整流程，断言：
- No audit failure
- `canonical_private.jsonl` 有完整结构
- `public_replay.jsonl` 无任何 hole cards 字段（showdown 揭示的除外）
- `agent_view_snapshots.jsonl` 有 iterations
- `meta.json.chip_pnl` 求和为 0（零和博弈守恒）

---

## 13. 技术栈

### 13.1 Python 后端

| 包 | 用途 |
|---|---|
| `pokerkit` | NLHE 底层，**canonical state** |
| `fastapi` | HTTP + WebSocket |
| `uvicorn` | ASGI |
| `pydantic` ≥ 2.0 | DTO 校验（P2 边界） |
| `duckdb` | 查询 |
| `anthropic` | Anthropic SDK |
| `openai` | OpenAI（也可连 DeepSeek） |
| `google-generativeai` | Gemini |
| `litellm` | fallback adapter |
| `eval7` | equity 计算主 backend |
| `treys` | equity 计算 fallback |
| `hypothesis` | property tests |
| `atheris` | fuzz |
| `pytest`, `pytest-asyncio` | test runner |
| `jinja2` | prompt 模板 |
| `pyyaml` | config |
| `rich` | CLI 美化 |
| `python-dotenv` | API key |
| `phh` / 自写 parser | PHH 标准 |

Python ≥ 3.11（PokerKit 要求）。

### 13.2 前端

（同 v1：React + Vite + Tailwind + shadcn/ui + TanStack Query + Zustand）

---

## 14. 项目目录结构（v2 修订）

```
llm-poker-arena/
├── README.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── requirements-dev.txt
│
├── docs/
│   └── superpowers/
│       ├── specs/
│       │   ├── 2026-04-23-llm-poker-arena-design.md        # v1 SUPERSEDED
│       │   └── 2026-04-23-llm-poker-arena-design-v2.md     # v2（本文件）
│       └── plans/
│
├── src/
│   └── llm_poker_arena/
│       ├── __init__.py
│       ├── engine/
│       │   ├── __init__.py                # 公开 API 白名单
│       │   ├── _internal/                 # ← 下划线：非公开
│       │   │   ├── __init__.py
│       │   │   ├── poker_state.py         # CanonicalState（包 PokerKit）
│       │   │   ├── audit.py
│       │   │   ├── transition.py
│       │   │   └── rebuy.py               # auto-rebuy 逻辑
│       │   ├── projections.py             # build_player_view / public_view
│       │   ├── views.py                   # Pydantic DTO: PlayerView, PublicView, AgentSnapshot
│       │   ├── legal_actions.py           # LegalActionSet + default_safe_action
│       │   └── events.py                  # Event types
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── action_tools.py
│       │   ├── utility_tools.py
│       │   ├── tool_registry.py
│       │   ├── tool_runner.py
│       │   ├── range_parser.py            # RangeNotationParser
│       │   └── equity_backend/
│       │       ├── __init__.py
│       │       ├── base.py                # EquityBackend ABC + EquityResult
│       │       ├── eval7_backend.py
│       │       └── treys_backend.py
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py                    # Agent ABC
│       │   ├── llm_agent.py               # Bounded ReAct
│       │   ├── random_agent.py
│       │   ├── rule_based_agent.py        # ← 新：baseline
│       │   ├── human_agent.py
│       │   └── providers/
│       │       ├── __init__.py
│       │       ├── base.py                # LLMProvider + ProviderCapability
│       │       ├── reasoning_artifact.py  # ReasoningArtifact + Kind
│       │       ├── anthropic_provider.py
│       │       ├── openai_provider.py
│       │       ├── gemini_provider.py
│       │       ├── deepseek_provider.py
│       │       └── litellm_provider.py
│       ├── prompts/
│       │   ├── __init__.py
│       │   ├── builder.py                 # 接受 **serialized dict**，不接 PlayerView 对象
│       │   ├── templates/
│       │   │   ├── system_prompt.md.jinja
│       │   │   └── user_prompt.md.jinja
│       │   └── profiles/
│       │       └── default-v2.yaml
│       ├── stats/
│       │   ├── __init__.py
│       │   └── opponent_stats.py
│       ├── session/
│       │   ├── __init__.py
│       │   ├── session.py
│       │   ├── config.py
│       │   ├── orchestrator.py
│       │   └── seat_permutation.py        # ← 新：balanced assignments
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── batched_writer.py          # ← 新：batch flush
│       │   ├── canonical_writer.py
│       │   ├── public_writer.py
│       │   ├── snapshot_writer.py
│       │   ├── access_control.py          # ← 新：LogReader / PrivateLogReader
│       │   ├── duckdb_query.py
│       │   └── phh_exporter.py            # ← 新
│       ├── events/
│       │   ├── __init__.py
│       │   ├── event_bus.py
│       │   └── event_types.py
│       ├── api/
│       │   ├── main.py
│       │   ├── routes.py
│       │   └── websocket.py
│       └── cli/
│           ├── run_session.py
│           ├── replay.py
│           ├── replay_deterministic.py    # ← 新
│           ├── rerun_llm.py               # ← 新
│           └── analyze.py
│
├── tests/
│   ├── unit/
│   │   ├── test_playerview_dto_isolation.py
│   │   ├── test_default_safe_action.py    # ← 新
│   │   ├── test_range_parser.py
│   │   ├── test_equity_backend.py
│   │   ├── test_tool_runner.py
│   │   ├── test_batch_writer.py           # ← 新
│   │   └── test_access_control.py         # ← 新
│   ├── property/
│   │   ├── test_chip_conservation.py
│   │   ├── test_card_conservation.py
│   │   ├── test_min_raise_reopen.py       # ← 新
│   │   ├── test_auto_rebuy.py             # ← 新
│   │   └── test_playerview_projection_pure.py  # ← 新
│   ├── differential/                       # ← 新层
│   │   └── test_legal_actions_vs_pokerkit.py
│   ├── fuzz/
│   │   ├── test_range_parser_fuzz.py
│   │   └── test_tool_input_fuzz.py
│   ├── redteam/
│   │   ├── test_prompt_injection.py
│   │   ├── test_log_access_control.py     # ← 新
│   │   └── test_websocket_channel_isolation.py  # ← 新
│   ├── roundtrip/
│   │   └── test_phh_export_roundtrip.py   # ← 新
│   └── integration/
│       └── test_full_session_mock.py
│
├── frontend/
│   └── ...  (同 v1)
│
├── configs/
│   ├── pricing_matrix.yaml                # ← 新（HR2-01）runtime pricing
│   ├── example_pilot.yaml
│   ├── example_baseline_b1_random.yaml
│   ├── example_baseline_b2_rule_based.yaml
│   ├── example_baseline_b3_llm_pure.yaml  # ← 新（HR2-04）no tools, no memory
│   ├── example_baseline_b4_llm_math.yaml  # math tools, no memory
│   └── example_baseline_b5_llm_math_stats.yaml  # math tools + stats memory
│
├── prompts/
│   ├── default-v2.yaml
│   ├── system_prompt.md
│   └── user_prompt.md.jinja
│
├── runs/
│   └── .gitkeep
│
└── scripts/
    ├── setup.sh
    ├── run_baseline_suite.sh              # ← 新
    └── analyze_session.py
```

---

## 15. 实验设计（v2 重构）

### 15.1 关键原则

- **控制变量**：每次主实验只变一个因素
- **统计 power**：认知到 1000 手不够做 winrate 稳健比较；用来看 action distribution / tool usage / CoT patterns
- **Seat permutation**：across-session，balanced；session 内仅 button rotation
- **API 稳定性 vs 策略**：API 错误单独统计，不混入策略分析
- **Provider capability aware**：reasoning artifact matrix 作为数据分组维度
- **Rationale required 作为 ablation 轴**

### 15.2 主实验矩阵（5 组 baseline，HR2-04）

HR2-04 澄清：v2 初版把 stats memory (β) 和 tool 能力耦合在 B3/B4 里，"LLM-no-tools" 并不纯。v2.1 拆为 **5 组**，让 tools 和 stats memory 成独立 ablation 轴。

| 实验 | Agent 构成 | tools | memory | rationale_required | 手数 | 目的 |
|---|---|---|---|---|---|---|
| **B1-Random** | 6 × RandomAgent | - | - | - | 1,998 (= 333 × 6) | 下界 baseline；engine 压测 |
| **B2-RuleBased** | 6 × RuleBasedAgent（简单 tight/aggressive bot） | - | - | - | 1,998 | 非 LLM 的 skill floor baseline |
| **B3-LLM-pure** | 3 模型 × 2 实例 | 关 | **关** | true | 1,500 (= 250 × 6) | 纯 LLM reasoning baseline（无工具无记忆） |
| **B4-LLM-math** | 3 模型 × 2 实例（与 B3 完全同阵容） | **开**（pot_odds / equity / spr） | 关 | true | 1,500 | 孤立 math tools 的效应（vs B3） |
| **B5-LLM-math-stats** | 3 模型 × 2 实例（同阵容） | 开 | **(β) 开（n≥30）** | true | 1,500 | 孤立 stats memory 的效应（vs B4） |

所有 5 组都跑 **至少 6 个 session**（满足 HR2-05 的跨 session 正交 permutation，见 §15.4）。

**Rationale ablation（附加）**：
- `B3'-LLM-pure-no-rationale`：B3 同配置但 `rationale_required=false`，跑 1 session，观察强制推理是否改变策略。

**可归因差异（实验设计的核心叙事）**：
- **B4 − B3** = math tools 的纯效应（stats memory 都关）
- **B5 − B4** = stats memory 的纯效应（给定有 tools）
- **B3 vs B2** = 前沿 LLM 相比 rule-based bot 是否有 skill advantage
- 若 B3 < B2：LLM 裸打不过简单 bot，这本身是一个发现

**后续 ablation backlog**（不进 v2.1 首版 main）：
- B6-LLM-stats-only：无 tools 但开 stats memory（完成 tools × memory 的 2×2 factorial）
- B7-LLM-math-HUD：B5 + HUD on-demand tool
- B8-LLM-math-HUD-no-autoinject：HUD 替代 (β)，解缠"信息呈现方式"与"信息内容"
- B9-tournament-mode
- B10-human-in-the-loop

### 15.3 分析产出

每次实验跑完后的标准分析：

1. **Chip P&L 分布**：per-agent net P&L 的直方图 + CI
2. **Action distribution by street**：fold/call/raise/check 频率
3. **VPIP / PFR / AF / 3bet% / WTSD%**：正确 SQL 算出的指标
4. **Utility calls per turn** 分布（仅 B4）
5. **Illegal retry rate / default fallback rate** by model
6. **Reasoning artifact coverage report**：
   - 每 provider 的 `reasoning_artifact.kind` 分布
   - stated reasoning 长度 distribution by provider
   - **不做** "native vs stated similarity" 分析，因为 native 可能不可得
7. **Seat position bias check**：固定 seat 的 P&L vs 预期（BTN > CO > HJ > UTG > BB > SB）
8. **PHH export round-trip integrity**：所有 hands 能成功 export
9. **Censored-hands breakdown**：API error 导致的 invalid hands 数量 by provider

### 15.4 Seat Permutation（B-11 / HR2-05）

**HR2-05** 澄清：seat assignment 与 initial button 位置是**两个独立的轴**，需要正交 balanced。

**设计原则**（三层正交）：
1. 跨 session，每个 agent 在每个**绝对座位**出现次数相等
2. 跨 session，**initial button** 起始位覆盖所有 6 个 seat 等次数
3. `config.num_hands` 必须为 **6 的倍数**（`Session.validate_config` 强制 assert），保证 session 内 button rotation 本身 balanced

**Hand count 约束**：

```python
def validate_config(config: SessionConfig) -> None:
    if config.num_hands % config.num_players != 0:
        raise ConfigError(
            f"num_hands ({config.num_hands}) must be a multiple of num_players "
            f"({config.num_players}) to balance button rotation within a session."
        )
```

对 6-max session：`num_hands ∈ {..., 1500 (=250×6), 1998 (=333×6), 2502 (=417×6), ...}`。

**Seat + Button 正交设计（6 sessions 最小完全 balanced）**：

6 个 agent slot（3 模型 × 2 实例）为 M1, M2, M3, M4, M5, M6（例：M1=Claude_A, M2=Claude_B, M3=GPT_A, ...）。

每 session 有两个维度：
- `seat_assignment: seat → agent_slot`（列向量，6 个位置 × 6 个 slot 的 Latin square）
- `initial_button_seat: int`（0..5，决定本 session button rotation 起点）

6 session 的 balanced 设计：

| Session | seat_assignment（seat 1..6） | initial_button |
|---|---|---|
| S1 | M1 M2 M3 M4 M5 M6 | 1 |
| S2 | M2 M3 M4 M5 M6 M1 | 2 |
| S3 | M3 M4 M5 M6 M1 M2 | 3 |
| S4 | M4 M5 M6 M1 M2 M3 | 4 |
| S5 | M5 M6 M1 M2 M3 M4 | 5 |
| S6 | M6 M1 M2 M3 M4 M5 | 6 |

验证：
- 每个 M_i 在每个 seat 恰好出现一次（Latin 行）✓
- 每个 seat 的 initial button 位置 {1..6} 完整出现一次 ✓
- Session 内 button rotation 遍历所有 6 seat（因为 num_hands 是 6 的倍数）✓

Session ≥ 12 时可用双重 Latin square 进一步平衡（seat × button 正交）。spec 先给 6-session 版本；更大规模时 `seat_permutation.py` 按 pyDOE/相关库生成。

**实现规范**（`engine/session/seat_permutation.py`）：
- 输入：`engine_seed: int`, `n_sessions: int`, `n_agents: int`, `n_seats: int`
- 输出：`list[SessionAssignment]`（每 session 的 `seat_assignment` + `initial_button_seat`）
- 跨调用 deterministic（同 `engine_seed` 同输出）
- 默认用上表（6 session）；更多 session 时扩展

### 15.5 Cost 预算（B-10 / HR2-01）

**HR2-01**：成本 **不硬编码**。spec 只给 per-turn token assumption 和公式；实际金额由 session 启动脚本按当前 provider pricing 计算并写入 `meta.json.estimated_cost_breakdown`。

#### 15.5.1 Token usage 假设（per turn，用于估算）

| 参数 | 假设值（conservative） |
|---|---|
| 每手平均 action turn 数 | ~15（6 seat × 3 street + 早期弃牌折减，pre-flop aggressive-aware） |
| Bounded ReAct 平均 API 调用 / turn | 2.5（B4/B5），1（B3） |
| API 调用 / 手（B4/B5） | ~37.5 |
| API 调用 / 手（B3） | ~15 |
| Prompt tokens / 调用（uncached） | ~1,500 |
| Prompt tokens / 调用（cache hit after hand 1） | ~500（system prompt cached） |
| Completion tokens / 调用 | ~500 |
| Reasoning tokens / 调用 | ~500（if provider 暴露 + bills 独立） |

#### 15.5.2 Runtime pricing matrix

```yaml
# configs/pricing_matrix.yaml（session 启动时加载；不写入 spec 的硬编码）
# 实际价格请以 provider 官网当日为准。以下字段名固定，值由用户 pin。
pricing_per_million_tokens:
  anthropic:
    "<opus_tier_frontier>":
      input_usd: null          # e.g. 5.0 at time of config
      output_usd: null         # e.g. 25.0
      cached_input_usd: null   # e.g. 0.5 (Anthropic prompt caching read)
    "<sonnet_tier>":
      input_usd: null
      output_usd: null
      cached_input_usd: null
  openai:
    "<reasoning_tier_frontier>":
      input_usd: null
      output_usd: null
      cached_input_usd: null
  google:
    "<gemini_pro_tier>":
      input_usd: null
      output_usd: null
      cached_input_usd: null
```

#### 15.5.3 估算公式

Session 启动脚本：

```python
def estimate_session_cost(
    config: SessionConfig,
    pricing: PricingMatrix,
    num_hands: int,
    api_calls_per_hand: float,
    prompt_tokens_cached: int,
    prompt_tokens_new: int,
    completion_tokens: int,
    reasoning_tokens: int,
) -> dict[str, float]:
    total = {}
    for agent in config.agents:
        price = pricing.resolve(agent.provider, agent.model_tier)
        if price.input_usd is None:
            total[agent.label] = None  # "pricing not pinned"; warn caller
            continue
        calls = num_hands * api_calls_per_hand / config.num_players  # per agent
        input_cost = calls * (
            prompt_tokens_cached * price.cached_input_usd / 1e6 +
            prompt_tokens_new * price.input_usd / 1e6
        )
        output_cost = calls * (completion_tokens + reasoning_tokens) * price.output_usd / 1e6
        total[agent.label] = input_cost + output_cost
    return total
```

#### 15.5.4 操作建议（不含硬编码金额）

1. **先跑 B1 + B2**（random / rule-based）——零 API 成本，先验证 engine 和 analysis 链路
2. **B3 先跑 1 session 小样本**（比如 600 手，仍 6 倍数）校准实际 token usage 与延迟 → 回填 `meta.json.actual_cost`
3. 根据 1-session 实测，决定是否跑完整 6-session balanced permutation
4. **混合 frontier + economy 模型**可大幅降低总成本：例如 3 agents 用 frontier tier，3 agents 用 economy tier
5. spec 不承诺绝对金额；任何"this experiment costs $X"的表述**必须**引用 `meta.json.actual_cost`，不得在 spec 内硬编码

### 15.6 API 错误处理（B-12）

```python
@dataclass
class HandOutcome:
    status: Literal["normal", "invalid_api_error", "invalid_audit_failure"]
    ...

# 分析层
def filter_valid_hands(hands: list[HandOutcome]) -> list[HandOutcome]:
    return [h for h in hands if h.status == "normal"]

def censored_hands_stats(hands) -> dict:
    return {
        "total": len(hands),
        "valid": sum(1 for h in hands if h.status == "normal"),
        "api_error": sum(1 for h in hands if h.status == "invalid_api_error"),
        "audit_failure": sum(1 for h in hands if h.status == "invalid_audit_failure"),
    }
```

**不把 API 错误当 fold**。标 invalid 后：
- P&L / winrate 计算只用 valid hands
- 同状态 (same deck_seed, same config) 可选地 replay
- Provider 稳定性作为独立 metric 上报

### 15.7 Timebank（H-15，前置）

每 turn / iteration 双层 timeout：

```yaml
# config.yaml (节选)
timeouts:
  per_iteration_sec: 60
  per_turn_total_sec: 180       # BR2-06: asyncio.wait_for 外层 hard 限
  backoff_initial_ms: 1000
  backoff_max_retries: 1        # api_retry_count 的上限
```

**超时路径（PP-06 修订，与 BR2-01 一致）**：

1. Per-iteration timeout 触发 → `asyncio.TimeoutError` 被捕获 → `api_retry_count += 1`
2. 若 `api_retry_count < MAX_API_RETRY` → sleep(backoff) → 重试同一步
3. 若 `api_retry_count ≥ MAX_API_RETRY` → 返回 `TurnDecisionResult(final_action=None, api_error=ApiErrorInfo(...), ...)`
4. Per-turn total timeout 触发（外层 `asyncio.wait_for(total_turn_timeout_sec)`） → 返回 `TurnDecisionResult(final_action=None, api_error=ApiErrorInfo(type="TotalTurnTimeout"), turn_timeout_exceeded=True, ...)`
5. Session orchestrator 检测 `final_action is None` → `mark_hand_censored(reason="invalid_api_error")` → 跳过当前 hand，**绝不** 执行 `default_safe_action`

**关键约束**：API / timeout 类错误永远**不映射到**任何扑克动作。API 不可达时不知道"这个 seat 本来会怎么打"，强行 fallback 会把 provider 稳定性混进策略分析。整手 censor 之后从 winrate 统计中剥离，单独以 `censored_hands_count` / `timeout_count` / `api_error_count_by_provider` 报告。

实验层面：记录每 provider 的 `mean_wall_time_ms_per_turn`、`per_iteration_timeout_count`、`per_turn_timeout_count`、`api_retry_triggered_count`，作为稳定性/延迟的比较维度。

---

## 16. 实施阶段

### 16.1 MVP 实施顺序（权威关键路径）

v2.1.1 采纳用户 review 给出的 12 步 MVP 顺序作为 `writing-plans` 产出 Phase 1 计划的权威依据。

**关键路径原则**：
- PokerKit deterministic hand → random/rule-based engine → logs/analysis → mock ReAct → real providers
- **不要先做 UI**，不要先接真实 LLM
- 每一 MVP step 必须有明确的"已完成"判据（可跑的 smoke test + 通过的单元测试）

**12 步路线**：

| # | MVP Step | 关键交付 | 完成判据 |
|---|---|---|---|
| 1 | **Repo / Tooling** | `pyproject.toml` / 包结构 / ruff+pytest+hypothesis / CI 基础命令 | 空测试套件能 `pytest` 跑通；ruff/mypy 无错误；未接 PokerKit |
| 2 | **Card / Config / DTO** | `SessionConfig` / `HandContext` / `PlayerView` / `PublicView` / `AgentSnapshot` / `SessionParamsView` | Pydantic 序列化白名单 + private 信息隔离单元测试通过；无 engine 逻辑 |
| 3 | **PokerKit Deterministic Hand** | `CanonicalState` + `build_deterministic_deck` + 正确 button/blind rotation + 手动 deal hole/flop/turn/river | 单一 hand 可复现：固定 seed + button_seat → 相同 hole cards + community 序列 |
| 4 | **Action Engine** | `RandomAgent` + 合法动作投影 + `apply_action` + `default_safe_action` + 两套 audit | 1,000 手 random 无 crash、无 audit failure |
| 5 | **Edge Case Coverage** | side pot / all-in / short all-in reopen / min raise 的 property + differential tests | 50,000 random sequences 无 audit failure；differential test 对 PokerKit 原生 `can_*` 全部一致 |
| 6 | **Storage (3 Layer)** | 三层 JSONL writer（canonical_private / public_replay / agent_view_snapshots）+ batch flush | Mock decisions 下跑 1,000 手；public_replay 无 private 信息泄漏（property test）；crash at arbitrary point 最多丢最后 10 条 |
| 7 | **Analysis (DuckDB)** | DuckDB query layer + `safe_json_source` + VPIP/PFR/action_distribution SQL | B1 Random 和 B2 RuleBased 可完整跑 + 出图；`is_forced_blind=false` 路径正常执行 |
| 8 | **Tool System** | RangeNotationParser + pot_odds + spr + seeded hand_equity_vs_ranges + EquityBackend | 不接真实 LLM；RuleBased/MockAgent 能正确调用 utility tools；fuzz tests 全过 |
| 9 | **Mock ReAct Loop** | `LLMAgent.decide` 完整实现 + `MockLLMProvider` | 四类 retry counter + `final_action=None` censor + total_turn_timeout 全部覆盖 integration test |
| 10 | **First Real Provider** | 接 OpenAI 或 Anthropic 一家（先选一） + `probe()` + `serialize_assistant_turn()` + reasoning artifact 记录 + 第二家 | 两家 provider 都能跑通 pilot 前的 smoke session；`meta.json.provider_capabilities` 写入正确 |
| 11 | **Pilot Session** | 100 手 same-model 或低成本模型 session（跑 B3-LLM-pure 小样本） | 成本、日志完整性、DuckDB 查询、censored hand 记录、artifact coverage 全部校验 |
| 12 | **UI** | Spectator（仅 public_replay）→ replay → reasoning panel | Web UI 可观战已完成 session；private replay 和 reasoning panel 在 spectator 稳定后增加 |

**关键里程碑检查点**：
- 完成 **MVP 1-5** 后：Phase 1 "engine + 测试"部分收尾，随时可开始 Phase 2
- 完成 **MVP 6-7** 后：B1/B2 可完整跑完并出图，不花任何 API 钱
- 完成 **MVP 8-9** 后：可以开始讨论是否跑 pilot 前 benchmark
- 完成 **MVP 10-11** 后：pilot 完成，成本和数据链路实测校准，再决定主实验规模
- 完成 **MVP 12**：全项目可 demo

### 16.2 Phase 映射（粗粒度时间估计）

| Phase | 包含 MVP Steps | 时间 | 目标 |
|---|---|---|---|
| **Phase 1** | MVP 1-5 | **~2 周** | Engine + PokerKit 适配 + 防作弊骨架 + 完整测试套件（单元 / property / differential / fuzz / red-team）。**不接 LLM**。 |
| **Phase 2** | MVP 6-7 | ~1.5 周 | 3 层存储 + DuckDB 查询层 + B1/B2 可完整跑 + PHH exporter + 首份分析图表 |
| **Phase 3** | MVP 8-9 | ~1.5 周 | Tool system + Mock ReAct + 完整 retry/timeout 覆盖；所有 integration tests 用 MockLLMProvider 跑通 |
| **Phase 4** | MVP 10-11 | ~2 周 | 接入 2 家真实 provider + probe + serialize_assistant_turn + reasoning artifact；Pilot 100 手跑完 |
| **Phase 5** | MVP 12 前半 + 5-baseline 主实验 | ~2.5 周 | 5 组 baseline（含 6-session balanced seat/button permutation）+ 分析 notebook + 图表产出 |
| **Phase 6** | MVP 12 后半 | ~1.5 周 | Web UI（spectator / replay / reasoning panel，标注 artifact kind） |
| **Phase 7+**（可选 backlog） | - | - | HUD-vs-autoinject ablation / tournament mode / human-in-loop / self-notes / 更多 provider |

**总计 Phase 1-6 约 11 周**（v2.1 里是 9-10 周；v2.1.1 按 MVP 顺序重排并把 UI 后置，总量稍增但关键路径缩短）。

---

## 17. Open Questions / Backlog

v1 的 Open Questions 中，大部分已在 v2 解决。剩余：

1. **PHH 元数据扩展**：未来是否为 LLM metadata 定义 PHH 扩展 section？保留 observation，不阻塞。
2. **跨 session 记忆**：目前完全隔离；未来 agent 是否"记得"之前的对手？研究感兴趣但复杂度高。
3. **Rake / 特殊规则**：一期 rake=0。未来可研究 rake 对策略的影响。
4. **部署形态**：一期本地。UI 公网访问需求出现再上云。
5. **模型版本漂移**：provider 升级版本时如何保持跨时段实验可比？—— 锁 date-pinned version + re-run smoke test。

---

## 18. 术语表

（同 v1，新增）

- **Canonical state**: PokerKit.State，本系统唯一游戏状态真相
- **PlayerView / PublicView / AgentSnapshot**: read-only 投影 DTO
- **ReasoningArtifactKind**: raw / summary / thinking_block / encrypted / redacted / unavailable
- **Default safe action**: 非法/超时 fallback 的合法动作（check if legal, else fold）
- **Censored hand**: API 错误导致的 invalid hand，不进 winrate 统计
- **Balanced seat permutation**: Latin-square 跨 session seat 分配，保证每模型每位置次数相等
- **PHH**: Poker Hand History 标准格式（phh.readthedocs.io）
- **Bounded ReAct**: K utility calls + 1 forced action step 的 agent 循环

---

## 19. 参考文献

- [PokerKit (arxiv 2308.07327)](https://arxiv.org/abs/2308.07327)
- [PokerKit GitHub](https://github.com/uoftcprg/pokerkit)
- [PokerKit PyPI](https://pypi.org/project/pokerkit/)
- [PokerBench (arxiv 2501.08328, AAAI 2025)](https://arxiv.org/abs/2501.08328)
- [PokerGPT (arxiv 2401.06781)](https://arxiv.org/abs/2401.06781)
- [ToolPoker (arxiv 2602.00528)](https://arxiv.org/abs/2602.00528)
- [Husky Hold'em (OpenReview)](https://openreview.net/forum?id=jARUSddVIB)
- [Game Reasoning Arena (arxiv 2508.03368)](https://arxiv.org/abs/2508.03368)
- [ReAct (arxiv 2210.03629)](https://arxiv.org/abs/2210.03629)
- [Poker TDA Rules](https://www.pokertda.com/view-poker-tda-rules/)
- [Robert's Rules of Poker](https://www.briggsoft.com/docs/pmavens/Rules_Roberts.htm)
- [OpenAI Reasoning docs](https://platform.openai.com/docs/guides/reasoning)
- [Anthropic Extended Thinking docs](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)
- [PHH spec](https://phh.readthedocs.io/en/stable/spec.html)
- [eval7 (github)](https://github.com/julianandrews/eval7)
- [treys (github)](https://github.com/ihendley/treys)

---

## 20. 版本历史

| Version | Date | Notes |
|---|---|---|
| 0.1 (v1) | 2026-04-23 | Brainstorming 产出初稿。SUPERSEDED。 |
| 2.0 (v2) | 2026-04-23 | 整合用户技术 review（12 阻断 + 16 高风险 + 5 建议）。所有决策以 v2 为准。 |
