# AutoAIAnswer

Windows 截图搜题助手。通过全局鼠标手势框选屏幕题目，调用视觉模型分析，并把答案实时流式发送到同一局域网内的手机浏览器；也可选择在桌面显示轻量透明悬浮答案。

## 功能

- 支持选择题、判断题、填空题、计算题和简答题
- DeepSeek 与 OpenRouter 双提供商配置
- 每次启动优先使用 DeepSeek；DeepSeek 返回 HTTP 402 时自动切换 OpenRouter
- OpenRouter 默认模型为 `qwen/qwen3.8-flash`，模型 ID 可修改
- DeepSeek Key、OpenRouter Key 和模型设置可在桌面界面保存
- 手机二维码配对，答案与解析在单一输出框中流式显示
- 可拖动、置顶的透明桌面悬浮答案，默认关闭
- 模型生成期间暂停鼠标手势，避免误触

## 使用方式

1. 启动程序，填写并保存 DeepSeek Key、OpenRouter Key 和 OpenRouter 模型。
2. 确保手机与电脑连接同一局域网。
3. 用手机扫描桌面窗口中的二维码并保持页面打开。
4. 在题目区域起点按住鼠标左键至少 2 秒，松开后移动到区域终点，再普通单击一次左键。
5. 程序截图并分析，答案会实时显示在手机端；若开启悬浮答案，也会同步显示在桌面。

Windows 首次运行可能询问防火墙权限，请允许程序访问“专用网络”，否则手机可能无法连接电脑的 8000 端口。

## 模型切换规则

- 软件启动后首先使用 DeepSeek 官方接口与视觉模型。
- 只有 DeepSeek 返回 HTTP 402（额度不足）时，才会用同一截图重试 OpenRouter。
- 切换后，本次软件运行期间继续使用 OpenRouter；重启软件后重新从 DeepSeek 开始。
- 认证失败、限流、超时、网络错误和服务端错误不会自动切换，以免重复消耗额度。

## 从源码运行

需要 Windows 和 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

也可以直接编辑界面中的 Key 并保存。`.env` 仅用于首次提供默认值，已被 Git 忽略。

## 配置

复制 `.env.example` 为 `.env`，按需设置：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash-vision-exp
DEEPSEEK_BASE_URL=https://api.deepseek.com

OPENROUTER_API_KEY=
OPENROUTER_MODEL=qwen/qwen3.8-flash
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

不要提交真实 API Key。桌面界面保存的设置由 Qt `QSettings` 存储在当前 Windows 用户配置中。

## 测试

```powershell
python -m pytest tests -q
```

## 构建单文件 EXE

先在本地 `.env` 填好你希望内置的默认配置，然后运行：

```bat
build_windows_exe.bat
```

生成文件为 `dist\AI_Assistant.exe`。构建脚本会把本地 `.env` 嵌入 EXE；请勿公开上传带有真实 Key 的构建产物。仓库已忽略 `dist/`、`build/`、`.env` 和 `*.spec`。

## 安全说明

- API Key 在用户要求下以明文形式显示和保存，请只在可信电脑上使用。
- 桌面悬浮窗是普通置顶窗口，可能出现在屏幕共享或录制内容中。
- 本项目不提供规避录屏、共享屏幕或监控检测的功能。

## License

当前仓库未附带开源许可证。未经作者明确授权，不代表允许复制、修改或再分发。
