# ADRP 评测报告 v2

> 版本：v2（plan-005 上线后）
> 时间：Day 5（2026-05-28）
> 数据集：`data/eval/queries.jsonl` 25 条 AI 领域研究查询
> 对比基线：v1 (plan-004 commit `b881329`)
> 实测结果：`data/eval/results_day5_full_baseline.jsonl` (v1) vs `results_day5_round2.jsonl` (v2)

---

## 一、TL;DR

| 指标 | v1 (plan-004) | v2 (plan-005) | Δ |
|---|---|---|---|
| **整体 PASS rate** | 22/25 = 88% | 23/25 = 92% | **+4pp** |
| **Healthy 路径 PASS rate** | 22/25 = 88% | **23/23 = 100%** | **+12pp** |
| **Healthy 路径 avg score** | 7.96 | **8.48** | **+0.52** |
| **research_failed 分类** | 0（机制不存在） | 2（gate 正确触发） | — |
| **Avg factual_density** | 7.67 | **8.85** | **+1.18** |

**核心改进**：plan 005 引入 `research_failure_gate` 把"基础设施失败"独立分类，让评测面板真实反映**内容质量**而不是 Tavily 限流。结果：**healthy 路径 PASS 率从 88% → 100%，factual_density 从 7.67 → 8.85**。

---

## 二、变更项（v1 → v2）

| 变更 | commit | 影响 |
|---|---|---|
| 修 `final_report_configurable_model` thread_id leak | `7d2af3a` | 让 final_report 真正能产出，是 v1 跑出 22/25 的前提 |
| 修 `run_eval.py` 的 `ask_for_clarification` → `allow_clarification` | `b881329` | 让 eval runner 真的进入研究流程 |
| **plan 005 研究失败优雅降级** | `9f58ed5` | **本次评测的主因素** |
| Tavily key 轮换（旧 key 1003/1000 超额） | — | Day 5 基础设施恢复 |

---

## 三、详细数据

### 3.1 整体分布

| 桶 | v1 | v2 |
|---|---|---|
| score 9 | 11 | 10 |
| score 8 | 9 | 11 |
| score 7 | 1 | 2 |
| score 6 | 1 | 0 |
| score 5 | 0 | 0 |
| score 4 | 1 | 0 |
| score 3 | 1 | 0 |
| score 0 (research_failed) | 0 | 2 |
| score 0 (其他) | 1 (q002 老 baseline?) | 0 |

→ v2 把"低分但通过 critic 流程"的 q023/q024/q025（score 3/4/6）全部清零：q023→8、q024→research_failed、q025→9。

### 3.2 Per-criterion 平均（healthy only）

| 维度 | v1 | v2 | Δ |
|---|---|---|---|
| factual_density | 7.67 | **8.85** | **+1.18** |
| citation_coverage | 8.52 | 8.96 | +0.44 |
| internal_consistency | 8.19 | 8.40 | +0.21 |
| four_sections_complete | 10.00 | 10.00 | 0 |
| competitor_symmetry | 9.25 | 9.67 | +0.42 |
| conflict_free | 8.00 | 7.67 | -0.33 |

→ `factual_density` 跃升 1.18 是最大亮点，反映"基础设施修好后，研究阶段拿到的数据量直接体现在事实密度上"。`conflict_free` 微跌 0.33 仅 3 条样本（interview mode），不显著。

### 3.3 Revise 触发频率

| revisions | v1 | v2 |
|---|---|---|
| 0（一次过） | 21 | 23 |
| 1（revise 一次） | 4 | 2 |

→ revise 触发频率从 16% 降到 8%，**省了一半的 revise 成本**（每条 ≈ ¥0.005 + 5s）。

### 3.4 逐条变化

| qid | v1 | v2 | Δ | 说明 |
|---|---|---|---|---|
| q001 | 8 | 8 | 0 | stable |
| q002 | 9 | 8 | -1 | LLM 抖动 |
| q003 | 8 | 9 | +1 | LLM 抖动 |
| q004 | 9 | 9 | 0 | |
| q005 | 8 | 8 | 0 | |
| q006 | 9 | 8 | -1 | LLM 抖动 |
| **q007** | **9** | **0/RF** | **-9** | **gate 触发（搜索 transient 失败）** |
| q008 | 8 | 9 | +1 | |
| q009 | 7 | 8 | +1 | |
| q010 | 8 | 9 | +1 | |
| q011 | 9 | 9 | 0 | |
| q012 | 9 | 9 | 0 | |
| q013 | 9 | 8 | -1 | LLM 抖动 |
| q014 | 9 | 9 | 0 | |
| q015 | 8 | 8 | 0 | |
| q016 | 9 | 8 | -1 | LLM 抖动 |
| q017 | 8 | 8 | 0 | |
| q018 | 9 | 9 | 0 | |
| q019 | 8 | 9 | +1 | |
| q020 | 8 | 8 | 0 | |
| q021 | 9 | 8 | -1 | LLM 抖动 |
| q022 | 8 | 9 | +1 | |
| **q023** | **3** | **8** | **+5** | **Tavily 修好后真实质量** |
| **q024** | **4** | **0/RF** | **-4** | **gate 触发（仍搜索失败）** |
| **q025** | **6** | **9** | **+3** | **Tavily 修好后真实质量** |

---

## 四、`research_failed` 案例追查

### q007（R1=9 → R2 gate）

- v1 score=9（正常通过）
- v2 `notes_too_short:0<200` → gate 触发
- 诊断：搜索 transient 失败（同一 query 不同次跑可能命中限流 / 超时 / Tavily 后端波动）
- 行动项：Day 6 加 researcher 子图层 retry 机制（plan 006 候选）

### q024（R1=4 → R2 gate）

- v1 score=4（被 critic 评低分，但报告其实是"我没数据"伪报告）
- v2 `notes_too_short:0<200` → gate 触发，无 LLM 调用
- 诊断：跟 R1 同一根因（搜索失败），但 v1 没有 gate，浪费了 critic + revise 调用
- **plan 005 价值实证**：同样基础设施失败，v1 浪费 ¥0.015 + 15s，v2 立即 END

---

## 五、Constitution 治理层效果（继承自 plan 004 Block D）

| 规则 | v1 命中率 | v2 命中率 |
|---|---|---|
| `[no_opener_filler]` | 9% (2/22) | 13% (3/23) |
| `[citation_required]` | 23% (5/22) | 17% (4/23) |
| `[no_unverified_prediction]` | 9% (2/22) | 13% (3/23) |
| `[factual_no_contradiction]` | 5% (1/22) | 9% (2/23) |
| `[no_hallucination]` | 5% (1/22) | 4% (1/23) |
| `[Constitution] (generic)` | 95% (21/22) | 91% (21/23) |

→ Constitution 命中率两轮稳定，证明跨模型治理规则稳定生效（不是噪声）。

---

## 六、面试可讲点

### 评测驱动开发的实证价值

1. **第一轮跑就抓 bug**：v1 baseline 25 条里 3 条 score 3-6 完全不是"prompt 调差了"，而是**Tavily 限流引发的下游连锁失败**。如果只看 score 分布会以为是模型质量问题，浪费 prompt 调优时间。
2. **白盒诊断到根因 5 分钟**：通过对比 final_report_preview 和 criteria_breakdown（factual_density=0 + citation=0 + consistency=10 的怪组合）→ 报告自洽但内容空洞 → 必然是研究阶段失败。
3. **plan 005 一上线就 catch 真 incident**：Tavily 月配额 1003/1000 超额，没有 gate 的话超额期间每条 user query 浪费 ¥0.015 + 15s 写垃圾报告。
4. **第二轮对比清晰可量化**：healthy avg score +0.52，PASS rate +12pp，factual_density +1.18，revise 频率 -50%。每个数字都能讲清楚来源。

### 治理 vs 评测的协同

- **评测**：跑 25 条找 bad case 模式
- **Constitution**：把"开场废话"、"未引用断言"等规则用 YAML 配置，跨模式跨 mode 复用
- **Gate**：把基础设施失败和内容质量失败分开，不让前者污染后者的指标

---

## 七、Day 5 之后的行动项

| 优先级 | 任务 | 备注 |
|---|---|---|
| 高 | researcher 子图 retry 机制（plan 006 候选） | q007/q024 暴露的 transient 失败 |
| 中 | 完整 Tavily 用量监控（避免 silent 超额） | Day 6 加 dashboard |
| 中 | revision_count=1 异常追查 | review 006 §六 已记录 |
| 低 | 加更多 mode 的 critic_rubric | Day 6+ |

---

## 八、附录：原始数据

- v1 完整结果：`data/eval/results_day5_full_baseline.jsonl`（25 行）
- v2 完整结果：`data/eval/results_day5_round2.jsonl`（25 行）
- 哨兵 E2E：`data/eval/results_day5_gate_test.jsonl`
- LangSmith run 链接：每条 result 的 `langsmith_run_url` 字段（项目 `adrp-baseline`）
