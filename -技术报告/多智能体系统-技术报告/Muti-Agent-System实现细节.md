## 0. 前言

本文目的是希望读者在不阅读源代码及其注释的情况下也能知悉Muti-Agent System的具体实现方式



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
	对每个Agent而言，可能同时参与多个任务群组。一个任务群组只专注于一个任务（一个完整任务流程），当任务完成时，该群组解散。

	特殊情况（MAS中的第一个Task）：
	MAS初始化时必须创建一个任务，以此为Agent提供初始活动空间，该任务名为"MAS基础任务进程"。
	该任务群组会包含管理Agent，这些Agent专门负责帮助人类创建和管理新的任务。
	该任务保证了管理Agent能够持续获取来自人类操作员的指令，一般该"MAS基础任务进程"永不结束。

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
    MAS中的某个拥有任务管理权限的Agent接到需求后，会将需求转化为明确的任务目标，在SyncState中创建一个相应的TaskState。
    该任务所绑定的管理Agent需要首先为任务添加相关的Agent，这些Agent在一个任务中组成了一个Task Group任务群组。
    其次管理Agent会将总任务目标合理地拆分成阶段目标，并为每个阶段目标分配相应的Agent去执行。

- 2.Stage
    Task中的多个Stage是串行执行的，一个Stage完成后，Task Group中的管理Agent会根据当前Stage的完成情况，决定下一个Stage的执行情况。
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
    Agent间通信需要由一方主动发起。发起方会通过执行 `send message` 技能，向接收方发送一条message。
    - 如果这条message是需要回复的，则接收方Agent的`step`列表中会被追加一个 `send message` step，用于向发起方发送回复消息。
    - 如果这条消息是不需要回复的，则接收方Agent的`step`列表中会被追加一个 `process message` step，用于确保处理该消息内容。
    因此，如果是一个单向消息，则通过Send Message和Process Message可以完成；
    如果是长期多轮对话，则通过一系列的Send Message和最后一个Process Message实现。

    特殊机制-步骤锁：
    在Agent通信中，如果发起方认为需要等待该消息的回复，则会为自身添加步骤锁。直到接受到该次消息的回复，自身都不再进行任何步骤的执行。

### Task State
本小节将简要介绍 task_state 涉及的字段

属性:
    task_id (str): 任务ID，用于标识一个任务的唯一ID
    task_name (str): 一个任务简介的名称，向人类使用者提供基本的信息区分
    task_intention (str): 任务意图, 较为详细的任务目标说明
    task_manager (str): 任务管理者Agent ID，负责管理这个任务的Agent ID

    task_group (list[str]): 任务群组，包含所有参与这个任务的Agent ID
    shared_info_pool (List[Dict]): 任务群组共享消息池（可选结构：包含agent_id, role, content等），主要记录行为Action
    communication_queue (queue.Queue): 用于存放任务群组的通讯消息队列，Agent之间相互发送的待转发的消息会被存放于此
    shared_conversation_pool (List[Dict[str, Message]]): 任务群组共享会话池（Message），主要记录会话Message

    stage_list (List[StageState]): 当前任务下所有阶段的列表（顺序执行不同阶段）
    execution_state (str): 当前任务的执行状态，"init"、"running"、"finished"、"failed"
    task_summary (str): 任务完成后的总结，由SyncState或调度器最终生成

说明:
共享消息池是各个Agent完成自己step后同步的简略信息，且共享消息池的信息所有Agent可主动访问，但是不会一有新消息就增量通知Agent。Agent可以不感知共享消息池的变化。
通讯消息队列是Agent之间相互发送的待转发的消息，里面存放的是Agent主动发起的通讯请求，里面必然包含需要其他Agent及时回复/处理的消息。

### Stage State
本小节将简要介绍 stage_state 涉及的字段

属性:
    task_id (str): 任务ID，用于标识一个任务的唯一ID
    stage_id (str): 阶段ID，用于标识一个阶段的唯一ID

    stage_intention (str): 阶段的意图, 由创建Agent填写(仅作参考并不需要匹配特定格式)。例如：'Extract contract information and archive it...'
    agent_allocation (Dict[<agent_id>, <agent_stage_goal>]):
        阶段中Agent的分配情况，key为Agent ID，value为Agent在这个阶段职责的详细说明

    execution_state (str): 阶段的执行状态
        "init" 初始化（阶段状态已创建）
        "running" 执行中
        "finished" 已完成
        "failed" 失败（阶段执行异常终止）

    every_agent_state (Dict[<agent_id>, <agent_state>]): 涉及到的每个Agent在这个阶段的状态
        "idle" 空闲
        "working" 工作中
        "finished" 已完成
        "failed" 失败（agent没能完成阶段目标）
        这里的状态是指Agent在这个阶段的状态，不是全局状态

    completion_summary (Dict[<agent_id>, <completion_summary>]): 阶段中每个Agent的完成情况

## Agent内部工作流
Agent内部工作流程是Agent在执行一个阶段的目标时，如何规划并执行多个Step以完成该目标。
Agent内部工作流是多Agent系统(MAS)的重要组成部分, 它是Agent**自主决定自身工作逻辑与自主决定使用什么工具与技能**的重要实现方式之一。

单个Agent内部通过不断顺序执行一个个step从而完成一次次操作action。
Agent通过planning步骤与reflection步骤来为自己增加新的step与调整已有的step。
每一个step执行一个具体的操作，包括调用一个技能或工具，或者发送消息给其他Agent。

**skill**
技能的定义是所有由LLM驱动的具体衍生能力。其主要区别在于提示词的不同，且是随提示词的改变而具备的特定衍生能力。
技能库包括包括规划 `planning`、反思 `reflection`、总结 `summary` 、快速思考 `quick_think` 、指令生成 `instruction_generation` 等 。

**tool**
工具的定义是LLM本身所不具备的能力，而通过访问Agent外部模块接口实现的一系列功能。相比于技能，工具更接近现实世界的交互行为，能够获取或改变Agent系统外的事物。
工具库包括搜索引擎 `search_engine` 等。

### Step State
step_state是由Agent生成的最小执行单位。包含LLM的文本回复（思考/反思/规划/决策）或一次工具调用。
本小节将简要介绍 step_state 涉及的字段

属性:
    task_id (str): 任务ID，用于标识一个任务的唯一ID
    stage_id (str): 阶段ID，用于标识一个阶段的唯一ID
    agent_id (str): Agent ID，用于标识一个Agent的唯一ID
    step_id (str): 步骤ID，用于标识一个步骤的唯一ID，自动生成
    step_intention (str): 步骤的意图, 由创建Agent填写(仅作参考并不需要匹配特定格式)。例如：\"ask a question\", \'provide an answer\', \'use tool to check...\'

    type (str): 步骤的类型,例如：'skill', 'tool'
    executor (str): 执行该步骤的对象，如果是 type 是 'tool' 则填工具名称，如果是 'skill' 则填技能名称
    execution_state (str): 步骤的执行状态：
        'init' 初始化（步骤已创建）
        'pending' 等待内容填充中（依赖数据未就绪），一般情况下只出现在工具指令填充，技能使用不需要等待前一步step去填充 TODO:工具step是否需要这个状态
        'running' 执行中
        'finished' 已完成
        'failed' 失败（步骤执行异常终止）

    text_content (str): 文本内容，对step_intention详细而具体的描述，一般由前面步骤的LLM生成
      	- 如果是技能调用则是填入技能调用的提示文本（不是Skill规则的系统提示，而是需要这个skill做什么具体任务的目标提示文本）
          step中的这个属性是只包含当前步骤目标的提示词，不包含Agent自身属性（如技能与工具权限）的提示词
      	- 如果是工具调用则应当填写该次工具调用的具体详细的目标。
    instruction_content (Dict[str, Any]): 指令内容，如果是工具调用则是具体工具命令
      	- instruction_content一般只在工具调用时使用，在绝大部分step初始化中都不需要填入
          在工具调用前一步的instruction_generation会负责生成具体的工具调用命令。
	execute_result (Dict[str, Any]): 执行结果，如果是文本回复则是文本内容，如果是工具调用则是工具返回结果

### Agent State
agent_state 是 Agent的重要承载体，它是一个字典包含了一个Agent的所有状态信息。
Agent被实例化时需要初始化自己的 agent_state, agent_state 会被持续维护用于记录Agent的基本信息、状态与记忆。
所有Agent使用相同的类，具有相同的方法属性，相同的代码构造。不同的Agent唯一的区别就是 agent_state 的区别。

本小节将简要介绍 agent_state 字典涉及的key。

参数：
	agent_id (str): Agent 的唯一标识符，由更高层级的 Agent 管理器生成。
    name (str): Agent 的名称。
    role (str): Agent 的角色，例如 数据分析师、客服助手 等。
    profile (str): Agent 的角色简介，描述该 Agent 的核心能力。
    
    working_state (str): Agent 的工作状态，例如 idle 空闲, working 工作中, awaiting 等待执行反馈中。
    llm_config (Dict[str, Any]): （仅会存在于LLM-Agent中）LLM（大语言模型）的配置信息
    human_config (Dict[str, Any]): （仅会存在于Human-Agent中）人类操作员的配置信息，包含人类操作员的ID和名称
    
    working_memory (Dict[str, Any]: 
        以任务视角存储 Agent 的工作记忆。  
        结构为 `{<task_id>: {<stage_id>: [<step_id>, ...], ...}, ...}`  
        记录未完成的任务、阶段和步骤，不用于长期记忆。  
    persistent_memory (Dict[str,str]): 
		永久追加的精简记忆，用于记录Agent的持久性记忆，不会因为任务,阶段,步骤的结束而被清空。
		其中key为记录的时间戳，value为对应的文本内容。（md格式纯文本，**里面只能用三级标题及以下！不允许出现一二级标题！**）
    
    agent_step (AgentStep): AgentStep是一个对step_state的管理类，维护一个包含step_state的列表
    step_lock (List[str]):
        一般用于及时通信中的步骤锁机制
        包含多个唯一等待ID的列表，只有列表中所有等待ID都回收后，才执行下一个step，否则会步骤锁会一直暂停执行下一个step
  
    tools (List[str], 可选): Agent 可用的工具列表，例如 `['搜索引擎', '计算器']`，默认为空列表。
    skills (List[str], 可选): Agent 可用的技能列表，例如 `['文本摘要', '图像识别']`，默认为空列表。
    
    conversation_pool (List[Dict[str, Any]], 可选): （仅会存在于Human-Agent中）Agent 的对话池，记录与其他 Agent 或人类的对话内容。
```



### 1.2 Message Dispatcher

消息分发类，一般实例化在MAS类中，与SyncState和Agent同级，用于消息分发。

它会遍历所有 TaskState 的消息队列 `task_state.communication_queue`，捕获到消息后：

1. 将消息分发给对应的 Agent（会调用agent.receive_message方法来处理消息）
2. 记录该成功分发的消息到任务会话池中（追加到task_state.shared_conversation_pool中）



### 1.3 MultiAgentSystem

MultiAgentSystem 多Agent系统（简称MAS）的核心类，负责管理所有Agent的生命周期和状态同步。

该类实例化三个上层组件：

- 状态同步器
    首先在MultiAgentSystem类中创建一个与Agent实例平级的sync_state，
    以确保sync_state是全局唯一一个状态同步器，同时保证sync_state中的task_state是所有Agent共享的。
- Agent智能体
    MAS类是唯一的 agent 生命周期管理者，所有agent映射由这个类统一提供。
- 消息分发器
    同时实现一个MAS中的消息转发组件，该组件不断地从sync_state.all_tasks中的每个
    task_state.communication_queue中获取消息，并向指定的Agent发送消息。

同时还额外包含三个特殊组件，这三个特殊组件的目的均是为了Agent能够调用MCP工具：

- AsyncLoopThread

  主要向 MultiAgentSystem 提供异步环境，实现一个用于在多线程环境中运行异步任务的异步事件循环线程。

  由此可以在 MAS 中的 Agent 和 Executor 中向 AsyncLoopThread 提交异步调用任务而不引起额外阻塞。

- MCPClient

  全局唯一的 MCP 客户端，用于执行工具；该客户端在 MAS 初始化时创建，并在 MAS 关闭时关闭。

- MCPClientWrapper

  主要用于在 MAS 中调用 MCPClient 方法，其负责将对 MCPClient 的调用提交到异步事件循环线程 AsyncLoopThread 中。

  由此 MAS 中给每个 Agent 和工具 Executor 传入的就不再是 MCPClient 实例，而是 MCPClientWrapper 包装器，通过调用 MCPClientWrapper 以实现在 MAS 中的异步调用 MCPClient 方法。









#### 1.3.1 启动流程

1. 先启动消息分发器的循环（在一个线程中异步运行）

   后续任务的启动和创建均依赖此分发

2. 添加第一个Agent（管理者）

   Agent在被实例化时就会启动自己的任务执行线程

3. 创建MAS中第一个任务，并启动该任务

   指定MAS中第一个Agent为管理者，并启动其中的阶段

4. 启动状态监控网页服务（可视化 + 热更新）

   状态监控服务server会同时实例化StateMonitor,以装饰器的形式获取MAS中的四种状态

5. 主线程保持活跃，接受来自人类操作端的输入

   人类操作端**（TODO）**



#### 1.3.2 运作方式

在MAS中，我们管理多个Agent，每个Agent在启动的时候初始化自己的一个线程用于循环执行Action。因此整个MAS的结构是 **多线程并行 + 每个线程内部同步逻辑** 。



- **MAS 主线程**：负责初始化系统、创建 Agent、启动 Agent 的线程。

- **每个 Agent**：有自己的 `threading.Thread`，在 `action()` 循环中同步执行任务（顺序处理 Steps）。

- **Agent 与 Agent**之间的执行是**并行的**，因为它们在不同线程中运行。

- **Agent 内部**：Action 循环是同步的，不使用 `async/await`，所以每个 Agent 在执行具体 Executor 调用时会阻塞当前线程，直到 Executor 返回结果。以此实现顺序执行一个个 Step。



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

- task_name (str):

  一个任务简介的名称，向人类使用者提供基本的信息区分

- task_intention (str): 

  任务意图, 较为详细的任务目标说明



- task_group (list[str]): 

  任务群组，包含所有参与这个任务的Agent ID

- shared_info_pool (List[Dict]): 

  任务群组共享信息池（可选结构：包含agent_id, role, content等）

  该消息池内容主要存放大家的执行动作记录

- communication_queue (queue.Queue()):

  用于存放任务群组的通讯消息队列，Agent之间相互发送的待转发的消息会被存放于此。待MAS系统的消息处理模块定期扫描task_state的消息处理队列，执行消息传递任务。

- self.shared_conversation_pool (List[Dict[str, Message]]):

  任务群组共享会话池（Message）

  记录的是对话信息，包含所有的消息记录，供Agent展示群聊使用。



- stage_list (List[StageState]):

  当前任务下所有阶段的列表（顺序执行不同阶段）

- execution_state (str): 

  当前任务的执行状态，"init"、"running"、"finished"、"failed"

- task_summary (str): 

  任务完成后的总结，由SyncState或调度器最终生成



#### 2.1.1 Task完成的判定

我们会在SyncState.sync_state中接收到task_instruction的 `finish_stage` 分支中，当 `finish_stage` 后不存在下一个阶段时，触发任务完成判定 `SyncState.check_task_completion` 方法。其中：

使用消息通知管理Agent，要求其对任务完成情况进行判断（使用ask_info获取信息，使用task_manager进行任务交付或任务修正）。

当使用task_manager的finish_task指令时，会更新总结信息到`task_state.summary`中。



注：Task完成后，我们不会设计要求Agent主动向人类操作员进行通知。



#### 2.1.2 判定Task完成失败时的修正

管理Agent会使用task_manager技能尝试为Task添加新的Stage来弥补不满足的条件





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



- on_stage_complete (Optional[Callable]): 

  阶段完成时的回调函数，用于向task_state提交阶段完成情况

  在task_state中添加stage_state时会自动绑定该回调函数，不需要手动传入。




#### 2.2.1 Stage完成的判定 

**Agent**

当执行Agent完成自己被分配的一个Stage内的目标后，会以一个Summary Step结尾。在Summary Step中，该Agent会总结自己Stage的完成情况，通过SyncState.sync_state的 `update_stage_agent_completion` 字段提交到StageState.completion_summary中。

当Stage中所有Agent都提交了完成总结时触发Stage完成判定

**StageState**

当Stage中所有Agent都提交了完成总结时，会使用回调函数 `on_stage_complete` 通知上一级状态task_state

**TaskState**

TaskState中添加的每个StateState都会自动为其 `on_stage_complete` 回调函数绑定具体方法 `self._handle_stage_completion` 

当Stage触发使用该回调函数时，执行`TaskState._handle_stage_completion`方法：

- 构造向任务管理Agent的阶段完成通知消息

  ```python
  message: Message = {
      "task_id": self.task_id,
      "sender_id": "[TaskState系统通知]",
      "receiver": self.task_manager,
      "message": f"[TaskState] 已侦测到阶段 {stage_id} 下所有Agent均已提交完成总结。\n"
                 f"**阶段中各个Agent被分配阶段目标**: {agent_allocation} \n"
                 f"**阶段中各个Agent提交的完成总结**: {completion_data} \n"
                 f"**现在你作为管理Agent需要对该阶段完成情况进行判断**:\n"
                 f"- 如果阶段完成情况满足预期，则使用task_manager技能结束该任务阶段\n"
                 f"- 如果阶段完成情况不满足预期，则使用task_manager和agent_manager技能指导Agent进行相应的调整\n",
      "stage_relative": stage_id,
      "need_reply": False,
      "waiting": None,
      "return_waiting_id": None
  }
  ```

- 将构造好的消息放入任务的通信队列中

  ```python
  self.communication_queue.put(message)
  ```

  



> 后续该消息会经由Message Dispatcher消息分发器分发给该管理Agent。
>
> 阶段完成判定通知的消息会进入该Agent的`receive_message`方法分支中，最终由Agent的process_message技能处理。



#### 2.2.2 判定Stage完成失败时的修正

当判定Stage完成失败时，我们需要管理Agent能够修正失败Stage的阶段目标。一种符合我们MAS设计惯性的方式并非修改当前已经失败的Stage，而是插入一个相同目标但是优化了更详细分配内容和执行细节的Stage去执行，从而达到重试的效果。

当管理Agent在Stage完成判定中判定该Stage完成失败时，管理Agent可以使用task_manager技能中的retry_stage指令——创建一个修正分配情况与阶段目标的新Stage用于重试。

> task_manager的retry_stage指令会由SyncState.sync_state去组装执行，在执行中重试阶段 retry_stage 会创建一个新的相同目标的阶段去执行，达到重试的效果：
>
> > 1.插入新的阶段到任务状态中
> > 	1.1 实例化一个新的StageState
> > 	1.2 插入新的阶段状态到任务状态中
> > 	1.3 如果stage中的agent不在task群组中，则添加到task群组中
> > 	1.4 同步工作记忆到任务参与者
> >
> > 2.将旧阶段的状态设置为"failed"
> > 	2.1 获取旧阶段状态并设置为"failed"
> > 	2.2 向Agent发送结束当前阶段的指令
> >
> > 3.开启新的阶段





### 2.3 Agent State

agent_state 是 Agent的重要承载体，它包含了一个Agent的所有状态信息。

所有Agent使用相同的类，具有相同的方法属性，相同的代码构造。不同Agent的区别仅有 `agent_state` 的不同，可以通过 `agent_state` 还原出一样的Agent 。



| key               | 类型           | 说明                                                         | LLM-Agent | 人类-Agent |
| ----------------- | -------------- | ------------------------------------------------------------ | --------- | ---------- |
| agent_id          | str            | Agent的唯一标识符                                            | 是        | 是         |
| name              | str            | Agent的名称                                                  | 是        | 是         |
| role              | str            | Agent的角色                                                  | 是        | 是         |
| profile           | str            | Agent的角色简介                                              | 是        | 是         |
| working_state     | str            | Agent的当前工作状态；<br /> idle 空闲, working 工作中, waiting 等待执行反馈中 | 是        | 是         |
| llm_config        | Dict[str, Any] | 从配置文件中获取 LLM 配置                                    | 是        | 否         |
| human_config      | Dict[str, Any] | 从配置文件中获取人类账号密码等配置                           | 否        | 是         |
| working_memory    | Dict[str, Any] | Agent工作记忆 {<task_id>: {<stage_id>: [<step_id>,...],...},...} 记录Agent还未完成的属于自己的任务 | 是        | 是         |
| persistent_memory | Dict[str,str]  | 由Agent自主追加的永久记忆，不会因为任务、阶段、步骤的结束而被清空；<br />其中Key为时间戳 `%Y%m%dT%H%M%S`，<br />Value为md格式纯文本（里面只能用三级标题 ### 及以下！不允许出现一二级标题！） | 是        | 是         |
| agent_step        | AgentStep实例  | AgentStep,用于管理Agent的执行步骤列表；<br />（一般情况下步骤中只包含当前任务当前阶段的步骤，在下一个阶段时，上一个阶段的step_state会被同步到stage_state中，不会在列表中留存） | 是        | 是         |
| step_lock         | List[str]      | 一般用于及时通信中的步骤锁机制；<br />包含多个唯一等待ID的列表，只有列表中所有等待ID都回收后，才执行下一个step，否则会步骤锁会一直暂停执行下一个step | 是        | 否         |
| tools             | List[str]      | Agent可用的技能                                              | 是        | 是         |
| skills            | List[str]      | Agent可用的工具                                              | 是        | 是         |
| conversation_pool | Dict[str, Any] | "conversation_groups"记录群聊对话组<br />"conversation_privates"记录一对一私聊对话组<br />"global_messages"记录用于通知人类操作员的全局重要信息 | 否        | 是         |
|                   |                |                                                              |           |            |



#### 2.4.1 工作记忆的更新

Working Memory （Dict[str, Any]）记录Agent还未完成的任务与阶段

向AgentStep中添加步骤/插入步骤时一般调用 `AgentStep.add_step()` 和 `AgentStep.add_next_step()` 。然而AgentStep自身的方法无法为agent_state追加工作记忆。因此需要上一层调用时追加工作记忆。



**执行器 `executor_base` ：**

执行器 `Execuotr.add_step()` 和`Execuotr.add_next_step()` 中添加/插入步骤时记录工作记忆：

```python
agent_state["working_memory"][current_step.task_id][current_step.stage_id,].append(step_state.step_id)  # 记录在工作记忆中
```



**Agent `agent_base` :**

Agent基础类 `AgentBase.add_step()` 和 `Execuotr.add_next_step()` 中添加/插入步骤时记录工作记忆：

```python
self.agent_state["working_memory"][task_id][stage_id].append(step_state.step_id)  # 返回添加的step_id, 记录在工作记忆中
```



Agent基础类 `AgentBase.process_message()` 接收到任务管理指令时，会同步记录工作记忆：

1. finish_stage 结束阶段指令

   ```python
   # 清除相应的工作记忆
   if task_id in self.agent_state["working_memory"]:
       if stage_id in self.agent_state["working_memory"][task_id]:
           del self.agent_state["working_memory"][task_id][stage_id]
   ```

2. finish_task 结束任务指令

   ```python
   # 清除相应的工作记忆
   if task_id in self.agent_state["working_memory"]:
       del self.agent_state["working_memory"][task_id]
   ```

3. update_working_memory 直接增加工作记忆指令

   ```python
   # 指令内容 {"update_working_memory": {"task_id": <task_id>, "stage_id": <stage_id>或None}}
   task_id = instruction["update_working_memory"]["task_id"]
   stage_id = instruction["update_working_memory"]["stage_id"]
   self.agent_state["working_memory"][task_id] = stage_id
   ```





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

  持续记录所有 StepState，即使执行完毕也不会立即被删除，方便后续查询、状态更新和管理。
  
  这里step_list的顺序其实等于实际执行顺序了。



#### 2.4.1 Step的清除机制

与Stage相关的Step会在Agent接收到该Stage的“finish_stage”指令后清除，
与Stage无关的Step会在Agent接收到该Task的“finish_task”指令后清除。



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
| send_shared_info              | 添加共享信息到任务共享消息池                                 |
| update_stage_agent_completion | 更新阶段中Agent完成情况                                      |
| send_message                  | 将Agent.executor传出的消息添加到task_state.communication_queue通讯队列中 |
| task_instruction              | 解析并执行具体任务管理操作：<br />1. 创建任务 add_task<br />2. 为任务创建阶段 add_stage<br />3. 结束任务 finish_task<br />4. 结束阶段 finish_stage<br />5. 重试阶段 retry_stage<br /> |
| agent_instruction             | 解析并执行具体Agent管理操作<br />1. 实例化新的Agent<br />2. 将Agent添加到任务群组中<br /> |
| ask_info                      | 解析并执行具体信息查询操作<br />1. 查看自身所管理的task_state及其附属stage_state的信息<br />2. 查看自身所参与的task_state及参与的stage_state的信息<br />3. 查看指定task_state的信息<br />4. 查看指定stage_stage的信息<br /><br />5. 查看所有可直接实例化的Agent配置信息<br />6. 查看MAS中所有Agent的profile<br />7. 查看Team中所有Agent的profile<br />8. 查看指定task_id的task_group中所有Agent的profile<br />9. 查看指定stage下协作的所有Agent的profile<br />10. 查看指定agent_id或多个agent_id的详细agent_state信息<br /><br />11. 查看MAS中所有技能与工具的详细说明<br /> |
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
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(planning_config["use_prompt"])
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
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    Planning顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
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
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(reflection_config["use_prompt"])
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
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    Reflection顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行Reflection步骤:{shared_step_situation}，"
>    }
>    ```



### 3.3 Summary

**期望作用：**

Agent通过Summary总结并结束自己的一个stage，标志着一个stage的结束。

整理该stage内所有step的信息并通过execute_output同步stage_state.completion_summary中。

**summary技能不允许在Planning时主动使用！！**只能在reflection时主动使用。

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
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(summary_config["use_prompt"])
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
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
>    ```
>



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
>    summary顺利完成时`update_agent_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    **一般情况下，summary标志的Agent完成当前阶段，只有summary可以为every_agent_state更新”finished“，其它步骤完成时都只能更新”working“**
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    summary顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
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
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(instruction_generation_config["use_prompt"])
>
> 4 tool step:（# 一级标题）
>
> ​	4.1 工具step.step_intention 当前步骤的简要意图（## 二级标题）
>
> ​	4.2 工具step.text_content 具体目标（## 二级标题）
>
> ​	4.3 MCP工具调用的基础规则提示（#### 四级标题）
>
> ​	4.4 当前MCP工具的简要描述
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
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
>    ```
>



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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    instruction_generation顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
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
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(think_config["use_prompt"])
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	5.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	5.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
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
>    think顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    think顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行think步骤:{shared_step_situation}，"
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
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(quick_think_config["use_prompt"])
>
> 4 持续性记忆:（# 一级标题）
>
> ​	4.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	4.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
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
>
> 4. 添加步骤完成情况到task_state的共享消息池：
>
>    通过`send_shared_info`字段指导sync_state更新，
>
>    quick_think顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行quick_think步骤:{shared_step_situation}，"
>    }
>    ```





### 3.7 Send Message 

**期望作用：**Agent在MAS系统内部的对另一个Agent实例的单向消息发送。

**说明：**

Send Message首先会判断当前Agent已有的信息是否满足发送消息的条件，即要发送的正确消息内容，当前Agent是否已知。
- 如果存在未获取的信息，不能支撑当前Agent发送消息内容，则会进入"**获取更多信息分支**"。
- 如果当前Agent已有的信息满足发送消息的条件，则会进入"**直接消息发送分支**"。



> **获取更多信息分支：**
>
> 当前Send Message执行时，Agent已有的信息不满足发送消息的条件（由LLM自行判断），进入获取更多信息分支。
> 该分支的主要目的是将Send Message变为一个长尾技能，通过插入追加一个Decision Step来获取更多信息。
> LLM会根据当前Agent已有的信息，判断需要获取哪些更多信息，返回:
>
> ```python
> <get_more_info>
> {
>     "step_intention": "获取系统中XXX文档的XXX内容",  # 获取信息的意图说明
>     "text_content": "我需要获取系统中关于XXX文档的XXX内容，需要精确到具体的XXX信息，以便我可以完成后续的消息发送。",  # 获取信息的详细描述
> }
> </get_more_info>
> ```
>
> 我们会根据LLM返回的内容，追插入一个对应属性的Decision Step
> 和与当前Send Message属性相同Send Message Step到当前Agent的步骤列表中。
> (于`construct_decision_step_and_send_message_step`方法中构造)



> **直接消息发送分支：**
>
> Send Message会获取当前stage所有step执行情况的历史信息，使用LLM依据当前send_message_step意图进行汇总后，向指定Agent发送消息。
>
> Send Message 首先需要构建发送对象列表。[<agent_id>, <agent_id>, ...]
> 其次需要确定发送的内容，通过 Send Message 技能的提示+LLM调用返回结果的解析可以得到。
> 需要根据发送的实际内容，LLM需要返回的信息:
>
> ```python
> <send_message>
> {
>     "receiver": ["<agent_id>", "<agent_id>", ...],
>     "message": "<message_content>",  # 消息文本
>     "stage_relative": "<stage_id或no_relative>",  # 表示是否与任务阶段相关，是则填对应阶段Stage ID，否则为no_relative的字符串
>     "need_reply": <bool>,  # 需要回复则为True，否则为False
>     "waiting": <bool>,  # 等待回复则为True，否则为False
> }
> </send_message>
> ```
>



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
     
     

4. 消息等待机制与Agent步骤锁

   如果发送者需要等待回复，则为所有发送对象填写唯一等待标识ID。不等待则为 None。

   如果等待，则发起者将在回收全部等待标识前不会进行任何步骤执行。

   


   一般情况下，由Agent自主规划的Send Message的消息传递均是与任务阶段相关的，因此在发送消息时需要指定stage_id。



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
> 2. llm调用
> 3. 解析llm返回的消息内容
>
> 如果进入 直接消息发送 分支：
>
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
>
> 5. 如果发送消息需要等待回复，则触发步骤锁机制
>
> 6. 返回用于指导状态同步的execute_output
>
> 如果进入 获取更多信息 分支：
>
> 4. 解析persistent_memory并追加到Agent持续性记忆中
> 5. 构造插入的Decision Step与Send Message Step，插入到Agent的步骤列表中
> 6. 返回用于指导状态同步的execute_output



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
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(send_message_config["use_prompt"])
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	5.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	5.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. **直接消息发送分支：**将LLM初步消息体转换为MAS通用消息体，并添加待处理消息到task_state.communication_queue：
>
>    通过`send_message`字段指导sync_state更新，
>
>    ```python
>    # 构造execute_output，中标准格式的消息
>    execute_output["send_message"]:Message = {
>        "task_id": task_id,
>        "sender_id": agent_state["agent_id"],
>        "receiver": send_message["receiver"],
>        "message": send_message["message"],
>        "stage_relative": send_message["stage_relative"],
>        "need_reply": send_message["need_reply"],
>        "waiting": send_message["waiting"],
>        "return_waiting_id": return_waiting_id,
>    }
>    ```
>
>    最终execute_output["send_message"]符合Message格式。
>
>    其中 send_message["waiting"] 字段在execute中使用get_execute_output方法前就已经通过代码自动为每个receiver生成唯一等待标识ID，完成了从 bool 到 optional[list[str]] 的转换。
>
>    其中 return_waiting_id 从step.text_content中提取（如果存在return_waiting_id ，Agent生成该step时会将其放入该位置）：
>
>    ```python
>    return_waiting_id = self.extract_return_waiting_id(step_state.text_content)
>    ```
>
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
>    ```
>
> 3. **直接消息发送分支：**如果发送的消息需要等待回复，则触发Agent步骤锁：
>
>    为消息中的每个receiver生成唯一等待标识ID，并将其全部添加到步骤锁中。在Agent回收全部标识ID（收到包含标识ID的信息）前，步骤锁一直生效，暂停后续step的执行。
>
>    ```python
>    if message["waiting"]:
>    	waiting_id_list = [str(uuid.uuid4()) for _ in message["receiver"]]
>    	agent_state["step_lock"].extend(waiting_id_list)
>    ```
>
> 4. **获取更多信息分支：**构造插入的Decision Step与Send Message Step，插入到Agent的步骤列表中：
>
>    通过`construct_decision_step_and_send_message_step`将LLM输出指令构造成步骤添加指令，构造相应意图与说明的Decision Step和一个与当前Send Message一致的Send Message Step。
>
>    `construct_decision_step_and_send_message_step()`：
>
>    ```python
>    # 获取当前步骤的状态
>    current_step = agent_state["agent_step"].get_step(step_id)[0]
>    # 构造Decision Step与Send Message Step
>    decision_step = {
>        "step_intention": instruction["step_intention"],
>        "type": "skill",
>        "executor": "decision",
>        "text_content": instruction["text_content"]
>    }
>    send_message_step = {
>        "step_intention": current_step.step_intention,
>        "type": "skill",
>        "executor": "send_message",
>        "text_content": current_step.text_content
>    }
>    return [decision_step, send_message_step]
>    ```
>
>    将构造的decision和send_message插入到Agent的步骤列表中：
>
>    ```python
>    self.add_next_step(step_list, step_id, agent_state)
>    ```
>



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    **直接消息发送分支：**
>
>    ```python
>    execute_result = {"send_message": send_message}
>    step.update_execute_result(execute_result)
>    ```
>
>    **获取更多信息分支：**
>
>    ```python
>    execute_result = {"get_more_info": instruction}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    send_message顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    send_message顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行Send Message步骤:{shared_step_situation}，"
>    }
>    ```





### 3.8 Process Message

**期望作用：**Agent处理MAS内部来自另一个Agent实例的单项消息，且该消息明确不需要回复。

**说明：**

接收到消息后，Agent会使用process_message step，调用llm来处理消息的非指令部分

（指令部分在agent_base中process_message方法中处理），

一般情况下意味着该消息需要被LLM消化并整理，也有可能仅仅作为多轮对话的结尾。

> 在AgentBase类中的process_message方法主要用于处理message中的指令部分，依照指令进行实际操作。
>
> 在技能库中的ProcessMessageSkill主要用于让LLM理解并消化消息的文本内容。
>



Process Message会理解并消化不需要回复的消息内容，并在必要时刻能够对消息内容做出与环境交互上的反应:
- 如果判断不需要对消息内容做出行为反应，则会消化理解消息内容，并记录重要部分到持续性记忆中

- 如果判断需要对消息内容做出行为反应，则会额外执行"行为反应"分支。

  > 该分支的主要目的是赋予Process Message能够产生与环境交互行为的能力，通过插入追加一个Decision Step来规划接下来的短期反应行为的步骤。LLM会根据自己判断的需要做出交互的行为，返回指令:
  >
  > ```python
  > <react_action>
  > {
  >     "step_intention": "规划获取帮助文档指定信息的步骤",
  >     "text_content": "接收到来自管理Agent的消息，要求我按照'帮助文档'的内容来执行手中的合同审查任务。我需要规划一些步骤来获取帮助文档中的相关信息。其中帮助文档位于......",
  > }
  > </react_action>
  > ```
  >
  > 我们会根据LLM返回的指令内容，追加插入一个对应属性的Decision Step到当前Agent的步骤列表中。



**提示词顺序：**

> Message内容可能包含md标题，为了防止与其他提示的md标题形成标题冲突，因此得调整提示词顺序。

系统 → 角色 →目标 → 记忆 → （规则）



**具体实现：**

> 1. 组装预提示词
> 2. 组装消息处理步骤提示词
> 3. llm调用
> 4. 解析llm返回的理解内容
> 5. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 6. 如果解析到行为反应指令，则追加插入一个Decision Step到当前Agent的步骤列表中
> 7. 返回用于指导状态同步的execute_output



**预提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​	2.1 Agent角色背景提示词（## 二级标题）
>
> ​	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 历史步骤执行结果（# 一级标题）
>
> 4 持续性记忆:（# 一级标题）
>
> ​	4.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	4.2 Agent持续性记忆内容提示词（## 二级标题）



**消息处理步骤提示词：**

> 1 process_message step:
>
> ​	1.1 step.step_intention 当前步骤的简要意图
>
> ​	1.2 step.text_content 接收到的消息内容
>
> ​	1.3 技能规则提示(process_message_config["use_prompt"])



**交互行为：**

> 1. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
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
>    process_message顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    process_message顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行process_message步骤:{shared_step_situation}，"
>    }
>    ```





### 3.9 Task Manager

**期望作用：**Agent对任务的管理与调度。（一种特殊权限的技能，一般只有管理者Agent拥有）

**说明：**

Task Manager会参考自身历史步骤信息（前面步骤获取任务信息与阶段信息），生成用于管理任务进程的指令。

任务管理者Agent会通过该技能生成相应操作的指令，指令会再MAS系统中操作对应组件完成实际行动。

例如通过SyncState操作task_state与stage_state,通过send_message形式通知相应Agent。



1. 发起一个Task:

    创建任务 add_task。

    该操作会创建一个 task_state,包含 task_intention 任务意图

    

2. 为任务分配Agent与阶段目标:

   为任务创建阶段 add_stage。

   该操作会为 task_state 创建一个或多个 stage_state,

   包含 stage_intention 阶段意图与 agent_allocation 阶段中Agent的分配情况。



3. 任务判定已完成，交付任务:

   结束任务 finish_task。

   该操作会将 task_state 的状态更新为 finished 或 failed，并通知task_group中所有Agent。

   同时该操作需要管理Agent生成任务总结信息。



4. 任务阶段判定已结束，进入下一个任务阶段:

   结束阶段 finish_stage。

   该操作会将 stage_state 的状态更新为 finished

   对该阶段进行交付，阶段完成进入下一个阶段。

   

5. 阶段失败后的重试:

   重试执行失败的阶段 retry_stage。

   该操作首先会更新旧阶段状态为"failed"，然后根据经验总结创建一个更好的相同的新阶段用于再次执行。

   （旧的失败阶段状态会保留，我们会插入一个修正后的相同目标的新阶段，并立即执行该阶段。）



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
> 2. llm调用
> 3. 解析llm返回的指令构造
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
> 3 task_managerstep:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(task_manager_config["use_prompt"])
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	5.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	5.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 包含多种不同任务操作行为，由sync_state完成任务指令的解析与具体执行：
>
>    通过`task_instruction`字段指导sync_state更新，
>
>    ```python
>    # 在指令中添加自身agent_id
>    task_instruction["agent_id"] = agent_state["agent_id"]
>    execute_output["task_instruction"] = task_instruction
>    ```
>
>    此时task_instruction中包含"agent_id","action"和其他具体操作指令涉及的字段。
>
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"task_instruction": task_instruction}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    task_manager顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    task_manager顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行task_manager步骤:{shared_step_situation}，"
>    }
>    ```



### 3.10 Agent Manager

**期望作用：** Agent对其他Agent的操控与调度。（一种特殊权限的技能，一般只有管理者Agent拥有）

**说明：**

Agent Manager会参考自身历史步骤信息（前面步骤获取相关Agent信息），生成用于操控其他Agent的指令。任务管理者Agent会通过该技能生成相应操作的指令，指令会在MAS系统中操作对应组件完成实际行动。



1. 创建一个新Agent:

   实例化一个新的Agent init_new_agent

   该操作会有管理Agent自主创建一个新Agent实例

   通过在SyncState中调用MultiAgentSystem的add_agent方法实现

2. 将Agent添加到任务中:

   添加agent到任务群组中 add_task_participant

   该操作会为指定任务添加Agent，Agent会被添加到该任务的任务群组task_group中

   所有参与该任务的Agent都应当存在于该任务的任务群组中



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词
>     
> 2. llm调用
> 3. 解析llm返回的指令构造
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
> 3 agent_manager step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(agent_manager_config["use_prompt"])
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	5.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	5.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 包含多种不同任务操作行为，由sync_state完成任务指令的解析与具体执行：
>
>    通过`agent_instruction`字段指导sync_state更新，
>
>    ```python
>    # 在指令中添加自身agent_id
>    agent_instruction["agent_id"] = agent_state["agent_id"]
>    execute_output["agent_instruction"] = agent_instruction
>    ```
>
>    此时agent_instruction中包含"agent_id","action"和其他具体操作指令涉及的字段。
>
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"agent_instruction": agent_instruction}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    agent_manager顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    task_manager顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行agent_manager步骤:{shared_step_situation}，"
>    }
>    ```



### 3.11 Ask Info

**期望作用：**Agent通过Ask Info获取自身以外的系统/任务信息或其他Agent信息

**说明：**

Ask Info向Agent提供了查看自身以外的信息的能力包括其他Agent的profile及状态，
由SyncState帮助收集上级stage_state，task_state等信息，使用Message传递回Agent。

我们通过提示词约束LLM以特定格式返回获取相应信息的特定指令，通过这些特定指令指导SyncState进行特定查询操作，查询结果通过Message消息传递回Agent。



> 技能支持的查询选项有：
>    1. 查看自身所管理的task_state及其附属stage_state的信息
>
>    2. 查看自身所参与的task_state及参与的stage_state的信息
>
>    3. 查看指定task_state的信息
>
>    4. 查看指定stage_stage的信息
>
>          
>
>    5. 查看可直接新实例化的Agent配置文件
>
>    6. 查看MAS中所有Agent的profile
>
>    7. 查看Team中所有Agent的profile  TODO：Team未实现
>
>    8. 查看指定task_id的task_group中所有Agent的profile
>
>    9. 查看指定stage下协作的所有Agent的profile
>
>    10. 查看指定agent_id或多个agent_id的详细agent_state信息
>           
>11. 查看MAS中所有技能与工具



Ask Info本质上是一种的特殊消息发送技能，它起两个作用

- 向Agent提供信息查询选项

- 向SyncState传递信息查询指令

SyncState接收到消息查询指令后立刻回复消息给Agent，Agent立即使用process_message step来接收。因此，Ask Info技能需要实时性，Ask Info会触发等待通信的步骤锁，直到收到返回消息（执行process_message step）



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词:
> 2. llm调用
> 3. 解析llm返回的查询信息
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 必定触发通信等待的步骤锁
> 6. 返回用于指导状态同步的execute_output



**提示词：**

> 1 MAS系统提示词（# 一级标题）
> 2 Agent角色:（# 一级标题）
> 	2.1 Agent角色背景提示词（## 二级标题）
> 	2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
> 3 ask_info step:（# 一级标题）
> 	3.1 step.step_intention 当前步骤的简要意图
> 	3.2 step.text_content 具体目标
> 	3.3 技能规则提示(ask_info_config["use_prompt"])
> 4 持续性记忆:（# 一级标题）
> 	4.1 Agent持续性记忆说明提示词（## 二级标题）
> 	4.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 丰富LLM生成的初步指令调用信息：
>
>    通过`ask_info`字段指导sync_state更新，
>
>    ```python
>    ask_instruction["sender_id"] = sender_id
>    ask_instruction["sender_task_id"] = sender_task_id
>    # 将添加了发送者ID和发送者任务ID的查询指令放入输出的ask_info字段中
>    execute_output["ask_info"] = ask_instruction
>    ```
>
>    此时查询指令结构：
>
>    ```python
>    execute_output["ask_instruction"] = {
>      "type":"<不同查询选项>",
>      "waiting_id":"<唯一等待标识ID>",
>      "sender_id":"<查询者的agent_id>"
>      "sender_task_id":"<查询者的task_id>"
>      ...
>    }
>    ```
>
>    该指令结构会在SyncState组件中触发具体查询行为：
>
>    > 在SyncState中根据不同的查询指令的"type"值查询不同结果，并构造包含等待标识ID的消息体：
>    >
>    > ```python
>    > message: Message = {
>    >     "task_id": ask_info["sender_task_id"],  # 发送者所处的任务
>    >     "sender_id": ask_info["sender_id"],  # 发送者
>    >     "receiver": [ask_info["sender_id"]],  # 接收者
>    >     "message": "\n".join(return_ask_info_md),  # 返回md格式的查询结果
>    >     "stage_relative": "no_relative",
>    >     "need_reply": False,
>    >     "waiting": None,
>    >     "return_waiting_id": ask_info["waiting_id"]  # 返回唯一等待标识ID
>    > }
>    > ```
>    >
>    > 以向Agent追加process_message step的形式，返回查询结果。
>
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
>    ```
>
> 3. 必定触发Agent步骤锁：
>
>    生成唯一等待标识ID，直到SyncState回复消息中包含该ID（Agent回收步骤锁后），Agent才可进行后续step执行。
>
>    ```python
>    waiting_id = str(uuid.uuid4())
>    agent_state["step_lock"].append(waiting_id)  
>    ask_instruction["waiting_id"] = waiting_id
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"ask_instruction": ask_instruction}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    ask_info顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    ask_info顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行Ask Info步骤:{shared_step_situation}，"
>    }
>    ```



### 3.12 Tool Decision

**期望作用：**Agent通过Tool Decision处理长尾工具的返回结果，并决定下一步该工具的执行或是结束长尾工具调用。

**说明：**

该技能会调用LLM接收并处理长尾工具的返回结果，并决定下一步该工具的调用的方向（指导指令生成步骤）或是结束长尾工具调用。如果该技能不终止继续调用工具，则该技能能够为Agent追加一个Instruction Generation和一个该工具步骤。

如果工具返回结果需要向LLM确认，并反复多次调用该工具的，这种情况为工具的长尾调用。同一个工具的连续多次调用，需要由LLM不断判断每一步工具使用的方向。

长尾工具会在工具步骤执行后将工具返回结果经由SyncState以消息的方式,让Agent追加一个Tool Decision来决策工具否继续调用及如何继续调用。因此：**Tool Decision技能不允许在Planning/Reflection时由Agent主动使用！！**只能由长尾工具主动触发。



因此多次调用的长尾工具:

以InstructionGeneration开始，以ToolDecision结尾，其中可能包含多次(指令生成-工具执行)的步骤。

```python
[I.G.] -> [Tool] -> [ToolDecision] -> [I.G.] -> [Tool] -> [ToolDecision] -> ...
```



> 在该技能中，LLM需要获取足够进行决策判断的条件:
>
> 1. 工具最初调用的意图
>
>    工具最初的调用意图放在和工具的历史调用结果一并获取，executor_base.get_tool_history_prompt
>
> 2. 工具当次调用的执行结果
>
>    由长尾工具在执行后将工具返回结果通过execute_output传出，使用"need_tool_decision"字段，SyncState会捕获该字段内容。
>    need_tool_decision字段需要包含：
>        "task_id" 指导SyncState构造的消息应当存于哪个任务消息队列中
>        "Stage_id" 保证和Stage相关性，可同一清除
>        "agent_id" 指导MessageDispatcher从任务消息队列中获取到消息时，应当将消息发送给谁
>        "tool_name" 指导Agent接收到消息后，追加ToolDecision技能步骤的决策结果应当使用哪个工具
>    注：工具当次调用结果不需要单独传出，由Tool Decision执行时，获取该工具的历史调用结果一并获取即可。
>
> 3. 该长尾工具的历史调用的执行结果和每次调用之间的历史决策
>
>    executor_base.get_tool_history_prompt获取。
>
> 4. 由工具定义的不同决策对应不同格式指令的说明
>
>    Tool Decision不需要知道具体工具指令调用方式，Tool Decision只需要给出下一步工具调用的执行方向。由Instruction Generation根据工具具体提示生成具体工具调用指令。



- 该Tool Decision的触发经过了MAS中的一个经典循环，执行该技能前有：

  Step（具体工具Tool执行）-> SyncState（生成指令消息）-> MessageDispatcher（分发消息给对应Agent）->  Agent（receive_message处理消息）-> Step（插入一个ToolDecision步骤）

  

- 执行该技能后，如果Tool Decision继续工具调用则有：

  Step（ToolDecision技能确认工具继续调用，追加接下来的工具调用步骤）-> Step（InstructionGeneration）-> Step（对应Tool）

  

- 执行该技能后，如果Tool Decision终止工具继续调用则有：

  Step（ToolDecision技能终止工具继续调用）
  
  
  
- 对于MCP工具的长尾调用，一个问题是首次调用返回的MCP工具调用描述capabilities_list_description，该如何通过tool_decision传达给下一个Instruction_Generation?

  我们在tool_decision_config.yaml的提示词中指定其填入工具步骤的 text_content时有：

  ```markdown
  你需要工具在下次调用时完成的具体目标的详细提示文本，如果你已知晓MCP Server返回的capabilities_list_description，你应当在此处指导其MCP Server能力的具体的调用格式（请写入某个能力的返回描述的完整字典）。
  ```

  



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词:
>     
> 2. llm调用
> 3. 解析llm返回的步骤信息，更新AgentStep中的步骤列表
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 返回用于指导状态同步的execute_output



**提示词：**

> 1 MAS系统提示词（# 一级标题）
>
> 2 Agent角色:（# 一级标题）
>
> ​    2.1 Agent角色背景提示词（## 二级标题）
>
> ​    2.2 Agent可使用的工具与技能权限提示词（## 二级标题）
>
> 3 tool_decision step:（# 一级标题）
>
> ​    3.1 step.step_intention 当前步骤的简要意图
>
> ​    3.2 step.text_content 长尾工具提供的返回结果
>
> ​    3.3 技能规则提示(tool_decision_config["use_prompt"])
>
> 4 MCP工具调用基础提示词（# 一级标题）
>
> 5 该工具的历史执行结果（# 一级标题）
>
> 6 持续性记忆:（# 一级标题）
>
> ​    6.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​    6.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 如果继续调用工具，则更新AgentStep中的步骤列表
>
>    ```python
>    self.add_next_step(planned_step, step_id, agent_state)  # 将决策的步骤列表添加到AgentStep中，插队到下一个待执行步骤之前
>    ```
>
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录工具决策结果：
>
>    ```python
>    execute_result = {"tool_decision": tool_decision_step}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    tool_decision顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    tool_decision顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行Tool Decision步骤:{shared_step_situation}，"
>    }
>    ```



### 3.13 Decision

**期望作用：**一种更自由的即时的决策技能。该技能与Stage解耦，不再依赖Stage的状态来进行决策，同时Decision规划的步骤均以插入形式添加而非在末尾追加。

**说明：**

与其他决策技能的区别:
- Decision技能不依赖Stage的状态来进行决策。Decision决策自由度更高，能够更自由的应对非任务相关的决策，例如突发的消息回复
- Decision技能的规划步骤以插入形式添加，而非在末尾追加。Decision决策的步骤优先级更高



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装提示词:
>
> 2. llm调用
> 3. 解析llm返回的步骤信息，更新AgentStep中的步骤列表
> 4. 解析llm返回的持续性记忆信息，插入到Agent的持续性记忆中
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
> 3 decision step:（# 一级标题）
>
> ​	3.1 step.step_intention 当前步骤的简要意图
>
> ​	3.2 step.text_content 具体目标
>
> ​	3.3 技能规则提示(decision_config["use_prompt"])
>
> 4 历史步骤执行结果（# 一级标题）
>
> 5 持续性记忆:（# 一级标题）
>
> ​	5.1 Agent持续性记忆说明提示词（## 二级标题）
>
> ​	5.2 Agent持续性记忆内容提示词（## 二级标题）



**交互行为：**

> 1. 更新AgentStep中的步骤列表，以插入到下一个step之前的形式
>
>    ```python
>    self.add_next_step(decision_step, step_id, agent_state)  # 将规划的步骤列表添加AgentStep中
>    ```
>
> 2. 解析persistent_memory指令内容并应用到Agent持续性记忆中
>
>    ```python
>    instructions = self.extract_persistent_memory(response)
>    self.apply_persistent_memory(agent_state, instructions)
>    ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    ```python
>    execute_result = {"decision_step": decision_step}
>    step.update_execute_result(execute_result)
>    ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    Decision顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    Decision顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行Decision步骤:{shared_step_situation}，"
>    }
>    ```



### 3.14 （TODO）

**期望作用：**



**说明：**



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**



**提示词：**



**交互行为：**



**其他状态同步：**











## 4. Tool 工具

我们所有的工具均以MCP（model context protocol）模型上下文协议的标准实现。为此我们的工具实现包含：

- MCP Client ：实现基础的MCP客户端功能
- MCP Tool Executor ： 负责在MAS系统中调用具体MCP Server的能力的执行器

在此基础上，我们通过在MCP Client中加载各种第三方MCP Server，实现任意工具的高效拓展。



**在MAS系统中调用工具说明**

所有的工具 `tool` 一般都不包含LLM调用，工具的指令生成由专门的技能 `InstructionGeneration` 技能完成。因此一个基本的工具执行包含两个Step：

```python
[InstructionGeneration]->[Tool]
```

如果需要需要反复向LLM确认的，则通过步骤锁+添加新的步骤来实现，这类需要相同工具多次调用的情况被称为工具的长尾调用。

对于工具的**长尾调用**，我们使用 `ToolDecision` 技能来串联：

```python
([I.G.] -> [Tool]) -> [ToolDecision] -> ([I.G.] -> [Tool]) -> ......
```

`ToolDecision` 技能负责调用LLM接收并处理长尾工具的返回结果，并决定下一步该工具的执行（指导指令生成步骤）或是结束长尾工具调用。

长尾工具会在工具步骤执行后通过`execute_output` 指导 `SyncState`生成一个指令消息让 Agent 追加一个 `ToolDecision` 来决策工具否继续调用及如何继续调用。

该工具的历史执行结果由`ToolDecision`主动获取。因此，**工具步骤务必在`execute_result`存放详细调用结果！**



因此：

- 对于单次调用的一般工具

  以 `InstructionGeneration` 开始，以具体工具步骤结尾。

- 对于多次调用的长尾工具

  以 `InstructionGeneration` 开始，以  `ToolDecision` 结尾，其中可能包含多次 “指令生成-工具执行” 的步骤。

  

### 4.1 MCP Client

**基础方法**

我们在 `mas.tools.mcp_client.py` 中实现 `MCPClient` 客户端类，用于向Executor提供MCP Client的相关功能：



- `connect_to_server`: 连接指定的 MCP 服务器

  该方法接受一个 `server_list` 的输入，根据  `server_list`  中的服务器名称，通过其在 MCPClient.server_config 中的配置连接到对应的 MCP 服务器。连接到指定 MCP 服务器，并将连接的服务器实例记录到 MCPClient.server_sessions 中。

  

  尝试连接时兼容本地/远程两种方式：

  - 如果配置中有 "command" 字段，则认为是本地执行的 MCP 服务器，使用 stdio_client 连接。
  - 如果配置中有 "baseurl" 字段，则认为是远程的 MCP 服务器，使用 sse_client 连接。

  

- `get_server_description`: 获取服务器支持的指定能力的详细描述，例如tools/resources/prompts

  该方法接受两个参数的输入：

  - `server_name`:  要获取描述的MCP Server名称
  - `capability_type`: 要获取的能力类型，"tools"、"resources" 或"prompts"


  尝试从server_descriptions中获取对应能力的详细描述。

  - 优先从本地缓存 server_descriptions 获取。
  - 否则通过已连接的MCP Server获取。
      如果server_descriptions中没有该能力的描述，则从server_sessions对应活跃的MCP Server连接中调用能力描述信息。
  - 如果没有连接过服务器，则尝试自动连接再请求描述。
      如果server_sessions中没有对应的MCP Server连接，则从server_config中获取对应的MCP Server配置并连接。



- `use_capability`: 使用指定能力并返回结果

  从 MCPClient.server_sessions 中已连接的对应服务器会话，从中调用server指定能力。该方法接受四个参数的输入：

  - `server_name`:  MCP Server的名称
  - `capability_type`:  能力类型，可以是 "tools"、"resources" 或 "prompts"
  - `capability_name`:  要调用的能力的具体名称
  - `arguments`:  调用能力时需要传入的参数，以字典形式传入

  

  如果没有连接过服务器则会调用 `MCPClient.connect_to_server()` 方法连接服务器

  如果已经已经连接过服务器，则根据能力类型的不同（tools/resources/prompts）使用session中的不同方法进行调用，并返回不同格式内容的结果

  

  **tools 能力类型时：**

  调用方法 `session.call_tool(capability_name, arguments or {})`

  传入参数 `arguments` 字典内容（根据获取的工具描述构造）：

  ```python
  {
      "<PROPERTY_NAME>": PROPERTY_VALUE,
      "<PROPERTY_NAME>": PROPERTY_VALUE,
      ...
  }
  ```

  返回工具结果 `result.content`：

  ```python
  [
      {
          "type": "text",
          "text": "Current weather in New York:\nTemperature: 72°F\nConditions: Partly cloudy"
      }
  ],
  ```

  

  **resources 能力类型时：**

  调用方法 `session.read_resource(arguments.get("uri", ""))`

  传入参数 `arguments` 字典内容（根据获取的资源描述构造）：

  ```python
  {"uri": "<RESOURCE_URI>"}
  ```

  返回工具结果 `result.contents`：

  ```python
  [
    {
      "uri": "test://static/resource/1",
      "name": "Resource 1",
      "title": "Rust Software Application Main File",
      "mimeType": "text/x-rust",
      "text": "Resource 1: This is a plaintext resource"
    }
  ]
  ```

  

  **prompts 能力类型时：**

  调用方法 `session.get_prompt(capability_name)`

  不需要传入任何参数 `arguments`

  返回工具结果 `result.messages`：

  ```python
  [
      {
          "role": "user",
          "content": {
              "type": "text",
              "text": "Please review this Python code:\ndef hello():\n    print('world')"
          }
      }
  ]
  ```

  

  

**状态管理**

为了实现以上三个功能，我们实际对于MCP的连接管理有四种层级的划分（其中一三四级时MCPClient类中维护的状态，第二级是MAS中AgentState中实际可用的工具权限）：



- 第一级：MCPClient.server_config

  存放了MAS中所有支持的MCP Server的启动配置

  

- 第二级：AgentState.tools

  存放了Agent可调用的外部工具（MCP服务）的权限。第二级可用MCP服务是第一级的子集。

  

- 第三级：MCPClient.server_sessions

  存放了活跃的MCP Server连接实例，key为MCP Server名称，value为requests.Session实例。

  server_sessions会动态连接第二级权限包含的MCP Server，并保证MAS中所有Agent的工具权限所涉及到的MCP Server都处于活跃连接状态。

  

  MCPClient.server_sessions 内容如下：

  ```python
  {
      "<SERVER_NAME>": <ClientSession>,  # 连接的 MCP 服务器会话实例
  }
  ```

  

- 第四级：MCPClient.server_descriptions

  存放了MCP Server中可用工具的详细描述，key为工具名称，value为工具描述。

  server_descriptions 会从第三级中活跃session连接中调用工具名称，描述和使用方式并记录。

  在Agent获取全部工具和技能提示词时，server_descriptions 相应支持；在Agent执行具体工具Step/组装工具Step提示词时，server_descriptions 也会提供具体工具的描述和调用格式信息。


  MCPClient.server_descriptions 内容如下：

  ```python
  {
      "<SERVER_NAME>": {
          "capabilities":{
              "prompts": bool,                                          # 是否支持提示词
              "resources": bool,                                        # 是否支持资源
              "tools": bool,                                            # 是否支持工具
          },
          "tools": {                                                    # 如果支持工具，则存储工具描述
              "<TOOL_NAME>": {                                          # 工具名称
                  "description": "<TOOL_DESCRIPTION>",
                  "tittle": "<TOOL_TITLE>",                             # 工具标题
                  "input_schema": {
                      "type": "object",                                 # 工具输入参数类型
                      "properties": {
                          "<PROPERTY_NAME>": {                          # 工具输入参数名称
                              "type": "<PROPERTY_TYPE>",                # 工具输入参数类型
                              "description": "<PROPERTY_DESCRIPTION>",  # 工具输入参数描述
                          },
                          ...                                           # 其他输入参数
                      }
                  },
                  "output_schema": <OUTPUT_SCHEMA>,                     # 工具输出参数的JSON Schema说明（可能类似input_schema），官方文档没有要求该字段，但是在一些实现中确实存在该字段
                  "required": ["<PROPERTY_NAME>", ...]                  # 工具输入参数是否必需
              },
              ...                                                       # 其他工具
          },
          "resources": {                                                # 如果支持资源，则存储资源描述
              "<RESOURCE_NAME>": {                                      # 资源名称
                  "description": "<RESOURCE_DESCRIPTION>",              # 资源描述
                  "title": "<RESOURCE_TITLE>",                          # 资源标题
                  "uri": "<RESOURCE_URI>",                              # 资源URI
                  "mimeType": "<RESOURCE_MIME_TYPE>",                   # 资源MIME类型
              },
              ...                                                       # 其他资源
          },
          "prompts": {                                                  # 如果支持提示词，则存储提示词描述
              "<PROMPT_NAME>": {                                        # 提示词名称
                  "description": "<PROMPT_DESCRIPTION>",                # 提示词描述
                  "title": "<PROMPT_TITLE>",                            # 提示词标题
                  "arguments": {                                        # 提示词参数
                      "<ARGUMENT_NAME>": {                              # 提示词参数名称
                          "description": "<ARGUMENT_DESCRIPTION>",      # 提示词参数描述
                          "required": bool,                             # 提示词参数是否必需
                      },
                      ...                                               # 提示词参数其他属性
                  }
              },
              ...                                                       # 其他提示词
          },
      }
  }
  ```



#### 4.1.1 MCP Client 的调用

MCP Client本身具有管理连接会话的作用，我们希望整个MAS只维护一个全局唯一的MCP Client。

因为我们MAS 架构是 多线程并行 + 每个线程内部同步逻辑，我们希望我们在Agent内能并发执行多个MCP Client的方法调用（而不是一个个阻塞）。

我们的目标：在同一个 Agent 内部并行多个 MCP 操作；允许多个 Agent 共享同一个 MCP Client 事件循环。



我们需要实现 **同步包装器**，内部用 `asyncio.run_coroutine_threadsafe` 提交到**全局事件循环线程**，这样：

- Agent 调 MCPClient → 不会卡死整个系统（只阻塞该 Agent 线程）。
- 多个 Agent 调 MCPClient → 并发执行（因为 MCPClient 运行在事件循环线程，异步调度）。
- 即使一个 Agent 想在一个 Step 中**发起多个 MCP 调用并发执行**，也可以通过 `asyncio.gather` 在 MCPClient 事件循环里实现。



**具体实现**

我们于 `mas.async_loop` 实现 `AsyncLoopThread` 类和 `MCPClientWrapper` 类，其中：

- AsyncLoopThread 主要向MultiAgentSystem提供异步环境，实现一个用于在多线程环境中运行异步任务的异步事件循环线程。

  由此可以在MAS中的Agent和Executor中向 AsyncLoopThread 提交异步调用任务而不引起额外阻塞。

- MCPClientWrapper 主要用于在MAS中调用MCPClient方法，其负责将对MCPClient的调用提交到异步事件循环线程 AsyncLoopThread 中。

  由此MAS中给每个Agent和工具Executor传入的就不再是MCPClient实例，而是 MCPClientWrapper 包装器，调用 MCPClientWrapper 以实现在MAS中的异步调用MCPClient方法。



在 `MultiAgentSystem` 类的初始化中，我们初始化AsyncLoopThread，MCPClient和MCPClientWrapper：

```python
class MultiAgentSystem:
    def __init__(self):
        # 实例化异步事件循环线程，用于在多线程环境中运行异步任务，例如MCPClient的异步调用
        self.async_loop = AsyncLoopThread()
        self.async_loop.start()
        # 在事件循环中创建 MCPClient 并初始化
		future = self.async_loop.run_coroutine(self._init_mcp_client())
        self.mcp_client = future.result()  # 同步等待初始化完成
		# 实例化MCPClient包装器，用于在各个Agent中将MCPClient的调用提交到async_loop异步事件循环线程中
        # 传递给Agent的也是这一个MCPClient包装器，而不是直接传递MCPClient实例。
        self.mcp_client_wrapper = MCPClientWrapper(self.mcp_client, self.async_loop)
        ...
    
    # 异步初始化 MCPClient。
	async def _init_mcp_client(self):
        mcp_client = MCPClient()
        await mcp_client.initialize_servers()
        return mcp_client
```

此后新建Agent的时候传入的就是全局唯一的`mcp_client_wrapper`包装器而不是原始`mcp_client`实例。Agent通过Executor对`mcp_client_wrapper`的操作实现对MCPClient方法的异步调用。



#### 4.1.2 MCP Client Wrapper

`MCPClientWrapper` 类是MCPClient的同步包装器，用于在MAS架构中提供异步调用支持。实现于`mas/async_loop.py`中，主要用于将MCPClient的调用提交到 异步事件循环线程 AsyncLoopThread 中。

该类初始化时传入全局唯一的 `MCPClient` 和 `AsyncLoopThread` 实例。

在该MCP客户端包装器中实现了 MCP Tool Executor 所调用的两大核心方法，负责将 `MCPClient` 中对应的实现方法提交到 `AsyncLoopThread` 中：

- `get_capabilities_list_description` ：

  获取 MCP 服务的 prompts/resources/tools 描述

-  `use_capability_sync` ：

  传入参数使用 MCP server 提供的能力 （提交协程，并等待结果）



### 4.2 MCP Tool Executor

**期望作用：**Agent通过调用该工具，从而能够调度任意MCP（Model Context Protocol）的服务器端点。（本MCP Tool用于在MAS中兼容MCP协议的服务器端实现。）



**说明：**

对于Agent而言，MCP工具连接多个MCP的服务端。对于真正的MCP Server端点而言，该MCP Server工具是他们的Client客户端。

```python
Agent  -->  MCP Tool    -->  MCP Server Endpoint
Agent  <--  MCP Client  <--  MCP Server Endpoint
```

Agent通过mcp工具能够实现调用符合MCP协议的任意服务器端点。



对于工具使用流程而言，在MAS中：
   1. 获取到 MCP Server 级别描述：

        Agent通过每个技能Executor中提示词“available_skills_and_tools”部分，可以获取到每个工具server写在 `mas/tools/mcp_server_config` 下 `<tool_name>_mcp_config.yaml` 文件中的描述，并根据此做出是否调用的决策。

   2. 获取到 MCP Server 的具体能力级别的描述：

        MCPTool Executor 通过调用 MCPClient 获取到当前工具下所有可用的能力的list（根据该MCP Server支持的能力，获取其所有能力对应的调用list）。并根据此做出具体调用哪个具体能力的决策。

   3. 调用 MCP Server 的具体能力：

        根据第2步获取到的能力列表，Agent可以选择调用其中的某个能力。并按照其格式 MCPTool Executor 通过调用 MCPClient 的 execute 方法，传入具体的能力名称和参数，来执行该能力并获取结果。



在MCP Tool的实际执行过程中：

- 指令生成和工具决策技能均能够获取 `mcp_base_prompt` 提示词：

  指令生成技能Instruction Generation 在组装 tool step 提示词中包含 `mcp_base_prompt` ，工具决策技能 Tool Decision 在 `get_tool_decision_prompt()` 方法中包含 `mcp_base_prompt` 

- 工具调用，有别于技能调用：

  技能调用直接找到 `StepState.executor` 对应的技能 Executor 即可。但是工具中的`StepState.executor` 实际上是 MCP Server 的名字，而只要是工具 StepState 就会调用该 MCPToolExecutor 。

  因此调用 MCPToolExecutor 的依据是 `StepState.type = tool` 就调用。

  > 如果不接入MCP，则为每一个工具都实现一个Executor，此时执行步骤时传入的StepState.executor对应上相应的工具Executor即可；
  >
  > 然而，我们全盘接入MCP，则始终仅有一个MCPToolExecutor对应所有的MCP Server。
  > 即，所有的工具Step，不论StepState.executor是什么，均会调用这一个MCPToolExecutor。
  > （这一部分调用逻辑在Router路由中设置。）





**具体实现：**

我们的MCP Tool Executor负责获取StepState.instruction_content中的指令，解析并具体调用MCP Client的相关方法。

在 `MCPTool.execute` 中：

- 获取MCP服务的能力列表描述：

  如果指令类型`instruction_type`字段是`get_description`，则获取MCP服务的能力列表描述：

  ```python
  mcp_server_name = step_state.executor  # 工具执行器名称即为MCP服务名称
  capabilities_list_description = mcp_client_wrapper.get_capabilities_list_description(mcp_server_name)
  ```

  获取到能力描述后，插入追加工具决策Step：

  ```python
  # 如果获取到能力列表描述，同时触发tool_decision技能进一步决策调用哪个具体能力
  self.add_next_tool_decision_step(
      step_intention="决策调用MCP Server的具体能力",
      text_content=f"根据上一步工具调用结果返回的capabilities_list_description能力列表描述，"
                   f"决策使用哪个具体的能力进行下一步操作，以满足工具调用目标。\n"
                   f"需要决策的工具名：<tool_name>{mcp_server_name}</tool_name>",
      step_id=step_id,
      agent_state=agent_state,
  )
  ```

  

- 执行MCP服务的具体能力:

  如果指令类型`instruction_type`字段是`function_call`，则执行MCP服务的具体能力：

  ```python
  server_name = step_state.executor  # 工具执行器名称即为MCP服务名称
  arguments = instruction_content.get("arguments", {})  # 获取指令内容中的参数，如果没有则默认为空字典
  mcp_server_result = mcp_client_wrapper.use_capability_sync(
      server_name=server_name,
      capability_type=capability_type,
      capability_name=capability_name,
      arguments=arguments,
  )
  ```

  获取到返回的调用结果后，插入追加工具决策Step：

  ```python
  # 更新执行结果，同时触发tool_decision技能进行工具调用的完成判定
  self.add_next_tool_decision_step(
      step_intention="决策工具调用完成与否",
      text_content=f"根据上一步工具调用步骤的execute_result执行结果中返回的mcp_server_result具体调用结果，"
                   f"决策当前工具调用目标是否达成。\n"
                   f"需要决策的工具名：<tool_name>{server_name}</tool_name>，",
      step_id=step_id,
      agent_state=agent_state,
  )
  ```



**其他状态同步：**

> 1. 更新agent_step中当前step状态：
>    execute开始执行时更新状态为 “running”，完成时更新为 “finished”，失败时更新为 “failed”
>
> 2. 在当前step.execute_result中记录技能解析结果：
>
>    - 如果指令类型是get_description ：
>
>      ```python
>      step_state.update_execute_result({"capabilities_list_description": capabilities_list_description})
>      ```
>
>    - 如果指令类型是function_call ：
>
>      ```python
>      step.update_execute_result({"mcp_server_result": mcp_server_result})
>      ```
>
> 3. 更新stage_state.every_agent_state中自己的状态：
>
>    通过`update_stage_agent_state`字段指导sync_state更新，
>
>    Decision顺利完成时`update_agent_situation`更新为 ”working“，失败时更新为 “failed”
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
>    通过`send_shared_info`字段指导sync_state更新，
>
>    Decision顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_info"] = {
>        "task_id": task_id,
>        "stage_id": stage_id,
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "content": f"执行Decision步骤:{shared_step_situation}，"
>    }
>    ```





### 4.3 MCP 基础提示词

MCP基础提示，一般只有在涉及到工具步骤的时候才会调用，例如InstructionGeneration / ToolDecision 。

该提示的作用是教会Agent正确与MCP Server进行交互，包含:

​	1.如何理解MCP Server能力列表

​	2.如何生成MCP Server能力具体调用的参数

​	3.如何理解MCP Server对能力调用的具体返回结果

需要注意：

​	Agent已经知晓如何调用MAS中的工具，只是不了解MCP协议。编写本提示中需要避免混淆 工具调用方式提示 和 Agent能直接看到的涉及到MCP协议执行过程的交互提示，本提示的重点在后者。



MCP 基础提示词位于 `mas.tools.mcp_base_prompt.yaml` 中 `mcp_base_prompt` 字段：

```python
  MCP(model context protocol) Server 一般支持三种不同的 Capabilities，分别是：
  - tools : 允许模型执行作或检索信息的可执行函数
  - resources : 为模型提供额外上下文的结构化数据或内容
  - prompts : 指导语言模型交互的预定义模板或说明
  
  作为MAS中的Agent，你所拥有的工具权限均来自于MCP Server(你的工具名称实际上对应的每个MCP服务的名称)。
  MCP Server 的构成(注意：MCP Server不总是完全支持三种能力，大多数MCP Server仅支持tools调用能力):
  MCP Server
      ├── tools
      │   ├── <tool_name>
      │   └── ...
      ├── resources
      │   ├── <resource_name>
      │   └── ...
      └── prompts
          ├── <prompt_name>
          └── ...
  
  下面将介绍你会实际接触到的与MCP Server的交互说明：
  
  #### 1. 如何生成获取MCP Server能力列表的具体指令
  在你首次使用该工具时，你如果没有获取过该工具的MCP Server能力列表，你应当首先获取其支持的MCP Server能力列表。
  如果你当前正在执行Instruction Generation步骤你可以通过生成以下指令来使得下一个Tool Step进行能力列表的获取：
      <tool_instruction>
      {
          "instruction_type": "get_description",
      }
      </tool_instruction>
  其中instruction_type字段为"get_description"，表示这是一个获取MCP Server能力列表的指令。
  **请确保你生成的指令使用<tool_instruction>标签包裹**
  
  #### 2. 如何理解MCP Server能力列表
  在你决策使用工具时，MAS会为你获取指定MCP Server所支持能力的列表
  MAS会以以下格式的提示词呈现当前MCP Server支持能力的具体调用(以结构化的json数据提示)：
      "tools": {
          "<TOOL_NAME>": {
              "description": "<TOOL_DESCRIPTION>",
              "tittle": "<TOOL_TITLE>",
              "input_schema": {
                  "type": "object",
                  "properties": {
                      "<PROPERTY_NAME>": {
                          "type": "<PROPERTY_TYPE>",
                          "description": "<PROPERTY_DESCRIPTION>",
                      },
                      ...
                  }
              },
              "output_schema": <OUTPUT_SCHEMA>,
              "required": ["<PROPERTY_NAME>", ...]
          },
          ...
      },
      "resources": {
          "<RESOURCE_NAME>": {
              "description": "<RESOURCE_DESCRIPTION>",
              "title": "<RESOURCE_TITLE>",
              "uri": "<RESOURCE_URI>",
              "mimeType": "<RESOURCE_MIME_TYPE>",
          },
          ...
      },
      "prompts": {
          "<PROMPT_NAME>": {
              "description": "<PROMPT_DESCRIPTION>",
              "title": "<PROMPT_TITLE>",
              "arguments": {
                  "<ARGUMENT_NAME>": {
                      "description": "<ARGUMENT_DESCRIPTION>",
                      "required": bool,
                  },
                  ...
              }
          },
          ...
      },
  根据以上格式的提示，你需要重点关注该Server支持何种能力下的哪些具体实现。
  你需要根据每种具体实现的描述确定什么时候使用它，同时在使用具体能力的时候需要传入哪些参数。
  
  #### 3. 如何生成MCP Server能力具体调用的参数
  当你决定需要调用MCP Server的某种具体能力时，你需要生成工具调用指令（这里默认你会将工具调用指令包裹在<tool_instruction>中）
  - 如果你要使用MCP Server的tools能力：
        <tool_instruction>
        {
            "tool_name": "<TOOL_NAME>",
            "arguments": {
                "<PROPERTY_NAME>": PROPERTY_VALUE,
                "<PROPERTY_NAME>": PROPERTY_VALUE,
                ...
            }
        }
        </tool_instruction>
    其中tool_name字段传入你要使用的MCP Server的工具名称，
    arguments字段传入一个包含具体参数的字典，字典的键为该工具所需的参数名称，值为对应的参数值。
    **请根据MCP Server能力列表中的提示信息，正确填写具体工具所需的参数。**
  
  - 如果你要使用MCP Server的resources能力：
        <tool_instruction>
        {
            "resource_name": "<RESOURCE_NAME>",
            "arguments": {"uri": "<RESOURCE_URI>"}
        }
        </tool_instruction>
    其中resource_name字段传入你要使用的MCP Server的资源名称，
    arguments字段仅需传入一个包含uri的字典，uri是该资源的访问地址（从MCP Server能力列表获得）。
  
  - 如果你要使用MCP Server的prompts能力，指令格式如下：
      <tool_instruction>
      {
          "prompt_name": "<PROMPT_NAME>",
          "arguments": None
      }
      </tool_instruction>    
    其中prompt_name字段传入你要使用的MCP Server的prompt名称，
    arguments字段传入None，因为prompt能力不需要任何其他参数
  
  **一定要看清你生成的是tool、resource还是prompt的指令，不要把能力搞混了。**
  
  #### 4. 如何理解MCP Server对能力调用的具体返回结果
  当你通过生成具体指令调用MCP Server的某种能力时，MAS会为你获取该能力调用的返回结果。
  该能力执行的返回结果会放在step_state.execute_result中，你需要熟悉MCP Server对能力调用的返回格式：
  
  - tool响应示例：
    {
      "content": [
        {
          "type": "text",
          "text": "Current weather in New York:\nTemperature: 72°F\nConditions: Partly cloudy"
        }
      ],
    }
  
  - resource响应示例：
    {
      "contents": [
        {
          "uri": "file:///project/src/main.rs",
          "name": "main.rs",
          "title": "Rust Software Application Main File",
          "mimeType": "text/x-rust",
          "text": "fn main() {\n    println!(\"Hello world!\");\n}"
        }
      ]
    }
  
  - prompt响应示例：
    {
      "description": "Code review prompt",
      "messages": [
        {
          "role": "user",
          "content": {
            "type": "text",
            "text": "Please review this Python code:\ndef hello():\n    print('world')"
          }
        }
      ]
    }
  
  每种具体能力的响应示例都与MCP Server能力列表中的说明一一对应，请准确理解MCP Server的响应结果。
```









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

4.MCP工具调用的基础规则提示：

​	获取`mas/tools/mcp_base_prompt.yaml`文件中的MCP基础提示词

5.当前工具的简要描述：

​	获取对应MCP工具配置文件的`use_guide.description`字段值



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



### 5.6 历史步骤执行结果

获取当前Stage下所有历史的step的执行结果（**会同时获取到已执行的，和未执行的step信息**），作为提示词

```python
md_output.append(f"# 历史步骤（包括已执行和待执行） history_step\n")
history_steps = self.get_history_steps_prompt(step_id, agent_state)  # 不包含标题的md格式文本
md_output.append(f"{history_steps}\n")
```

**执行器基类函数名：**get_history_steps_prompt

**作用：**获取当前stage_id下所有step信息，并将其结构化组装。会区分已执行和待执行步骤

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
        "step_intention": str,
        "type": str,
        "executor": str,
        "text_content": str
    },
    ...
]
```



### 5.8 插入Step

为agent_step的列表中插入多个Step，插入在下一个待执行step之前。

```python
self.add_next_step(planned_step, step_id, agent_state)  # 更新AgentStep中的步骤列表，插入在下一个待执行步骤之前
```

**执行器基类函数名：**add_next_step

**作用：**为agent_step的列表中插入多个Step (插入在下一个待执行的步骤之前)

```python
# 倒序获取
for step in reversed(planned_step):
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
    # 插入到AgentStep中
    agent_step.add_next_step(step_state)
    # 记录在工作记忆中
    agent_state["working_memory"][current_step.task_id][current_step.stage_id,].append(step_state.step_id)
```

接受planned_step格式为`List[Dict[str:str]]`：

```python
[
    {
        "step_intention": str,
        "type": str,
        "executor": str,
        "text_content": str,
    },
    ...
]
```



### 5.9 长尾工具的历史调用信息提示词

获取该工具历史执行结果

```python
md_output.append(f"# 该工具历史的历史信息 tool_history\n")
history_tools_result = self.get_tool_history_prompt(step_id, agent_state, tool_name)  # 不包含标题的md格式文本
md_output.append(f"{history_tools_result}\n")
```

**执行器基类函数名：**get_tool_history_prompt

**作用：**

本方法应用于tool_decision中用于获取该工具的历史执行结果、历史调用决策与最初执行意图。


接收tool_name，向前提取当前stage_id下最新的长尾工具连续调用步骤链。根据筛选的连续调用步骤链，结构化组装其提示信息：

- 该工具的历次调用结果
- 该工具的历次工具决策
- 该工具最初的执行意图



为了只获取当前阶段下，正在进行的完整连续长尾工具调用步骤链，而不获取到其他干扰项或先前的长尾工具调用链，执行步骤如下：

1. 获取当前阶段的所有步骤

2. 从后向前遍历所有步骤获取executor来比较，为了避免获取到该阶段下前一段长尾工具的调用：

   从最近一次 [Tool] 开始，尝试向前“恢复”出成对的 [Tool] -> [ToolDecision]，直到不能再恢复。

   2.1 从末尾倒序遍历 steps 找到第一个 Tool（匹配工具名），作为起点

   2.2 从该 Tool 向前寻找最近的 ToolDecision

   ​	（中间允许跳过 InstructionGeneration 和 SendMessage，但如果存在其他步骤则视为非法，终止这轮）

   2.3 一旦找到了 ToolDecision，说明前面是一个完整调用：

   ​	一定会存在 Tool -> ToolDecision 成对的步骤。

   ​        继续寻找 ToolDecision 前的 Tool ，把这一对 Tool -> ToolDecision 都加入结果，

   ​        随后以这一对调用的开头 Tool 为新的起点。

   2.4 在新的 Tool 作为起点，继续重复2.2向前查找，直到中途出现非法步骤
   	（如遇到不是 tool_decision 又不是 gap 的步骤）

   2.5 如果向前找 Tool 的前一个有效步骤非 ToolDecision 则终止查找。

   ​	（排除 InstructionGeneration 和 SendMessage ）

3. 获取最初工具调用步骤意图

4. 将恢复的历史 Tool / ToolDecision 步骤组装为结构化提示词（Markdown格式）



> 注：这一段在代码中实现的可读性不高



### 5.10 管理持续性记忆

对于LLM输出的有关持续性记忆的指令，Executor实现了将其应用到`agent_state["presistent_memory"]`的方法

**执行器基类函数名：**extract_persistent_memory

**作用：**

从文本中解析持续性记忆，将持续性记忆指令从<persistent_memory>List[Dict]</persistent_memory>形式的LLM文本输出，转换成List[Dict]的具体指令格式。



**执行器基类函数名：**apply_persistent_memory

**作用：**

将解析出来的持续性记忆应用到Agent状态中

支持指令：

- {"add": "你要追加的内容"}   → 自动生成时间戳为 key
- {"delete": "时间戳"}       → 删除对应 key 的内容



### 5.11 MCP工具调用基础提示词

获取MAS系统的基础提示词

```python
md_output.append("# MCP调用提示 mcp_base_prompt\n")
mcp_base_prompt = self.get_mcp_base_prompt(key="mcp_base_prompt")  # 已包含 #### 四级标题的md
md_output.append(f"{mcp_base_prompt}\n")
```

**执行器基类函数名：**get_mcp_base_prompt

**作用：**传入mcp_base_prompt，从`mas/tools/mcp_base_prompt.yaml`中获取`key=“mcp_base_prompt”`的值





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

**step_action()：**

> 执行单个step_state的具体Action
> 1. 根据Step的executor执行具体的Action，由路由器分发执行器
>
>    使用router.get_executor方法
>
> 2. 执行器执行当前step
>
>    使用executor.execute方法
>
> 3. 向stage_state与task_state同步执行状态
>
>    使用sync_state.sync_state方法



### 6.2 Receive Message

接收来自其他Agent的消息（该消息由MAS中的message_dispatcher转发），
根据消息内容添加不同的step：

- 如果需要回复则添加send_message step
- 如果不需要回复则进入process_message分支，
  考虑执行消息中的指令或添加process_message step



#### 6.2.1 需要回复的消息

如果消息需要回复 `message["need_reply"]` ，则继续判断消息发送的对方是否等待该消息的回复 `message["waiting"]` ：

- 发送方等待该消息回复

  解析出自己对应的唯一等待ID

  ```python
  return_waiting_id = message["waiting"][message["receiver"].index(self.agent_state["agent_id"])]
  ```

  在步骤列表中插入回复消息步骤，在下一个步骤中立即执行该消息的回复：

  ```python
  self.add_next_step(
      task_id=message["task_id"],
      stage_id=message["stage_relative"],  # 可能是no_relative 与阶段无关
      step_intention=f"回复来自Agent {message['sender_id']}的消息，**消息内容见当前步骤的text_content**",
      step_type="skill",
      executor="send_message",
      text_content=message["message"] + f"\n\n<return_waiting_id>{return_waiting_id}</return_waiting_id>"  # 将消息内容和回应等待ID一起填充
  )
  ```



- 发送方不等待该消息回复

  在步骤列表中追加回复消息步骤

  ```python
  self.add_step(
      task_id = message["task_id"],
      stage_id = message["stage_relative"],  # 可能是no_relative 与阶段无关
      step_intention = f"回复来自Agent {message['sender_id']}的消息，**消息内容见当前步骤的text_content**",
      step_type = "skill",
      executor = "send_message",
      text_content = message["message"]
  )
  ```



#### 6.2.2 Process Message

处理不需要回复的消息，会进入该消息处理分支

> message格式：
> {
>     "task_id": task_id,
>     "sender_id": "<sender_agent_id>",
>     "receiver": ["<agent_id>", "<agent_id>", ...],
>     "message": "<message_content>",  # 消息文本
>     "stage_relative": "<stage_id或no_relative>",  # 表示是否与任务阶段相关，是则填对应阶段Stage ID，否则为no_relative的字符串
>     "need_reply": <bool>,  # 需要回复则为True，否则为False
>     "waiting": <list>,  # 如果发送者需要等待回复，则为所有发送对象填写唯一等待ID。不等待则为 None
>     "return_waiting_id": <str>,  # 如果消息发送者需要等待回复，则返回消息时填写接收到的消息中包含的来自发送者的唯一等待ID
> }

解析`message["message"]`中的内容

1. 对于需要LLM理解并消化的消息，添加process_message step
2. 如果instruction字典包含start_stage的key，则执行start_stage：
   当一个任务阶段的所有step都执行完毕后，帮助Agent建立下一个任务阶段的第一个step: planning_step）
3. 如果instruction字典包含finish_stage的key，则执行清除该stage的所有step并且清除相应working_memory
4. 如果instruction字典包含finish_task的key，则执行清除该task的所有step并且清除相应working_memory
5. 如果instruction字典包含update_working_memory的key，则更新Agent的工作记忆

6. 如果instruction字典包含add_tool_decision的key，插入tool_decision步骤





### 6.3 添加步骤

#### 6.3.1 add_step

为agent_step的列表中添加一个Step

1. 构造一个完整的StepState

```python
step_state = StepState(...)
```

2. 追加一个该Step到agent_step中

```python
self.agent_state["agent_step"].add_step(step_state)
```

3. 将StepState的id, 记录在工作记忆中

```python
self.agent_state["working_memory"].setdefault(task_id, {}).setdefault(stage_id, []).append(step_state.step_id)
```



#### 6.3.2 add_next_step

为agent_step的列表中插队添加一个Step,将该Step直接添加到下一个要处理的Step之前

1. 构造一个完整的StepState

```python
step_state = StepState(...)
```

2. 添加一个该Step到agent_step中,插队到下一个step之前

```python
self.agent_state["agent_step"].add_next_step(step_state)
```

3. 将StepState的id, 记录在工作记忆中

```python
self.agent_state["working_memory"].setdefault(task_id, {}).setdefault(stage_id, []).append(step_state.step_id)
```





## 7. HumanAgent 人类操作端

人类操作端是实现人类介入 Muti-Agent System 的唯一方式。在MAS中，人类以HumanAgent的形式出现，与之对应的是由LLM驱动的LLM-Agent。人类与LLM-Agent之间的通信与协作均等同于Agent与Agent之间的通信与协作。

即HumanAgent通过同名receive_message方法接收来自MAS内其他Agent的消息，通过send_message方法向其他Agent发送消息。



HumanAgent ，继承Agent基础类，拥有和LLM-Agent相同的构造与接口。唯一的区别是人类操作端是由人类驱动而非LLM驱动。

HumanAgent即人类操作行为会被添加AgentStep来追踪。但实际不执行AgentStep。其核心区别在于：

- LLM-Agent先添加AgentStep用于确定要执行什么操作，再具体执行该步骤。
- Human-Agent人类操作员先实际执行操作，在添加AgentStep用于记录该操作



### 7.1 通讯

Human-Agent需要同时兼顾实际使用与向人类展示，因此Human-Agent中的agent_state专门维护一个对话池。该对话池仅记录一对一的私聊记录，群聊记录由前端筛选TaskState.shared_conversation_pool实现。

```python
agent_state["conversation_pool"] = {
    "conversation_privates": {"agent_id": <conversation_private>, ...},  # Dict[str,List]  记录所有私聊对话组
    "global_messages": [str, ...],  # List[str] 用于通知人类操作员的全局重要消息
}
```

利用 agent_state["conversation_pool"] 来存储和管理人类操作端的对话消息，实时展示其中内容以呈现人类操作员的界面：

1. 将接收到的消息添加进 conversation_pool 中；

2. 人类操作员主动发起的消息也添加进 conversation_pool 中。



> 其中 `<conversation_group>` 是一个字典，包含与其他Agent群聊的对话信息：
>
> ```python
> {
>     "group_id": str,  # 对话组的唯一标识符
>     "participants": List[str],  # 参与群聊对话的Agent ID列表，群聊中只允许Human-Agent出现，不允许LLM-Agent出现
>     "messages": [  # 对话消息列表
>         {
>             "sender_id": str,  # 发送者Agent ID
>             "content": str,  # 消息内容
>             "timestamp": str,  # 消息发送时间戳
>         },
>         ...
>     ]
> }
> ```
>
> 
>
> 其中 `<conversation_private>` 是一个字典，包含与其他Agent的私聊对话信息：
>
> ```python
>"agent_id":[
>     {
>         "sender_id": str,  # 发送者Agent ID
>         "content": str,  # 消息内容
>         "stage_relative": str,  # 如果消息与任务阶段相关，则填写对应阶段Stage ID，否则为"no_relative"
>         "timestamp": str,  # 消息发送时间戳
>         "need_reply": bool,  # 是否需要回复
>         "waiting": bool,  # 如果需要回复，发起方是否正在等待该消息回复
>         "return_waiting_id": Optional[str], # 如果发起方正在等待回复，那么需要返回的唯一等待标识ID
>     }
> ]
> ```
> 



**私聊与群聊对话组**

目前所有HumanAgent主动发送和被动接收的消息，全都会存入一对一私聊记录中（`agent_state["conversation_pool"]["conversation_privates"]`）。

如果要构建群聊和相应群聊记录，我们通过筛选记录在Task下 `shared_conversation_pool` 中的完整消息存档来展示群聊。

Task下所有的通信记录都会存放于 `shared_conversation_pool` ，因此Task下任何群聊记录均是 `shared_conversation_pool` 的子集。







### 7.2 执行操作 （TODO）

人类操作端能够手动执行可以调用的工具，同时会在AgentStep中记录工具执行调用结果（绑定在相应stage中）。







### 7.3 Receive Message

接收来自其他Agent的消息（该消息由MAS中的message_dispatcher转发），

根据消息内容执行相应操作：
- 如果消息需要回复，则提示人类操作员进行回复
    - 如果对方在等待该消息的回复，则提示人类操作员优先回复。并解析出对应的唯一等待ID，添加在返回消息内容中
- 如果消息不需要回复，则直接处理消息内容



#### 7.3.1 需要回复的消息

如果消息需要回复 `message["need_reply"]` ，则继续判断消息发送的对方是否等待该消息的回复 `message["waiting"]` ：

如果发送方等待该消息回复，则解析出自己对应的唯一等待ID

```python
return_waiting_id = None
if message["waiting"] is not None:
    # 解析出自己对应的唯一等待ID
    return_waiting_id = message["waiting"][message["receiver"].index(self.agent_state["agent_id"])]
```



随后将消息添加到 `conversation_pool` 中私聊对话组中。

```python
self.agent_state["conversation_pool"]["conversation_privates"][message["sender_id"]].append(
    {
        "sender_id": message["sender_id"],  # 发送者Agent ID
        "content": message["message"],  # 消息内容
        "stage_relative": message["stage_relative"],  # stage_id或"no_relative"
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "need_reply": True,  # 是否需要回复
        "waiting": True if return_waiting_id else False,  # 如果需要回复，发起方是否等待该消息回复
        "return_waiting_id": return_waiting_id,  # 如果等待回复，那么唯一等待标识ID
    }
)
```



提示人类操作员进行回复。

```python
self.agent_state["conversation_pool"]["global_messages"].append(
    f"来自Agent[<agent_id>{message['sender_id']}</agent_id>]的消息需要您回复。"
)
```



#### 7.3.2 Process Message

对于不需要回复的消息，进入消息处理分支

> message格式：
> {
>     "task_id": task_id,
>     "sender_id": "<sender_agent_id>",
>     "receiver": ["<agent_id>", "<agent_id>", ...],
>     "message": "<message_content>",  # 消息文本
>     "stage_relative": "<stage_id或no_relative>",  # 表示是否与任务阶段相关，是则填对应阶段Stage ID，否则为no_relative的字符串
>     "need_reply": <bool>,  # 需要回复则为True，否则为False
>     "waiting": <list>,  # 如果发送者需要等待回复，则为所有发送对象填写唯一等待ID。不等待则为 None
>     "return_waiting_id": <str>,  # 如果消息发送者需要等待回复，则返回消息时填写接收到的消息中包含的来自发送者的唯一等待ID
> }

解析`message["message"]`中的内容

1. 对于需要人类理解并消化的消息，添加到`agent_state["conversation_pool"]["conversation_privates"]`中
2. 对于start_stage指令，提醒人类操作员
3. 对于finish_stage指令，提醒人类操作员，并清除相应工作记忆
4. 对于finish_task指令，提醒人类操作员，清除相应工作记忆，和对应任务下私聊消息记录
5. 对于update_working_memory指令，更新Agent的工作记忆

其中通过增加 `agent_state["conversation_pool"]["global_messages"]` 的方式来提醒人类操作员，对话池中的全局消息应当在人类操作端界面上广播展示。





### 7.4 Send Message

这是人类操作端发送消息的方法，区别于LLM-Agent的send_message技能，这是暴露给外部的消息发送方法。

当人类操作员主动向其他Agent发送信息时（例如在某个私聊/群聊对话组中发送消息）则调用 `HumanAgent.send_message` 方法。



> 1. 构造 message 消息格式
> 2. 如果在 conversation_pool 的 conversation_privates 中发现该消息是回复上一条等待消息的，则追加 return_waiting_id 到构造好的 message 消息体中
> 3. 将消息添加到 conversation_pool 中
> 4. 构造 execute_output 将消息传递给 SyncState 进行后续分发
>     
>     注：如果人类向多个Agent发/回消息，其中只有一些Agent需要返回唯一等待ID，则不能使用SyncState进行群发，只能一条一条地单独发送。因为每一条消息在 return_waiting_id  中都是独一无二的
>     
>     因此send_message会遍历所有接收者id列表，然后向每个接收者单独发送消息
> 5. 生成 AgentStep 来记录发送的消息操作



#### 7.4.1 人类操作端API

于 `mas.utils.web.server` 实现人类操作端发送消息的接口实现后端接口：

------

**验证登录**

用于将当前前端操作绑定到某个HumanAgent时（后续操作以该HumanAgent的身份进行），验证登录。

```python
POST /api/bind_human_agent
```

请求参数（JSON）：

```python
{
    "human_agent_id": "<HumanAgent的ID>"
    "password": "<HumanAgent的密码>"
}
```

返回格式：

```python
{
    "success": true,
    "human_agent_id": "<传入的HumanAgent的ID>"
    "message": "<调用成功或失败的消息>"
}
```



------

**发送消息**

以某个HumanAgent的身份向其他Agent发送消息

```python
POST /api/send_message
```

请求参数（JSON）：

```json
{
    "human_agent_id": "人类操作员ID",  # 这个ID是uuid.uuid4()的agent_id,而不是监控器中带"HumanAgent_"前缀的ID
    "task_id": "任务ID",
    "receiver": ["接收者ID1", "接收者ID2", ...],
    "content": "消息内容",
    "stage_relative": "相关阶段ID", // 可选，默认为"no_relative"
    "need_reply": true,  // 可选，默认为true
    "waiting": true      // 可选，默认为false
}
```

返回格式：

```python
{
    "success": true,"message": "消息已发送"
}
```









## 8. 其他基本组件



### 8.1 LLM Client

LLM API 调用封装类，不直接维护对话历史，而是使用 LLMContext。
该类实现两种API调用方式：Ollama 和 OpenAI。在不同分支中

调用时使用 `LLMClient.call()` 传入提示词 prompt 和上下文管理器 `LLMContext` 。



> LLMContext 类负责维护对话历史，包括追加、删除、获取历史等功能。
>
> - add_message 追加新的对话记录
> - remove_last_message 删除最后一条消息
> - trim_history 仅保留最近 `context_size` 轮对话
> - set_history 直接替换整个对话历史
> - get_history 获取当前的对话历史
> - clear 清空对话历史



### 8.2 Router

Router类根据step_state.type和step_state.executor两个字符串，访问Executor的注册表_registry。获取对应执行器类，并返回实例化后的执行器类。



### 8.3 Message

定义了MAS内部消息传递的基本格式

> Message字典包含Key及含义:
>
> ​	task_id (str): 任务ID
>
> ​	sender_id (str): 发送者ID
>
> ​	receiver (List[str]): 接收者ID列表
>
> ​	message (str): 消息内容
> ​		如果其中包含指令，则用<instruction>和</instruction>包裹指令字典
>
> ​	
>
> ​	stage_relative (str): 是否与任务阶段相关
> ​		用于方便清除机制判断是否要随任务阶段
>
> ​	need_reply (bool): 是否需要回复
> ​		如果需要回复，则接收者被追加一个指向发送者的Send Message step，
>
> ​		如果不需要回复，则接收者被追加一个Process Message step，
> ​		Process Message 不需要向其他实体传递消息或回复
>
> ​	
>
> ​	waiting (Optional[List[str]]): 等待回复的唯一ID列表
> ​		如果发送者需要等待回复，则为所有发送对象填写唯一等待标识ID。不等待则为 None
>
> ​		如果等待，则发起者将在回收全部等待标识前不会进行任何步骤执行
>
> ​	return_waiting_id (Optional[str]): 返回的唯一等待标识ID
> ​		如果这个消息是用于回复消息发起者的，且消息发起时带有唯一等待标识ID，
> ​		则回复时也需要返回这个唯一等待标识ID
>
> ​		如果不返回，则会导致消息发起者无法回收这个唯一等待标识ID，发起者将陷入无尽等待中。



### 8.4 Message Dispatcher 

这是一个消息分发模块，一般实例化在MAS类中，与SyncState和Agent同级，用于消息分发。

它会遍历所有 TaskState 的消息队列，捕获到消息后会调用`agent.receive_message`方法来处理消息。



在MAS初始启动时需要开启一个单独的线程循环执行该模块的`MessageDispatcher.dispatch_messages`方法。在该方法中，遍历所有 TaskState 的消息队列，将消息分发给对应的 Agent。



### 8.5 State Monitor

状态监控器，我们在MAS中实现了一个StateMonitor监控器类。

通过装饰器，对TaskState，StageState，AgentBase.agent_state，StepState等状态类进行监控。并将监控信息呈现在网页中（通过web/server.py推送）



注意：
服务获取监控内容时，该监控器需要处理不可序列化的字段为特殊含义的可表示形式。
使用`_safe_serialize`方法递归序列化需要可视化的字段



**监控状态可视化：**

实现监控状态可视化，我们采用以下技术方案：

| 模块     | 实现                                               |
| -------- | -------------------------------------------------- |
| 后端     | Flask + `StateMonitor`                             |
| 推送     | Flask + WebSocket (建议用 `flask-socketio`)        |
| 前端     | 可用简单的 HTML + JavaScript，或 Vue/React         |
| 后台线程 | `threading.Timer` 或 `while True + sleep` 周期推送 |

在`mas.utils`路径下实现推送服务和前端页面的结构：

```python
├── web/
│   ├── server.py         # Flask + SocketIO 服务端
│   └── templates/
│       └── index.html    # 前端界面
```



实现后端接口：

```python
GET /api/states?type=task
GET /api/states?type=stage
GET /api/states?type=agent
GET /api/states?type=step
```

返回格式：

```python
{
    "StateID_1": { "task_id": "...", "task_name": "...", ... },
    "StateID_2": { ... },
    ...
}
```



于`mas.utils.web.server.py`中`get_states`方法来进行API调用



## 9. 特殊机制



### 9.1 步骤锁-通信等待回复时

由于我们MAS中Agent与其他组件或其他Agent的通信是通过 Send Message 和 Process Message 技能，以步骤 Step 的方式执行。

为了避免后续待执行 Step 中存在一些依赖当前 Send Message 的回复信息的步骤，在获取到回复信息前就被执行从而导致执行失败，我们在通信机制中引入了步骤锁 Step Lock。

步骤锁可以在等待重要消息回复时暂停Agent Step的执行，直到全部步骤锁被回收（成功接收重要消息的回复）后，回复Agent Step的执行。以此保证涉及到通信等待的Step与其他Step之间逻辑依赖关系不被破坏。即，当我要向其他Agent咨询信息，并对该信息进行整理时，我不会出现在获取到咨询回复（执行 Process Message Step）之前就过早地执行整理 Step 的情况。



通信情况下的 Step Lock 步骤锁涉及三种组件：Agent本身接收消息的执行逻辑 `AgentBase.received` 与 `AgentState`、消息发送 `SendMessage` 和 系统中通信消息构造体的定义 `Message` 。

我们将依次介绍在这些组件下 Step Lock 的运行方式以及我们的考虑



#### 9.1.1 Message

作为MAS中跨Agent的消息传递的一般通用格式，Message字典中有两个字段专门用来帮助传递 Step Lock 步骤锁的信息。



- waiting (Optional[List[str]])：

  （由发起方填写）包含与 receiver (List[str]) 中对应的每个接收者的唯一等待ID

  如果Message发起方需要等待该消息的回复，则该字段会为每个接收方生成一个唯一等待ID，只有当所有的唯一等待ID都回收后，发起方才会进行下一个step，在此之前发起者不进行任何step活动。

  如果不等待，则为None

- return_waiting_id (Optional[str])：

  （由接收方在回复中填写）为接收者在发起者消息中所对应的唯一等待ID

  如果接收方接收到的消息中包含 waiting 字段的唯一等待ID，则接收方回复消息时需要填写自己所对应的唯一等待ID，以便发起方回收发出的唯一等待ID。

  如果不等待，则为None

  

#### 9.1.2 Send Message 技能



1.Send Message 技能中调用LLM生成初步消息体时，LLM只需要判断是否回复与是否等待：

```python
{
    "receiver": ["<agent_id>", "<agent_id>", ...],
    "message": "<message_content>",  # 消息文本
    "stage_relative": "<stage_id或no_relative>",  # 表示是否与任务阶段相关，是则填对应阶段Stage ID，否则为no_relative的字符串
    "need_reply": <bool>,  # 需要回复则为True，否则为False
    "waiting": <bool>  # 需要等待则为True，否则为False
}
```

> Send Message 对于 waiting 字段的提示是：
>
> ```yaml
> skill_prompt: |
> 	...
> 	在需要回复的情况下，你需要判断是否等待该回复：
>     - 如果等待回复：
>       将waiting字段设置为True，此时你将暂停执行后续步骤，直到接收方的消息到达。
>       如果你规划的步骤中有依赖于该回复的步骤，你需要将该步骤的waiting字段设置为True，防止在获取消息回复前就执行了依赖该消息的步骤。
>     - 如果不等待回复：
>       将waiting字段设置为False，则说明你不需要等待该回复，你可以继续执行后续步骤。
>       你的后续步骤并不依赖你这次需要回复的消息。
> 	...
> return_format: |
> 	...
> 	waiting (bool): 表示是否需要等待接收方的回复，如果需要等待则为True，否则为False。
>         该字段用于防止你收到获取重要信息回复前，就执行了依赖该信息的后续步骤。
>         在你需要获取到回复/答案才能完成后续步骤的情况下，你需要将该字段设置为True。
>         此时你将暂停执行后续步骤，直到接收方的消息到达。
> 	...
> ```



2.在Send Message技能解析完LLM输出后，会判断LLM是否认为当前发送的消息需要等待：

**Step Lock 的添加** ：

如果需要等待，则会为自动为初步消息体中的每个receiver生成唯一等待标识ID，用以替换LLM生成的初步消息体中的["waiting"]，并添加唯一等待ID到agent_state["step_lock"]中

```python
if message["waiting"]:
    # 为每个receiver生成唯一等待标识ID
    waiting_id_list = [str(uuid.uuid4()) for _ in message["receiver"]]
    # 将唯一等待ID添加到agent_state["step_lock"]中
    agent_state["step_lock"].extend(waiting_id_list)

    # 将消息中的["waiting"]字段替换为生成的唯一等待ID
    message["waiting"] = waiting_id_list
else:
    # 如果不需要等待，则将waiting字段设置为None
    message["waiting"] = None
```

此时 message["waiting"] 字段值已经从布尔值 bool 变为了可选的包含每个接收对象的唯一等待ID的列表 optional[list[str]]



3.在Send Message技能构造execute_ouput时，将LLM生成的初步消息体 转换为 MAS 中通用消息格式 Message：



**回复”等待回复“的步骤：**

此时构造 return_waiting_id 字段值，尝试从 `step_state.text_content` 中提取。

(一般情况下，如果Agent接收到存在 message["waiting"] 字段值的消息时，则添加回复步骤 Send Message Step 时会提取对应的需要返回的唯一等待ID 放在步骤的 text_content 末尾)



最终在 get_execute_output 方法中构造的消息为：

```python
# 获取当前步骤的task_id与stage_id
task_id = step_state.task_id

# 如果对方在等待该回复，则解析并构造return_waiting_id
# 从当前step的text_content中提取return_waiting_id
return_waiting_id = self.extract_return_waiting_id(step_state.text_content)  # 如果存在<return_waiting_id>包裹的回复唯一等待ID则返回，否则返回None

# 构造execute_output，中标准格式的消息
execute_output["send_message"]:Message = {
    "task_id": task_id,
    "sender_id": agent_state["agent_id"],
    "receiver": send_message["receiver"],
    "message": send_message["message"],
    "stage_relative": send_message["stage_relative"],
    "need_reply": send_message["need_reply"],
    "waiting": send_message["waiting"],
    "return_waiting_id": return_waiting_id,
}
```



#### 9.1.3 Agent接收消息 与 StepLock 执行

Agent于AgentBase.receive_message中接收消息：

对于自己发起后收到回复的处于“等待”状态的消息，和别人发起的自己需要回复的处于“等待”状态的消息，Agent都会使用add_next_step插队添加消息处理step。其他情况会添加正常排队的step



------

**Step Lock 的状态**：

在AgentState初始化时增加一个用于存储唯一等待ID的步骤锁列表：

```python
agent_state["step_lock"] = [] 
```

**Step Lock 对步骤执行的阻断：**

在AgentBase的action方法中，增加对步骤锁的判定：

```python
while True:
    if len(self.agent_state["step_lock"]) > 0:
        # 如果有步骤锁，则等待
        self.agent_state["working_state"] = "waiting"
        time.sleep(1)
        continue
	...
```

如果步骤锁列表不为空，则等待，并更新agent的工作状态为 “waiting”



**Step Lock 的添加：**

生成Message的技能，例如Send Message和Ask Info，可为Agent添加步骤锁



**Step Lock 的回收：**

AgentBase.recieve_message中，尝试获取消息中的return_waiting_id，回收步骤锁：

```python
if message["return_waiting_id"] is not None:
    # 回收步骤锁
    self.agent_state["step_lock"].remove(message["return_waiting_id"])
```





### 9.2 休眠与唤醒

我们采用了无Step执行就进入休眠的机制，那么我们可能需要一个唤醒机制。

> **无Step休眠**
>
> 在本MAS中，Agent的休眠机制是自然而然地无需特地实现的。具体来说，我们Agent的活动方式完全依赖于Step：如果没有Step，Agent将不会进行任何活动；如果有待执行Step，Agent不需要任何额外控制就会自动执行剩余Step。
>
> 因此，我们Agent没有任何待执行Step时（当`AgentStep.todo_list`为空时），会自然进入“无Step休眠”，期间 LLM 零 token 开销。



这个唤醒机制可能是消息进来后Agent的`receive_message`方法能够追加`reflection`技能以重新启动（当前Stage无其它`reflection`技能时）？

- 对于执行Agent而言：

  执行Agent只有一种可能当前Stage无任何Step，那就是当前Stage被完成的情况，因此也不会存在需要唤醒机制。如果需要执行Agent去开始任何新的Stage或Task，都由管理Agent使用管理技能去控制和决策。

  不存在向执行Agent以消息的形式去让执行Agent自己唤醒去赋予自己任务的情况。
  如果是执行Agent接收到询问信息的消息，即便处于休眠状态下也不影响Agent回复。

  因此对于执行Agent而言，额外的唤醒机制是不必要的。



- 对于管理Agent而言：

  当管理Agent休眠，但是下辖的执行Agent仍在工作时。由于下属执行Agent工作完成时会以消息形式通知管理Agent，管理Agent能够通过Stage结束流程进行任务管理。

  当管理Agent休眠，同时下属执行Agent也已经完成相关工作。此时管理Agent并不拥有任何活跃中的Task。则管理Agent失去了活动空间，没法被自然唤醒。但是我们可以通过指定系统初始Task永不结束，永远保持有一个活跃Stage来使得管理Agent能够进行任务管理。



综上，对于任何情况下，**我们不需要额外实现唤醒机制**，仅需要保持MAS系统初始任务一直活跃，使得存在至少一位管理Agent一直活跃即可。



### 9.3 Persistent Memory 持续性记忆

因为我们MAS中Agent执行被拆分为了一个个Step，每个Step之间重新组提示词并不共享上下文。因此我们在 `agent_state` 实现了名为 `persistent_memory` 的字典用于存放跨Step甚至是跨任务的持续性记忆。

该持续性记忆完全由Agent自主管理，Agent在每个Step中都会接收到关于如何管理持续性记忆的提示词，以及在每个技能调用时Agent都能够查看自己已有的持续性记忆。

#### 9.3.1 持续性记忆的形式

`agent_state["persistent_memory"] = {}` 持续性记忆初始化为一个字典。每个step执行中，Agent要添加的持续性记忆都会以 时间戳为Key、具体内容为Value 添加到字典中。

例如：

```python
{
	"20250613T103022":"当前我完成了...",
    "20250613T103523":"当前我正在...",
    "20250613T104023":"记录任务信息...",
}
```



#### 9.3.2 持续性记忆的管理

我们在 `mas.agent.base.base_prompt` 的YAML文件中记录了管理和使用持续性记忆的提示词 `persistent_memory_prompt` 。

我们在 `mas.agent.base.executor_base.Executor` 类实现了用于从LLM返回结果中解析持续性记忆指令并应用指令的管理方法 `extract_persistent_memory` 和 `apply_persistent_memory` 。



我们的允许Agent以以下方式管理其持续性记忆：

- 追加永久持续性记忆

  使用add指令和要添加的新记忆内容。通过在输出结果中添加以下格式的文本来追加永久持续性记忆：

  ```python
  <persistent_memory>
  [{"add":"要追加的永久持续性记忆内容"}]
  </persistent_memory>
  ```

- 删除已有的记忆内容：

  通过使用delete指令和对应的时间戳，删除对应时间戳下的记忆内容。通过在输出结果中添加以下格式的文本来替换/修改已有的永久持续性记忆内容：

  ```python
  <persistent_memory>
  [{"delete":"要删除的永久持续性记忆的时间戳"}]
  </persistent_memory>
  ```

  

示例：

如果我想要替换20250613T103022时间戳下的记忆内容为"ABC网站网址是XXXX"我可以先删除再追加，输出以下内容：

```python
<persistent_memory>
[
    {"delete":"20250613T103022"},
    {"add":"ABC网站网址是XXXX"}
]
</persistent_memory>
```





## 10. 讨论



### 10.1 更好的消息回复

> Date：2025/6/16

首先我们不应该将接收消息的两种情况（接收消息之后更好地去执行与接收消息之后更好地回复）混为一谈，前者属于**消息干预执行**，后者属于本次要讨论的问题——更好地消息回复：

当Agent接收到一条询问消息，Agent会添加一个send_message用于回复该消息。

然而当Agent在send_message中不知道正确回复答案时，却没有任何能力能够先去获取答案再进行send_message回复。因为接收到需要回复的消息后，在Agent.receive_message分支中没有能够增加信息获取step的能力，send_message步骤也没有能够进行信息获取的能力。

> send_message主动添加的时候一般都会规划好预先获取的信息去发送消息。而send_message被动添加的时候，没法去获取暂时不知道的情况，只能立即通过send_message回复。



此时应当在需要回复的时候通过一些其他方法去判断和获取额外信息，有几种可能的方式：

- 将添加send_message改为长尾技能，使得send_message能够触发ask_info等技能或工具获取信息。将多步技能整合到send_message一步技能中，或者将send_message的输出结果变为可以在"获取更多信息"和”直接消息回复“之间决策。

- 在Agent.receive_message需要回复的分支中不直接添加send_message技能，而是添加一个决策步骤，判断下一步是直接添加send_message步骤还是先添加ask_info等获取信息再添加send_message步骤。

  > 这个决策技能可能是reflection？然而reflection却又都是针对Stage完成情况反思的，reflection不直接适用于该情景的决策。要么修改reflection的能力，要么直接实现一个更自由地不考虑Stage目标的步骤规划/决策技能。

一个综合以上两种的方式是，我们首先允许send_message走向两个分支：1）直接输出消息；2）获取更多信息。在获取更多信息中，实际插入追加（add_next_step）一个decision自由决策技能。

其次我们实现这个decision技能，专门用于与阶段解耦的动态决策。该决策技能能够和planning/reflection/tool_decision一样去规划新的step。



### 10.2 更好的消息干预执行

> Date：2025/6/20

我们这里阐述我们允许何种形式的消息干预执行。我们需要Agent能够对消息内容产生自主的Action。具体而言，我们不应该一一指定什么样的非指令消息对应什么样的反应，而是希望Agent能够自己决策。

因此，我们的消息处理分支Agent.receive_message需要导向一个能够产生行为的决策分支。准确说就是导向到添加一个Decision Step，由Decision Step规划短期即时的步骤去产生和MAS内环境的交互。

为此我们为Agent.receive_message接收消息的分支的两个末端：`send_message`和`process_message`技能都引入了一个新的决策分支，允许这两个技能在必要时刻通过插入追加Decision Step来实现与环境交互的能力，而非单纯的回复消息和理解消息。



### 10.3 Agent同时处理多个不同Stage的任务

> Date：2025/6/26

MAS并不限制Agent同时接受多个Stage的任务。由于Agent执行Step是单线程操作，Agent在同时进行多个Stage时是多个Stage各自的Step交替执行的。

我们需要考虑的就是避免来自不同Stage的Step交替执行时不会引发额外异常。

**Stage混淆：**

我们在Executor中的几个技能常用的基础方法：

> `get_history_steps_prompt` 组装历史步骤（已执行和待执行的step）信息提示词`get_tool_history_prompt` 组装指定长尾工具的历史调用信息
> `get_tool_instruction_generation_step_prompt` 组装为工具指令生成时的提示词

方法中查找和调用时均已区分不同Stage，因此不会产生Stage之间的混淆。

**性能影响：**

多Stage交替执行会影响性能，例如现在有两个不同的Stage分别为A和B，那么来自这些Stage的步骤如下：

```
A B A A B B B B B B B B B A
```

如果想结束A Stage那么就得等B Stage下的所有步骤均执行完毕。因此很大程度上，Agent同时处理N个不同Stage则会导致平均每个Stage以N倍的时间结束。

（这是很符合人类工作模式的，请让Agent尽量保持专注在一个任务阶段上。）

我们应当注意**避免Agent同时接受过多Stage**，我们可以通过实例化多个相似功能的Agent来替代。



### 10.4 如何接入MCP服务

为了兼容标准，我们希望我们也能享受到MCP服务的便利，我们需要将MCP服务的一部分与我们的MAS融合，以实现在MAS已有工作逻辑中支持调用任意MCP服务。

最终我们选择将MAS系统中的工具库全盘使用MCP来构建，我们接受的任何一个基于MCP标准的服务无缝接入我们的MAS框架。



**实现 MCP Client**

首先我们实现了一个 MCP Client 用于维护和管理MAS中所有的MCP服务的连接会话。同时MCP Client还实现了 服务连接、服务能力的描述获取、服务能力的描述调用 等基础方法以供工具Executor使用



**MAS 中组件合理访问 MCP Client**

该MCP Client应当是全局唯一的，我们使ExecutorBase能够访问到这个全局唯一的MCP Client，即可让工具Executor子类访问到这个全局唯一的MCP Client。

同时因为我们MAS系统时多个Agent并行的，每个Agent在自己的线程中想要异步调用同一个MCP Client我们需要一些额外的组件帮我们实现这点。

因此我们实现了 AsyncLoopThread 和 MCPClientWrapper 两个组件，使其随着MAS时初始化。同时将 MCPClientWrapper 传入Agent，让每个Agent的Executor都可以访问到 MCPClientWrapper 。

> MCPClientWrapper 负责向 AsyncLoopThread  提交来自 MCPClient 的异步调用任务。



**实现 MCP Tool Executor**

与技能Skill一样，我们的工具Tool调用依旧依赖Executor。我们在Executor完善工具Step的具体调用逻辑

> 但与技能不同的是，技能Executor的名称与当前执行的StepState.executor一一对应，但是工具StepState.executor实际是MCP Server的名称，所有的MCP Server均调用者一个MCP Tool Executor。
>
> 因此我们在Routor中区分，如果是工具Step即StepState.type==“tool”则调用MCP Tool Executor。技能Step则是根据StepState.executor调用对应具体的技能Executor。



我们在工具执行器中实现两个逻辑，获取MCP Server支持能力（tools/resources/prompts）的描述 和 调用具体MCP Server能力。我们根据StepState.instruction_content中的内容（由InstructionGeneration技能生成）来决定进入哪个分支逻辑

- 获取MCP Server能力描述

- 调用MCP Server能力

  




### 10.5 向人类展示的群聊内容

首先一个前提是，MAS中所有的私聊/群聊对话都依赖于任务Task，如果对话参与者不再同一个任务群组中，则无法互相对话。

其次，我们需要考虑群聊情景下的消息发送与展示。



作为消息发送者，我们需要考虑以何种界面能够便捷地实现一下情况：

以消息发送对象的数量区分：

- 消息是面向群聊内的所有人
- 消息是面向群聊内的部分人

以消息发送的类型区分：

- 发送者 不需要接收者对该条消息进行回复
- 发送者 需要接收者对该条消息进行回复，但不需要立即回复
- 发送者 需要接收者对该条消息进行回复，且需要立即回复



作为消息接收者而言，我需要考虑以何种界面能够便捷地识别以下情况的消息：

与我相关与否：

- 该消息的接收对象是我
- 该消息的接收对象不是我

以消息的类型区分：

- 我不需要对该条消息进行回复

- 我需要对该条消息进行回复，但不需要立即回复

- 我需要对该条消息进行回复，且需要立即回复




#### 10.5.1 群聊消息的格式

> 为了区分普通消息与群聊消息，一个最简单的增加群聊功能的方式便是为Message类型增加一个字段group_id用于区分是否属于群聊消息：
>
> - 如果 `Message.group_id` 为None，则说明Message是不属于任何聊天群组中的消息
> - 如果 `Message.group_id` 有值，则Message属于相应聊天群组中的消息
>
> 
>
> 那么对于Agent区分Message消息类型，首先我们考虑两种形式，
>
> - 一是HumanAgent区分group_id，LLMAgent不区分群聊与私聊。
>
>   此时有HumanAgent来判断LLMAgent发过来的消息应当归类为哪个group_id。
>
>   这也意味着在群聊中，LLMAgent无法主动发言（不区分群聊消息与私聊，故而只能发送私聊消息），只能被动回复来自HumanAgent的消息。
>
> - 二是HumanAgent与LLMAgent都区分群聊与私聊。
>
>   我们即面临LLMAgent如何区分群聊与私聊的问题：
>
>   - 只被动区分，不做主动区分。那么LLMAgent只能回复群聊消息，没法主动发起群聊消息。
>
>   - 做主动区分。那么LLMAgent需要辨别群聊与私聊的情形，LLMAgent至少需要获取到群聊中的属性和部分内容以做判断。但此时群聊记录是在HumanAgent中各自维护，而不由LLMAgent维护。
>
>     我们是否要为了LLMAgent能够判断群聊内容而在LLMAgent的状态中维护相应的群聊信息呢？这可能带来提示词增长的极大开销。
>
> 
>
> > 聊天群组（不论群聊或私聊）与我们最初的Agent通信设计相斥。我们最初设计MAS之间的通信不考虑持续性通信（即通信只考虑单次收发，不考虑维护一个通信池保持长期消息收发）。
>
> 要合理地实现持续性通信，我们可能不适合在Message这一级别的单次消息发送机制上修改。

我们最终决定不为每一个群聊单独维护，我们将所有的群聊或私聊都看作是在Task下消息记录的子集。我们只实现一个由TaskState中维护的中心化的会话池，包含现有Task下的所有Message记录。

至此，HumanAgent将不再需要持有或维护群聊记录，而是直接向人类展示TaskState中会话池的子集。



**具体实现**

我们将所有成功发送的Message记录在TaskState.shared_conversation_pool中，该列表：

```python
[
	{"<timestamp>":Message},
    {"<timestamp>":Message},
    ...
]
```



#### 10.5.2 界面展示（TODO）

为了解决这个问题，我们可以在发送端增加一小步结构化操作，从**“发送对象”**和**“消息类型”**两个维度对信息进行结构化处理。

1. 作为消息发送者 (Sender)

核心目标：在不离开当前聊天输入界面的前提下，用最少的步骤，清晰地定义消息的“发给谁”和“需要对方做什么”。

界面设计方案：

在传统的消息输入框旁边，增加两个关键的控制按钮：“**@提及**”和“**消息类型**”

a. 定义发送对象

- 面向所有人（Defalut）。默认行为，消息面向群内所有人。最高频、最简单
- 面向部分人（Targeted）。
  - 提及功能（@Mention）：键盘点击直接输入”@“，会弹出一个可搜索的群成员列表。
  - 预设分组：列表不仅可以选个人，还可以选择预设的“角色组”（如 @设计师、@工程师）或“临时组”。
  - 视觉反馈：在输入框中，被@到的人名或组名会以特殊的“标签胶囊”形式高亮显示，让发送者清晰地知道有哪些接收对象

b. 定义消息类型（Action Type）

点击“消息类型”按钮（可以用一个类似“❗”或“⚡️”的图标），会弹出一个选项菜单，定义这条消息的性质。发送后，图标会附在发送气泡框右上角。

- 周知消息 (FYI):
  - 图标: 📢 (喇叭)
  - 功能: 发送者可以看到谁“已阅”，适用于通知、分享等无需回复的场景。
- 待办消息 (Action Required):
  - 图标：☑ (复选框)
  - 功能：发送者可以清晰地看到每个人“未完成”或“已完成”的状态。适用于布置任务、收集确认等需要接收者对该条消息进行回复，但不需要立即回复的场景。
- 紧急消息 (Urgent / Ding):
  - 图标: 🚨 (警报灯)
  - 功能:最高优先级的消息。发送后，会通过特殊的强提醒方式（如应用内弹窗）通知接收者，直到对方确认为止。这借鉴了钉钉（DingTalk）的核心功能，适用于需要对该条消息进行回复，且需要立即回复的紧急消息。

2. 作为消息接收者（Receiver）

核心目标是：快速扫描信息列表，一眼就能识别出“哪些与我有关”以及“它们的紧急/重要程度如何”。

界面设计方案：

通过对消息列表和消息气泡的视觉设计，来区分不同类型的消息。

a. 识别相关性 

- 与我相关的消息：明显的视觉区分，强高亮，使用不同的背景色（如淡黄色）、左侧出现一条高亮色带，并带有一个“@我”的醒目标签胶囊。

- 与我无关的消息: 保持标准的气泡样式

b. 识别消息类型
消息气泡上会清晰地展示发送者定义的消息类型图标，

- 周知消息 (📢):
  - **界面:** 看到此图标，接收者明白只需阅读即可。已读消息后，消息下方会有一个“已阅”的灰色字样，发送者端的状态会更新。
- 待办消息（☑）
  - **界面:** 消息气泡上会直接附带交互按钮，如“标记为完成”或“回复处理”。
  - **追踪:** 完成后，消息的交互按钮会变为“已完成”状态。

- 紧急消息（🚨）
  - **界面:** 除了接收时有强提醒外，这条消息在聊天列表中会持续高亮，直到用户点击“收到”或“处理”来确认。它的视觉样式（如红色边框、闪烁图标）应该是最醒目的。

