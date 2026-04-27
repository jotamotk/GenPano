# Test Archive

这个文件夹存放临时测试脚本、调试文件和截图，按日期组织。

## 目录结构

```
test_archive/
├── README.md
├── 2026-03-27/          # Gemini 调试相关文件
│   ├── debug_gemini_server.py
│   ├── test_gemini_*.py
│   ├── trigger_*.py
│   └── ...
└── YYYY-MM-DD/           # 未来的测试文件
```

## 归档文件说明

### 2026-03-27
- **Gemini 调试**: Playwright 浏览器版本问题、输入框可见性问题调试
- 主要修复:
  1. 更新 Playwright 到 1.58 解决 "Target crashed"
  2. 放宽输入框可见性检查 (visible=False 也接受)
