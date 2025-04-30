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
shared_message_pool (List[Dict]): 任务群组共享消息池（可选结构：包含agent_id, role, content等）
communication_queue (queue.Queue): 用于存放任务群组的通讯消息队列，Agent之间相互发送的待转发的消息会被存放于此

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
llm_config (Dict[str, Any]): LLM（大语言模型）的配置信息
working_memory (Dict[str, Any]: 
    以任务视角存储 Agent 的工作记忆。  
    结构为 `{<task_id>: {<stage_id>: [<step_id>, ...], ...}, ...}`  
    记录未完成的任务、阶段和步骤，不用于长期记忆。  
persistent_memory (str): 永久追加的精简记忆，用于记录Agent的持久性记忆，不会因为任务,阶段,步骤的结束而被清空
	md格式纯文本，**里面只能用三级标题及以下！不允许出现一二级标题！**
agent_step (AgentStep): AgentStep是一个对step_state的管理类，维护一个包含step_state的列表
tools (List[str], 可选): Agent 可用的工具列表，例如 `['搜索引擎', '计算器']`，默认为空列表。
skills (List[str], 可选): Agent 可用的技能列表，例如 `['文本摘要', '图像识别']`，默认为空列表。
```



### 1.2 Message Dispatcher

消息分发类，一般实例化在MAS类中，与SyncState和Agent同级，用于消息分发。

它会遍历所有 TaskState 的消息队列 `task_state.communication_queue`，捕获到消息后会调用agent.receive_message方法来处理消息。



### 1.3 MultiAgentSystem

多Agent系统的核心类，负责管理所有Agent的生命周期和状态同步。该类实例化三个组件：

- 状态同步器
    首先在MultiAgentSystem类中创建一个与Agent实例平级的sync_state，
    以确保sync_state是全局唯一一个状态同步器，同时保证sync_state中的task_state是所有Agent共享的。

- Agent智能体
    MAS类是唯一的 agent 生命周期管理者，所有agent映射由它统一提供。

- 消息分发器
    同时实现一个MAS中的消息转发组件，该组件不断地从sync_state.all_tasks中的每个task_state
    task_state.communication_queue中获取消息，并向指定的Agent发送消息。



#### 1.3.1 启动流程

1. 先启动消息分发器的循环（在一个线程中异步运行）

   后续任务的启动和创建均依赖此分发

2. 添加第一个Agent（管理者）

   Agent在被实例化时就会启动自己的任务执行线程

3. 创建MAS中第一个任务，并启动该任务

   指定MAS中第一个Agent为管理者，并启动其中的阶段

4. 主线程保持活跃，接受来自人类操作端的输入

   人类操作端**（TODO）**





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
| working_state     | str            | Agent的当前工作状态；<br /> idle 空闲, working 工作中, waiting 等待执行反馈中 |
| llm_config        | Dict[str, Any] | 从配置文件中获取 LLM 配置                                    |
| working_memory    | Dict[str, Any] | Agent工作记忆 {<task_id>: {<stage_id>: [<step_id>,...],...},...} 记录Agent还未完成的属于自己的任务 |
| persistent_memory | str            | 由Agent自主追加的永久记忆，不会因为任务、阶段、步骤的结束而被清空；<br />（md格式纯文本，里面只能用三级标题 ### 及以下！不允许出现一二级标题！） |
| agent_step        | AgentStep实例  | AgentStep,用于管理Agent的执行步骤列表；<br />（一般情况下步骤中只包含当前任务当前阶段的步骤，在下一个阶段时，上一个阶段的step_state会被同步到stage_state中，不会在列表中留存） |
| step_lock         | List[str]      | 一般用于及时通信中的步骤锁机制；<br />包含多个唯一等待ID的列表，只有列表中所有等待ID都回收后，才执行下一个step，否则会步骤锁会一直暂停执行下一个step |
| tools             | List[str]      | Agent可用的技能                                              |
| skills            | List[str]      | Agent可用的工具                                              |
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
| task_instruction              | 解析并执行具体任务管理操作：<br />1. 创建任务 add_task<br />2. 为任务创建阶段 add_stage<br />3. 结束任务 finish_task<br />4. 结束阶段 finish_stage<br /> |
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
>    Reflection顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
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
>    通过`send_shared_message`字段指导sync_state更新，
>
>    think顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
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
>
> 4. 添加步骤完成情况到task_state的共享消息池：
>
>    通过`send_shared_message`字段指导sync_state更新，
>
>    quick_think顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
>        "content": f"执行quick_think步骤:{shared_step_situation}，"
>    }
>    ```





### 3.7 Send Message 

**期望作用：**Agent在MAS系统内部的对另一个Agent实例的单向消息发送。

**说明：**

Send Message会获取当前stage所有step执行情况的历史信息，使用LLM依据当前send_message_step意图进行汇总后，向指定Agent发送消息。

Send Message 首先需要构建发送对象列表。[<agent_id>, <agent_id>, ...]
其次需要确定发送的内容，通过 Send Message 技能的提示+LLM调用返回结果的解析可以得到。
需要根据发送的实际内容，LLM需要返回的信息:

```python
<send_message>
{
    "receiver": ["<agent_id>", "<agent_id>", ...],
    "message": "<message_content>",  # 消息文本
    "stage_relative": "<stage_id或no_relative>",  # 表示是否与任务阶段相关，是则填对应阶段Stage ID，否则为no_relative的字符串
    "need_reply": <bool>,  # 需要回复则为True，否则为False
    "waiting": <bool>,  # 等待回复则为True，否则为False
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
> 4. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 5. 如果发送消息需要等待回复，则触发步骤锁机制
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

> 1. 将LLM初步消息体转换为MAS通用消息体，并添加待处理消息到task_state.communication_queue：
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
> 2. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
>    ```
>
> 3. 如果发送的消息需要等待回复，则触发Agent步骤锁：
>
>    为消息中的每个receiver生成唯一等待标识ID，并将其全部添加到步骤锁中。在Agent回收全部标识ID（收到包含标识ID的信息）前，步骤锁一直生效，暂停后续step的执行。
>
>    ```python
>    if message["waiting"]:
>    	waiting_id_list = [str(uuid.uuid4()) for _ in message["receiver"]]
>    	agent_state["step_lock"].extend(waiting_id_list)
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
>    通过`send_shared_message`字段指导sync_state更新，
>
>    send_message顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
>        "content": f"执行Send Message步骤:{shared_step_situation}，"
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



Message内容可能包含md标题，为了防止与其他提示的md标题形成标题冲突，因此得调整提示词顺序。



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**

> 1. 组装预提示词
> 2. 组装消息处理步骤提示词
> 3. llm调用
> 4. 解析llm返回的理解内容
> 5. 解析llm返回的持续性记忆信息，追加到Agent的持续性记忆中
> 6. 返回用于指导状态同步的execute_output



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
>    通过`send_shared_message`字段指导sync_state更新，
>
>    process_message顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
>        "content": f"执行process_message步骤:{shared_step_situation}，"
>    }
>    ```





### 3.9 Task Manager

**期望作用：**Agent对任务的管理与调度。（一种特殊权限的技能，一般只有管理者Agent拥有）

**说明：**

Task Manager会参考自身历史步骤信息（前面步骤获取任务信息与阶段信息），生成用于管理任务进程的指令。

任务管理者Agent会通过该技能生成相应操作的指令，指令会再MAS系统中操作对应组件完成实际行动，
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

   该操作会将 task_state 的状态更新为 finished 或 failed

   并通知task_group中所有Agent。



4. 任务阶段判定已结束，进入下一个任务阶段:

   结束阶段 finish_stage。

   该操作会将 stage_state 的状态更新为 finished 或 failed

   阶段完成则进入下一个阶段，如果失败则反馈给任务管理者。



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
>    通过`send_shared_message`字段指导sync_state更新，
>
>    task_manager顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
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
>    通过`send_shared_message`字段指导sync_state更新，
>
>    task_manager顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
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
>
>        11. 查看MAS中所有技能与工具



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
> 2. 解析persistent_memory并追加到Agent持续性记忆中
>
>    ```python
>    new_persistent_memory = self.extract_persistent_memory(response)
>    agent_state["persistent_memory"] += "\n" + new_persistent_memory
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
>    通过`send_shared_message`字段指导sync_state更新，
>
>    ask_info顺利完成时`shared_step_situation`更新为 ”finished“，失败时更新为 “failed”
>
>    ```python
>    execute_output["send_shared_message"] = {
>        "agent_id": agent_state["agent_id"],
>        "role": agent_state["role"],
>        "stage_id": stage_id,
>        "content": f"执行Ask Info步骤:{shared_step_situation}，"
>    }
>    ```



### 3.12 （TODO）

**期望作用：**



**说明：**



**提示词顺序：**

系统 → 角色 → (目标 → 规则) → 记忆



**具体实现：**



**提示词：**



**交互行为：**



**其他状态同步：**











## 4. Tool 工具



工具步骤如果需要反复向LLM确认的，则可以通过步骤锁+添加第二个相同的工具步骤来实现

在工具内部实现分支



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



**process_message方法:**

处理不需要回复的消息，会进入该消息处理分支

> message格式：
> {
>     "task_id": task_id,
>     "sender_id": "<sender_agent_id>",
>     "receiver": ["<agent_id>", "<agent_id>", ...],
>     "message": "<message_content>",  # 消息文本
>     "stage_relative": "<stage_id或no_relative>",  # 表示是否与任务阶段相关，是则填对应阶段Stage ID，否则为no_relative的字符串
>     "need_reply": <bool>,  # 需要回复则为True，否则为False
> }

解析`message["message"]`中的内容

1. 对于需要LLM理解并消化的消息，添加process_message step
2. 如果instruction字典包含start_stage的key,则执行start_stage：
   当一个任务阶段的所有step都执行完毕后，帮助Agent建立下一个任务阶段的第一个step: planning_step）
3. 如果instruction字典包含finish_stage的key,则执行清除该stage的所有step并且清除相应working_memory
4. 如果instruction字典包含finish_task的key,则执行清除该task的所有step并且清除相应working_memory
5. 如果instruction字典包含update_working_memory的key,则更新Agent的工作记忆



## 7. 其他基本组件



### 7.1 LLM Client





### 7.2 Router

Router类根据step_state.type和step_state.executor两个字符串。

访问Executor的注册表_registry，获取对应执行器类，并返回实例化后的执行器类。



### 7.3 Message

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



## 8. 特殊机制



### 8.1 步骤锁（通信等待回复时）

由于我们MAS中Agent与其他组件或其他Agent的通信是通过 Send Message 和 Process Message 技能，以步骤 Step 的方式执行。

为了避免后续待执行 Step 中存在一些依赖当前 Send Message 的回复信息的步骤，在获取到回复信息前就被执行从而导致执行失败，我们在通信机制中引入了步骤锁 Step Lock。

步骤锁可以在等待重要消息回复时暂停Agent Step的执行，直到全部步骤锁被回收（成功接收重要消息的回复）后，回复Agent Step的执行。以此保证涉及到通信等待的Step与其他Step之间逻辑依赖关系不被破坏。即，当我要向其他Agent咨询信息，并对该信息进行整理时，我不会出现在获取到咨询回复（执行 Process Message Step）之前就过早地执行整理 Step 的情况。



通信情况下的 Step Lock 步骤锁涉及三种组件：Agent本身接收消息的执行逻辑 `AgentBase.received` 与 `AgentState`、消息发送 `SendMessage` 和 系统中通信消息构造体的定义 `Message` 。

我们将依次介绍在这些组件下 Step Lock 的运行方式以及我们的考虑



#### 8.1.1 Message

作为MAS中跨Agent的消息传递的一般通用格式，Message字典中有两个字段专门用来帮助传递 Step Lock 步骤锁的信息。



- waiting (Optional[List[str]])：

  （由发起方填写）包含与 receiver (List[str]) 中对应的每个接收者的唯一等待ID

  如果Message发起方需要等待该消息的回复，则该字段会为每个接收方生成一个唯一等待ID，只有当所有的唯一等待ID都回收后，发起方才会进行下一个step，在此之前发起者不进行任何step活动。

  如果不等待，则为None

- return_waiting_id (Optional[str])：

  （由接收方在回复中填写）为接收者在发起者消息中所对应的唯一等待ID

  如果接收方接收到的消息中包含 waiting 字段的唯一等待ID，则接收方回复消息时需要填写自己所对应的唯一等待ID，以便发起方回收发出的唯一等待ID。

  如果不等待，则为None

  

#### 8.1.2 Send Message



1.Send Message 中调用LLM生成初步消息体时，LLM只需要判断是否回复与是否等待：

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



#### 8.1.3 Agent接收消息 与 StepLock 执行

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



