# Windows PowerShell 5.1; UTF-8 BOM is added below.
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $root '.venv\Scripts\python.exe'
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    Set-Location -LiteralPath $root
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        [Console]::WriteLine('Окружение не найдено. Откройте Mashup-Lab.bat и выберите пункт 2.')
        exit 1
    }
    [Console]::WriteLine('Проверка зависимостей перед запуском...')
    & $python -m mashup.environment_check | Out-Host
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m mashup gui | Out-Host
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine("Не удалось запустить интерфейс: $_. Откройте Mashup-Lab.bat для диагностики.")
    exit 1
}
