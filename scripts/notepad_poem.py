"""自动化：在记事本中写静夜思并保存到桌面"""
import ctypes
import ctypes.wintypes as w
import time
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

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

def set_clipboard_text(text):
    """用 Win32 API 设置剪贴板文本"""
    data = text.encode('utf-16-le')
    GMEM = 0x0002 | 0x0040  # GMEM_MOVEABLE | GMEM_ZEROINIT
    user32.OpenClipboard(None)
    user32.EmptyClipboard()
    hMem = kernel32.GlobalAlloc(GMEM, len(data) + 2)
    pMem = kernel32.GlobalLock(hMem)
    ctypes.memmove(pMem, data, len(data))
    ctypes.memset(pMem + len(data), 0, 2)
    kernel32.GlobalUnlock(hMem)
    user32.SetClipboardData(13, hMem)  # CF_UNICODETEXT = 13
    user32.CloseClipboard()

# 1. 等待并激活记事本窗口
print("正在查找记事本窗口...")
hwnd = None
for _ in range(50):
    hwnd = user32.FindWindowW('Notepad', None)
    if hwnd:
        break
    time.sleep(0.1)

if not hwnd:
    # 尝试用类名查找
    for _ in range(50):
        hwnd = user32.FindWindowW(None, '无标题 - 记事本')
        if hwnd:
            break
        time.sleep(0.1)

if not hwnd:
    print("❌ 未找到记事本窗口")
    exit(1)

print("✅ 找到记事本窗口，激活中...")
user32.ShowWindow(hwnd, SW_RESTORE)
user32.SetForegroundWindow(hwnd)
user32.BringWindowToTop(hwnd)
time.sleep(0.5)

# 2. 粘贴静夜思
poem = '静夜思\n\n床前明月光，疑是地上霜。\n举头望明月，低头思故乡。'
print("正在输入静夜思...")
set_clipboard_text(poem)
time.sleep(0.2)
ctrl_key(VK_V)
time.sleep(0.5)

# 3. Ctrl+S 保存
print("正在保存文件...")
ctrl_key(VK_S)
time.sleep(1.5)  # 等待保存对话框

# 4. 获取桌面路径
desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
full_path = os.path.join(desktop, '静夜思.txt')
print(f"保存路径: {full_path}")

# 5. 在保存对话框中输入完整路径文件名
set_clipboard_text(full_path)
time.sleep(0.3)
ctrl_key(VK_V)
time.sleep(0.3)

# 6. 按 Enter 保存
press_key(VK_RETURN)
time.sleep(1)

# 验证文件是否存在
if os.path.exists(full_path):
    print(f"✅ 文件已保存到桌面: {full_path}")
else:
    print("⚠️ 文件可能未保存成功，检查是否有覆盖确认对话框...")
    # 按 Alt + Y/或Tab+Enter处理覆盖确认
    time.sleep(1)
    press_key(VK_RETURN)
    time.sleep(0.5)
    if os.path.exists(full_path):
        print(f"✅ 文件已保存到桌面: {full_path}")
    else:
        print("❌ 保存失败，请手动检查")
