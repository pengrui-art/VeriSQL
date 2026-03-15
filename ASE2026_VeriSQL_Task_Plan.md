# VeriSQL (ASE 2026) 论文写作与实验 Task Plan

**最后更新日期: 2026-03-14**

> 本文档专为 ASE 2026 论文发表冲刺（撰写与跑数）而设。
> 系统设计全景请看 [VeriSQL_Proposal.md](VeriSQL_Proposal.md)，代码基建状况请看 [VeriSQL_Progress.md](VeriSQL_Progress.md)。

## 🎯 一、 论文工作概览与冲刺路线图

目前工程代码已基本竣工。接下来的战略重心全部向**生成论文核心证据链 (Soundness)** 和 **符合 ASE 口味的撰稿 (Writing)** 转移。

### 时间倒推路线图 (Roadmap to ASE)

* **3月中旬 (跑分基建)**: 依托已完成的代码执行评测集（BIRD dev），产出首批带有 EX、SVR、CAA 指标及 Token Cost 的 Baseline 与跑批数据。
* **3月下旬 (消融与图表)**: 集中跑大规模对比消融实验（无静态、无沙盒、无修复），清洗数据生成核心图表。
* **4月上旬 (人工分析)**: 完成 100 条数据的 Ground Truth 校验，并对 Failure Cases （出错案例）打标进行定性分析。
* **4月中下旬 (暴力写作)**: 将实验组图与架构设计落实为双盲投稿论文（Method 撰写、Results 分析、Threats 免疫）。

---

## 📊 二、 阶段一：大规模实验数据获取 (Data Collection)

这里的任务侧重于**跑数据、分析结果**，为最终表格提供不可辩驳的支撑。

### Phase 1: 评估脚本补全与指标计算

- [X] **Task C1.1 真实环境 Schema 加载器**: 支持按 `db_id` 加载真实 Schema。(✅ `eval_bird.py` 的 `load_schema_from_sqlite` 已实现)
- [X] **Task C1.2 评估指标计算代码化**: 实现执行准确率(EX)、合规率/约束冲突率(SVR)、联合成功率(CAA) 及 Overhead 的统计。(✅ 均已实现在 `MetricsCalculator` 中，包括 Latency)
- [X] **Task C1.3 统一输入输出格式**: 规范评测输出为可追踪的 JSONL/Parquet。(✅ 已实现汇总到 `bird_results.json`)
- [X] **Task C1.4 开发端到端评测驱动脚本**: 能够自动拉起整个流程跑完 BIRD dev 集合（全量或大子集）。(✅ 已实现并发执行 Asyncio/Concurrency 与断点续传 Checkpointing)
  > **大规模 VeriSQL 评测运行命令 (示例)**:
  >
  > ```bash
  > conda activate verisql
  > python verisql/eval_bird.py --pred-source agent --output result_verisql_qwen.jsonl --limit 200 --concurrency 3
  > ```
  >

### Phase 2: 对比基线与消融实验 (Baseline & Ablation)

- [X] **Task C2.1 引入 Baseline 跑通代码**: 跑通单纯 LLM 零样本基线 (完成 `raw_llm` 消融模块评测基建，支持无沙盒、无约束修复的直接评估)。
  > **大规模 Baseline 评测运行命令 (纯 LLM 零样本)**:
  >
  > ```bash
  > conda activate verisql
  > python verisql/eval_bird.py --pred-source raw_llm --output result_baseline_qwen.jsonl --limit 200 --concurrency 3
  > ```
  >
- [x] **Task C2.2 实现并执行消融模式**: (✅ 已实现且跑通 `--ablation` 参数及 `no_dynamic` / `no_repair` 的节点阻断逻辑)
  - `w/o Dynamic`: 参数控制仅依赖静态 Z3 验证，跳过沙盒。
  - `w/o Repair`: 参数控制检出错误后直接抛出失败，不重试。
  > **大规模 Ablation (消融) 评测运行命令**:
  >
  > ```bash
  > # 1. 仅依赖静态验证 (无沙盒运行)
  > python verisql/eval_bird.py --pred-source agent --ablation no_dynamic --output result_nodynamic_qwen.jsonl --limit 200 --concurrency 3
  > 
  > # 2. 无重试修复 (发现错误直接返回)
  > python verisql/eval_bird.py --pred-source agent --ablation no_repair --output result_norepair_qwen.jsonl --limit 200 --concurrency 3
  > ```
  >
- [ ] **Task C2.3 验证结构化修复成效**: 跑数据并统计对比：使用 `PatchAction` vs 不使用时的平均修复轮数和最终成功率。
- [ ] **Task C2.4 [新增] 修复动作 (PatchAction) 的有效性统计**: 追踪哪种报错类型最多，以及哪些结构化修复动作 (如 `ADD_PREDICATE`, `FIX_BOUNDARY`) 的触发率与成功率最高，为实证分析 (Empirical Study) 提供真实数据洞察。

### Phase 3: 数据收集与诊断脚本

- [x] **Task C3.1 失败案例挖掘脚本**: 自动从 log 里捞出 20-50 个典型 Failed 案例用于定性分析。 (✅ `find_destructive_repairs.py` 已开发并成功定位 4 种失败归因，特别是 Z3 的类型抛错，导致模型破坏正确 SQL 的"Destructive Repair"现象)
- [x] **Task C3.1.5 (Hotfix) 修复符号验证的破坏性拦截**: (✅ 完成) 修复 `z3_utils.py` 中的类型断言问题 (引入 `BoolVal`)，并在 `graph.py` 中彻底阻断验证引擎 `ERROR` 崩溃流向 LLM 进行不必要的盲目修复，防止准确率退化。
- [ ] **Task C3.2 Z3/沙盒拦截效能统计**: 通过解析评测结果，计算静态和动态阶段的独立拦截率、假阳性 (FP) 和假阴性 (FN)。

---

## 📝 三、 阶段二：ASE 论文写作计划 (Paper Writing Tasks)

这些任务旨在将代码阶段跑出的数据和成果，包装成符合自动化软件工程 (ASE) 标准的原创性叙事。

### Section 1: Intro 与 Method 重新包装

- [ ] **Task P1.1 ASE 化主旨润色**: 重写 Introduction，淡化“Text-to-SQL 模型”色彩，强调“LLM Agent 的可靠性验证与自动化修复机制”。
- [ ] **Task P1.2 方法论框架图和描述**: 将 `ILR -> SQL/Spec -> 静态与动态混合验证 -> Patch Action` 的闭环画成规范的系统架构图并详细描述。

### Section 2: 实验组图绘制与分析 (Evaluation & Results)

- [ ] **Task P2.1 主表：核心指标展示**: 基于 Task C1.4 的结果，绘制包含 EX/SVR/CAA 和 Overhead 的主数据表。
- [ ] **Task P2.2 副表：基线与消融对比**: 基于 Task C2 结果，用图表证明验证模块和修复机制带来的增益。
- [ ] **Task P2.3 定性分析章 (Failure Taxonomy)**: 基于 Task C3.1 案例，用一个章节专门分析系统的报错类型及解决/未解决的案例。

### Section 3: 审稿防御准备 (Defending Threats to Validity)

- [ ] **Task P3.1 Ground Truth 标注可信度调查**: 抽样大约 50-100 条数据，测量由大模型生成的业务约束 (Spec) 的质量评估 (计算如 Cohen's Kappa 指标)，提供人工校验背书。(**[追加要求]** 并增加“Spec 错误如何影响最终 SQL 失败率”的传导分析以证明对不可靠 Spec 的容错情况)。
- [ ] **Task P3.2 完成 Threats to Validity 章节**: 系统防守幻觉关联 (Correlated hallucination)、Benchmark 评估分布偏误等问题。
- [ ] **Task P3.3 Replication Package 整理**: 将最终版代码、测评脚本打包制作成 README 和 Dockerfile 清晰的可复现包。
- [ ] **Task P3.4 [新增] 泛化性与开销反面验证 (No Regression on Simple Queries)**: 从经典的 Spider 验证集中抽样 100-200 条相对简单的数据跑一遍 VeriSQL。在论文中声明并证明：“本系统虽然针对复杂逻辑验证，但对简单查询也不会造成性能退步或过度开销 (Overkill)。”
