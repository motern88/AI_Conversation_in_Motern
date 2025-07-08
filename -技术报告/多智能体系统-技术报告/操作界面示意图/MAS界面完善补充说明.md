## MAS界面完善补充说明

记录一些可以完善的点




### 1. Step总览中展示的Step顺序部分有误

<img src="/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250708100649230.png" alt="image-20250708100649230" style="zoom:100%;" />

![image-20250708101226888](/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250708101226888.png)



我猜测这里是不是特地设计了让init的灰色块排在最左边？其实正常顺序应当是

```
 多个浅绿色块 -> 一个深绿色块 -> 多个灰色块
```

并且我记得step_list中直接顺序就是这样的，含义是：

```
已执行块 -> 正在执行块 -> 未执行块
```



### 2. Task完整信息弹窗中共享消息池显示

![image-20250708161431677](/C:/Users/20212/AppData/Roaming/Typora/typora-user-images/image-20250708161431677.png)

这里共享消息池显示顺序改为倒叙比较好，让最新的消息放在最上面，旧的消息在最下面。
