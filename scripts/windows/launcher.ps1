# Windows PowerShell 5.1; save with UTF-8 BOM for Russian text.
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$requirements = Join-Path $root 'requirements.txt'
$stamp = Join-Path $root '.venv\mashup-requirements.sha256'
$lastResult = 0
$originalInput = [Console]::InputEncoding
$originalOutput = [Console]::OutputEncoding
$oldPythonUtf8 = $env:PYTHONUTF8
$oldPythonIO = $env:PYTHONIOENCODING
try {
    # .NET console APIs use Unicode; also set UTF-8 for redirected I/O and Python.
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    Set-Location -LiteralPath $root
} catch {
    [Console]::Error.WriteLine("Не удалось настроить консоль или открыть каталог проекта: $_")
    exit 1
}

function Say([string]$message) { [Console]::WriteLine($message) }
function Ask([string]$message) {
    [Console]::Write($message)
    return [Console]::ReadLine()
}
function FullPath([string]$value) {
    $value = $value.Trim()
    if ($value.Length -ge 2 -and $value[0] -eq '"' -and $value[$value.Length - 1] -eq '"') {
        $value = $value.Substring(1, $value.Length - 2)
    }
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $root $value }
    return [IO.Path]::GetFullPath($value)
}
# Isolated subprocess: probing failures are expected and do not leak noisy stderr.
function Compatible([string]$exe, [string]$arguments) {
    try {
        $p = New-Object System.Diagnostics.Process
        $p.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
        $p.StartInfo.FileName = $exe
        $p.StartInfo.Arguments = "$arguments -c `"import sys; print('MASHUP_PYTHON_OK' if sys.version_info >= (3,11) else 'MASHUP_PYTHON_OLD')`""
        $p.StartInfo.UseShellExecute = $false
        $p.StartInfo.CreateNoWindow = $true
        $p.StartInfo.RedirectStandardOutput = $true
        $p.StartInfo.RedirectStandardError = $true
        if (-not $p.Start()) { return $false }
        $stdout = $p.StandardOutput.ReadToEnd()
        $stderr = $p.StandardError.ReadToEnd()
        $p.WaitForExit()
        return ($p.ExitCode -eq 0 -and $stdout.Trim() -eq 'MASHUP_PYTHON_OK')
    } catch { return $false }
}
function FindPython {
    $py = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($py) {
        foreach ($selector in @('-3.13', '-3.12', '-3.11')) {
            if (Compatible $py.Source $selector) { return @{ Exe = $py.Source; Args = @($selector) } }
        }
    }
    $python = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($python -and (Compatible $python.Source '')) { return @{ Exe = $python.Source; Args = @() } }
    if ($py -and (Compatible $py.Source '-3')) { return @{ Exe = $py.Source; Args = @('-3') } }
    return $null
}
function RequirementsHash {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($requirements)
        try { $bytes = $sha.ComputeHash($stream) } finally { $stream.Dispose() }
        return ([BitConverter]::ToString($bytes).Replace('-', ''))
    } finally { $sha.Dispose() }
}
function Ready {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { Say 'Окружение .venv не найдено. Выберите пункт 2.'; return $false }
    if (-not (Compatible $venvPython '')) { Say 'Python в .venv не работает или его версия ниже 3.11. Окружение не удаляется.'; return $false }
    if (-not (Test-Path -LiteralPath $stamp -PathType Leaf)) { Say 'Зависимости ещё не подготовлены. Выберите пункт 2.'; return $false }
    $hash = (RequirementsHash)
    if (([IO.File]::ReadAllText($stamp)).Trim() -ne $hash) { Say 'requirements.txt изменился. Выберите пункт 2.'; return $false }
    & $venvPython -c 'import yaml, numpy, soundfile; import mashup; import mashup.render' | Out-Host
    if ($LASTEXITCODE -ne 0) { Say 'Ошибка импорта библиотек. Выберите пункт 2.'; return $false }
    & $venvPython -m pip check | Out-Host
    if ($LASTEXITCODE -ne 0) { Say 'Проверка зависимостей не пройдена. Выберите пункт 2.'; return $false }
    return $true
}
function Prepare {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        if (Test-Path -LiteralPath (Join-Path $root '.venv')) {
            Say 'Каталог .venv существует, но Python в нём отсутствует. Он не удалён; проверьте его вручную.'; return 1
        }
        $candidate = FindPython
        if ($null -eq $candidate) {
            Say 'Python 3.11 или новее не найден. Установите Python с https://www.python.org/downloads/windows/ (с py launcher или добавлением в PATH), затем перезапустите лаунчер.'
            return 1
        }
        Say 'Создание локального окружения .venv...'
        $pythonArgs = $candidate.Args
        & $candidate.Exe @pythonArgs -m venv (Join-Path $root '.venv') | Out-Host
        if ($LASTEXITCODE -ne 0) { Say 'Не удалось создать .venv; существующие файлы не удалены.'; return 1 }
    }
    if (-not (Compatible $venvPython '')) { Say 'Python в .venv не работает или несовместим. Окружение не удалено.'; return 1 }
    if (Ready) { Say 'Окружение уже готово; переустановка не требуется.'; return 0 }
    # A stale stamp must never certify a failed installation.
    if (Test-Path -LiteralPath $stamp) { Remove-Item -LiteralPath $stamp -Force }
    Say 'Установка зависимостей в .venv из requirements.txt...'
    & $venvPython -m pip install -r $requirements | Out-Host
    if ($LASTEXITCODE -ne 0) { Say 'Ошибка установки. Проверьте интернет и сообщения pip; глобальный Python не изменён.'; return 1 }
    & $venvPython -c 'import yaml, numpy, soundfile; import mashup; import mashup.render' | Out-Host
    if ($LASTEXITCODE -ne 0) { Say 'Ошибка импорта после установки.'; return 1 }
    & $venvPython -m pip check | Out-Host
    if ($LASTEXITCODE -ne 0) { Say 'Ошибка проверки зависимостей.'; return 1 }
    [IO.File]::WriteAllText($stamp, (RequirementsHash))
    Say 'Окружение готово.'; return 0
}
function CheckEnvironment {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf) -or -not (Compatible $venvPython '')) {
        Say 'Зависимости не проверены: нет работающего .venv. Выберите пункт 2.'; return $false
    }
    & $venvPython -m mashup.environment_check | Out-Host
    return ($LASTEXITCODE -eq 0)
}
function PrepareGui {
    if (-not (Ready)) { return 1 }
    $guiRequirements = Join-Path $root 'requirements-gui.txt'
    if (-not (Test-Path -LiteralPath $guiRequirements -PathType Leaf)) { Say 'Файл requirements-gui.txt не найден.'; return 1 }
    Say 'Установка интерфейса PySide6 и FFmpeg (imageio-ffmpeg) в .venv...'
    & $venvPython -m pip install -r $guiRequirements | Out-Host
    if ($LASTEXITCODE -ne 0) { Say 'Не удалось установить интерфейс.'; return 1 }
    & $venvPython -m pip check | Out-Host
    if ($LASTEXITCODE -ne 0) { Say 'Проверка зависимостей не пройдена.'; return 1 }
    if (-not (CheckEnvironment)) {
        Say 'Попытка восстановить зависимости из requirements-gui.txt...'
        & $venvPython -m pip install --force-reinstall -r $guiRequirements | Out-Host
        if ($LASTEXITCODE -ne 0) { Say 'Не удалось восстановить зависимости.'; return 1 }
        if (-not (CheckEnvironment)) { Say 'Зависимости не прошли проверку. Проверьте сообщения выше и IMAGEIO_FFMPEG_EXE, затем повторите пункт 8.'; return 1 }
    }
    Say 'Интерфейс и FFmpeg установлены и проверены.'; return 0
}
function RunProject([string]$command) {
    if (-not (Ready)) { return 1 }
    $inputPath = Ask 'Путь к project.yaml (пустая строка — отмена): '
    if ([string]::IsNullOrWhiteSpace($inputPath)) { Say 'Отменено.'; return 0 }
    $project = FullPath $inputPath
    if (-not $project) { Say 'Отменено.'; return 0 }
    if (-not (Test-Path -LiteralPath $project -PathType Leaf)) { Say 'Файл проекта не найден.'; return 1 }
    $arguments = @('-m', 'mashup', $command, $project)
    if ($command -eq 'render') {
        Say 'Только PCM WAV 48 кГц; duration_ratio=1, pitch_semitones=0. Ресемплинг и time/pitch пока не поддерживаются.'
        $outputInput = Ask 'Путь к новому выходному WAV (пустая строка — отмена): '
        if ([string]::IsNullOrWhiteSpace($outputInput)) { Say 'Отменено.'; return 0 }
        $output = FullPath $outputInput
        if (-not $output) { Say 'Отменено.'; return 0 }
        if (Test-Path -LiteralPath $output) { Say 'Выходной файл уже существует: перезапись не поддерживается. Выберите другое имя.'; return 1 }
        $arguments += @('-o', $output)
    }
    & $venvPython @arguments | Out-Host
    $code = $LASTEXITCODE
    if ($code -ne 0) { Say "Ошибка CLI (код $code). См. сообщение выше." } else { Say 'Команда завершена.' }
    return $code
}
try {
    Say 'Mashup Lab — диагностика и команды CLI. Интерфейс: Start-Mashup-Lab.bat. Окно можно закрыть после выхода из меню.'
    while ($true) {
        Say "`n1. Проверить все зависимости и окружение`n2. Подготовить окружение и установить все зависимости`n3. Проверить проект`n4. Построить план проекта`n5. Выполнить рендер`n6. Открыть документацию`n7. Выход`n8. Установить / восстановить зависимости интерфейса"
        $choice = Ask 'Выберите пункт: '
        if ($null -eq $choice) { break }
        try {
            switch ($choice.Trim()) {
                '1' {
                    $candidate = FindPython
                    if ($candidate) { Say "Найден совместимый Python: $($candidate.Exe) $($candidate.Args -join ' ')" } else { Say 'Совместимый системный Python не найден (для создания .venv нужен Python 3.11+).' }
                    $baseReady = Ready
                    $guiReady = CheckGui
                    if ($baseReady -and $guiReady) { Say 'Окружение, интерфейс и FFmpeg готовы.'; $lastResult = 0 } else { $lastResult = 1 }
                }
                '2' {
                    $lastResult = Prepare
                    if ($lastResult -eq 0) { $lastResult = PrepareGui }
                }
                '3' { $lastResult = RunProject 'validate' }
                '4' { $lastResult = RunProject 'plan' }
                '5' { $lastResult = RunProject 'render' }
                '6' {
                    $doc = Join-Path $root 'docs\windows-launcher.md'
                    if (-not (Test-Path -LiteralPath $doc -PathType Leaf)) { Say 'Документация не найдена.'; $lastResult = 1 }
                    else { Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $doc + '"') -ErrorAction Stop; $lastResult = 0 }
                }
                '7' { break }
                '8' { $lastResult = PrepareGui }
                default { Say 'Введите число от 1 до 8.'; continue }
            }
            if ($choice.Trim() -eq '7') { break }
        } catch { [Console]::Error.WriteLine("Ошибка лаунчера: $_"); $lastResult = 1 }
    }
} finally {
    [Console]::InputEncoding = $originalInput
    [Console]::OutputEncoding = $originalOutput
    $env:PYTHONUTF8 = $oldPythonUtf8
    $env:PYTHONIOENCODING = $oldPythonIO
}
exit $lastResult
