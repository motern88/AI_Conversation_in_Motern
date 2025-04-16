'''
第一阶段

一，几何方法自动校准摄像头和投影仪：
摄像头坐标 A × 当前单应性矩阵 H(A,B) = 投影仪坐标 B
投影仪坐标 B 和摄像头中看到的成像 B’ 有固定的设备偏差 F， F(B)=B'

目标使得 B' = A ，即 F(A · H'(A,B)) = A ，其中 H'(A,B) 是目标情况下 A 到 B 的单应性矩阵
假设设备偏差F是线性的，将 F(B) 的作用形式定义为设备偏差矩阵 H_F(B,B'),则:
A · H(A,B) · H_F(B,B') = B' = A · H(A,B')
在目标情况下 A = B' 时:
A · H'(A,B) · H_F'(B,B') = B' = A = A · H'(A,B')
H'(A,B) · H_F(B,B') = H'(A,B') = I
我们已知目标情况下的 H'(A,B') = I ，可以通过求解目标情况下的单应性矩阵 H_F'(B,B')，
来推导出目标情况下的单应性矩阵 H'(A,B)

我们可以把流程划分为几个步骤：
1. 根据 B,B' 求设备偏差矩阵 H_F(B,B')
2. 根据H_F(B,B')求得H'(A,B)


第二阶段

预设一个H(A',A)，可以从已校准的设备中获取
H(A',A) · H'(A,B) · H_F(B,B') = I
已知 H(A',A) 和 H_F(B,B')，可以求得 H'(A,B)


'''
import os
import requests
import numpy as np
import base64
import json
import pickle
from io import BytesIO
from PIL import Image
from ultralytics import YOLO
import matplotlib.pyplot as plt
from scipy.optimize import linear_sum_assignment

class auto_projection:
    '''
    第一阶段自动推理脚本：

    可多次通过API接口获取到当前的 摄像头坐标A 单应性矩阵H(A,B) 和投影仪坐标B，将获取到的A,B,B'累积在历史记录中
        1. 根据历史B,B'求设备偏差矩阵 H_F(B,B')
        2. 根据H_F(B,B')求得H'(A,B)
    如果更新H'(A,B)，则清空历史数据

    第二阶段自动推理脚本：

    a)获取目标情况下的空间位置偏差H(A',A)
    在校准好的设备中，多次通过API接口获取到当前的 摄像头坐标A 单应性矩阵H(A,B) 和投影仪坐标B，将获取到的A,B,B'累积在历史记录中
        1. 根据历史B,B'求设备偏差矩阵 H_F(B,B')
        2. 根据计算出的H_F(B,B')和获取到的H'(A,B)，解出当前的H'(A’,A)

    b)使用预设的H(A',A)计算出未校准桌台的H'(A,B)
    在未校准的设备中，多次通过API接口获取到当前的 摄像头坐标A 单应性矩阵H(A,B) 和投影仪坐标B，将获取到的A,B,B'累积在历史记录中
        1. 根据历史B,B'求设备偏差矩阵 H_F(B,B')
        2. 根据预设的H(A',A)和计算得到的H_F(B,B')，解出当前的H'(A,B)

    '''
    def __init__(self):
        self.get_url = "http://192.168.3.145:18181/req"
        self.send_url = "http://192.168.3.145:18181/setm"
        self.model = YOLO("calibration_box2_gs003_p07.pt")
        self.A_positions_history = []  # 存储A坐标
        self.B_positions_history = []  # 存储B坐标
        self.B_prime_positions_history = []  # 存储B'坐标
        self.H_AB = None  # 存储当前更新前单应性矩阵H(A,B)
        self.H_A_prime_2_A = None  # 存储当前更新前单应性矩阵H(A',A)

    # 调用接口获取A,H(A,B),摄像头视角图片
    def get_request(self, get_url):
        '''
        通过API接口获取到当前的 摄像头坐标A 单应性矩阵H(A,B) 和投影仪坐标B
        '''
        response = requests.get(get_url)  # 发送 GET 请求
        if response.status_code == 200:  # 检查是否请求成功 (状态码 200 表示成功)
            response_data = response.json()  # 解析 JSON 响应
            data = response_data.get("data")

            # 提取 data 下的字段
            H_AB = data.get("m")  # 字符串
            # 去掉字符串中的方括号和分号，然后按逗号分割
            H_AB = H_AB.strip('[]')
            H_AB = H_AB.split(';')
            data_floats = [float(num) for sublist in H_AB for num in sublist.split(',')]
            # 将数值列表转换为 NumPy 数组，并重塑为 3x3 矩阵
            H_AB = np.array(data_floats).reshape(3, 3)

            if self.H_AB is not None:
                assert np.array_equal(self.H_AB, H_AB), f"多次调用时单应性矩阵H(A,B)不一致"
            else:
                self.H_AB = H_AB

            A = data.get("reco") # 获取到的是字符串
            A = json.loads(A)
            frame_base64 = data.get("pic")  # base64格式的图片

            # 将base64格式的图片转化为RGB图像
            frame_data = base64.b64decode(frame_base64)  # 解码 Base64 字符串为二进制数据
            frame = Image.open(BytesIO(frame_data))  # 使用 BytesIO 将二进制数据加载为图像
            rgb_frame = frame.convert("RGB")  # 转换为 RGB 格式

            return A, H_AB, rgb_frame
        else:
            print(f"请求失败，状态码：{response.status_code}")
        return None, None, None

    def send_matrix_to_api(self, matrix, send_url):
        '''
        将计算得到的单应性矩阵发送给API

        参数:
            matrix (list or np.ndarray): 一个 3x3 的矩阵。
            url (str): API 的 URL 地址，默认为 http://192.168.3.145:18181/setm。
        '''
        # 检查输入的矩阵
        if isinstance(matrix, list):
            matrix = np.array(matrix)
        if matrix.shape != (3, 3):
            raise ValueError("输入的矩阵必须是 3x3 的格式。")

        # 将矩阵转换为一维数组
        matrix_flat = matrix.flatten().tolist()

        # 构建 JSON 数据
        payload = {
            "m": matrix_flat
        }
        # 设置请求头
        headers = {
            "Content-Type": "application/json"
        }

        # 发送 POST 请求
        try:
            response = requests.post(send_url, json=payload, headers=headers)
            print("Status Code:", response.status_code)
            print("Response:", response.text)
            return response
        except Exception as e:
            print("请求发送失败:", str(e))
            return None

    # 计算B
    def get_B(self, A, H_AB):
        '''
        根据 摄像头坐标A 和 单应性矩阵H(A,B) 求 投影仪坐标B
        '''
        A_positions = []  # 储存A中多个物体的位置坐标
        B_positions = []  # 储存B中多个物体的位置坐标

        for item in A:
            x1, y1, x2, y2 = item["left"], item["top"], item["right"], item["bottom"]
            cls = item["id"]
            conf = item["confidence"]

            if cls not in [11,14]:
                # 计算中心点坐标
                x_center = (x1 + x2) / 2
                y_center = (y1 + y2) / 2

                # print(f"类别：{cls}，置信度：{conf}，坐标：{coords}")
                A_positions.append({
                    "positions": [x_center, y_center],
                    "class": cls,
                    "confidence": conf
                })

                # 将中心点转化为齐次坐标
                homogeneous_point = np.array([x_center, y_center, 1])  # 齐次坐标

                # 使用单应性矩阵进行坐标变换
                transformed_point = np.dot(H_AB, homogeneous_point)
                transformed_point /= transformed_point[2]  # 齐次归一化
                # 转换后的坐标
                transformed_coords = [transformed_point[0], transformed_point[1]]

                #  TODO:验证B坐标是否正确
                B_positions.append({
                    "positions": transformed_coords,
                    "class": cls,
                    "confidence": conf
                })
        # print("getB:",B_positions)
        return A_positions, B_positions

    # 计算B'
    def get_B_prime(self, rgb_frame):
        '''
        通过摄像头拍摄的图片获取到成像 B'的检测坐标
        '''
        # 执行检测
        results = self.model([rgb_frame], stream=True, conf=0.6, verbose=False)

        B_prime_positions = [] # 用于存储检测结果

        # 处理results对象生成器
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    # 左上角和右下角坐标
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    cls = box.cls.cpu().numpy()  # 物体类别
                    conf = box.conf.cpu().numpy()  # 置信度

                    # 计算中心点坐标
                    x_center = (x1 + x2) / 2
                    y_center = (y1 + y2) / 2

                    B_prime_positions.append({
                        "positions": [x_center, y_center],
                        "class": cls,
                        "confidence": conf
                    })
                    # print(f"投影成像B'坐标: {[x_center, y_center]}, 类别: {cls}, 置信度: {conf}")

        return B_prime_positions

    # 匹配B和B'中的坐标
    def match_B_and_B_prime(self, B_positions, B_prime_positions):
        """
        将投影仪坐标 B 与成像坐标 B' 联系起来。
        使用匈牙利算法找到 B 和 B' 的最佳匹配。
        """
        
        assert len(B_positions) > 0 and len(B_prime_positions) > 0, "B_positions 或 B_prime_positions 为空"
        assert len(B_positions) == len(B_prime_positions), "B_positions 和 B_prime_positions 的长度不一致"

        # 提取中心点坐标
        B_centers = np.array([pos["positions"] for pos in B_positions])
        B_prime_centers = np.array([pos["positions"] for pos in B_prime_positions])

        # 构建距离矩阵
        distance_matrix = np.linalg.norm(B_centers[:, None, :] - B_prime_centers[None, :, :], axis=2)

        # 使用匈牙利算法寻找最佳匹配
        row_indices, col_indices = linear_sum_assignment(distance_matrix)

        # 根据匹配结果重新排列 B_prime_positions
        reordered_B_prime_positions = [B_prime_positions[col] for col in col_indices]

        return reordered_B_prime_positions

    # 计算设备偏差矩阵H_F(B,B')
    def get_H_F(self, B_positions, B_prime_positions):
        '''
        根据投影仪坐标B和成像B'求设备偏差矩阵H_F(B,B')
        输入点需要已经是经过match_B_and_B_prime函数一一匹配的。
        '''

        # 提取中心点坐标
        B_centers = np.array([pos["positions"] for pos in B_positions])
        B_prime_centers = np.array([pos["positions"] for pos in B_prime_positions])

        # 计算单应性矩阵 H_F(B, B')
        # 构造 A 矩阵
        A = []
        for (x, y), (x_prime, y_prime) in zip(B_centers, B_prime_centers):
            A.append([x, y, 1, 0, 0, 0, -x_prime * x, -x_prime * y, -x_prime])
            A.append([0, 0, 0, x, y, 1, -y_prime * x, -y_prime * y, -y_prime])

        A = np.array(A)

        # 解方程 AX = 0 (利用 SVD 分解)
        _, _, vh = np.linalg.svd(A)
        h = vh[-1]  # 取最后一个奇异向量

        # 生成单应性矩阵 H_F 并归一化
        H_F = h.reshape(3, 3)
        H_F /= H_F[2, 2]  # 归一化

        return H_F

    # 计算目标情况下的单应性矩阵H'(A,B)
    def get_H_prime_A_2_B(self, H_F):
        '''
        根据设备偏差矩阵H_F和使得A=B'情况下的单应性矩阵H'(A,B')求得目标情况下的单应性矩阵H'(A,B)
        H'(A,B) = H'(A,B') · H_F^-1
        H'(A,B) = H_F^-1
        '''
        try:
            H_prime_A_2_B = np.linalg.inv(H_F)  # 计算 H_F 的逆矩阵
        except np.linalg.LinAlgError:
            raise ValueError("H_F 矩阵是奇异的，无法求逆。")

        return H_prime_A_2_B

    # 第一阶段执行一次收集数据+历史信息的计算
    def collect_and_calculate_in_history(self):
        '''
        执行一次收集数据+历史信息的计算
        '''
        # 获取摄像头坐标A、单应性矩阵H(A,B)和投影仪坐标B
        A, H_AB, rgb_frame = self.get_request(self.get_url)
        A, B = self.get_B(A, H_AB)

        # 获取B'的检测坐标，并与B进行匹配
        B_prime = self.get_B_prime(rgb_frame)
        B_prime = self.match_B_and_B_prime(B, B_prime)

        # 将A、B、B'的坐标存储到历史记录中
        self.A_positions_history = self.A_positions_history + A
        self.B_positions_history = self.B_positions_history + B
        self.B_prime_positions_history = self.B_prime_positions_history + B_prime
        assert len(self.A_positions_history) == len(self.B_positions_history) == len(self.B_prime_positions_history), "历史记录长度不一致"

        # 计算当前设备偏差矩阵H_F(B,B')
        H_F = self.get_H_F(self.B_positions_history, self.B_prime_positions_history)

        # A=B'情况下的单应性矩阵H'(A,B') = I ， 计算目标情况下的单应性矩阵H'(A,B)
        H_prime_A_2_B = self.get_H_prime_A_2_B(H_F)

        print(
            f"已收集数据对数: {len(self.A_positions_history)}"
            f"校准前的单应性矩阵 H(A,B): \n{H_AB}"
            f"\n当前计算校准后的单应性矩阵 H'(A,B): \n{H_prime_A_2_B}"
        )

        return H_prime_A_2_B

    # 清空历史数据
    def clear(self):
        '''
        一旦更新了H(A,B)就清空历史数据,因为收集的坐标对是历史H(A,B)下的坐标对，不是当前H(A,B)下的坐标对
        '''
        self.A_positions_history = []
        self.B_positions_history = []
        self.B_prime_positions_history = []
        self.H_AB = None
        self.H_A_prime_2_A = None
        print("已清除历史数据对")

    # 第一阶段校准交互
    def stage_1_interaction(self):
        print("请输入命令：\n"
              "'get' 多次调用获取数据计算所有历史数据下的H'(A,B)\n"
              "'send' 发送并应用矩阵\n"
              "'clear' 清除历史数据对\n"
              "'reset' 发送单位矩阵重置\n"
              "'print' 查看当前类历史数据状态\n"
              "输入 'exit' 退出程序。")
        H_prime_A_2_B = None
        while True:
            command = input("一阶段校准-输入命令：").strip().lower()

            if command == "get":
                # 可多次调用calculate函数，收集数据并计算所有历史数据下的H'(A,B)
                H_prime_A_2_B = self.collect_and_calculate_in_history()

            elif command == "send":
                if H_prime_A_2_B is not None:
                    # 此时应用H'(A,B)更新H(A,B)
                    self.send_matrix_to_api(
                        matrix=H_prime_A_2_B,
                        send_url=self.send_url
                    )
                    # 清除历史数据对
                    self.clear()
                else:
                    print("H'(A,B) is None")

            elif command == "clear":
                self.clear()

            elif command == "reset":
                # 将矩阵重置为单位矩阵
                H_prime_A_2_B = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
                self.send_matrix_to_api(
                    matrix=H_prime_A_2_B,
                    send_url=self.send_url
                )

            elif command == "print":
                # 打印当前历史信息状态：
                print("H(A,B)矩阵:", self.H_AB)
                print("历史A坐标:", self.A_positions_history)
                print("历史B坐标:", self.B_positions_history)
                print("历史B'坐标:", self.B_prime_positions_history)

            elif command == "exit":
                print("程序退出。")
                break

            else:
                print("无效命令，请输入 'get', 'send', 'reset', 'print' 或 'exit'。")


    # 第二阶段采集数据获取H(A',A)
    def data_collect(self):
        '''
        在已经校准好的设备中获取目标情况下，空间坐标到摄像头坐标的单应性矩阵H(A',A)
        可多次调用该函数，收集数据并计算所有历史数据下的H(A',A)
        '''
        # 获取摄像头坐标A、单应性矩阵H(A,B)和投影仪坐标B
        A, H_AB, rgb_frame = self.get_request(self.get_url)
        A, B = self.get_B(A, H_AB)

        # 获取B'的检测坐标，并与B进行匹配
        B_prime = self.get_B_prime(rgb_frame)
        B_prime = self.match_B_and_B_prime(B, B_prime)

        # 将A、B、B'的坐标存储到历史记录中
        self.A_positions_history = self.A_positions_history + A
        self.B_positions_history = self.B_positions_history + B
        self.B_prime_positions_history = self.B_prime_positions_history + B_prime
        assert len(self.A_positions_history) == len(self.B_positions_history) == len(
            self.B_prime_positions_history), "历史记录长度不一致"

        # 计算当前设备偏差矩阵H_F(B,B')
        H_F = self.get_H_F(self.B_positions_history, self.B_prime_positions_history)

        # H(A',A) = H(A,B)^-1 · H_F^-1
        H_A_prime_2_A = np.linalg.inv(self.H_AB) @ np.linalg.inv(H_F)

        return H_A_prime_2_A

    # 计算二阶段目标情况下的单应性矩阵H'(A,B)
    def get_H_prime_A_2_B_stage2(self, H_A_prime_2_A, H_F):
        '''
        H(A',A) · H'(A,B) · H_F = I
        H'(A,B) = H(A',A)^-1 · H_F^-1
        '''
        try:
            # 计算 H(A', A) 的逆
            H_A_prime_2_A_inv = np.linalg.inv(H_A_prime_2_A)
        except np.linalg.LinAlgError:
            raise ValueError("H_A_prime_2_A 矩阵是奇异的，无法求逆。")

        try:
            # 计算 H_F 的逆
            H_F_inv = np.linalg.inv(H_F)
        except np.linalg.LinAlgError:
            raise ValueError("H_F 矩阵是奇异的，无法求逆。")

        # 计算 H'(A,B)
        H_prime_A_2_B = np.dot(H_A_prime_2_A_inv, H_F_inv)

        return H_prime_A_2_B

    # 第二阶段执行一次收集数据+历史信息的计算
    def collect_and_calculate_in_history2(self):
        '''
        第二阶段，执行一次收集数据+历史信息的计算
        '''
        # 获取摄像头坐标A、单应性矩阵H(A,B)和投影仪坐标B
        A, H_AB, rgb_frame = self.get_request(self.get_url)
        A, B = self.get_B(A, H_AB)

        # 获取B'的检测坐标，并与B进行匹配
        B_prime = self.get_B_prime(rgb_frame)
        B_prime = self.match_B_and_B_prime(B, B_prime)

        # 将A、B、B'的坐标存储到历史记录中
        self.A_positions_history = self.A_positions_history + A
        self.B_positions_history = self.B_positions_history + B
        self.B_prime_positions_history = self.B_prime_positions_history + B_prime
        assert len(self.A_positions_history) == len(self.B_positions_history) == len(
            self.B_prime_positions_history), "历史记录长度不一致"

        # 计算当前设备偏差矩阵H_F(B,B')
        H_F = self.get_H_F(self.B_positions_history, self.B_prime_positions_history)

        if self.H_A_prime_2_A is None:
            try:
                with open("H_A_prime_2_A.pkl", "rb") as f:
                    self.H_A_prime_2_A = pickle.load(f)
            except FileNotFoundError:
                print("获取H(A',A)未实现。请手动预设H(A',A)。")

        # A'=B'情况下的单应性矩阵H'(A',B') = I ， 计算目标情况下的单应性矩阵H'(A,B)
        H_prime_A_2_B = self.get_H_prime_A_2_B_stage2(self.H_A_prime_2_A, H_F)

        print(
            f"已收集数据对数: {len(self.A_positions_history)}"
            f"校准前的单应性矩阵 H(A,B): \n{H_AB}"
            f"\n当前计算校准后的单应性矩阵 H'(A,B): \n{H_prime_A_2_B}"
        )

        return H_prime_A_2_B

    # 第二阶段校准交互
    def stage_2_interaction(self):
        print("请输入命令：\n"
              "'data_collection' 手动校准后多次调用采集H(A',A)并保存\n"
              "'set_H_A_prime_2_A' 从本地文件读取并设置预设的H(A',A)\n"
              "'get' 多次调用获取数据计算所有历史数据下的H'(A,B)\n"
              "'send' 发送并应用矩阵\n"
              "'clear' 清除历史数据对\n"
              "'reset' 发送单位矩阵以重置\n"
              "'print' 查看当前类历史数据状态\n"
              "输入 'exit' 退出程序。")
        H_prime_A_2_B = None  # H'(A,B)
        while True:
            command = input("二阶段校准-输入命令：").strip().lower()

            if command == "data_collection":
                # 在已绝对校准情况下，多次调用data_collect,收集数据并计算最新H(A',A)
                self.H_A_prime_2_A = self.data_collect()
                # 将self.H_A_prime_2_A保存成本地pkl文件
                with open("H_A_prime_2_A.pkl", "wb") as f:
                    pickle.dump(self.H_A_prime_2_A, f)
                print(f"已保存H(A',A)到本地文件：\n{self.H_A_prime_2_A}")

            elif command == "set_H_A_prime_2_A":
                # 设置H(A',A)为预设值
                with open("H_A_prime_2_A.pkl", "rb") as f:
                    self.H_A_prime_2_A = pickle.load(f)
                print(f"已设置H(A',A)为预设值：\n{self.H_A_prime_2_A}")

            elif command == "get":
                # 未校准时，多次调用calculate函数，收集数据并计算所有历史数据下的H'(A,B)
                H_prime_A_2_B = self.collect_and_calculate_in_history2()

            elif command == "send":
                if H_prime_A_2_B is not None:
                    # 此时应用H'(A,B)更新H(A,B)
                    self.send_matrix_to_api(
                        matrix=H_prime_A_2_B,
                        send_url=self.send_url
                    )
                    # 清除历史数据对
                    self.clear()
                else:
                    print("H'(A,B) is None")

            elif command == "clear":
                self.clear()

            elif command == "reset":
                # 将矩阵重置为单位矩阵
                H_prime_A_2_B = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
                self.send_matrix_to_api(
                    matrix=H_prime_A_2_B,
                    send_url=self.send_url
                )

            elif command == "print":
                # 打印当前历史信息状态：
                print("H(A,B)矩阵:", self.H_AB)
                print("计算的H(A',A)矩阵:", self.H_A_prime_2_A)
                print("历史A坐标:", self.A_positions_history)
                print("历史B坐标:", self.B_positions_history)
                print("历史B'坐标:", self.B_prime_positions_history)

            elif command == "exit":
                print("程序退出。")
                break

            else:
                print("无效命令，请输入'data_collection', 'set_H_A_prime_2_A', 'get', 'send', 'reset', 'print' 或 'exit'。")



def visualize_detections(rgb_frame, detections):
    """
    在原图上可视化检测结果。仅测试时使用。
    """
    # 创建图形
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    # 绘制原始图像
    ax.imshow(rgb_frame)
    ax.axis("off")  # 不显示坐标轴

    # 遍历检测结果，绘制框和类别
    for detection in detections:
        coords = detection["positions"]
        # 绘制检测框
        x0, y0, x1, y1 = coords
        w, h = x1 - x0, y1 - y0
        ax.add_patch(plt.Rectangle((x0, y0), w, h, edgecolor='red', facecolor='none', lw=1))

    # 显示图像
    plt.show()

if __name__ == '__main__':
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
    auto_projection = auto_projection()
    auto_projection.stage_1_interaction()  # 第一阶段自动校准测试
    # auto_projection.stage_2_interaction()  # 第二阶段自动校准测试
