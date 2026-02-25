"""从 icon.png 生成 icon.ico，供 PyInstaller 和窗口图标使用。仅打包时运行，需 Pillow。"""
import os
import sys

def main() -> int:
    png = os.path.join(os.path.dirname(__file__), "icon.png")
    ico = os.path.join(os.path.dirname(__file__), "icon.ico")
    if not os.path.isfile(png):
        return 1
    try:
        from PIL import Image
        img = Image.open(png).convert("RGBA")
        sizes = [(256, 256), (48, 48), (32, 32), (16, 16)]
        img.save(ico, format="ICO", sizes=sizes)
        return 0
    except Exception:
        return 1

if __name__ == "__main__":
    sys.exit(main())
