'''
台球物理碰撞模拟

- 定义屏幕尺寸（1920*1080分辨率）
- 球桌四个边界（用坐标表示）
- 定义台球直径尺寸

- 定义直线运动速度动量衰减率
- 定义撞击边界速度动量衰减率
- 定义台球相互撞击速度动量衰减率

定义好以上超参数后，初始化一些台球和初始速度方向，然后可视化模拟台球在球桌中的运动轨迹

'''

import pygame
import math
import random

# 初始化 pygame
pygame.init()

# 显示设置
SIM_WIDTH, SIM_HEIGHT = 1920, 1080  # 模拟坐标范围
WINDOW_WIDTH, WINDOW_HEIGHT = 960, 540  # 实际可视化窗口大小（半屏）

SCALE_X = WINDOW_WIDTH / SIM_WIDTH
SCALE_Y = WINDOW_HEIGHT / SIM_HEIGHT

# 球桌边界（不规则四边形）
TABLE_BOUNDARY = [
    (120, 110),   # 左上角
    (1800, 200),  # 右上角
    (1900, 950),  # 右下角
    (110, 950),   # 左下角
]


# 球参数
BALL_RADIUS = 20  # 台球半径（逻辑坐标）
FRICTION = 0.98  # 直线运动动量衰减
WALL_BOUNCE_DAMPING = 0.95  # 边界反弹动量衰减
BALL_COLLISION_DAMPING = 0.95  # 球之间碰撞动量衰减


# 台球类
class Ball:
    def __init__(self, x, y, vx, vy, color=None):
        self.x = x  # 逻辑坐标
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color if color else (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))

    # 移动规则
    def move(self):
        # 更新位置
        self.x += self.vx
        self.y += self.vy
        # 应用摩擦力
        self.vx *= FRICTION
        self.vy *= FRICTION
        # 撞击边界反弹
        self.reflect_if_outside(self, TABLE_BOUNDARY)

    # 绘制球体
    def draw(self, screen, scale_x, scale_y):
        # 缩放坐标
        draw_x = int(self.x * scale_x)
        draw_y = int(self.y * scale_y)
        draw_radius = int(BALL_RADIUS * (scale_x + scale_y) / 2)
        pygame.draw.circle(screen, self.color, (draw_x, draw_y), draw_radius)

    # 碰撞检测：判断球是否在边界内
    def reflect_if_outside(self, ball, polygon):
        for i in range(len(polygon)):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % len(polygon)]

            dx, dy = x2 - x1, y2 - y1
            edge_length = math.hypot(dx, dy)
            if edge_length == 0:
                continue
            # 法向量（指向多边形外侧）
            nx, ny = -dy / edge_length, dx / edge_length

            # 点到边的投影距离
            tx, ty = ball.x - x1, ball.y - y1
            proj = tx * nx + ty * ny  # 距离边界的“外扩投影距离”

            if proj < BALL_RADIUS:
                # 反弹速度
                vn = ball.vx * nx + ball.vy * ny
                if vn < 0:
                    ball.vx -= 2 * vn * nx * WALL_BOUNCE_DAMPING
                    ball.vy -= 2 * vn * ny * WALL_BOUNCE_DAMPING

                # 推回边界内
                correction = BALL_RADIUS - proj
                ball.x += nx * correction
                ball.y += ny * correction


# 台球模拟类
class BilliardsSimulation:
    def __init__(self, width=WINDOW_WIDTH, height=WINDOW_HEIGHT, ball_count=16):
        self.WINDOW_WIDTH = width
        self.WINDOW_HEIGHT = height
        self.scale_x = width / SIM_WIDTH
        self.scale_y = height / SIM_HEIGHT

        self.screen = pygame.display.set_mode((self.WINDOW_WIDTH, self.WINDOW_HEIGHT))
        pygame.display.set_caption("台球物理碰撞模拟")
        self.clock = pygame.time.Clock()
        self.balls = self.init_balls(ball_count)

        self.running = True

    # 判断点是否在多边形内
    def point_in_polygon(self, x, y, polygon):
        n = len(polygon)
        inside = False
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[(i + 1) % n]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-6) + xi):
                inside = not inside
        return inside

    # 随机生成一个在多边形内的点
    def random_point_inside_polygon(self, polygon, padding=BALL_RADIUS):
        min_x = min(p[0] for p in polygon)
        max_x = max(p[0] for p in polygon)
        min_y = min(p[1] for p in polygon)
        max_y = max(p[1] for p in polygon)

        while True:
            x = random.randint(int(min_x + padding), int(max_x - padding))
            y = random.randint(int(min_y + padding), int(max_y - padding))
            if self.point_in_polygon(x, y, polygon):
                return x, y

    # 随机生成球的初始位置和速度
    def init_balls(self, count):
        balls = []
        for _ in range(count):
            x, y = self.random_point_inside_polygon(TABLE_BOUNDARY)
            vx = random.uniform(-50, 50)  # 随机速度
            vy = random.uniform(-50, 50)  # 随机速度
            balls.append(Ball(x, y, vx, vy))
        return balls

    # 球之间碰撞检测
    def handle_ball_collisions(self, balls):
        for i in range(len(balls)):
            for j in range(i + 1, len(balls)):
                ball1 = balls[i]
                ball2 = balls[j]
                dx = ball2.x - ball1.x
                dy = ball2.y - ball1.y
                dist = math.hypot(dx, dy)
                if dist < 2 * BALL_RADIUS:
                    overlap = 2 * BALL_RADIUS - dist
                    nx = dx / (dist + 1e-6)
                    ny = dy / (dist + 1e-6)

                    # 位置校正
                    ball1.x -= nx * overlap / 2
                    ball1.y -= ny * overlap / 2
                    ball2.x += nx * overlap / 2
                    ball2.y += ny * overlap / 2

                    # 速度调整（简化弹性碰撞）
                    v1n = ball1.vx * nx + ball1.vy * ny
                    v2n = ball2.vx * nx + ball2.vy * ny
                    v1t = -ball1.vx * ny + ball1.vy * nx
                    v2t = -ball2.vx * ny + ball2.vy * nx

                    ball1.vx = v2n * nx - v1t * ny
                    ball1.vy = v2n * ny + v1t * nx
                    ball2.vx = v1n * nx - v2t * ny
                    ball2.vy = v1n * ny + v2t * nx

    def shoot_ball(self, pos):
        x, y = pos
        vx = random.uniform(-50, 50)  # 随机速度
        vy = random.uniform(-50, 50)  # 随机速度
        new_ball = Ball(x, y, vx, vy)
        self.balls.append(new_ball)

    def run(self):
        while self.running:
            self.clock.tick(60)  # 控制帧率为60 FPS
            self.screen.fill((30, 30, 30))  # 深色背景

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # 左键点击
                        self.shoot_ball(event.pos)

            # 更新球运动
            for ball in self.balls:
                ball.move()

            # 球体间碰撞处理
            self.handle_ball_collisions(self.balls)

            # 绘制球体
            for ball in self.balls:
                ball.draw(self.screen, self.scale_x, self.scale_y)

            # 绘制球桌边界
            scaled_boundary = [(int(x * self.scale_x), int(y * self.scale_y)) for (x, y) in TABLE_BOUNDARY]
            pygame.draw.polygon(self.screen, (0, 100, 0), scaled_boundary, width=5)

            pygame.display.flip()

        pygame.quit()

if __name__ == "__main__":
    '''
    运行脚本
    '''
    sim = BilliardsSimulation()
    sim.run()


