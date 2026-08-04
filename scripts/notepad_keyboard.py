"""自动化按键操作：粘贴文本 + 保存文件"""
import ctypes
import ctypes.wintypes as w
import time
import os
import sys

user32 = ctypes.windll.user32

KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56
VK_S = 0x53
VK_RETURN = 0x0D
SW_RESTORE = 9

def press_key(vk):
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.08)

def ctrl_key(k):
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.05)
    press_key(k)
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.3)

action = sys.argv[1] if len(sys.argv) > 1 else 'paste'

# 等待并激活记事本
hwnd = None
if action == 'paste':
    for _ in range(30):
        hwnd = user32.FindWindowW('Notepad', None) or user32.FindWindowW(None, '无标题 - 记事本')
        if hwnd:
            break
        time.sleep(0.1)
    if not hwnd:
        print("❌ 未找到记事本")
        exit(1)
    
    print("✅ 激活记事本窗口")
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    
    print("📝 粘贴静夜思...")
    ctrl_key(VK_V)
    time.sleep(0.3)
    print("✅ 粘贴完成")

elif action == 'save':
    print("💾 按 Ctrl+S 打开保存对话框...")
    ctrl_key(VK_S)
    time.sleep(2)
    
    # 粘贴路径
    ctrl_key(VK_V)
    time.sleep(0.5)
    
    # Enter 保存
    press_key(VK_RETURN)
    time.sleep(1)
    
    # 检查结果
    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    full_path = os.path.join(desktop, '静夜思.txt')
    if os.path.exists(full_path):
        print(f"✅ 文件已保存: {full_path}")
    else:
        # 可能有覆盖提示，按 Enter 确认
        press_key(VK_RETURN)
        time.sleep(0.5)
        if os.path.exists(full_path):
            print(f"✅ 文件已保存: {full_path}")
        else:
            print("❌ 保存未成功（可能需要手动处理）")

print("🎉 操作完成！")
