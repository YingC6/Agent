# HelloAgents智能旅行助手 🌍✈️

基于 HelloAgents 框架构建的智能旅行规划平台,集成 LangGraph 工作流编排、FAISS 向量 RAG、多智能体协作、高德地图 MCP 服务,提供个性化、可优化的多日旅行计划。

## ✨ 功能特点

### 核心能力
- 🤖 **LangGraph 工作流编排**: 状态机驱动多阶段规划(prepare → research → generate → review → optimize → enrich)
- 🧠 **FAISS 向量 RAG**: 知识库分块嵌入 + 向量检索 + 规则召回 + LLM 语义重排混合检索
- 🤝 **多智能体并行协作**: 景点/天气/酒店 Agent 独立实例并行调研,避免线程安全问题
- 🗺️ **高德地图 MCP 集成**: 通过 MCP 协议接入景点搜索、路线规划、天气查询
- 🔄 **Planning-Review 双阶段架构**: 规划 Agent 生成后由审核 Agent 检查,不通过自动修正(受最大轮次约束)

### 平台功能
- 👤 **用户系统**: 注册登录、JWT 认证、角色管理(普通用户/管理员)
- ❤️ **地点互动**: 收藏、打卡、点评,数据按 poi_id 关联,无需本地存储基础信息
- 💬 **社区**: 帖子发布(管理员审核)、评论直接发布、热门 POI 推荐
- 📚 **知识库管理**: Markdown 攻略导入、高评分行程自动转化、低评分自动清理
- 🎯 **用户偏好管理**: 长期记忆存储,影响行程生成
- 📝 **旅行清单**: AI 生成 + 手动编辑,按行程关联
- 💬 **多轮对话优化**: 行程生成后可对话式调整,会话持久化保留上下文

### 工程能力
- 🚀 **SSE 流式响应**: 行程生成步骤实时推送到前端
- 🔒 **接口限流**: 同一用户/游客 60 秒内最多 3 次(缓存命中不消耗次数)
- 💾 **Redis 缓存**: POI 搜索结果(TTL 3600s) + AI 行程结果(TTL 1800s)
- 🛡️ **ToolGovernance**: 工具调用超时、重试、限流治理
- 🛣️ **路线增强**: 调用高德路线规划 API 计算真实通勤时长、舒适度评估、备选方案

## 🏗️ 技术栈

### 后端
- **框架**: FastAPI + HelloAgents (SimpleAgent)
- **工作流编排**: LangGraph
- **向量检索**: FAISS + 阿里云 text-embedding-v3
- **MCP 工具**: amap-mcp-server (高德地图)
- **数据库**: SQLite (可切换 PostgreSQL)
- **缓存**: Redis (可选,未启动自动降级)
- **认证**: JWT + bcrypt
- **LLM**: 支持 OpenAI 兼容接口(阿里云千问/DeepSeek 等)

### 前端
- **框架**: Vue 3 + TypeScript
- **构建工具**: Vite
- **UI 组件库**: Ant Design Vue
- **状态管理**: Pinia
- **地图服务**: 高德地图 JavaScript API
- **HTTP 客户端**: Axios

## 📁 项目结构

```
helloagents-trip-planner/
├── backend/                        # 后端服务
│   ├── app/
│   │   ├── agents/                # 多智能体系统
│   │   │   └── trip_planner_agent.py
│   │   ├── api/
│   │   │   ├── main.py
│   │   │   ├── deps.py            # 依赖注入(认证、DB)
│   │   │   └── routes/
│   │   │       ├── trip.py        # 行程规划/优化
│   │   │       ├── trips.py       # 行程记录管理
│   │   │       ├── conversations.py # 多轮对话
│   │   │       ├── preferences.py # 用户偏好
│   │   │       ├── checklists.py  # 旅行清单
│   │   │       ├── poi.py         # 地点搜索/详情
│   │   │       ├── map.py         # 地图服务
│   │   │       ├── community.py   # 社区帖子/评论
│   │   │       ├── knowledge.py   # 知识库管理
│   │   │       ├── auth.py        # 认证
│   │   │       └── logs.py        # 生成日志
│   │   ├── services/
│   │   │   ├── agent_workflow.py     # LangGraph 工作流
│   │   │   ├── vector_store.py       # FAISS 向量存储
│   │   │   ├── embedding_service.py  # 嵌入服务
│   │   │   ├── knowledge_service.py  # 知识库混合检索
│   │   │   ├── tool_governance.py    # 工具治理
│   │   │   ├── route_service.py      # 路线规划
│   │   │   ├── plan_diff_service.py  # 行程差异预览
│   │   │   ├── checklist_service.py  # 清单生成
│   │   │   ├── memory_service.py     # 长期记忆
│   │   │   ├── ai_guard_service.py   # 限流/缓存
│   │   │   ├── ai_trip_service.py    # 行程解析/优化
│   │   │   ├── trip_repository.py    # 行程持久化
│   │   │   ├── amap_service.py       # 高德 API 封装
│   │   │   └── llm_service.py        # LLM 实例管理
│   │   ├── models/
│   │   │   ├── schemas.py          # Pydantic 模型
│   │   │   └── db_models.py        # SQLAlchemy 模型
│   │   ├── database.py
│   │   └── config.py
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py
├── frontend/                       # 前端应用
│   ├── src/
│   │   ├── views/                 # 页面
│   │   │   ├── Home.vue           # 首页(行程生成)
│   │   │   ├── Result.vue         # 行程结果+对话优化
│   │   │   ├── Discover.vue       # 地点发现
│   │   │   ├── PlaceDetail.vue    # 地点详情
│   │   │   ├── Community.vue      # 社区
│   │   │   ├── Knowledge.vue      # 知识库(管理员)
│   │   │   ├── Preferences.vue    # 偏好设置
│   │   │   ├── Trips.vue          # 我的行程
│   │   │   ├── Login.vue / Register.vue
│   │   │   └── CommunityAdmin.vue # 社区管理(管理员)
│   │   ├── services/api.ts
│   │   ├── stores/                # Pinia 状态
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 🚀 快速开始

### 前提条件

- Python 3.10+
- Node.js 16+
- 高德地图 API 密钥(**Web 服务 API 类型**,用于后端 MCP 调用)
- LLM API 密钥(阿里云千问 / DeepSeek / OpenAI 等兼容接口)
- Redis(可选,未安装自动降级为无缓存模式)

### 后端安装

1. 进入后端目录
```bash
cd backend
```

2. 创建虚拟环境并安装依赖
```bash
conda create -n agent python=3.10
conda activate agent
pip install -r requirements.txt
```

3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件,填入:
#   LLM_API_KEY        - LLM 服务密钥
#   LLM_BASE_URL       - LLM 服务地址
#   LLM_MODEL_ID       - 模型名称
#   LLM_TIMEOUT=300    - 行程生成需要较长超时
#   AMAP_API_KEY       - 高德地图 Web 服务 Key
```

4. 启动后端服务
```bash
python run.py
# 或: uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端安装

1. 进入前端目录
```bash
cd frontend
```

2. 安装依赖
```bash
npm install
```

3. 配置环境变量
```bash
cp .env.example .env
# 填入高德地图 Web 端 JS API Key(用于前端地图组件)
```

4. 启动开发服务器
```bash
npm run dev
```

5. 打开浏览器访问 `http://localhost:5173`

## 📝 使用指南

### 生成旅行计划

1. 在首页填写旅行信息:目的地、日期、天数、交通、住宿、偏好
2. 点击"生成旅行计划",系统通过 LangGraph 工作流执行:
   - **prepare_context**: 初始化需求与知识上下文
   - **research**: 并行调用景点/天气/酒店 Agent
   - **generate**: 规划 Agent 生成结构化行程
   - **review**: 审核 Agent 检查合理性
   - **optimize**: 不通过则修正(受最大轮次约束)
   - **enrich**: 补充真实通勤时长、舒适度、备选方案
3. 查看结果:每日行程、景点地图标记、路线时间轴、天气预报、餐饮推荐

### 对话式优化

在结果页点击顶部按钮打开对话窗口,输入修改要求(如"把第二天的颐和园换成长城,预算控制在 800 以内"),AI 会基于当前行程生成优化版本并展示差异。

### 其他功能

- **地点发现**: 搜索 POI、查看详情、收藏/打卡/点评
- **社区**: 发布旅行帖子、评论交流
- **知识库**(管理员): 导入 Markdown 攻略、管理知识条目
- **偏好设置**: 配置长期旅行偏好影响行程生成
- **旅行清单**: AI 根据行程自动生成清单,可手动编辑

## 🔧 核心实现

### LangGraph 工作流

```python
from langgraph.graph import StateGraph, START, END

graph = StateGraph(TravelWorkflowState)
graph.add_node("prepare_context", _prepare_context)
graph.add_node("research", _research)
graph.add_node("generate", _generate)
graph.add_node("review", _review)
graph.add_node("optimize", _optimize)
graph.add_node("enrich", _enrich)

# 条件路由:审核通过→enrich,未通过→optimize→review(循环受 max_rounds 约束)
graph.add_conditional_edges("review", _route_after_review, {...})
graph.compile()
```

### FAISS 向量 RAG 混合检索

```python
# 1. 规则评分召回 top-8(城市/天数/主题/关键词匹配)
# 2. FAISS 向量检索补充语义相似分块
# 3. LLM 语义重排选出 top-3
vector_store.build_index(knowledge_items)  # 分块+嵌入+L2归一化+IndexFlatIP
results = vector_store.search(query, top_k=8)  # 内积=余弦相似度
```

### 多智能体并行调研

```python
# 景点/天气/酒店 Agent 使用独立 MCPTool 实例,避免线程安全问题
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {
        executor.submit(governance.run_agent, tool_name, agent, query): key
        for key, (name, agent, query, _) in tasks.items()
    }
```

## 📄 API 文档

启动后端后访问 `http://localhost:8000/docs` 查看完整 API 文档。

主要端点:
- `POST /api/trip/plan` - 生成旅行计划
- `GET /api/trip/plan/stream` - SSE 流式生成
- `POST /api/trip/optimize` - 优化行程(返回差异预览)
- `POST /api/conversations` - 创建/恢复对话会话
- `POST /api/conversations/{id}/messages` - 发送对话消息
- `GET /api/preferences` - 用户偏好管理
- `POST /api/trips/{id}/checklist` - 旅行清单
- `GET /api/poi/search` - 地点搜索
- `GET /api/community/posts` - 社区帖子
- `GET /api/knowledge/items` - 知识库(管理员)

## 🤝 贡献指南

欢迎提交 Pull Request 或 Issue!

## 📜 开源协议

CC BY-NC-SA 4.0

## 🙏 致谢

- [HelloAgents](https://github.com/datawhalechina/Hello-Agents) - 智能体教程
- [HelloAgents 框架](https://github.com/jjyaoao/HelloAgents) - 智能体框架
- [LangGraph](https://github.com/langchain-ai/langgraph) - 工作流编排
- [FAISS](https://github.com/facebookresearch/faiss) - 向量检索
- [高德地图开放平台](https://lbs.amap.com/) - 地图服务
- [amap-mcp-server](https://github.com/sugarforever/amap-mcp-server) - 高德地图 MCP 服务器

---

**HelloAgents 智能旅行助手** - 让旅行计划变得简单而智能 🌈
