$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $env:DASHSCOPE_API_KEY) { throw '请先配置 DASHSCOPE_API_KEY 环境变量。' }
New-Item -ItemType Directory -Force data | Out-Null
$pythonExe = (Get-Command python).Source
$calculator = Start-Process -FilePath $pythonExe -ArgumentList 'external_calculator.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data/calculator.out.log' -RedirectStandardError 'data/calculator.err.log'
$server = Start-Process -FilePath $pythonExe -ArgumentList 'app.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data/server.out.log' -RedirectStandardError 'data/server.err.log'
@{server=$server.Id;calculator=$calculator.Id} | ConvertTo-Json | Set-Content -Encoding UTF8 data/processes.json
Write-Output 'CampusClaw 已启动：http://127.0.0.1:8092/platform'
