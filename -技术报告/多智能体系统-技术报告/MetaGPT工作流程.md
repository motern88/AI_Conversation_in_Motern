## 1. 智能体入门

文档实例如下：[智能体入门 | MetaGPT](https://docs.deepwisdom.ai/main/zh/guide/tutorials/agent_101.html)

```python
from metagpt.context import Context
from metagpt.roles.product_manager import ProductManager
from metagpt.logs import logger

async def main():
    msg = "Write a PRD for a snake game"
    context = Context()  # 显式创建会话Context对象，Role对象会隐式的自动将它共享给自己的Action对象
    role = ProductManager(context=context)
    while msg:
        msg = await role.run(msg)
        logger.info(str(msg))
```

首先显示创建 Context 对象

其次实例化一个角色，ProductManager，并将 Context 对象传入

最后使用实例化角色的 .run（） 方法运行msg

### 1.1 Context 类

主要用于管理MetaGPT运行环境，包括：

- `kwargs`（使用 `AttrDict` 存储额外环境参数）

  其中 `AttrDict` 支持通过属性访问键值对，运行额外字段，额外提供 `set()`、`get()`、`remove()` 方法。

- `config`（系统配置）
- `cost_manager`（费用管理）
- `_llm`（缓存的 LLM 实例）

关键功能：

1. 运行环境变量

   **new_environ**

   复制当前环境变量，返回一个新的环境变量字典。

2. LLM 费用管理

   **_select_costmanager**

   根据不同 LLM 配置，选择合适的费用管理器。

3. 获取 LLM 实例 

   **llm**

   创建 LLM 实例并缓存。

   若 LLM 实例没有 `cost_manager`，则为其设置费用管理器。

4. 直接从 `llm_config` 获取 LLM

   **llm_with_cost_manager_from_llm_config**

   直接基于 `llm_config` 生成一个 LLM 实例，并设置费用管理器。

5. 序列化和反序列化

   **serialize**

   `kwargs` 转换为字典存储。

   `cost_manager` 通过 `model_dump_json()` 序列化为 JSON。

   **deserialize**

   `kwargs` 逐项恢复。

   `cost_manager` 反序列化 JSON 并进行 Pydantic 验证。



### 1.2 专业化角色（RoleZero） 类

所有实例化的专业化角色都继承自 `RoleZero` 类，在所有专业化角色中都包括：

- `name`：str 角色名字
- `profile`：str 角色简介

- `goal`：str 角色目标
- `constraints`：str 角色约束
- `instruction`：`metagpt.prompts` 中获取，该角色的提示词指令，默认定义为常量
- `tools`：list[str] 该角色可用的工具，`metagpt.tools.libs` 中获取

关键功能

1. 初始化

   这里初始化每个专业化角色所需要初始化的都不同

2. 更新工具执行

   **_update_tool_execution**

   创建 `WritePRD()` 实例

   更新工具执行映射，指定 WritePRD 工具的运行方法

3. 自定义能力

   这里专业化角色会有自己定义的能力，例如  `_think`，`_act`，然而这些能力并不是最小化的技能单元。不同的专业化角色可能有相同的 `_think` 方法命名，但却执行不同的作用。所以MetaGPT这里在专业化角色中自定义的能力不是最小单元的技能，而是由多个最小单元的技能操作按照固定顺序封装的方法。

   > 一个更通用的设计是将这些最小单元的技能skills像Tools一样放在技能库里，由外部配置来组装而非固定顺序写死在代码中。由单Agent内部的循环去决定每一个step执行什么样的skill或tool。

> 在基础角色类以上，如果想实现一个动态角色类，所有的角色仅根据不同的配置文件初始化相同的动态角色类，可以尝试使用 `getattr` 动态调用：
>
> ```python
> class DynamicClass:
>     def __init__(self, name, method_choices):
>         self.name = name
>         self.method_map = {
>             "a": self.method_a,
>             "b": self.method_b,
>             "c": self.method_c
>         }
>         self.available_methods = {key: self.method_map[key] for key in method_choices if key in self.method_map}
> 
>     def method_a(self):
>         print(f"{self.name} 执行了 method_a")
> 
>     def method_b(self):
>         print(f"{self.name} 执行了 method_b")
> 
>     def method_c(self):
>         print(f"{self.name} 执行了 method_c")
> 
>     def call_method(self, method_name):
>         method = self.available_methods.get(method_name, lambda: print("未定义的方法"))
>         method()
> 
> # 创建实例
> obj1 = DynamicClass("实例1", ["a", "b"])  # 具有 method_a 和 method_b
> obj2 = DynamicClass("实例2", ["c"])      # 只有 method_c
> 
> # 调用动态方法
> obj1.call_method("a")  # 实例1 执行了 method_a
> obj1.call_method("b")  # 实例1 执行了 method_b
> obj2.call_method("c")  # 实例2 执行了 method_c
> obj2.call_method("a")  # 未定义的方法
> ```
>
> 如果方法名可能变化，`getattr()` 方式更灵活。



#### 1.2.1 RoleZero（Role） 类

RoleZero 定义了一个可以动态思考和行动的角色，具备工具调用和执行功能，并且可以根据配置进行个性化扩展

------

类的基本信息

```python
name: str = "Zero"
profile: str = "RoleZero"
goal: str = ""
system_msg: Optional[list[str]] = None  # 使用 None 作为默认值
system_prompt: str = SYSTEM_PROMPT
cmd_prompt: str = CMD_PROMPT
cmd_prompt_current_state: str = ""
instruction: str = ROLE_INSTRUCTION
task_type_desc: Optional[str] = None
```

`name` 和 `profile`：角色的名称和身份标识。

`goal`：角色的目标，可以动态设置。

`system_msg` / `system_prompt` / `cmd_prompt`：系统和指令相关的提示，影响角色的行为逻辑。

`instruction`：角色的基本指令。

`cmd_prompt_current_state`：用于存储当前的指令状态。

------

反应模式（ReAct）

```python
react_mode: Literal["react"] = "react"
max_react_loop: int = 50
```

`react_mode`：强制为 `"react"`，表示采用 ReAct 框架（结合推理与行动）。

`max_react_loop`：最大反应循环次数，避免死循环。

------

工具（Tools）

```python
tools: list[str] = []  # 使用特殊符号 ["<all>"] 表示使用所有已注册的工具
tool_recommender: Optional[ToolRecommender] = None
tool_execution_map: Annotated[dict[str, Callable], Field(exclude=True)] = {}
special_tool_commands: list[str] = ["Plan.finish_current_task", "end", "Terminal.run_command", "RoleZero.ask_human"]
exclusive_tool_commands: list[str] = [
    "Editor.edit_file_by_replace",
    "Editor.insert_content_at_line",
    "Editor.append_file",
    "Editor.open_file",
]
```

- `tools`：可用工具列表，可以是具体工具，也可以是 `["<all>"]` 表示全部工具。
- `tool_recommender`：工具推荐器，使用 BM25 进行匹配（后续会初始化）。
- `tool_execution_map`：工具名称到实际方法的映射（将在 `set_tool_execution` 里初始化）。
- `special_tool_commands`：这些特殊工具命令具有更高优先级（如 `ask_human`）。
- `exclusive_tool_commands`：独占工具命令，多个出现时只保留第一个。

------

默认工具

```python
editor: Editor = Editor(enable_auto_lint=True)
browser: Browser = Browser()
```

`editor`：提供文本编辑能力。

`browser`：提供网页浏览能力。

------

经验系统

```python
experience_retriever: Annotated[ExpRetriever, Field(exclude=True)] = DummyExpRetriever()
```

`experience_retriever`：经验检索模块（这里默认是 `DummyExpRetriever`，可能后续会替换成更复杂的版本）

------

记忆管理

```python
observe_all_msg_from_buffer: bool = True
command_rsp: str = ""  # 包含命令的原始字符串
commands: list[dict] = []  # 要执行的命令
memory_k: int = 200  # 记忆的数量
use_fixed_sop: bool = False
respond_language: str = ""  # 语言
use_summary: bool = True  # 是否总结
```

`observe_all_msg_from_buffer`：是否观察所有消息缓冲区内容。

`command_rsp` / `commands`：存储执行的命令。

`memory_k`：控制短期记忆容量。

`respond_language`：应答的语言。

`use_summary`：是否在最终总结任务。

------

**`_think` 方法**

该方法用于代理在 `ReAct` 模式下的思考（Think）过程，决定下一步行动。

**兼容性检查**：

- 如果 `use_fixed_sop` 为 `True`，则调用 `super()._think()`（父类的 `_think` 方法）。

**初始化目标**：

- 如果 `self.rc.todo` 为空，说明没有任务要执行，返回 `False`。
- 如果 `self.planner.plan.goal` 为空，则从记忆中获取最新的用户输入内容作为目标 (`self.get_memories()[-1].content`)。
- 通过 `DETECT_LANGUAGE_PROMPT` 让 LLM 检测语言，并存入 `self.respond_language`。

**获取经验**：

- `self._retrieve_experience()` 获取过去的相关经验（可能是从知识库或存储中检索示例）。

**获取计划状态**：

- `self._get_plan_status()` 获取当前计划状态，并返回 `plan_status` 和 `current_task`。

**工具推荐**：

- `self.tool_recommender.recommend_tools()` 推荐适合的工具，并将其转换为 JSON 格式存入 `tool_info`。

**构造系统提示（System Prompt）**：

- `system_prompt` 包含角色信息、任务描述、可用工具、示例、指令等信息。

**生成 LLM 提示（Prompt）**：

- `self.cmd_prompt.format(...)` 构造 LLM 需要的 `prompt`，用于指引 LLM 进行决策。

**处理记忆信息**：

- `memory = self.rc.memory.get(self.memory_k)` 获取历史记忆。
- 解析浏览器动作（`self.parse_browser_actions(memory)`）。
- 解析编辑器结果（`self.parse_editor_result(memory)`）。
- 解析图片（`self.parse_images(memory)`）。

**调用 LLM 进行推理**：

- `req = self.llm.format_msg(memory + [UserMessage(content=prompt)])` 构造 LLM 请求。
- `self.command_rsp = await self.llm_cached_aask(req=req, system_msgs=[system_prompt], state_data=state_data)` 发送请求，获取 LLM 的响应。
- `self.command_rsp = await self._check_duplicates(req, self.command_rsp)` 进行去重检查。

**返回 `True` 表示有任务待执行**。

------

**`_act` 方法**

执行 LLM 生成的命令。

- `commands, ok, self.command_rsp = await self._parse_commands(self.command_rsp)` 解析 LLM 生成的命令。
- 如果解析失败，则将错误信息存入 `self.rc.memory` 并返回错误消息。
- `outputs = await self._run_commands(commands)` 执行命令并获取输出结果。
- 记录命令及其输出。
- 将输出存入 `self.rc.memory` 并返回 `AIMessage`。

------

**`_react` 方法**

实现 `ReAct`（思考-行动-观察-思考）循环。

**设置 `todo`**：

- 调用 `self._set_state(0)` 允许处理新信息。

**快速思考**：

- `quick_rsp, _ = await self._quick_think()` 进行快速推理，如果可以快速回答，则直接返回答案。

**循环执行 `_think` 和 `_act`**：

- 进入 

  ```
  while actions_taken < self.rc.max_react_loop
  ```

   循环：

  - `await self._observe()` 观察新的信息。
  - `has_todo = await self._think()` 进行思考。
  - 如果没有新的待办事项，跳出循环。
  - `rsp = await self._act()` 执行任务。
  - 记录操作次数 `actions_taken += 1`。

**最大操作轮次检查**：

- 如果 `actions_taken >= self.rc.max_react_loop`，向人类用户询问是否继续。

**返回最终的 `rsp`**。

------

其他附加方法暂时不作介绍

#### 1.2.2 Role（BaseRole, ...）类

Role(BaseRole, SerializationMixin, ContextMixin, BaseModel)

> ##### 1.2.2.1 RoleReactMode
>
> 角色反应模式
>
> `RoleReactMode` 是一个 **枚举类**，定义了角色在不同情境下的 **反应方式**：
>
> - `REACT`（react）：常规模式，角色根据接收到的信息立即做出反应。
>
> - `BY_ORDER`（by_order）：按顺序执行任务，可能意味着角色有预设任务链，按步骤执行。
>
> - `PLAN_AND_ACT`（plan_and_act）：先进行规划（如任务分解、策略生成），然后执行。
>
> **作用**：
>
> 影响 `Role` 在 `RoleContext` 中如何处理 **消息和任务**。
>
> 可能决定 `Role` 处理任务的复杂度，例如：
>
> - `REACT` 适用于简单的指令执行。
>
> - `PLAN_AND_ACT` 可能适用于更复杂的 AI 角色，如 LLM 代理。
>
> ------
>
> ##### 1.2.2.2 RoleContext
>
> 角色的运行时上下文
>
> `RoleContext` 维护了角色的运行环境、记忆、状态等数据，是角色在运行时的核心上下文。
>
> **核心属性：**
>
> `env`：角色所在的环境（`BaseEnvironment`），避免循环导入问题。
>
> `msg_buffer`：角色的 **消息缓冲区**，基于 `MessageQueue`，支持异步更新。
>
> `memory`：角色的 **长期记忆**，存储过去的信息。
>
> `working_memory`：角色的 **工作记忆**，用于短期存储当前任务相关的信息。
>
> `state`：角色的 **当前状态**，默认值 `-1` 代表初始状态。
>
> `todo`：角色当前的 **待办任务**，类型为 `Action`，默认为 `None`。
>
> `watch`：角色 **关注的标签集合**，用于筛选重要消息。
>
> `news`：存储角色感兴趣的消息，当前未使用。
>
> `react_mode`：角色的 **反应模式**（`RoleReactMode`），默认值为 `REACT`。
>
> `max_react_loop`：**最大反应循环次数**，用于防止角色陷入无限循环。
>
> **关键方法：**
>
> - `important_memory(self) -> list[Message]` 
>
>   这个方法通过 `watch` 关注的标签，从 `memory` 获取相关记忆。
>
> - `history(self) -> list[Message]`
>
>   获取所有存储在 `memory` 里的对话历史。
>
> **作用**：
>
> `RoleContext` 充当 **角色的“运行时大脑”**，管理 **环境、消息、记忆、任务、状态** 等信息。
>
> 结合 `react_mode`，决定角色如何做出决策。

------

**基本信息**

```python
name: str = ""  # 角色名称
profile: str = ""  # 角色简介
goal: str = ""  # 角色目标
constraints: str = ""  # 角色约束条件
desc: str = ""  # 角色详细描述
role_id: str = ""  # 角色ID
```

**控制逻辑**

`is_human`：表示该角色是否是一个人类代理。如果是，则 LLM（大语言模型）应替换为 `HumanProvider`。

`enable_memory`：控制该角色是否可以记忆过去的信息。

**运行时状态**

`states`：存储角色当前的状态信息，例如当前正在执行的任务、角色的不同阶段等。

`actions`：该角色可以执行的动作，存储 `Action` 实例。

`rc`（`RoleContext`）：用于管理角色的运行时上下文，例如当前的任务状态、对话记录等。

**角色行为**

`addresses`：`set[str]` 角色的地址集合，通常用于消息传递或识别角色。

`planner`：角色的任务计划器，决定如何执行任务。

`recovered`：标记角色是否从某个状态恢复，例如因故暂停后恢复执行。

`latest_observed_msg`：如果角色因中断而停止，该字段会存储最新的观察消息，以便恢复时使用。

`observe_all_msg_from_buffer`：如果为 `True`，角色会存储所有缓冲区中的消息，否则仅存储特定类别的消息。

------

**核心方法**：

- `_think(self) -> bool`

  让智能体思考下一步该做什么

  如果 `actions` 只有一个，就直接执行该 `Action`

  如果存在恢复状态（`self.recovered`），就从 `self.rc.state` 继续

  如果 `react_mode` 是 **BY_ORDER**（按顺序执行），按顺序推进 `self.rc.state`

  其他情况，调用 **LLM 计算下一步状态**，并转换为整数

- `_act(self) -> Message`

  执行当前 `self.rc.todo`

  可能返回 `ActionOutput`、`ActionNode` 或 `Message`

  结果存入 `self.rc.memory`

- `_observe(self) -> int`

  处理新消息

  过滤出感兴趣的消息并存入 `self.rc.memory`

  维护 `self.latest_observed_msg`（最新观察到的消息）

- `_react(self) -> Message`

  **标准 ReAct（思考-行动循环）**

  调用 `_think()` 获取状态

  调用 `_act()` 执行动作

  直到 `self.rc.max_react_loop` 达到上限或任务完成

- `_plan_and_act(self) -> Message`

  先用 `self.planner` 进行 LLM 规划

  再执行多个 **_act()**

  处理任务结果，并返回最终计划

#### 1.2.3 BaseRole(BaseSerialization) 类

`BaseRole` 是一个抽象基类，定义了所有角色（agent）的基本行为。它继承自 `BaseSerialization`，并提供了一些必须由子类实现的方法。其中包含：

`is_idle`：表示角色是否处于空闲状态（即是否没有待执行的任务）

`think`：思考接下来要做什么，并决定下一步的行动。

`act`：执行当前的动作

`react`：`react` 是一个异步方法，表示角色在接收到信息后，采用某种策略进行反应：

​	基于规则 (By Order)：按照预设的顺序执行任务。

​	ReAct (Reason + Act)：通过思考 (`think()`) 和执行 (`act()`) 交替进行推理和行动。

​	基于计划 (Plan & Act)：角色会先制定一个完整的计划，然后依次执行各个任务。

`run`：该方法用于启动角色，使其能够在收到输入消息后进行思考 (`think()`) 并执行 (`act()`)。

​	该方法结合了观察、思考和行动的流程，通常会：观察 (`_observe()`)，思考 (`_think()`)。执行 (`_act()`)



### 1.3 Role.run（） 运行

```python
from metagpt.context import Context
from metagpt.roles.product_manager import ProductManager

async def main():
    msg = "Write a PRD for a snake game"
    context = Context()  # 显式创建会话Context对象，Role对象会隐式的自动将它共享给自己的Action对象
    role = ProductManager(context=context)
    while msg:
        msg = await role.run(msg)
```

其中role.run：

```python
    @role_raise_decorator
    async def run(self, with_message=None) -> Message | None:
        """观察并根据观察结果进行思考和行动"""
        if with_message:
            msg = None
            if isinstance(with_message, str):
                msg = Message(content=with_message)
            elif isinstance(with_message, Message):
                msg = with_message
            elif isinstance(with_message, list):
                msg = Message(content="\n".join(with_message))
            if not msg.cause_by:
                msg.cause_by = UserRequirement
            self.put_message(msg)
        if not await self._observe():
            # 如果没有新的信息，挂起并等待
            logger.debug(f"{self._setting}: 没有新信息。等待中。")
            return

        rsp = await self.react()

        # 重置下一个动作
        self.set_todo(None)
        # 将响应消息发布到环境对象，由环境将消息传递给订阅者。
        self.publish_message(rsp)
        return rsp
```

其中 `Message(BaseModel)` 于 `metagpt.schema.Message` 

中定义，用于表示一条对话消息（不包含全部上下文）

> `id` (str): 消息的唯一标识符，默认自动生成。
> `content` (str): 用户或代理的自然语言内容。
> `instruct_content` (Optional[BaseModel]): 结构化的指令内容，可选。
> `role` (str): 消息的角色，默认为 "user"（系统 / 用户 / 助手）。
> `cause_by` (str): 触发消息的原因。
> `sent_from` (str): 发送消息的来源。
> `send_to` (set[str]): 发送目标，默认为全体广播。
> `metadata` (Dict[str, Any]): 存储 `content` 和 `instruct_content` 相关的元数据。

其中`rsp = await self.react()`用于产生回复响应，`react()`：

```python
    async def react(self) -> Message:
        """进入三种策略之一，角色根据观察到的消息做出反应"""
        if self.rc.react_mode == RoleReactMode.REACT or self.rc.react_mode == RoleReactMode.BY_ORDER:
            rsp = await self._react()
        elif self.rc.react_mode == RoleReactMode.PLAN_AND_ACT:
            rsp = await self._plan_and_act()
        else:
            raise ValueError(f"不支持的反应模式: {self.rc.react_mode}")
        self._set_state(state=-1)  # 当前反应完成，重置状态为 -1 并将待办任务设为 None
        if isinstance(rsp, AIMessage):
            rsp.with_agent(self._setting)
        return rsp
```

Agent在反应这一步会根据预先设置好的模式选择 `_react()` 或 `_plan_and_act()` 进行进一步处理。

#### 1.3.1 _react()

```python
    async def _react(self) -> Message:
        """先思考，然后执行动作，直到角色认为不再需要进一步的任务为止。
        这是 ReAct 论文中的标准思考-行动循环，在任务求解中交替进行思考和行动，即 _think -> _act -> _think -> _act -> ...
        使用 llm 动态选择动作
        """
        actions_taken = 0
        rsp = AIMessage(content="No actions taken yet", cause_by=Action)  # 初始内容将会在角色 _act 后被覆盖
        while actions_taken < self.rc.max_react_loop:
            # 思考
            has_todo = await self._think()
            if not has_todo:
                break
            # 执行
            logger.debug(f"{self._setting}: {self.rc.state=}, 将执行 {self.rc.todo}")
            rsp = await self._act()
            actions_taken += 1
        return rsp  # 返回最后一次行动的结果
```

先思考 `_think()` 后执行 `_act()` 

- `_react()` 其中 `_think()` ：

```python
    async def _think(self) -> bool:
        """考虑接下来该做什么，并决定下一步的行动。如果无法执行任何操作，返回 False"""
        ...
        # 构造 Prompt
        prompt = self._get_prefix()
        # 格式化 Prompt
        prompt += STATE_TEMPLATE.format(
            history=self.rc.history,
            states="\n".join(self.states),
            n_states=len(self.states) - 1,
            previous_state=self.rc.state,
        )
		# 调用 LLM 生成下一步
        next_state = await self.llm.aask(prompt)
        # 解析 LLM 返回值
        next_state = extract_state_value_from_output(next_state)
        ...
        self._set_state(next_state)
        return True
```

- `_react()` 其中 `_act()` ：

```python
    async def _act(self) -> Message:
        ...
        # 执行任务
        response = await self.rc.todo.run(self.rc.history)
        # 解析response
        if isinstance(response, (ActionOutput, ActionNode)):
            msg = AIMessage(
                content=response.content,
                instruct_content=response.instruct_content,
                cause_by=self.rc.todo,
                sent_from=self,
            )
        elif isinstance(response, Message):
            msg = response
        else:
            msg = AIMessage(content=response or "", cause_by=self.rc.todo, sent_from=self)
        # 存入记忆
        self.rc.memory.add(msg)

        return msg
```

------

以上涉及关键方法： `llm.aask()` 和 `rc.todo.run()`

`self.llm` 于 `ContextMixin` 定义：

```python
from metagpt.provider.base_llm import BaseLLM
class ContextMixin(BaseModel):
	private_llm: Optional[BaseLLM] = Field(default=None, exclude=True)
    ...
	@property
    def llm(self) -> BaseLLM:
        """获取角色 LLM：如果不存在，则从角色配置初始化"""
        if not self.private_llm:
            self.private_llm = self.context.llm_with_cost_manager_from_llm_config(self.config.llm)
        return self.private_llm

    @llm.setter
    def llm(self, llm: BaseLLM) -> None:
        """设置角色 LLM"""
        self.private_llm = llm
```

其中 `provider.base_llm.BaseLLM` 中定义了 `aask` 方法

```python
    async def aask(
        self,
        msg: Union[str, list[dict[str, str]]],
        system_msgs: Optional[list[str]] = None,
        format_msgs: Optional[list[dict[str, str]]] = None,
        images: Optional[Union[str, list[str]]] = None,
        timeout=USE_CONFIG_TIMEOUT,
        stream=None,
    ) -> str:
        # 如果有系统消息，调用 _system_msgs 方法生成系统消息
        if system_msgs:
            message = self._system_msgs(system_msgs)
        else:
            message = [self._default_system_msg()]  # 默认的系统消息
        # 如果不使用系统提示，则清空 message 列表
        if not self.use_system_prompt:
            message = []
        # 如果有格式化消息，扩展到 message 中
        if format_msgs:
            message.extend(format_msgs)
        # 根据 msg 的类型决定如何处理
        if isinstance(msg, str):
            message.append(self._user_msg(msg, images=images))  # 添加用户消息
        else:
            message.extend(msg)  # 如果 msg 是列表，则直接扩展到 message 中
        ...

        # 压缩消息
        compressed_message = self.compress_messages(message, compress_type=self.config.compress_type)
        # 调用异步方法获取回答
        rsp = await self.acompletion_text(compressed_message, stream=stream, timeout=self.get_timeout(timeout))
        return rsp
```



`rc.todo.run()` 为 `RoleContext.todo.run()` 也就是 `Action.run()`

`metagpt.actions.action.Action.run()` 中：

```python
    async def run(self, *args, **kwargs):
        """运行动作"""
        if self.node:
            return await self._run_action_node(*args, **kwargs)  # 如果有节点，运行节点
        
    async def _run_action_node(self, *args, **kwargs):
        """运行动作节点"""
        msgs = args[0]
        context = "## 历史消息\n"
        context += "\n".join([f"{idx}: {i}" for idx, i in enumerate(reversed(msgs))])  # 创建历史消息上下文
        return await self.node.fill(req=context, llm=self.llm)  # 填充节点并返回
```



#### 1.3.2 _plan_and_act()

```python
    async def _plan_and_act(self) -> Message:
        """先规划，然后执行一系列动作，即 _think（规划） -> _act -> _act -> ... 使用 llm 动态制定计划"""
        if not self.planner.plan.goal:
            # 创建初始计划并更新，直到确认目标
            goal = self.rc.memory.get()[-1].content  # 获取最新的用户需求
            await self.planner.update_plan(goal=goal)

        # 执行任务，直到所有任务完成
        while self.planner.current_task:
            task = self.planner.current_task
            logger.info(f"准备执行任务 {task}")

            # 执行当前任务
            task_result = await self._act_on_task(task)

            # 处理任务结果，例如审核、确认、更新计划
            await self.planner.process_task_result(task_result)

        rsp = self.planner.get_useful_memories()[0]  # 返回完成的计划作为响应
        rsp.role = "assistant"
        rsp.sent_from = self._setting

        self.rc.memory.add(rsp)  # 将响应添加到持久化内存中

        return rsp
```

先思考创建任务 `planner.update_plan(goal=goal)`

随后执行任务 `_act_on_task(task)`

```python
while self.planner.current_task:
    task = self.planner.current_task
    task_result = await self._act_on_task(task)
```



其中 `_act_on_task()`，在Role类中未实现，需要在子类中实现（"处理计划中的任务执行"功能）

其中 `planer` 于 `metagpt.strategy.planner.Planner` 中实现。用于管理任务的规划、执行、更新和确认。该类的核心功能包括：

初始化 (`__init__`)

- `goal`: 任务目标
- `plan`: 任务计划对象，若未提供，则会根据目标创建一个新的 `Plan`
- `working_memory`: 存储当前任务的信息，任务完成后会清除
- `auto_run`: 是否自动运行

任务相关的属性

- `current_task`: 获取当前任务
- `current_task_id`: 获取当前任务的 ID

更新任务计划 (`update_plan`)

- 根据新的目标 (`goal`) 重新生成任务计划
- 通过 `WritePlan().run(context, max_tasks=max_tasks)` 生成新任务
- 对生成的计划进行 `precheck_update_plan_from_rsp` 预检查，确保其合理性
- 通过 `ask_review()` 让用户确认计划
- 计划确认后调用 `update_plan_from_rsp()` 更新 `plan`

处理任务执行结果 (`process_task_result`)

- 任务完成后请求用户确认
- 若确认成功，则调用 `confirm_task()` 记录任务进展
- 若用户要求重做，则跳过确认
- 若用户修改任务，则调用 `update_plan()` 更新计划

请求任务审查 (`ask_review`)

- 触发 `AskReview().run()` 获取用户审查结果
- 若用户未确认，则记录审查意见
- 若 `auto_run=True`，则默认任务执行成功

确认任务 (`confirm_task`)

- 更新任务结果 (`update_task_result`)
- 标记当前任务完成 (`finish_current_task`)
- 清除 `working_memory`
- 若用户确认任务但要求调整下游任务，则调用 `update_plan()`

获取有用的记忆 (`get_useful_memories`)

- 返回当前任务的上下文信息，包括：
  - 目标 (`goal`)
  - 计划的整体上下文 (`context`)
  - 任务列表 (`tasks`)
  - 当前任务 (`current_task`)

获取计划状态 (`get_plan_status`)

- 整合当前任务信息，包括：
  - 已完成的任务代码 (`code_written`)
  - 任务执行结果 (`task_results`)
  - 当前任务的说明 (`current_task.instruction`)
  - 指导信息 (`guidance`)







### 1.4 一个Agent运行周期流程


<img src="./asset/MetaGPT4.png" alt="image-20250318094851252" style="zoom: 67%;" />



### 1.5 定义动作 Action

MetaGPT中Agent可以选择的最小动作单元是`Action`。`Action`是动作的逻辑抽象，一般是由提示词封装、LLM输出、最后操作组合而成。例如

```python
from metagpt.actions import Action

class SimpleWriteCode(Action):
    PROMPT_TEMPLATE: str = """
    Write a python function that can {instruction} and provide two runnnable test cases.
    Return ```python your_code_here ``` with NO other texts,
    your code:
    """

    name: str = "SimpleWriteCode"

    async def run(self, instruction: str):
        prompt = self.PROMPT_TEMPLATE.format(instruction=instruction)

        rsp = await self._aask(prompt)

        code_text = SimpleWriteCode.parse_code(rsp)

        return code_text

    @staticmethod
    def parse_code(rsp):
        pattern = r"```python(.*)```"
        match = re.search(pattern, rsp, re.DOTALL)
        code_text = match.group(1) if match else rsp
        return code_text
```

其中run部分组合了提示词，LLM调用，与代码工具使用。



### 1.6 定义角色 Role

在 MetaGPT 中，`Role` 类是智能体的逻辑抽象。一个 `Role` 能执行特定的 `Action`，拥有记忆、思考并采用各种策略行动。基本上，它充当一个将所有这些组件联系在一起的凝聚实体。

一个定义Role的示例是：

1. 我们为其指定一个名称和配置文件。
2. 我们使用 `self._init_action` 函数为其配备期望的动作 `SimpleWriteCode`。
3. 我们覆盖 `_act` 函数，其中包含智能体具体行动逻辑。我们写入，我们的智能体将从最新的记忆中获取人类指令，运行配备的动作，MetaGPT将其作为待办事项 (`self.rc.todo`) 在幕后处理，最后返回一个完整的消息。

如果一个角色具有多个可选`action`时，由`Role.run`来根据策略选择进行`action`的顺序

![MetaGPT执行层级](./asset/MetaGPT执行层级.jpg)



### 1.7 执行 Action

一个示例是，在 `Role.act` 中：

```python
    async def act(self) -> ActionOutput:
        """
        导出 SDK API，供 AgentStore RPC 使用。
        导出的 `act` 函数
        """
        msg = await self._act()
        return ActionOutput(content=msg.content, instruct_content=msg.instruct_content)
```

**由 `_act()` 中执行了具体Action操作**，并生成由 `Message` 承载的Action返回信息，由 `ActionOutput` 来封装具体Action最终的返回信息

其中 `_act()` :

```python
response = await self.rc.todo.run(self.rc.history)
```

这里实际上执行的是 `Action.run` 。 `Action.run` 的实际功能于Action子类中实现，也就是具体组合的不同Action内部会执行不同的多步操作。不同的 `Role` 这里执行的也是不同的 `Role` 自己的 `Action.run` 。



其中 `ActionOutput` ：

```python
class ActionOutput:
    content: str  # 输出的内容，类型为字符串
    instruct_content: BaseModel  # 指令内容，类型为 Pydantic 的 BaseModel 类

    def __init__(self, content: str, instruct_content: BaseModel):
        """
        初始化 ActionOutput 类的实例
        :param content: 输出的文本内容
        :param instruct_content: 需要传递的指令内容，类型为 BaseModel 的实例
        """
        self.content = content  # 设置 content 属性
        self.instruct_content = instruct_content  # 设置 instruct_content 属性

```





## 2. 多智能体入门

在多智能体场景中，定义角色需要做两件事：

1. 使用 `set_actions` 为`Role`配备适当的 `Action`，这与设置单智能体相同
2. 多智能体操作逻辑：我们使`Role` `_watch` 来自用户或其他智能体的重要上游消息。回想我们的SOP，`SimpleCoder`接收用户指令，这是由MetaGPT中的`UserRequirement`引起的`Message`。因此，我们添加了 `self._watch([UserRequirement])`。

当定义好多个角色后，是时候将它们放在一起了。我们初始化所有角色，设置一个 `Team`，并`hire` 它们。运行 `Team`，我们应该会看到它们之间的协作！

```python
import fire
import typer
from metagpt.logs import logger
from metagpt.team import Team
app = typer.Typer()

@app.command()
def main(
    idea: str = typer.Argument(..., help="write a function that calculates the product of a list"),
    investment: float = typer.Option(default=3.0, help="Dollar amount to invest in the AI company."),
    n_round: int = typer.Option(default=5, help="Number of rounds for the simulation."),
):
    logger.info(idea)

    team = Team()
    team.hire(
        [
            SimpleCoder(),
            SimpleTester(),
            SimpleReviewer(),
        ]
    )

    team.invest(investment=investment)
    team.run_project(idea)
    await team.run(n_round=n_round)

if __name__ == "__main__":
    fire.Fire(main)
```

### 2.1 内部机制

![image-20250320104525953](./asset/MetaGPT5.png)

如图的右侧部分所示，`Role`将从`Environment`中`_observe` `Message`。如果有一个`Role` `_watch` 的特定 `Action` 引起的 `Message`，那么这是一个有效的观察，触发`Role`的后续思考和操作。

在 `_think` 中，`Role`将选择其能力范围内的一个 `Action` 并将其设置为要做的事情。在 `_act` 中，`Role`执行要做的事情，即运行 `Action` 并获取输出。将输出封装在 `Message` 中，最终 `publish_message` 到 `Environment`，完成了一个完整的智能体运行。

在每个步骤中，无论是 `_observe`、`_think` 还是 `_act`，`Role`都将与其 `Memory` 交互，通过添加或检索来实现。





## 3. 使用记忆

记忆是智能体的核心组件之一。智能体需要记忆来获取做出决策或执行动作所需的基本上下文，还需要记忆来学习技能或积累经验。

在MetaGPT中，`Memory`类是智能体的记忆的抽象。当初始化时，`Role`初始化一个`Memory`对象作为`self.rc.memory`属性，它将在之后的`_observe`中存储每个`Message`，以便后续的检索。简而言之，`Role`的记忆是一个含有`Message`的列表。

**检索记忆：**

当需要获取记忆时（获取LLM输入的上下文），可以使用`self.get_memories`。函数定义如下：

```python
def get_memories(self, k=0) -> list[Message]:
    """A wrapper to return the most recent k memories of this role, return all when k=0"""
    return self.rc.memory.get(k=k)
```

使用记忆的完整片段如下：

```python
async def _act(self) -> Message:
        logger.info(f"{self._setting}: ready to {self.rc.todo}")
        todo = self.rc.todo

        # context = self.get_memories(k=1)[0].content # use the most recent memory as context
        context = self.get_memories() # use all memories as context

        code_text = await todo.run(context, k=5) # specify arguments

        msg = Message(content=code_text, role=self.profile, cause_by=todo)

        return msg
```

**添加记忆:**

可以使用`self.rc.memory.add(msg)`添加记忆，，其中`msg`必须是`Message`的实例。请查看上述的代码片段以获取示例用法。

建议在定义`_act`逻辑时将`Message`的动作输出添加到`Role`的记忆中。通常，`Role`需要记住它先前说过或做过什么，以便采取下一步的行动。



## 4. 人类介入

最初，LLM扮演 `SimpleReviewer` 的角色。假设我们想对更好地控制审阅过程，我们可以亲自担任这个`Role`。这只需要一个开关：在初始化时设置 `is_human=True`。代码变为：

```python
team.hire(
    [
        SimpleCoder(),
        SimpleTester(),
        # SimpleReviewer(), # 原始行
        SimpleReviewer(is_human=True), # 更改为这一行
    ]
)
```

我们作为人类充当 `SimpleReviewer`，现在与两个基于LLM的智能体 `SimpleCoder` 和 `SimpleTester` 进行交互。我们可以对`SimpleTester`写的单元测试进行评论，比如要求测试更多边界情况，让`SimpleTester`进行改写。这个切换对于原始的SOP和 `Role` 定义是完全不可见的（无影响）。

每次轮到我们回应时，运行过程将暂停并等待我们的输入。只需输入我们想要输入的内容，然后就将消息发送给其他智能体了。

MetaGPT的局限性是人类交互必须写死在代码中，以替代代码中的特定步骤，或作再次确认。然而一个更优的交互形式自然是作为Agent整体随时参与/退出动态工作流程中。



## 5. Agent间通信

智能体之间的消息交换是通过Message中提供标签的属性，以及`Environment`提供的`publish_message`能力来实现的。

- 智能体作为消息的发送者，只需提供消息的来源信息即可。消息的来源对应`Message`的`sent_from`、`cause_by`。

- 智能体作为消息的使用者，需要订阅相应的消息。消息的订阅标签对应`Message`的`cause_by`。

- Environment对象负责将消息按各个智能体的订阅需求，广播给各个智能体。



在规划智能体之间的消息转发流程时，首先要确定智能体的功能边界，这跟设计一个函数的套路一样：

1. 智能体输入什么。智能体的输入决定了智能体对象的`rc.watch`的值。
2. 智能体输出什么。智能体的输出决定了智能体输出`Message`的参数。
3. 智能体要完成什么工作。智能体要完成什么工作决定了智能体有多少action，action之间按什么状态流转。

假设我们要实现如下的流程：

```
Agent A 接收需求并拆分成 10 个子任务。
Agent B 负责执行这 10 个子任务。
Agent C 负责汇总这 10 个子任务的结果。
Agent D 负责审核汇总结果，并向 Agent B 提供反馈。

步骤 2-4 需要重复 3-4 次。

我该如何设计系统架构，确保这些步骤按照正确的方式执行？
我可以用临时代码将它们拼凑在一起，但我想知道正确的架构方式。
```

分析这个场景，我们可以得出如下结论：

1. Agent A负责将需求拆分成10个subtasks.
2. 对于每一个subtask, Agent B,C,D按如下流程处理：

```
Message(subtask) -> AgentB.run -> AgentC.run -> AgentD.run -> AgentB.run -> AgentC.run -> AgentD.run -> ...
```

也就是：

1. Agent B的输入是Agent A的一个subtask，或者是Agent D的执行结果；
2. Agent C的输入是Agent B的输出；
3. Agent D的输入是Agent C的输出；



在所有智能体都定义完毕后，需要将它们放到同一个Environment对象中，然后向第一个Agent发送消息，让它们联动起来：

```python
    context = Context() # Load config2.yaml
    env = Environment(context=context)
    env.add_roles([AgentA(), AgentB(), AgentC(), AgentD()])
    env.publish_message(Message(content='New user requirements', send_to=AgentA)) # 将用户的消息发送个Agent A，让Agent A开始工作。
    while not env.is_idle: # env.is_idle要等到所有Agent都没有任何新消息要处理后才会为True
        await env.run()
```



Environment对象起到了一个Agent间活动的空间。类似我们的Task Group，但最终我们实现MAS在Task Group外面还需要更高一层的活动空间，因为存在部分活跃的Agent却不参与任何Task。





## 6. 序列化与断点恢复

**定义**

断点恢复指在程序运行过程中，记录程序不同模块的产出并落盘。当程序碰到外部如`Ctrl-C`或内部执行异常如LLM Api网络异常导致退出等情况时。

再次执行程序，能够从中断前的结果中恢复继续执行，而无需从0到1开始执行，降低开发者的时间和费用成本

------

**序列化与反序列化**

为了能支持断点恢复操作，需要对程序中的不同模块产出进行结构化存储即序列化的过程，保存后续用于恢复操作的现场。

序列化的操作根据不同模块的功能有所区分，比如角色基本信息，初始化后即可以进行序列化，过程中不会发生改变。

记忆信息，需要执行过程中，实时进行序列化保证完整性（序列化耗时在整个程序执行中的占比很低）。这里，我们统一在发生异常或正常结束运行时进行序列化。



### 6.1 实现逻辑

可能产生中断的情况：

- 网络等问题，LLM-Api调用重试多次后仍失败
- Action执行过程中，输出内容解析失败导致退出
- 人为的`Ctrl-C`对程序进行中断



为了减少后续新增功能对存储结构的影响，使用“一体化“的单json文件进行存储。

当程序发生中断或结束后，在存储目录下的文件结构如下：

```
./workspace
  storage
    team
      team.json          # 包含团队、环境、角色、动作等信息
```



由于MetaGPT是异步执行框架，对于下述几种典型的中断截点和恢复顺序。

1. 角色A（1个action）-> 角色B（2个action），角色A进行action选择时出现异常退出。
2. 角色A（1个action）-> 角色B（2个action），角色B第1个action执行正常，第2个action执行时出现异常退出



情况1

执行入口重新执行后，各模块进行反序列化。角色A未观察到属于自己处理的Message，重新执行对应的action。角色B恢复后，观察到一条之前未处理完毕的Message，则在`_observe`后重新执行对应的`react`操作，按react策略执行对应2个动作。

情况2

执行入口重新执行后，各模块进行反序列化。角色A未观察到属于自己处理的Message，不处理。角色B恢复后，`_observe`到一条之前未完整处理完毕的Message，在`react`中，知道自己在第2个action执行失败，则直接从第2个action开始执行。



**从中断前的Message开始重新执行**

一般来说，Message是不同角色间沟通协作的桥梁，当在Message的执行过程中发生中断后，由于该Message已经被该角色存入环境（Environment）记忆（Memory）中。在进行恢复中，如果直接加载角色全部Memory，该角色的`_observe`将不会观察到中断时引发当时执行`Message`，从而不能恢复该Message的继续执行。
因此，为了保证该Message在恢复时能够继续执行，需要在发生中断后，根据`_observe`到的最新信息，从角色记忆中删除对应的该条Message。

**从中断前的Action开始重新执行**

一般来说，Action是一个相对较小的执行模块粒度，当在Action的执行过程中发生中断后，需要知道多个Actions的执行顺序以及当前执行到哪个Action（`_rc.state`）。当进行恢复时，定位到中断时的Action位置并重新执行该Action。



### 6.2 讨论

MetaGPT的序列化主要用于断点恢复，因为MetaGPT中Agent的角色是通过不同代码组装而来的，所以需要完整记录角色的属性信息，因此保存的需要是每个活跃角色类的序列化信息。

因此在MetaGPT中所有实例对象都继承 `pydantic` 的 `BaseModel` 专门用于方便以序列化的形式保存，同时因为 `BaseModel` 会在反序列化的时候无法恢复子类属性（无法实现多态子类序列化），因此MetaGPT专门写了一个序列化的补充函数 `BaseSerialization` 随着 `BaseModel` 一起继承用于实现多态子类序列化与反序列化。



然而，我们的不同Agent具有相同的属性，Agent与Agent的区别仅在于 `agent_state` 的不同，其实例化的类的代码完全相同。我们通过 `task_state` , `stage_state` , `step_state` , `agent_state` 的设定来完整表示一个活跃项目的全部信息。

**因此我们不需要作额外序列化的操作**，我们只需要将本身字典格式的四种状态保存下来，我们就可以根据状态信息来恢复一个完整的活跃项目。