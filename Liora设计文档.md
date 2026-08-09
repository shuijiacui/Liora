# AI 桌面反思伙伴（AI Reflection Companion）设计文档

## 1. 项目定位

### 项目名称（暂定）

AI Reflection Companion

一个拥有 Q 版电子形象的桌面 AI 伙伴，通过每日学习反思、自然语言交流和知识沉淀，帮助用户构建个人知识体系。

它不是传统 AI 助手，也不是简单的电子宠物，而是：

> 一个能够陪伴用户学习成长，并逐渐理解用户认知方式的个人 AI 伙伴。

---

# 2. 核心设计理念

## 2.1 核心问题

目前个人知识管理存在几个问题：

1. 用户很难长期维护知识库
2. 学习过程中大量想法没有被记录
3. 单纯收藏资料无法形成真正理解
4. 用户知道“应该复习”，但缺少持续反馈机制

因此，本项目不要求用户主动整理知识，而是通过轻量化的每日反思，让知识自然进入系统。

---

## 2.2 核心机制

产品核心流程：

```
学习
 ↓
AI主动邀请用户反思
 ↓
用户自然语言复述学习内容
 ↓
AI提取知识结构
 ↓
生成个人知识节点
 ↓
连接已有知识
 ↓
形成个人知识体系
```

---

# 3. 产品核心功能

## 3.1 桌面电子形象

用户界面不是传统聊天窗口，而是一个桌面常驻的小型 AI 角色。

目标：

- 增强陪伴感
- 提高每日使用意愿
- 让 AI 具有“生命感”

角色需要支持：

- idle（待机）
- happy（开心）
- thinking（思考）
- sleepy（疲惫）
- asking（提问）
- listening（倾听）

等状态。

---

## 3.2 每日学习反思

这是整个系统的核心功能。

AI 不主动教学，而是帮助用户回忆。

例如：

AI：

> 今天学到了什么有意思的东西？

用户：

> 今天学习了 Transformer 的 attention，我觉得它有点像 CNN 的动态 kernel。

AI：

继续追问：

> 为什么你觉得它像动态 kernel？

用户：

> 因为 kernel 参数固定，而 attention 根据输入调整权重。


此过程实现：

- 主动回忆（retrieval practice）
- 自我解释（self explanation）

提高学习效果。

---

# 4. 系统整体架构

```
                 用户
                  |
        语音输入 / 文字输入
                  |
                  ↓

            Reflection Agent

                  |
       ------------------------
       |                      |
       ↓                      ↓

 Knowledge Extractor     Conversation Manager

       |
       ↓

 Personal Knowledge Base

       |
       ↓

 Knowledge Graph

       |
       ↓

 User Cognitive Model

       |
       ↓

 Desktop AI Character
```

---

# 5. 软件架构设计

## 5.1 前端：桌面 AI 角色

推荐：

Electron

负责：

- 桌面悬浮窗口
- 角色展示
- 动画播放
- 用户交互

技术：

```
Electron
 |
 HTML
 CSS
 Javascript
```

---

角色资源：

```
character/

├── idle/
│   ├── idle_01.png
│   └── idle_02.png
│
├── happy/
│
├── thinking/
│
├── listening/
│
└── sleepy/
```

AI 输出：

```json
{
    "emotion":"happy",
    "action":"jump"
}
```

前端根据状态播放对应动画。

---

# 6. 后端 AI 系统

推荐：

Python


目录：

```
backend/

├── main.py

├── agent/
│   ├── reflection_agent.py
│   ├── knowledge_extractor.py
│   └── knowledge_connector.py

├── memory/
│   ├── database.py
│   └── vector_store.py

└── user_model/
    └── profile.py
```

---

# 7. Agent设计

## 7.1 Reflection Agent

作用：

负责每日反思对话。

目标：

不是回答问题，而是帮助用户回忆。


示例：

用户：

> 今天学了深度学习。


AI：

不要直接总结。


继续：

> 哪个概念让你印象最深？

---

规则：

- 不评价用户回答是否正确
- 不打断用户思考
- 重点鼓励用户解释自己的理解


---

## 7.2 Knowledge Extractor

作用：

将自然语言转换为结构化知识。


输入：

```
Attention像动态kernel，因为它根据输入调整权重。
```

输出：

```json
{
"title":"Attention与CNN Kernel类比",

"concepts":[
    "Attention",
    "CNN Kernel"
],

"user_understanding":
"Attention weights change according to input",

"learning_stage":
"intuition",

"need_review":
true
}
```

---

## 7.3 Knowledge Connector

作用：

发现新知识与旧知识之间的关系。

例如：

已有：

```
CNN feature extraction
```

新增：

```
Attention mechanism
```

建立：

```
CNN Kernel
       |
    similar
       |
Attention
```

---

# 8. 数据存储设计

## 8.1 原始反思记录

使用 SQLite。


表：

reflection

字段：

```
id
time
content
source
```

示例：

```json
{
"time":"2026-08-07",
"content":
"attention像动态kernel"
}
```

---

## 8.2 知识节点

存储：

用户理解后的知识。

例如：

```json
{
"title":
"Attention机制",

"user_view":
"动态kernel",

"related_topics":
[
"CNN",
"Transformer"
]
}
```

---

## 8.3 向量数据库

用于语义检索。

推荐：

- Chroma
- FAISS


作用：

回答：

“我以前有没有思考过类似的问题？”

---

# 9. 用户认知模型

系统长期维护：

```
User Profile

├── 兴趣方向
│
├── 当前学习主题
│
├── 常见理解方式
│
├── 知识薄弱点
│
└── 思考习惯
```

例如：

```json
{
"research":
[
"AI",
"protein modeling"
],

"learning_style":
"prefers analogy explanation",

"current_projects":
[
"NNAA prediction"
]
}
```

---

# 10. 主动行为系统

AI 不应该频繁打扰。

设计：

主动出现策略。


例如：

每天：

最多主动提醒：

1-3次。


触发：

## 学习反思

晚上：

```
今天有什么值得留下来的知识？
```

---

## 知识关联

发现新连接：

```
我发现你今天学习的内容，
和三个月前记录的 CNN kernel 有联系。
```

---

## 复习提醒

长期未出现：

```
你之前记录过 attention，
最近又遇到了类似概念。
```

---

# 11. MVP开发路线

## Phase 1：桌面角色

目标：

让 AI “存在”。

实现：

- Electron窗口
- Q版角色
- 基础动画


---

## Phase 2：反思系统

目标：

让 AI “陪伴学习”。

实现：

- 每日提问
- 文本输入
- AI追问
- 对话保存


---

## Phase 3：知识库

目标：

让 AI “理解成长”。

实现：

- SQLite
- Vector DB
- 知识提取
- 知识搜索


---

## Phase 4：硬件实体化

目标：

让 AI “来到现实”。

硬件：

```
ESP32

+

TFT屏幕

+

麦克风

+

扬声器
```

架构：

```
电脑AI大脑

      |
      USB

ESP32

      |

显示屏
```

电脑负责：

- LLM
- 数据库
- 记忆系统


ESP32负责：

- 显示
- 动画
- 简单交互

---

# 12. 第一版成功标准

不是功能数量。

而是：

用户是否愿意每天花3分钟和它交流。

核心指标：

```
学习输入成本低

↓

反思过程自然

↓

知识自动沉淀

↓

长期形成个人知识体系
```

---

# 13. 长期愿景

最终形态：

桌面 AI 伙伴成为用户个人知识系统的入口。

它拥有：

- 身体（电子形象）
- 记忆（个人知识库）
- 思考能力（AI Agent）
- 成长轨迹（用户认知模型）

目标：

> 帮助用户把零散的每日学习过程，转化为持续成长的个人第二大脑。