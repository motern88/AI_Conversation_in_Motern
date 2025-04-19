## 0. 前言

本文目的是希望读者在不阅读代码注释的情况下也能知悉Muti-Agent System的具体实现方式



## 1. MAS 系统

### 1.1 基础设定

MAS系统调用LLM的系统提示词（位于`mas/agent/base/base_prompt.yaml`）

```markdown
你必须牢记系统提示基础设定的内容，这对于你的工作至关重要。

## Muti-Agent System (MAS)
MAS 多Agent系统是MoternAI团队实现的一个多Agent工作系统，它包含明确的结构划分，任务执行流程和完善的配套设施：

**结构划分**
MAS中由四种层级组成，分别是Team、Task Group、Stage、Step（Agent单独说明，不在此列出）：

- Team 团队：
包含当前团队所有实例化的Agent

- Task Group 任务群组（一个Team可以同时存在多个Task Group）：
团队被分配的多个任务中，每一个任务会有自己的一个任务群组。任务群组由多个Agent组成。
对每个Agent而言，可能同时参与多个任务群组。一个任务群组至专注于一个任务（一个完整任务流程），当任务完成时，该群组解散。

- Stage 阶段（一个Task分为多个Stage）：
由任务群组的管理者制定和调整当前任务流程需要经过的多个任务阶段，并为每个任务阶段分配相应的Agent去执行。
一个任务阶段可能由多个Agent协作执行。

- Step 执行步骤（一个Agent会通过执行多个Step来完成其所在阶段的目标）：
Agent被分配执行或协作执行一个阶段时，Agent会为自己规划数个执行步骤以完成目标。一次执行步骤是整个框架中的最小单位。

**状态信息**
对于信息的记录，我们实现了对应的状态空间

- task_state 任务状态（大量信息）：
任务状态由Agent/人类初始化，由Agent/人类进行更新。
包含任务名称、任务目标、具体步骤、完成情况等，同时也记录了任务群组中参与Agent的情况，以及任务群组中共享消息池的信息。

- stage_state 任务阶段状态（简单少量信息）：
任务阶段状态有任务群组中首个Agent负责规划，并初始化需要完成这个任务的多个阶段的任务阶段状态。
**同一时刻，Task Group中仅有一个Stage活跃**，因此不需要在阶段状态中维护任何共享消息池，阶段状态只记录阶段目标，完成情况和Agent信息

- agent_state 智能体状态（大量信息）：
Agent状态随着Agent的实例化而初始化（由其他Agent/人类初始化），由Agent自己/其他Agent/人类进行更新。
包含Agent的个人信息，使用工具与技能的权限，以及LLM上下文的缓存。

- step_state 任务步骤状态（简单少量信息）：
记录Agent中每一个最小动作的执行情况。仅记录当前步骤进行的具体操作，所属的任务阶段与所属的Agent。
Agent顺序执行步骤列表中待办步骤，**同一时刻，Agent中只有一个Step被执行**。

**任务执行流程**

- 1.Task
一个任务进来后，会被分配到一个Task Group中，Task Group中的首个Agent会规划任务的阶段流程。
Task Group中首个Agent会作为任务管理者将任务规划出多个阶段stage，并为每个stage都分配一个或多个Agent去执行。

- 2.Stage
Task中的多个Stage是串行执行的，一个Stage完成后，Task Group中的首个Agent会根据当前Stage的完成情况，决定下一个Stage的执行情况。
Stage在依次被执行的过程中，会维护一个Stage状态，记录当前Stage的目标，完成情况和参与Stage的每个Agent状态。
在当前Stage中的Agent会各自完成自己被分配到具体职责，协助完成Stage阶段目标。

- 3.Step
Agent完成或协助完成当前Stage目标的方式，是规划并执行一个个Step。
Step是Agent的最小操作单元，一个Step中包含一个技能或工具的调用，以及调用的具体目标。
Agent会根据当前Stage目标，通过planning规划模块生成多个Step以完成该目标，通过reflection反思模块来追加新的Step来修正Agent的执行结果。
Agent会顺序执行自己规划的Step，同时为每个Step维护一个Step状态，记录当前Step的目标，完成情况和所属Agent等。

**协作通信**

- Task Group共享消息池：
task_state中会维护一份共享消息池，用于记录任务的全局信息，包括任务管理Agent对任务流程的更新与追加操作，任务群组成员对任务不同阶段Stage的完成情况更新等。
共享消息池中的信息所有Agent都可以访问，然而共享消息池中的信息并不会主动发送给每个Agent，Agent并不被动接收共享消息池，Agent只会在需要的时候主动查看。
（同一时刻，Task Group中仅有一个Stage活跃，因此不需要在 `stage state` 中维护任务阶段的共享消息池，`stage state` 只记录阶段目标和完成情况）

- Agent间通信：
Agent间通信需要由一方主动发起（在发起方的某一个step中执行的是 `send message` 工具，接收方Agent的`step`列表中会被追加一个回应step，用于在回应step中回复这条message）

## 单Agent内部工作流
单Agent内部工作流程是Agent在执行一个阶段的目标时，如何规划并执行多个Step以完成该目标。
单Agent内部工作流是多Agent系统(MAS)的重要组成部分, 它是Agent**自主决定自身工作逻辑与自主决定使用什么工具与技能**的重要实现方式之一。

单个Agent内部通过不断顺序执行一个个step从而完成一次次操作与action。
Agent通过planning模块与reflection模块来为自己增加新的step与调整已有的step。
每一个step执行一个具体的操作，包括调用一个技能或工具，或者发送消息给其他Agent。

**skill**
技能的定义是所有由LLM驱动的具体衍生能力。其主要区别在于提示词的不同，且是随提示词的改变而具备的特定衍生能力。
技能库包括包括规划 `planning`、反思 `reflection`、总结 `summary` 、快速思考 `quick_think` 、指令生成 `instruction_generation` 等 。

**tool**
工具的定义是LLM本身所不具备的能力，而通过访问Agent外部模块接口实现的一系列功能。相比于技能，工具更接近现实世界的交互行为，能够获取或改变Agent系统外的事物。
工具库包括向量数据库检索增强生成 `rag`、搜索引擎 `search_engine`、光学字符识别 `ocr` 等。

### Step State
本小节将简要介绍 step_state 涉及的字段

属性:
task_id (str): 任务ID，用于标识一个任务的唯一ID
stage_id (str): 阶段ID，用于标识一个阶段的唯一ID
agent_id (str): Agent ID，用于标识一个Agent的唯一ID
step_id (str): 步骤ID，用于标识一个步骤的唯一ID，自动生成
step_intention (str): 步骤的意图, 由创建Agent填写(仅作参考并不需要匹配特定格式)。例如：\"ask a question\", \'provide an answer\', \'use tool to check...\'

type (str): 步骤的类型,例如：\'skill\', \'tool\'
executor (str): 执行该步骤的对象，如果是 type 是 \'tool\' 则填工具名称，如果是 \'skill\' 则填技能名称
execution_state (str): 步骤的执行状态：
    \'init\' 初始化（步骤已创建）
    \'pending\' 等待内容填充中（依赖数据未就绪），一般情况下只出现在工具指令填充，技能使用不需要等待前一步step去填充
    \'running\' 执行中
    \'finished\' 已完成
    \'failed\' 失败（步骤执行异常终止）

text_content (str): 文本内容，
    - 如果是技能调用则是填入技能调用的提示文本（不是Skill规则的系统提示，而是需要这个skill做什么具体任务的目标提示文本）
      step中的这个属性是只包含当前步骤目标的提示词，不包含Agent自身属性（如技能与工具权限）的提示词
    - 如果是工具调用则应当填写该次工具调用的具体详细的目标。
instruction_content (Dict[str, Any]): 指令内容，如果是工具调用则是具体工具命令  TODO：Dict[str, Any]具体格式
execute_result (Dict[str, Any]): 执行结果，如果是文本回复则是文本内容，如果是工具调用则是工具返回结果  TODO：Dict[str, Any]具体格式

### Agent State
agent_state 是 Agent的重要承载体，它是一个字典包含了一个Agent的所有状态信息。
Agent被实例化时需要初始化自己的 agent_state, agent_state 会被持续维护用于记录Agent的基本信息、状态与记忆。
所有Agent使用相同的类，具有相同的方法属性，相同的代码构造。不同的Agent唯一的区别就是 agent_state 的区别。

本小节将简要介绍 agent_state 字典涉及的key。

参数：
agent_id (str): Agent 的唯一标识符，由更高层级的 Agent 管理器生成。
name (str): Agent 的名称。
role (str): Agent 的角色，例如 数据分析师、客服助手 等。
profile (str): Agent 的角色简介，描述该 Agent 的核心能力和任务。
working_state (str): Agent 的工作状态，例如 Unassigned 未分配任务, idle 空闲, working 工作中, awaiting 等待执行反馈中。
llm_config (Dict[str, Any]): LLM（大语言模型）的配置信息
working_memory (Dict[str, Any]: 
    - 以任务视角存储 Agent 的工作记忆。  
    - 结构为 `{<task_id>: {<stage_id>: [<step_id>, ...], ...}, ...}`  
    - 记录未完成的任务、阶段和步骤，不用于长期记忆。  
persistent_memory (str): 永久追加精简记忆，用于记录Agent的持久性记忆，不会因为任务,阶段,步骤的结束而被清空
    - md格式纯文本，里面只能用三级标题 ### 及以下！不允许出现一二级标题！
agent_step (AgentStep): AgentStep是一个对step_state的管理类，维护一个包含step_state的列表
tools (List[str], 可选): Agent 可用的工具列表，例如 `['搜索引擎', '计算器']`，默认为空列表。
skills (List[str], 可选): Agent 可用的技能列表，例如 `['文本摘要', '图像识别']`，默认为空列表。

```



### 1.2 Message Dispatcher

消息分发类，一般实例化在MAS类中，与SyncState和Agent同级，用于消息分发。

它会遍历所有 TaskState 的消息队列 `task_state.communication_queue`，捕获到消息后会调用agent.receive_message方法来处理消息。



## 2. State 状态

首先我们实现两种状态空间，一种是以任务视角为主的状态空间（TaskState和StageState），记录任务信息。一种是以Agent视角的状态空间（AgentState和StepState），记录Agent自己的信息。



- `task_state` 任务状态（大量信息）：

  任务状态由Agent/人类初始化，由Agent/人类进行更新。包含任务名称、任务目标、具体步骤、完成情况等，同时也记录了任务群组中参与Agent的情况，以及任务群组中共享消息池的信息。

- `stage_state` 任务阶段状态（简单少量信息）：

  任务阶段状态有任务群组中首个Agent负责规划，并初始化需要完成这个任务的多个阶段的任务阶段状态。

  **同一时刻，Task Group中仅有一个Stage活跃**，因此不需要在阶段状态中维护任何共享消息池，阶段状态只记录阶段目标，完成情况和Agent信息

- `agent_state` 智能体状态（大量信息）：

  Agent状态随着Agent的实例化而初始化（由其他Agent/人类初始化），由Agent自己/其他Agent/人类进行更新。包含Agent的个人信息，使用工具与技能的权限，以及LLM上下文的缓存。

- `step_state` 任务步骤状态（简单少量信息）：

  记录Agent中每一个最小动作的执行情况。仅记录当前步骤进行的具体操作，所属的任务阶段与所属的Agent。Agent顺序执行步骤列表中待办步骤，**同一时刻，Agent中只有一个Step被执行**。



其中`Task State` 和 `Stage State` 是相互指向的，即任务状态记录自己有哪些阶段，阶段状态记录自己所属哪个任务。

但是 `Stage State` 是不指向具体 `Step State` 的，只指向负责执行的 Agent。因为 `Step State` 是由 Agent 内部产生的，只被记录在 `Agent State` 里。

同时，`Step State` 会指向 `Stage State` 用于标明自己属于哪一个任务，因为一个Agent可能被分配多个不同任务的 Stage 。



### 2.1 Task State

**类名:** TaskState

**说明：**

MAS系统接收到一个具体任务时，会实例化一个TaskState对象用于管理这个任务的状态。

一个任务会被拆分为多个阶段（多个子目标），即TaskState内会包含多个StageState以记录每个阶段的信息

**属性：**

- task_id (str): 

  任务ID，用于标识一个任务的唯一ID

- task_intention (str): 

  任务意图, 较为详细的任务目标说明



- task_group (list[str]): 

  任务群组，包含所有参与这个任务的Agent ID

- shared_message_pool (List[Dict]): 

  任务群组共享消息池（可选结构：包含agent_id, role, content等）

- communication_queue (queue.Queue()):

  用于存放任务群组的通讯消息队列，Agent之间相互发送的待转发的消息会被存放于此。待MAS系统的消息处理模块定期扫描task_state的消息处理队列，执行消息传递任务。



- stage_list (List[StageState]):

  当前任务下所有阶段的列表（顺序执行不同阶段）

- execution_state (str): 

  当前任务的执行状态，"init"、"running"、"finished"、"failed"

- task_summary (str): 

  任务完成后的总结，由SyncState或调度器最终生成





### 2.2 Stage State

**类名:** StageState

**说明：**

Agent被分配执行或协作执行一个任务时，任务会由管理Agent拆分成具体阶段Stage。

阶段内容包含 所属任务ID与参与阶段的 Agent ID，阶段的意图与每个Agent需要完成的阶段目标，阶段与Agent的状态等。

**属性：**

- task_id (str): 

  任务ID，用于标识一个任务的唯一ID

- stage_id (str): 

  阶段ID，用于标识一个阶段的唯一ID



- stage_intention (str): 

  阶段的意图, 由创建Agent填写(仅作参考并不需要匹配特定格式)。例如：'Extract contract information and archive it...'

- agent_allocation (Dict[<agent_id>, <stage_goal>]):

  阶段中Agent的分配情况，key为Agent ID，value为Agent在这个阶段职责的详细说明



- execution_state (str):

  阶段的执行状态：
  	"init" 初始化（阶段状态已创建）
  	"running" 执行中
  	"finished" 已完成
  	"failed" 失败（阶段执行异常终止）

- every_agent_state (Dict[<agent_id>, <agent_state>]): 

  涉及到的每个Agent在这个阶段的状态：
  	"idle" 空闲
  	"working" 工作中
  	"finished" 已完成
  	"failed" 失败（agent没能完成阶段目标）
  	这里的状态是指Agent在这个阶段的状态，不是全局状态

- completion_summary (Dict[<agent_id>, <completion_summary>]): 

  阶段中每个Agent的完成情况





### 2.3 Agent State

agent_state 是 Agent的重要承载体，它包含了一个Agent的所有状态信息。

所有Agent使用相同的类，具有相同的方法属性，相同的代码构造。不同Agent的区别仅有 `agent_state` 的不同，可以通过 `agent_state` 还原出一样的Agent 。



| key               | 类型           | 说明                                                         |
| ----------------- | -------------- | ------------------------------------------------------------ |
| agent_id          | str            | Agent的唯一标识符                                            |
| name              | str            | Agent的名称                                                  |
| role              | str            | Agent的角色                                                  |
| profile           | str            | Agent的角色简介                                              |
| working_state     | str            | Agent的当前工作状态；<br />Unassigned 未分配任务, idle 空闲, working 工作中, awaiting 等待执行反馈中 |
| llm_config        | Dict[str, Any] | 从配置文件中获取 LLM 配置                                    |
| working_memory    | Dict[str, Any] | Agent工作记忆 {<task_id>: {<stage_id>: [<step_id>,...],...},...} 记录Agent还未完成的属于自己的任务 |
| persistent_memory | str            | 由Agent自主追加的永久记忆，不会因为任务、阶段、步骤的结束而被清空；<br />（md格式纯文本，里面只能用三级标题 ### 及以下！不允许出现一二级标题！） |
| agent_step        | AgentStep实例  | AgentStep,用于管理Agent的执行步骤列表；<br />（一般情况下步骤中只包含当前任务当前阶段的步骤，在下一个阶段时，上一个阶段的step_state会被同步到stage_state中，不会在列表中留存） |
| tools             | List[str]      | Agent可用的技能                                              |
| skills            | List[str]      | Agent可用的工具                                              |
|                   |                |                                                              |
|                   |                |                                                              |





### 2.4 Step State

**类名:** StepState

**说明：**Agent被分配执行或协作执行一个阶段时，Agent会为自己规划数个执行步骤以完成目标。步骤step是最小执行单位，每个步骤的执行会维护一个 step_state 。

具体实现: 封装一个AgentStep类，该类用于管理其内部的step_state的列表

**属性：**

- task_id (str): 

  任务ID，用于标识一个任务的唯一ID

- stage_id (str): 

  阶段ID，用于标识一个阶段的唯一ID

- agent_id (str): 

  Agent ID，用于标识一个Agent的唯一ID

- step_id (str): 

  步骤ID，用于标识一个步骤的唯一ID，自动生成

- step_intention (str): 

  步骤的意图, 由创建Agent填写(仅作参考并不需要匹配特定格式)。例如：'ask a question', 'provide an answer', 'use tool to check...'

  

- type (str): 

  步骤的类型，例如：'skill', 'tool'

- executor (str): 

  执行该步骤的对象，如果是 type 是 'tool' 则填工具名称，如果是 'skill' 则填技能名称

- execution_state (str): 

  步骤的执行状态：
      'init' 初始化（步骤已创建）
      'pending' 等待内容填充中（依赖数据未就绪），一般情况下只出现在工具指令填充，技能使用不需要等待前一步step去填充
      'running' 执行中
      'finished' 已完成
      'failed' 失败（步骤执行异常终止）

  

- text_content (str): 文本内容，
  - 如果是技能调用则是填入技能调用的提示文本（不是Skill规则的系统提示，而是需要这个skill做什么具体任务的目标提示文本）
    step中的这个属性是只包含当前步骤目标的提示词，不包含Agent自身属性（如技能与工具权限）的提示词
  - 如果是工具调用则可以选填该次工具调用的具体详细的目标。
    instruction_content (Dict[str, Any]): 指令内容，如果是工具调用则是具体工具命令
    execute_result (Dict[str, Any]): 用来记录LLM输出解析或工具返回的结果，主要作用是向reflection反思模块提供每个步骤的执行信息

- instruction_content (Dict[str, Any]): 

  指令内容，如果是工具调用则是具体工具命令

- execute_result (Dict[str, Any]): 

  用来记录LLM输出解析或工具返回的结果，主要作用是向reflection反思模块提供每个步骤的执行信息

------

**类名：**AgentStep

**说明：**

Agent的执行步骤管理类，用于管理Agent的执行步骤列表。包括添加、删除、修改、查询等操作。

初始化会对应上agent_id，会初始化一个step_list用于承载StepState，同时将每个未执行的StepState的step_id放入todo_list中。Agent执行Action是按照todo_list的共享队列顺序执行，但是更新与修改操作可以根据step_id、stage_id、task_id操作。

**属性：**

- agent_id (str)：

  Agent唯一标识ID

- todo_list (queue.Queue())：

  只存放待执行的 step_id，执行者从队列里取出任务进行处理，一旦执行完就不会再回到 todo_list

- step_list (List[StepState])：

  持续记录所有 StepState，即使执行完毕也不会被删除，方便后续查询、状态更新和管理。



### 2.5 Sync State

**类名：**SyncState

**说明：**

在MAS中，sync_state状态同步器专门负责管理不属于单一Agent的状态，stage_state与task_state。

相对而言，Agent自身的局部状态，agent_state与step_state会在executor执行过程中更新。无需sync_state参与。

executor执行返回的executor_output用于指导sync_state工作

**属性：**

- all_tasks（Dict[str, TaskState]）：存储系统中所有任务状态，键为 task_id，值为对应的 TaskState 实例

**方法：**

sync_state（executor_output: Dict[str, any]）接收executor的输出字典，根据字典中不同的字段更新不同的任务状态与阶段状态

| 匹配的key名                   | 功能                                                         |
| ----------------------------- | ------------------------------------------------------------ |
| update_stage_agent_state      | 更新Agent在stage中的状态                                     |
| send_shared_message           | 添加共享消息到任务共享消息池                                 |
| update_stage_agent_completion | 更新阶段中Agent完成情况                                      |
| send_message                  | 将Agent.executor传出的消息添加到task_state.communication_queue通讯队列中 |
|                               |                                                              |
|                               |                                                              |
|                               |                                                              |







## 3. Skill 技能

所有的技能都会继承`mas.agent.base.executor_base.Executor`使用基础执行器类的通用方法



### 3.1 Planning

**期望作用：**

Agent通过Planning技能规划任务执行步骤，生成多个step的执行计划。

**说明：**

Planning需要有操作Agent中AgentStep的能力，AgentStep是Agent的执行步骤管理器，用于管理Agent的执行步骤列表。我们通过提示词约束LLM以特定格式返回规划的步骤信息，然后基于规则的代码解析这些信息，增加相应的步骤到AgentStep中。

**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
>
> 2. llm调用
> 3. 解析llm返回的步骤信息，更新AgentStep中的步骤列表（核心行为需要包含失败判定，如果失败更新step执行失败状态）
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 返回用于指导状态同步的execute_output



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 planning step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	3.2 step.text_content 具体目标（## 二级标题）
>
> ​	3.3 技能规则提示(planning_config["use_prompt"])（## 二级标题）
>
> 4 持续性记忆:（# 一级标题）
>
> ​	4.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	4.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 更新AgentStep中的步骤列表
>
>    ```python
>    self.add_step(planned_step, step_id, agent_state)  # 将规划的步骤列表添加到AgentStep中
>    ```
>
> 2. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"planned_step": planned_step}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    Planning顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
>
>    ```python
>    execute_output["update_stage_agent_state"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "state": update_agent_situation,
>    }
>    ```
>
> 4. 添加步骤完成情况到task_state的共享消息池：
>
>    通过`send_shared_message`字段指导sync_state更新，
>
>    Planning顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
>        "content": f"执行Planning步骤:{shared_step_situation}，"
>    }
>    ```



### 3.2 Reflection

**期望作用：**

Agent通过Reflection技能反思已执行步骤是否符合预期。如果需要调整则生成新的多个step执行计划，如果不需要调整则增加一个总结步骤。

**说明：**

Reflection需要获取到过去执行步骤的信息，并且具备操作AgentStep追加step的能力。我们整理过去执行步骤的结果和阶段目标以特定格式输入LLM进行反思，同时通过提示词约束LLM以特定格式返回反思结果和规划的步骤信息。然后基于规则的代码解析这些信息，增加相应的步骤到AgentStep中。

反思技能获取不到stage信息，阶段目标信息从Planning_step中获取：
	Planning_step中text_content中记录阶段整体目标和Agent被分配的具体目标。
	由agent_base.py中start_stage方法将Stage信息注入到Planning_step中。



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
>
> 2. llm调用
> 3. 解析llm返回的步骤信息，更新AgentStep中的步骤列表（核心行为需要包含失败判定，如果失败更新step执行失败状态）
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 返回用于指导状态同步的execute_output



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 reflection step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	3.2 step.text_content 具体目标（## 二级标题）
>
> ​	3.3 技能规则提示(reflection_config["use_prompt"])（## 二级标题）
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	4.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	4.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 更新AgentStep中的步骤列表
>
>    ```python
>    self.add_step(reflection_step, step_id, agent_state)  # 将规划的步骤列表添加AgentStep中
>    ```
>
> 2. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"reflection_step": reflection_step}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    Reflection顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
>
>    ```python
>    execute_output["update_stage_agent_state"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "state": update_agent_situation,
>    }
>    ```
>
> 4. 添加步骤完成情况到task_state的共享消息池：
>
>    通过`send_shared_message`字段指导sync_state更新，
>
>    Planning顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
>        "content": f"执行Reflection步骤:{shared_step_situation}，"
>    }
>    ```



### 3.3 Summary

**期望作用：**

Agent通过Summary总结并结束自己的一个stage，标志着一个stage的结束。

整理该stage内所有step的信息并通过execute_output同步stage_state.completion_summary中。

(Summary只负责Agent执行step的汇总，不负责交付阶段stage结果。例如假设阶段目标是输出一段文本，那么输出文本的这个交付过程应当由一个交付工具例如"send_message"执行，而非留给Summary技能来完成。)



**说明：**

Summary需要获取到过去执行步骤的信息。我们整理过去执行步骤的结果和阶段目标以特定格式输入LLM进行总结，同时通过同时通过提示词约束LLM以特定格式返回其总结结果。然后基于规则的代码解析这些信息，生成对应的execute_output。

Summary技能对stage信息的获取来源于第一个步骤Planning_step：
	Planning_step中text_content中记录阶段整体目标和Agent被分配的具体目标。
	由agent_base.py中start_stage方法将Stage信息注入到Planning_step中。



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
>
> 2. llm调用
>
> 3. 解析llm返回的总结信息
>
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
>
> 5. 返回用于指导状态同步的execute_output
>
>    （更新stage_state.completion_summary的指令，更新stage_state.every_agent_state中自己的状态）



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 summary step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	3.2 step.text_content 具体目标（## 二级标题）
>
> ​	3.3 技能规则提示(summary_config["use_prompt"])（## 二级标题）
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	4.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	4.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 将总结结果同步到stage_state.completion_summary
>
>    通过构造execute_output指导SyncState的方式
>
>    ```python
>    execute_output["update_stage_agent_completion"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "completion_summary": agent_completion_summary,
>    }
>    ```
>
> 2. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"summary": summary}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    summary顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
>
>    ```python
>    execute_output["update_stage_agent_state"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "state": update_agent_situation,
>    }
>    ```
>
> 4. 添加步骤完成情况到task_state的共享消息池：
>
>    通过`send_shared_message`字段指导sync_state更新，
>
>    summary顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
>        "content": f"执行summary步骤:{shared_step_situation}，"
>    }
>    ```



### 3.4 Instrcution Generation

**期望作用：**为下一个工具step生成实际工具调用指令。

**说明：**

Instruction Generation会获取下一个工具step的信息，并具备更新下一个工具step的能力。我们将获取到的下一个工具step中工具的提示信息和指令生成的提示信息以特定格式输入LLM进行指令生成，同时捕获LLM以特定格式返回的指令内容。然后基于规则的代码解析这些信息，并更新下一个工具step的指令内容。



一种可能的特殊情况是，在instruction_generation_step和tool_step之间被插入了一个额外tool_step,(插入step很常见，任务分配线程有权利这么做)。这将会导致instruction_generation为错误的tool_step生成指令。

实际上插入step的操作只会插入在下一个未执行的step前：
	如果 instruction_generation_step 未执行，则插入step会插入在 instruction_generation_step 之前；
	如果 instruction_generation_step 正在执行，则线程锁会暂时禁止AgentStep被Agent的任务分配线程插入step；
	如果 instruction_generation_step 执行完成，原定下一个 tool_step 未执行，这时插入step会插入在 tool_step。但此时原定下一个 tool_step 已经被生成完指令了，因此也不会对工具执行造成影响。

因此，只要Agent的任务执行线程、Agent的任务分配线程、线程锁等逻辑不发生改变，则指令生成一般都能够顺利为正确工具生成指令。



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
>
> 2. llm调用
>
> 3. 解析llm返回的指令内容，并追加到下一个工具step的指令内容中
>
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
>
> 5. 返回用于指导状态同步的execute_output
>
>    （更新stage_state.every_agent_state中自己的状态）



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 instruction_generation step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	3.2 step.text_content 具体目标（## 二级标题）
>
> ​	3.3 技能规则提示(instruction_generation_config["use_prompt"])（## 二级标题）
>
> 4 tool step:（# 一级标题）
>
> ​	4.1 工具step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	4.2 工具step.text_content 具体目标（## 二级标题）
>
> ​	4.3 技能规则提示(tool_config["use_prompt"])（## 二级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	4.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	4.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 将LLM返回的指令内容追加到下一个工具step中
>
>    ```python
>    next_tool_step.update_instruction_content(tool_instruction)
>    ```
>
> 2. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"instruction_generation": tool_instruction}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    instruction_generation顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
>
>    ```python
>    execute_output["update_stage_agent_state"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "state": update_agent_situation,
>    }
>    ```
>
> 4. 添加步骤完成情况到task_state的共享消息池：
>
>    通过`send_shared_message`字段指导sync_state更新，
>
>    instruction_generation顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
>        "content": f"执行instruction_generation步骤:{shared_step_situation}，"
>    }
>    ```





### 3.5 Think

**期望作用：**Agent通过Think来处理一些需要历史步骤信息的文本生成任务。

**说明：**MAS中常规的基于历史步骤信息的LLM调用/文本生成。

**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
> 2. llm调用
> 3. 解析llm返回的思考内容
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 返回用于指导状态同步的execute_output



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 think step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	3.2 step.text_content 具体目标（## 二级标题）
>
> ​	3.3 技能规则提示(think_config["use_prompt"])（## 二级标题）
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	5.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	5.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"think": _think}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    instruction_generation顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
>
>    ```python
>    execute_output["update_stage_agent_state"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "state": update_agent_situation,
>    }
>    ```



### 3.6 Quick Think

**期望作用：**Agent通过Quick Think来快速反应一些不需要历史步骤信息的文本生成任务。

**说明：**MAS中一次简单的LLM调用/文本生成。

**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
> 2. llm调用
> 3. 解析llm返回的思考内容
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 返回用于指导状态同步的execute_output



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 quick_think step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	3.2 step.text_content 具体目标（## 二级标题）
>
> ​	3.3 技能规则提示(quick_think_config["use_prompt"])（## 二级标题）
>
> 4 持续性记忆:（# 一级标题）
>
> ​	4.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	4.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"quick_think": quick_think}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    instruction_generation顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
>
>    ```python
>    execute_output["update_stage_agent_state"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "state": update_agent_situation,
>    }
>    ```



### 3.7 Send Message

**期望作用：**Agent在MAS系统内部的对另一个Agent实例的单向消息发送。

**说明：**

Send Message会获取当前stage所有step执行情况的历史信息，使用LLM依据当前send_message_step意图进行汇总后，向指定Agent发送消息。

Send Message 首先需要构建发送对象列表。[<agent_id>, <agent_id>, ...]
其次需要确定发送的内容，通过 Send Message 技能的提示+LLM调用返回结果的解析可以得到。
需要根据发送的实际内容，LLM需要返回的信息:

```
<send_message>
{
    "sender_id": "<sender_agent_id>",
    "receiver": ["<agent_id>", "<agent_id>", ...],
    "message": "<message_content>",  # 消息文本
    "stage_relative": "<stage_id或no_relative>",  # 表示是否与任务阶段相关，是则填对应阶段Stage ID，否则为no_relative的字符串
    "need_reply": <bool>,  # 需要回复则为True，否则为False
}
</send_message>
```



1. 消息如何被发送：

   消息体通过execute_output,由sync_state将消息放入task_state的消息处理对列中，
   会由MAS系统的消息处理模块定期扫描task_state的消息处理队列，执行消息传递任务。

   

2. Agent通信方式/流程：
   接收者以被追加一个step（Process Message/Send Message）的方式处理消息。
   如果发送者认为需要回复，则接收者被追加一个指向发送者的Send Message step，
   如果发送者认为不需要回复，则接收者被追加一个Process Message step，Process Message 不需要向其他实体传递消息或回复

   

   因此，如果是一个单向消息，则通过Send Message和Process Message可以完成；如果是长期多轮对话，则通过一系列的Send Message和最后一个Process Message实现。

   

3. send_message与process_message这类消息step是否隶属某一个stage：

   - 如果这类消息传递是任务阶段相关的话，应当属于某一个stage。

     这样通讯消息也是完成任务的一部分，stage完成与否也必须等待这些通讯消息的结束。

   - 如果这类消息是任务阶段相关的，则不应属于某一个stage。step中的stage_id应当为"no_stage"，

     这样这些消息的完成与否不会影响任务段的完成，任务阶段的完成也不会中断这些通讯消息的执行。


   一般情况下，由Agent自主规划的Send Message的消息传递均是与任务阶段相关的，因此在发送消息时需要指定stage_id。



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
> 2. llm调用
> 3. 解析llm返回的消息内容
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 返回用于指导状态同步的execute_output



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 send_message step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	3.2 step.text_content 具体目标（## 二级标题）
>
> ​	3.3 技能规则提示(send_message_config["use_prompt"])（## 二级标题）
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	5.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	5.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"send_message": send_message}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    instruction_generation顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
>
>    ```python
>    execute_output["update_stage_agent_state"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "state": update_agent_situation,
>    }
>    ```
>
> 4. 添加步骤完成情况到task_state的共享消息池：
>
>    通过`send_shared_message`字段指导sync_state更新，
>
>    instruction_generation顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_message"] = {
>        "task_id": step_state.task_id,
>        "sender_id": send_message["sender_id"],
>        "receiver": send_message["receiver"],
>        "message": send_message["message"],
>        "stage_relative": send_message["stage_relative"],
>        "need_reply": send_message["need_reply"],
>    }
>    ```





### 3.8 Process Message

**期望作用：**Agent处理MAS内部来自另一个Agent实例的单项消息，且该消息明确不需要回复。

**说明：**

接收到消息后，Agent会使用process_message step，调用llm来处理消息的非指令部分

（指令部分在agent_base中process_message方法中处理），

一般情况下意味着该消息需要被LLM消化并整理，也有可能仅仅作为多轮对话的结尾。



在AgentBase类中的process_message方法主要用于处理message中的指令部分，依照指令进行实际操作。

在技能库中的ProcessMessageSkill主要用于让LLM理解并消化消息的文本内容。



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
> 2. llm调用
> 3. 解析llm返回的理解内容
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 返回用于指导状态同步的execute_output



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 process_message step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	3.2 step.text_content 具体目标（## 二级标题）
>
> ​	3.3 技能规则提示(process_message_config["use_prompt"])（## 二级标题）
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	5.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	5.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"process_message": process_message}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    instruction_generation顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
>
>    ```python
>    execute_output["update_stage_agent_state"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "state": update_agent_situation,
>    }
>    ```



### 3.9 （TODO）

**期望作用：**



**说明：**



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**



**提示词：**



**交互行为：**



**其他状态同步：**















## 4. Tool 工具







## 5. Executor 及通用提示词

`mas.agent.base.executor_base.Executor`为定义的执行器基础类，所有的skills与tools都继承自Executor基类。



在`Executor`基类中会维护一份技能及工具的注册表，并通过类型和名称注册子类，可以实现动态路由和解耦设计，在实际使用中，路由器`Router`类会根据step_state中指定的执行器名称返回具体的executor。



### 5.1 系统提示词

获取MAS系统的基础提示词

```python
md_output.append("# 系统提示 system_prompt\n")
system_prompt = self.get_base_prompt(key="system_prompt")  # 已包含 # 一级标题的md
md_output.append(f"{system_prompt}\n")
```

**执行器基类函数名：**get_base_prompt

**作用：**传入system_prompt，从`mas/agent/base/base_prompt.yaml`中获取`key=“system_prompt”`的值



### 5.2 角色提示词

获取Agent角色背景提示词 与 工具/技能权限提示词

```python
md_output.append("# Agent角色\n")
# 角色背景
agent_role_prompt = self.get_agent_role_prompt(agent_state)  # 不包含标题的md格式文本
md_output.append(f"## 你的角色信息 agent_role\n"
                 f"{agent_role_prompt}\n")
# 工具与技能权限
available_skills_and_tools = self.get_skill_and_tool_prompt(agent_state["skills"],agent_state["tools"])  # 包含###三级标题的md
md_output.append(f"## 角色可用技能与工具 available_skills_and_tools\n"
                 f"{available_skills_and_tools}\n")
```

**执行器基类函数名：**get_agent_role_prompt

**作用：**从`agent_state`中获取`name`，`role`，`profile`属性信息并组装



**执行器基类函数名：**get_skill_and_tool_prompt

**作用：**

根据`agent_state`中的技能与工具权限列表，获取技能与工具的使用引导，并返回markdown格式提示词：

```markdown
## 角色可用技能与工具 available_skills_and_tools
### 可用技能skills
- **<skill_name>**: <skill_prompt>
- **<skill_name>**: <skill_prompt>

### 可用工具tools
- **<tool_name>**: <tool_prompt>
- **<tool_name>**: <tool_prompt>
```

其中使用`load_skill_config`获取技能提示，使用`load_tool_config`获取工具提示。
这两个方法会各自调用相应的配置文件，获取`use_guide.description`字段的值



### 5.3 技能步骤提示词

获取当前需要执行的技能的步骤信息

```python
md_output.append(f"# 当前需要执行的步骤 current_step\n")
current_step = self.get_current_skill_step_prompt(step_id, agent_state)  # 不包含标题的md格式文本
md_output.append(f"{current_step}\n")
```

**执行器基类函数名：**get_current_skill_step_prompt

**作用：**组装Agent当前执行的技能Step的提示词

1.当前步骤的简要意图：

​	获取当前`step_state`中`step_intention`属性值

2.从step.text_content获取的具体目标：

​	获取当前`step_state`中`text_content`属性值

3.技能规则提示：

​	获取对应技能配置文件的`use_prompt.skill_prompt`和`use_prompt.return_format`字段值



### 5.4 工具步骤提示词

获取当前需要进行指令生成的工具步骤的工具调用提示

```python
md_output.append(f"# 生成实际工具调用指令的提示 tool_step\n")
tool_prompt = self.get_tool_instruction_generation_step_prompt(step_id, agent_state)  # 不包含标题的md格式文本
md_output.append(f"{tool_prompt}\n")
```

**执行器基类函数名：**get_tool_instruction_generation_step_prompt

**作用：**组装Agent指令生成步骤的目标工具Step的提示词

1.通过当前指令生成的步骤ID查找下一个工具Step：

​	使用`get_next_tool_step`获取

2.当前工具步骤的简要意图：

​	获取工具`step_state`中`step_intention`属性值

3.从step.text_content获取的具体目标：

​	获取工具`step_state`中`step_intention`属性值

4.工具规则提示：

​	获取对应工具配置文件的`use_prompt.tool_prompt`和`use_prompt.return_format`字段值



### 5.5 持续性记忆提示词

获取持续性记忆的使用说明，获取持续性记忆的具体内容

```python
md_output.append("# 持续性记忆persistent_memory\n")
# 获取persistent_memory的使用说明
base_persistent_memory_prompt = self.get_base_prompt(key="persistent_memory_prompt")  # 不包含标题的md格式文本
md_output.append(f"## 持续性记忆使用规则说明：\n"
                 f"{base_persistent_memory_prompt}\n")
# persistent_memory的具体内容
persistent_memory = self.get_persistent_memory_prompt(agent_state)  # 不包含标题的md格式文本
md_output.append(f"## 你已有的持续性记忆内容：\n"
                 f"{persistent_memory}\n")
```

**执行器基类函数名：**get_base_prompt

**作用：**传入system_prompt，从`mas/agent/base/base_prompt.yaml`中获取`key=“persistent_memory_prompt”`的值



**执行器基类函数名：**get_persistent_memory_prompt

**作用：**从`agent_state`中获取`persistent_memory`字段值



### 5.6 历史step执行结果

获取当前Stage下所有历史的step的执行结果，作为提示词

```python
md_output.append(f"# 历史已执行步骤 history_step\n")
history_steps = self.get_history_steps_prompt(step_id, agent_state)  # 不包含标题的md格式文本
md_output.append(f"{history_steps}\n")
```

**执行器基类函数名：**get_history_steps_prompt

**作用：**获取当前stage_id下所有step信息，并将其结构化组装。

通常本方法应用于reflection，summary技能中。读取step的信息一般都会以str呈现，使用json.dumps()来处理步骤中execute_result与instruction_content。



### 5.7 添加Step

为agent_step的列表中添加多个Step，

```python
self.add_step(planned_step, step_id, agent_state)  # 将规划的步骤列表添加到AgentStep中
```

**执行器基类函数名：**add_step

**作用：**将接收到的planned_step构造为一个个StepState实例，添加到agent_step中，并记录在工作记忆中

```python
for step in planned_step:
    # 构造新的StepState
    step_state = StepState(
        task_id=current_step.task_id,
        stage_id=current_step.stage_id,
        agent_id=current_step.agent_id,
        step_intention=step["step_intention"],
        step_type=step["type"],
        executor=step["executor"],
        text_content=step["text_content"]
    )
    # 添加到AgentStep中
    agent_step.add_step(step_state)
    # 记录在工作记忆中
    agent_state["working_memory"][current_step.task_id][current_step.stage_id,].append(step_state.step_id)
```

接受planned_step格式为`List[Dict[str:str]]`：

```python
[
    {
        "step_intention": "获取当前时间",
        "type": "tool",
        "executor": "time_tool",
        "text_content": "获取当前时间"
    },
    ...
]
```





## 6. AgentBase 基础Agent方法

基础Agent类，定义各基础模块的流转逻辑



整体分为两个部分，执行线程和任务管理线程

- 执行
    
    action方法只负责不断地执行执行每一个step，有新的step就执行新的step。
    
    action方法执行step时不会区分是否与当前stage相关，只要在agent_step.todo_list中就会执行。
    执行线程保证了Agent生命的自主性与持续性。
    
- 任务管理
    
    任务管理用于管理任务进度，保证Agent的可控性。所有的任务管理都通过消息传递，Agent会使用receive_message接收。
    
    receive_message方法：Agent接收和处理来自其他Agent的不可预知的消息，提供了Agent之间主动相互干预的能力。该方法最终会根据是否需要回复消息走入两个不同的分支，process message分支和send message分支

### 6.1 Action

不断从 agent_step.todo_list 获取 step_id 并执行 step_action

agent_step.todo_list 是一个queue.Queue()共享队列，用于存放待执行的 step_id对 todo_list.get() 到的每个step执行step_action()



### 6.2 Receive Message



process_message方法:

根据解析出的指令的不同进入不同方法

start_stage方法: 当一个任务阶段的所有step都执行完毕后，帮助Agent建立下一个任务阶段的第一个step: planning_step）。
