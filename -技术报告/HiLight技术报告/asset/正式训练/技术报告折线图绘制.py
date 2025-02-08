import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

# 设置matplotlib支持中文的字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用宋体
plt.rcParams['axes.unicode_minus'] = False  # 正确显示负号

# 读取Excel文件
file_path = 'D:/markdown/HiLight技术报告/asset/正式训练/lr1e-5_ft_2332_table10k/进球test.xlsx'
df = pd.read_excel(file_path, index_col=0, header=0)

# 设置图形大小
plt.figure(figsize=(10, 6))

# 循环绘制每个样本的折线
for sample in df.index:  # 每个样本
    sample_data = df.loc[sample]  # 获取该样本的所有数据
    plt.plot(sample_data.index, sample_data.values, label=f'Sample {sample}')  # 绘制折线，x轴为模型步数，y轴为相似性得分，添加标签

# # 循环绘制每一列数据
# for column in df.columns:  # 遍历每一列数据
#     plt.plot(df.index, df[column], label=column)  # 绘制折线，x轴为索引，y轴为相应列数据，添加标签


# 添加标题和轴标签
plt.title('table10k训练过程以进球视频测试')
plt.xlabel('模型训练步数（10000）')
plt.ylabel('不同文本的数值相似性')

# 显示图例
plt.legend()

# 显示网格
plt.grid(True)

# 显示图表
plt.show()