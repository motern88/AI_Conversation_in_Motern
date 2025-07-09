## MAS界面完善补充说明

记录一些可以完善的点



### 1. Task完整信息弹窗中共享消息池显示

![image-20250708161431677](/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250708161431677.png)

这里共享消息池显示顺序改为倒叙比较好，让最新的消息放在最上面，旧的消息在最下面。

**同时，这里共享消息池字段有变更**！见 `T1 Task` - `C3 通讯` 章节

含义从 `共享消息池` 变更为 `共享信息池`

API中获取到TaskState中对应字段从 `shared_message_pool`  变更为 `shared_info_pool` 





### 2. Step总览显示

![image-20250708175940009](/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250708175940009.png)

- 代表Agent的每一行的高度可以再低一点（矮一点），同理代表每个Step的元素块可以同步矮一点

- 代表每个Step的元素块可以再窄一点：

  其中当前显示是：

  ```markdown
  [skill] Planning
  ```

  但其实可以窄一点显示成

  ```markdown
  [skill]
  Planning
  ```

  其中Step类型（skill或tool）可以放在和状态指示灯同一行的位置；状态指示灯在最上行左边，Step类型在最上行右边



### 3. Step完整信息弹窗-内容

![image-20250708180727270](/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250708180727270.png)

Step完整信息展示中两个部分的标题可以去掉`|------------XXX------------|`的形式。
直接显示Text content 和 Instruction content标题就好



### 4. 完整信息弹窗窗口缩放

能不能让弹窗的窗口大小缩放，从只能拖拽右下角的特定位置，改为可以从上下左右四条边任意拖拽来缩放窗口大小





### 5. 弹窗无法贴到浏览器边框

![image-20250708181536366](/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250708181536366.png)

弹窗可移动区域，距离浏览器边界有一定距离。

有没有办法能够取消这个限制，使得弹窗可以紧贴着边界
