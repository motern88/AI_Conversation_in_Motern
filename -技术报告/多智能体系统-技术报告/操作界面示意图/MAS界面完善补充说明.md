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



### 4. Agent详细信息弹窗中，执行一栏未正常更新step

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



### 5. Agent总览中Agent卡片展示关于step的地方，未正常更新

<img src="/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250702113550520.png" alt="image-20250702113550520" style="zoom:67%;" />

图注：这里已经执行了多个step了，但是仍然只有一个最开始的step（灰色的方块）并没有更新其他step



### 6. Human-Agent完整信息弹窗 - 对话消息 - 对话组界面

<img src="/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250702142329916.png" alt="image-20250702142329916" style="zoom:67%;" />

图注：

对话组界面中线（分隔 左侧对话组列表 和 右侧对话记录）希望增加可以左右拖动以缩放页面中左侧和右侧画幅比例的功能




### 7. Step总览中展示的Step顺序错乱

<img src="/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250704114250874.png" alt="image-20250704114250874" style="zoom:67%;" />

这里展示的Step顺序没有正确反映出step_list的顺序。step_list字段值是正常的，但是展示出的卡片顺序是不正常的。