from pymem import Pymem
import pymem.process
import time
import os
import pygame
import keyboard
import tkinter as tk

# ================= 配置区 =================
PROCESS_NAME = "Grim Dawn.exe"
MODULE_NAME = "Engine.dll"
# TODO: 填入你用 CE 找出的基址偏移和多级偏移量
BASE_OFFSET = 0x00361534  # 替换为真实的基址偏移
OFFSETS = [0x2C, 0x248, 0x108, 0x390, 0xDD4] # 替换为真实的偏移量路径

COMBO_TIMEOUT = 5.0  # 连杀中断时间（秒），比如 5 秒内没杀怪就结算

# --- 动态难度配置 ---
BASE_TIMEOUT = 5.0   # 刚开始连杀时的允许间隔（秒）
MIN_TIMEOUT = 1.5    # 无论连杀多高，最低保留的间隔（秒）
TIME_DECAY = 0.1     # 每多杀一只怪，允许时间减少多少秒

# --- 音效配置区 ---
SOUND_EFFECTS = {
    10: "sounds/rampage.wav",     
    20: "sounds/unstoppable.wav", 
    30: "sounds/godlike.wav"      
}
# ==========================================

class ComboOverlay:
    def __init__(self, root):
        self.root = root
        self.setup_ui()
        
        self.pm = None
        self.base_address = None
        self.previous_total_kills = None
        self.current_combo = 0
        self.last_kill_time = 0
        self.current_timeout = BASE_TIMEOUT # 当前允许的连杀时间
        
        pygame.mixer.init()
        self.connect_to_game()

    def setup_ui(self):
        """设置透明无边框置顶窗口 (使用 Canvas 替代 Label)"""
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-transparentcolor", "black")
        self.root.config(bg="black")
        
        # 把窗口稍微加宽一点，给两边的进度条留足空间 (宽 600, 高 150)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = int((screen_width - 600) / 2)
        y_pos = int(screen_height - 300)
        self.root.geometry(f"600x150+{x_pos}+{y_pos}")

        # 创建画板 (背景纯黑，无边框)
        self.canvas = tk.Canvas(self.root, width=600, height=150, bg="black", highlightthickness=0)
        self.canvas.pack(expand=True)
        
        self.draw_ui(text="等待连接...", color="#FFD700", size=36, ratio=0)

    def connect_to_game(self):
        try:
            self.pm = Pymem(PROCESS_NAME)
            module = pymem.process.module_from_name(self.pm.process_handle, MODULE_NAME)
            self.base_address = module.lpBaseOfDll
            self.draw_ui(text="监听中...", color="#00FF00", size=24, ratio=0)
            
            self.root.after(2000, lambda: self.canvas.delete("all"))
            self.root.after(2000, self.memory_loop)
            
        except Exception:
            self.draw_ui(text="未检测到游戏进程", color="#FF0000", size=24, ratio=0)
            self.root.after(2000, self.connect_to_game)

    def get_total_kills(self):
        try:
            addr = self.pm.read_uint(self.base_address + BASE_OFFSET)
            if addr == 0: return None
            for offset in OFFSETS[:-1]:
                addr = self.pm.read_uint(addr + offset)
                if addr == 0: return None
            return self.pm.read_int(addr + OFFSETS[-1])
        except:
            return None

    def play_sound(self, combo_count):
        if combo_count in SOUND_EFFECTS:
            sound_file = SOUND_EFFECTS[combo_count]
            if os.path.exists(sound_file):
                try:
                    pygame.mixer.Sound(sound_file).play()
                except:
                    pass

    def get_dynamic_timeout(self, combo_count):
        """核心难度公式：根据连杀数计算当前允许的时间"""
        # 初始5秒，每多杀1只减0.1秒，但绝对不会低于1.5秒
        calc_time = BASE_TIMEOUT - (combo_count * TIME_DECAY)
        return max(MIN_TIMEOUT, calc_time)

    def draw_ui(self, text, color, size, ratio):
        """核心绘图逻辑：同时画出文字和两边的倒计时条"""
        self.canvas.delete("all") # 先清空上一帧的画面
        
        # 1. 在正中心绘制文字 (x=300, y=75)
        self.canvas.create_text(300, 75, text=text, fill=color, font=("Impact", size, "italic"), justify="center")
        
        # 2. 如果剩余时间比例大于0，绘制两边的燃烧条
        if ratio > 0:
            # 颜色随时间变化：时间多是橙色，快断了变红色
            bar_color = "#FF5E00" if ratio > 0.3 else "#FF0000"
            
            # 最大长度为 180 像素，离中心文字有 20 像素的间距
            max_bar_length = 180
            current_length = max_bar_length * ratio
            
            # 左侧燃烧条：右端固定在 x=200，左端往右缩进
            left_bar_x1 = 200 - current_length
            left_bar_x2 = 200
            self.canvas.create_rectangle(left_bar_x1, 70, left_bar_x2, 80, fill=bar_color, outline="")
            
            # 右侧燃烧条：左端固定在 x=400，右端往左缩进
            right_bar_x1 = 400
            right_bar_x2 = 400 + current_length
            self.canvas.create_rectangle(right_bar_x1, 70, right_bar_x2, 80, fill=bar_color, outline="")

    def memory_loop(self):
        if keyboard.is_pressed('f9'):
            print("\n【系统提示】收到 F9 指令，悬浮窗安全退出！")
            os._exit(0)

        current_total_kills = self.get_total_kills()

        if current_total_kills is not None:
            if self.previous_total_kills is None:
                self.previous_total_kills = current_total_kills

            # --- 检测到击杀 ---
            elif current_total_kills > self.previous_total_kills:
                kills_just_made = current_total_kills - self.previous_total_kills
                self.current_combo += kills_just_made
                self.last_kill_time = time.time()
                self.previous_total_kills = current_total_kills
                
                # 更新当前允许的倒计时阈值！
                self.current_timeout = self.get_dynamic_timeout(self.current_combo)
                
                self.play_sound(self.current_combo)

        # --- 刷新 UI 与倒计时逻辑 ---
        if self.current_combo > 0:
            # 计算已经过去了多少时间
            time_elapsed = time.time() - self.last_kill_time
            # 计算剩余时间比例 (0.0 到 1.0)
            ratio = 1.0 - (time_elapsed / self.current_timeout)
            
            if ratio > 0:
                # 倒计时还在走，刷新文字和变短的进度条
                self.draw_ui(f"{self.current_combo} 连杀", color="#FFD700", size=48, ratio=ratio)
            else:
                # 比例 <= 0，连杀中断！结算！
                if self.current_combo >= 10:
                    if self.current_combo <= 20:
                        self.draw_ui(f"小试牛刀!\n{self.current_combo} 杀", color="#8A2BE2", size=40, ratio=0)
                        self.root.after(3000, lambda: self.canvas.delete("all"))
                    elif self.current_combo <= 30:
                        self.draw_ui(f"锋芒毕露!\n{self.current_combo} 杀", color="#FFE600", size=40, ratio=0)
                        self.root.after(3000, lambda: self.canvas.delete("all"))
                    elif self.current_combo <= 40:
                        self.draw_ui(f"大杀特杀!\n{self.current_combo} 杀", color="#FFAE00", size=40, ratio=0)
                        self.root.after(3000, lambda: self.canvas.delete("all"))
                    elif self.current_combo > 50:
                        self.draw_ui(f"天下无双!\n{self.current_combo} 杀", color="#FF0000", size=40, ratio=0)
                        self.root.after(3000, lambda: self.canvas.delete("all"))
                else:
                    self.canvas.delete("all")
                    
                self.current_combo = 0

        # 每 30 毫秒刷新一次（提高到 30ms 让进度条动画更丝滑）
        self.root.after(30, self.memory_loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = ComboOverlay(root)
    print("【系统提示】悬浮窗已启动！在游戏内按下 F9 键即可安全退出程序。")
    root.mainloop()