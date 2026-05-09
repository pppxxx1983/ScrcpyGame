# 启动脚本：设置大模型 API Key 后运行项目
# 等 DeepSeek Key 到了，取消下面一行的注释并填入

$env:DASHSCOPE_API_KEY = "sk-b368216722514ad1956826669fe15b05"
$env:DEEPSEEK_API_KEY = "sk-891612caaa0f4d018dd8ba0a391632d3"

# 若提示权限错误，先在 PowerShell 执行: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
# 或直接右键 -> 使用 PowerShell 运行

.\venv\Scripts\python.exe main.py
