## MAS界面完善补充说明

记录一些可以完善的点



### 1. markdown编译

以下涉及到展示文本的字段值需要进行markdown编译

例如:

- Task State 中

  `task_intention` 和 `task_summary` 字段值展示时需要md编译

- Stage State 中

  `stage_intention` 和 `completion_summary` 字段值展示时需要md编译

- Agent State 中

  `profile` 字段值展示时需要md编译

- Step State 中

  `step_intention` 和 `text_context` 字段值展示时需要md编译

  

### 2. Step总览中Agent卡片调整

显示步骤状态时 Agent 卡片（元素`C1`）尽量窄一点。该卡片在这个界面只展示状态和名字，不需要多大的空间，可以窄一点，把名字压缩得换行也行



### 3. Step总览中Step卡片颜色调整

**Step状态卡片背面颜色：**

finished 应当为浅绿色 , running 为深绿色；
但是目前finished 的卡片背面颜色为 蓝色，需要改为浅绿色

**Step状态卡片正面颜色：**

状态指示灯中，finished的浅绿色和running的深绿色 色差需要再拉大一些，区分更明显



### 4. Step总览中Step卡片顺序

当前Step总览中每个Step是无序排列的

```python
"agent_step":{
	"step_list": List[Dict] # 包含多个步骤的列表，每个步骤以字典形式存储信息
	"todo_list": List(str) # 包含step_id的顺序列表
}
```

step_list中记录每个step的详细信息，但是是无序的。

todo_list中按顺序记录了每个step的id。



#### 4.1 记录Agent中Step顺序的难点

尽管todo_list是一个按顺序记录step_id的列表，可以根据todo_list去排列实际的step_list中的信息。

**但是todo_list是一个随时变化的列表**，其靠前的元素会随着Agent的执行，而逐渐被取走。

所以可能需要

1. 及时获取todo_list的信息并记录（避免前端没有在 todo_list更新的某个step_id到该step_id消失期间获取到）
2. 一个汇总的包含全部step顺序的列表（由不同时刻的todo_list组合而成，根据此表可以查看到已经在当前todo_list中消失的step_id所处的实际位置顺序），每个Agent都应该维护一张这个列表。
3. 场上所有的 `step_state` 状态根据汇总的顺序表确定自己的相对位置。
   因为step_list中的 `step_state` 也会随着任务的执行而被清除。所以仅需要展示当前时刻的 step_list 中的所有 `step_state` ，并且按照一个汇总的包含全部step顺序的列表。

**很有可能还是我们在MAS内部维护这个完整顺序列表比较好**，因为前端缓存可能因为访问频率的限制漏掉一些产生变化的状态。





### 5. Agent详细信息弹窗中，执行一栏未正常更新step

<img src="/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250702113523949.png" alt="image-20250702113523949" style="zoom: 67%;" />

图注：这里已经执行了多个step了，但是仍然只有一个最开始的step并没有更新其他step



Agent详细信息弹窗中 `执行` 一栏应当记录Agent下所有Step信息。

但是目前发现其中只有第一个step信息，没有展示后续更新的其他Step信息



注：这里每个Step是有顺序的

```python
"agent_step":{
	"step_list": List[Dict] # 包含多个步骤的列表，每个步骤以字典形式存储信息
	"todo_list": List(str) # 包含step_id的顺序列表
}
```



### 6. Agent总览中Agent卡片展示关于step的地方，未正常更新

<img src="/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250702113550520.png" alt="image-20250702113550520" style="zoom:67%;" />

图注：这里已经执行了多个step了，但是仍然只有一个最开始的step（灰色的方块）并没有更新其他step



### 7. Human-Agent完整信息弹窗 - 对话消息 - 对话组界面

<img src="/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250702142329916.png" alt="image-20250702142329916" style="zoom:67%;" />

图注：

对话组界面中线（分隔 左侧对话组列表 和 右侧对话记录）希望增加可以左右拖动以缩放页面中左侧和右侧画幅比例的功能