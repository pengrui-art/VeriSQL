# VeriSQL：面向数据库分析智能体的神经符号运行时验证

一种具备形式化正确性保障的文本转SQL（Text-to-SQL）可验证智能体架构。

## 🎯 核心创新点

VeriSQL 通过以下方式将**混合验证**与**大语言模型智能体（LLM Agents）** 相结合：
1. **混合验证**：「静态（Z3求解器）+ 动态（沙箱执行）」双重校验机制。
2. **双路径生成**：同步生成SQL语句与线性时序逻辑（LTL）规格说明。
3. **自动形式化器（ILR）**：基于中间逻辑表示（Intermediate Logic Representation）消除语义歧义。
4. **对抗性模拟数据**：生成微型数据库（Micro-DB）用于边界场景测试。
5. **追踪引导修复**：结合具体反例的反馈循环机制。

## 📁 项目结构 & 文件说明

```
verisql/
├── agents/                 # 智能体工作流模块
│   ├── graph.py            # LangGraph工作流定义
│   ├── nodes.py            # 工作流节点实现
│   └── state.py            # 状态数据模型定义
├── core/                   # 形式化表示层
│   ├── ilr.py              # 中间逻辑表示（ILR）定义
│   ├── dsl.py              # 约束领域特定语言（DSL）定义
│   └── ltl_compiler.py     # LTL公式编译器
├── modules/                # 验证与修复模块
│   ├── dynamic_verifier.py # 动态验证器
│   └── fault_localizer.py  # 故障定位器
├── utils/                  # 工具类模块
│   ├── __init__.py
│   ├── diagnosis.py        # SQL错误诊断工具
│   ├── spec_utils.py       # 规格说明解析工具
│   └── z3_utils.py         # Z3符号验证工具
├── DataBase/
│   └── Bird/               # BIRD基准测试数据集（开发集 + 训练集）
├── app.py                  # Gradio Web界面入口
├── cli.py                  # 命令行工具入口
├── config.py               # 全局配置模块
├── create_sample_db.py     # 测试数据库生成脚本
├── eval_bird.py            # BIRD基准测试评估脚本
├── main.py                 # 程序式调用入口
├── requirements.txt        # 依赖清单
└── test_*.py               # 单元/集成测试文件
```

---

### `agents/` — LangGraph 工作流

#### `agents/graph.py`
定义**LangGraph `StateGraph`**，编排整个VeriSQL流水线。按以下顺序构建并连接所有节点：

```
意图解析器 → 自动形式化器 → SQL生成器 → 规格说明生成器
    → 符号验证器 → 动态验证器
        ─── 通过 ──→ 执行器 → 结束
        ─── 失败 ──→ 形式化修复器 → SQL生成器（循环，最多3次）
        ─── 达上限 ──→ 结束（返回错误）
```

核心函数：`compile_verisql_app()` — 返回编译完成、可调用的LangGraph应用实例。

#### `agents/nodes.py`
实现**所有在工作流中执行的LangGraph节点函数**。每个节点从`VeriSQLState`读取数据，调用一个或多个LLM提示词/验证器模块，并将结果写回状态。

| 节点 | 功能 |
|---|---|
| `intent_parser_node` | 将自然语言查询解析为结构化意图JSON（操作类型、实体、时间范围、过滤条件） |
| `auto_formalizer_node` | 将解析后的意图转换为ILR（中间逻辑表示） |
| `sql_generator_node` | 基于ILR通过思维链（Chain-of-Thought）提示生成SQL；遵循平局处理策略 |
| `spec_generator_node` | 从ILR生成用于形式化验证的DSL `ConstraintSpec`（约束规格） |
| `symbolic_verifier_node` | 调用基于Z3的`SymbolicVerifier`，静态校验SQL是否符合规格说明 |
| `dynamic_verifier_node` | 在对抗性微型数据库上执行SQL，检测运行时违规行为 |
| `formal_repair_node` | 调用`FaultLocalizer`，生成结构化`PatchAction`（补丁操作），重构反馈信息 |
| `executor_node` | 在真实SQLite数据库上执行已验证的SQL，并返回结果 |

同时包含`create_llm()` — 工厂函数，创建针对当前服务商（OpenAI / 深度求索 / 通义千问）配置的`ChatOpenAI`实例。

#### `agents/state.py`
定义所有**Pydantic数据模型**和在图中流转的`VeriSQLState`类型字典（TypedDict）。

| 模型 | 描述 |
|---|---|
| `VeriSQLState` | 主工作流状态：携带查询语句、数据库模式、ILR、SQL、规格说明、验证结果、修复历史和最终输出 |
| `VerificationResult` | 验证结果（`通过/失败/错误/跳过`）、反例及每一步的详细信息 |
| `PatchActionType` | 结构化修复操作类型枚举（`添加谓词`、`修正边界`、`修正列名`等） |
| `PatchAction` | 子句级修复指令：指定目标子句、当前代码片段和建议替换内容 |
| `FaultLocalization` | 将验证失败关联到具体SQL子句，并附带对应的`PatchAction` |
| `RepairSuggestion` | 存储在修复历史日志中的顶层修复记录 |

---

### `core/` — 形式化表示层

#### `core/ilr.py`
定义**ILR（意图逻辑表示）** 模式 — 核心中间表示层，解耦自然语言理解与SQL/规格说明生成过程，降低关联幻觉风险。

核心Pydantic模型：
- `ILR` — 顶层中间表示：作用域（实体+连接+时间）、操作（查询/聚合/计数）、约束条件、输出格式
- `FilterConstraint`/`ExistentialConstraint`/`CompositeConstraint` — 类型化约束构建块
- `TieBreakingStrategy` — 平局处理策略（`返回所有平局结果`/`随机返回一个`/`不返回平局结果`），控制SQL是否使用子查询或`LIMIT 1`
- `TemporalSpec` — 结构化时间范围（绝对时间、相对时间或命名时间如Q1-Q4）

#### `core/dsl.py`
定义**约束DSL（领域特定语言）** — 一种简化、适配LLM的领域特定语言，用于表达查询约束。LLM生成该DSL而非原始LTL，再由确定性编译器转换为形式化逻辑。

| DSL类型 | 描述 |
|---|---|
| `TemporalConstraint` | 日期范围、季度（Q1-Q4）、年份或相对时间过滤 |
| `FilterDSL` | 字段级比较过滤（等于、不等于、大于、大于等于、包含、模糊匹配等） |
| `AggregateConstraint` | 聚合函数规格（求和、平均值、计数、最小值、最大值） |
| `ExistenceConstraint` | 存在/不存在子查询校验 |
| `UniquenessConstraint` | 多列组合唯一性约束 |
| `ConstraintSpec` | 顶层规格说明：作用域表 + `DSLConstraint`列表 |

#### `core/ltl_compiler.py`
**确定性编译器**，将`ConstraintSpec`（DSL）转换为用于Z3验证的LTL（线性时序逻辑）公式。无任何LLM调用 — 纯符号转换逻辑。

核心类：`LTLCompiler.compile(spec)` — 通过将每个DSL约束分发到类型化的`_compile_*`方法，生成形如`∀行 ∈ <表>: (φ₁ ∧ φ₂ ∧ …)`的`LTLFormula`。

---

### `modules/` — 验证与修复模块

#### `modules/dynamic_verifier.py`
实现**混合验证流水线的动态校验部分**。不依赖单一的符号/静态分析，该模块合成对抗性数据并在沙箱中执行SQL，检测行为层面的违规。

组件：
- `MockDBGenerator` — 构建最小化微型数据库，包含「黄金行」（满足所有规格约束）和「对抗行」（每次违反一个约束）。也可基于Z3反例生成数据行。
- `SandboxExecutor` — 在内存SQLite数据库中执行SQL，收集执行结果。
- `DynamicVerifier` — 编排器：生成模拟数据库 → 执行SQL → 校验输出是否符合规格 → 返回`VerificationResult`。

#### `modules/fault_localizer.py`
实现**C3（反例引导的结构化修复）** — 区别于模糊文本反馈的核心特性。

`FaultLocalizer.localize(sql, spec, verification_result)` 流程：
1. 使用`sqlglot`将SQL解析为抽象语法树（AST）。
2. 针对每个违规的规格约束，在AST中查找对应的谓词。
3. 故障分类：`缺失`（谓词不存在）、`错误`（值错误）、`边界`（差一错误）。
4. 生成指向具体SQL子句并建议修复方案的`PatchAction`。

辅助函数：`format_patch_actions()` — 将补丁列表序列化为结构化提示字符串，供SQL修复节点使用。

---

### `utils/` — 工具模块

#### `utils/z3_utils.py`
提供**基于Z3 SMT的符号验证**层。

核心类：
- `SQLConstraintExtractor` — 使用`sqlglot`解析SQL字符串，将WHERE子句谓词提取为标准化约束字典列表。
- `SchemaValidator` — 验证SQL中的所有表/列名是否存在于`schema_info`中，在Z3执行前拦截幻觉生成的标识符。
- `SymbolicVerifier` — 将SQL约束和规格约束编码为Z3公式，校验可满足性，并返回附带反例的`VerificationResult`。

顶层函数：`verify_sql_against_spec(sql, spec, schema_info)` — 供节点和CLI使用的便捷封装函数。

#### `utils/spec_utils.py`
提供**鲁棒的LLM生成`ConstraintSpec` JSON解析与清理**能力。

核心函数：
- `parse_json_from_text(text)` — 剥离Markdown代码块、移除C风格注释，从原始LLM输出中提取有效JSON。
- `sanitize_constraint(constraint)` — 规范化常见LLM格式错误（如`"time"` → `"temporal"`，`"where"` → `"filter"`）。
- `parse_spec_safely(text, scope_table)` — 完整流水线：解析JSON → 清理每个约束 → 构建有效的`ConstraintSpec`，遇不可恢复错误时回退为空规格。

#### `utils/diagnosis.py`
提供**智能的SQL执行错误运行时诊断**。

核心函数：
- `diagnose_sql_error(error_msg, schema_info)` — 启发式识别「无此列」「无此表」错误，并使用`difflib`建议最接近的有效名称。
- `check_result_quality(rows)` — 当结果行包含高重复率时发出警告，提示可能缺失`DISTINCT`或JOIN错误。

---

### 根目录文件

#### `config.py`
核心**配置模块**。通过`python-dotenv`读取环境变量，配置以下内容：
- **LLM服务商**：`openai` / `deepseek` / `qwen`，包含各服务商的API密钥和基础URL。
- **模型名称**：`SQL_MODEL`、`SPEC_MODEL`（各服务商默认值）。
- **验证设置**：`MAX_REPAIR_ITERATIONS`（最大修复次数）、`Z3_TIMEOUT_MS`（Z3超时时间）、`VERIFICATION_MODE`（验证模式）。
- **模式辅助配置**：`TEMPORAL_MAPPINGS`（Q1-Q4日期范围映射）。

核心函数：`get_llm_config(provider)` — 返回指定服务商的`{api_key, base_url}`字典。

#### `main.py`
**程序式入口**，用于对单个自然语言查询运行VeriSQL。初始化`VeriSQLState`，调用编译后的LangGraph应用，并打印格式化的详细报告。

使用方式：
```bash
python -m verisql.main "2024年第三季度活跃产品的总销售额是多少？" -v
```

#### `app.py`
**Gradio Web界面**，支持交互式使用。

- `DatabaseManager` — 加载SQLite文件，提取数据库模式，可选加载BIRD风格的CSV语义描述。
- 流式智能体流水线：UI中可实时查看分步推理过程。
- 展示生成的SQL、LTL公式、验证状态（静态+动态）和执行结果。

使用方式：
```bash
python -m verisql.app
```

#### `cli.py`
**命令行界面**，优化适配批量和迭代测试场景。

- `CLIDatabaseManager` — 命令行风格的数据库加载器（支持显式指定`description_dir`）。
- 支持通过问题ID加载BIRD `dev.json`中的问题。
- 输出结构化JSON，便于自动化流水线解析。
- 硬编码默认路径指向BIRD `california_schools`数据库，方便快速测试。

使用方式：
```bash
python -m verisql.cli --db path/to/db.sqlite --question "..."
```

#### `eval_bird.py`
**BIRD基准测试评估脚本**。

- 加载`dev.json`问题集和对应的黄金SQL。
- 对每个问题调用`run_verisql()`，执行生成的SQL和黄金SQL，对比结果集。
- 追踪每个问题的指标（精确匹配、执行准确率、验证通过率）。
- 写入结果JSON并打印汇总表格。

使用方式：
```bash
python verisql/eval_bird.py --dev path/to/dev.json --db-root path/to/dev_databases/
```

#### `create_sample_db.py`
**测试夹具生成器**。创建最小化电商SQLite数据库（`sample_store.db`），包含四张表（`products`、`customers`、`orders`、`order_items`）并填充示例数据，用于本地开发和冒烟测试。

#### `test_*.py` — 测试文件

| 文件 | 覆盖范围 |
|---|---|
| `test_z3_core.py` | Z3符号验证单元测试（`SymbolicVerifier`、`SchemaValidator`） |
| `test_spec_utils.py` | `parse_spec_safely`、`sanitize_constraint`、`parse_json_from_text`单元测试 |
| `test_dynamic_verifier.py` | `MockDBGenerator`和`DynamicVerifier`流水线单元测试 |
| `test_fault_localizer.py` | `FaultLocalizer`故障定位和`PatchAction`生成单元测试 |
| `test_agent_robustness.py` | 端到端智能体对抗性输入鲁棒性集成测试 |
| `test.py` | 临时/冒烟测试，用于快速手动验证 |

---

## 🚀 快速开始

```bash
# （推荐）从仓库根目录安装
pip install -e .

# 或仅安装依赖
pip install -r verisql/requirements.txt
```

### 环境变量

在`verisql/`目录创建`.env`文件（或直接导出环境变量），配置至少一个服务商：

```bash
LLM_PROVIDER=openai  # 可选值：openai | deepseek | qwen

OPENAI_API_KEY=...
# DEEPSEEK_API_KEY=...
# DASHSCOPE_API_KEY=...

# 可选配置
SQL_MODEL=gpt-4o
SPEC_MODEL=gpt-4o
MAX_REPAIR_ITERATIONS=3
Z3_TIMEOUT_MS=5000
```

### 运行（程序式 / 命令行）

```bash
python -m verisql.main "2024年第三季度活跃产品的总销售额是多少？" -v
```

### 运行（Web界面）

```bash
python -m verisql.app
```

### 运行（BIRD基准测试）

```bash
python verisql/eval_bird.py \
  --dev verisql/DataBase/Bird/dev_20240627/dev.json \
  --db-root verisql/DataBase/Bird/dev_20240627/dev_databases/
```

## 📦 依赖项

- `langgraph>=0.1.0` — 智能体工作流框架
- `langchain>=0.2.0` — LLM集成工具
- `z3-solver>=4.12.0` — SMT验证求解器
- `sqlglot>=20.0.0` — SQL解析/抽象语法树处理
- `openai>=1.0.0` — OpenAI兼容API客户端（也用于深度求索/通义千问）
- `pydantic>=2.0.0` — 数据验证与模式定义
- `python-dotenv>=1.0.0` — 环境变量管理
- `gradio>=4.0.0` — 演示用Web界面
- `httpx>=0.25.0` — HTTP客户端（适配多服务商）
- `pandas>=2.0.0`, `numpy>=1.24.0` — 动态沙箱验证器依赖
- `tqdm>=4.0.0` — 基准测试进度条

（注：本项目为研究原型）

## 🌟 近期更新（2026年1月）

- **Gradio Web界面**：完整UI支持，包含智能体推理过程流式输出、SQL可视化和交互式验证反馈。
- **多LLM支持**：通过`create_llm`辅助函数集成OpenAI、深度求索（DeepSeek）和通义千问（Qwen/DashScope）API。
- **增强型验证**：新增`SchemaValidator`，在符号验证前拦截幻觉生成的列/表名。
- **迭代式修复**：实现反馈循环机制，智能体接收验证错误后自动修正SQL（最多3次）。
- **语义感知**：支持加载BIRD风格的CSV格式`database_description`，实现列语义理解。
- **结构化修复（C3）**：`FaultLocalizer` + `PatchAction`替代模糊文本反馈，提供子句级修复指令。