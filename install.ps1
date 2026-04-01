#Requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$Claude,
    [switch]$Cursor,
    [switch]$Codex,
    [switch]$Opencode,
    [switch]$Gemini,
    [switch]$Antigravity,
    [switch]$Copilot,
    [switch]$All,
    [switch]$List,
    [string]$Skills,
    [switch]$NoInteractive,
    [switch]$Help
)

$NexusBaseUrl = if ($env:TASKSMITH_NEXUS_URL) { $env:TASKSMITH_NEXUS_URL } else { "https://repo.gabia.com/repository/raw-repository/tasksmith" }
$GitLabHost = if ($env:TASKSMITH_GITLAB_HOST) { $env:TASKSMITH_GITLAB_HOST } else { "gitlab.gabia.com" }
$GitLabProject = if ($env:TASKSMITH_GITLAB_PROJECT) { $env:TASKSMITH_GITLAB_PROJECT } else { "gabia/idc/tasksmith" }
$Branch = if ($env:TASKSMITH_BRANCH) { $env:TASKSMITH_BRANCH } else { "main" }
$ArchiveName = "tasksmith-skills.zip"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] " -ForegroundColor Blue -NoNewline
    Write-Host $Message
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Get-UserHomePath {
    foreach ($candidate in @($env:USERPROFILE, $HOME, [Environment]::GetFolderPath("UserProfile"))) {
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            return $candidate
        }
    }
    throw "사용자 홈 디렉터리를 확인할 수 없습니다."
}

$UserHomePath = Get-UserHomePath
$AgentOrder = @("claude", "cursor", "codex", "opencode", "gemini", "antigravity", "copilot")
$AgentConfig = @{
    "claude" = @{ Name = "Claude Code"; Path = Join-Path $UserHomePath ".claude\skills" }
    "cursor" = @{ Name = "Cursor"; Path = Join-Path $UserHomePath ".claude\skills" }
    "codex" = @{ Name = "Codex CLI"; Path = Join-Path $UserHomePath ".codex\skills" }
    "opencode" = @{ Name = "OpenCode"; Path = Join-Path $UserHomePath ".config\opencode\skills" }
    "gemini" = @{ Name = "Gemini CLI"; Path = Join-Path $UserHomePath ".gemini\skills" }
    "antigravity" = @{ Name = "Antigravity"; Path = Join-Path $UserHomePath ".gemini\antigravity\global_skills" }
    "copilot" = @{ Name = "GitHub Copilot"; Path = Join-Path $UserHomePath ".claude\skills" }
}

function Show-HelpText {
@"
Windows용 Tasksmith 스킬 설치기

사용법:
  irm <url>/install.ps1 | iex
  .\install.ps1 -Codex

옵션:
  -Claude -Cursor -Codex -Opencode -Gemini -Antigravity -Copilot
  -All
  -List
  -Skills "tasksmith,tasksmith-worker"
  -NoInteractive

환경변수:
  TASKSMITH_AGENTS         claude,codex 처럼 지정하거나 all 사용
  TASKSMITH_SKILLS         설치할 스킬 목록
  TASKSMITH_LIST           true면 목록 출력
  TASKSMITH_NO_INTERACTIVE true면 메뉴 생략
  TASKSMITH_NEXUS_URL      배포 산출물 기준 URL
"@
}

if ($Help) {
    Show-HelpText
    exit 0
}

function Test-CanPrompt {
    if ($NoInteractive) {
        return $false
    }
    try {
        return [Environment]::UserInteractive -and ([Console]::WindowHeight -gt 0)
    }
    catch {
        return $false
    }
}

function Get-LocalSkillsRoot {
    $scriptPath = $PSCommandPath
    if (-not $scriptPath) {
        return $null
    }
    $scriptDir = Split-Path -Parent $scriptPath
    $skillsRoot = Join-Path $scriptDir "skills"
    if (Test-Path $skillsRoot -PathType Container) {
        return $skillsRoot
    }
    return $null
}

$LocalSkillsRoot = Get-LocalSkillsRoot

function Get-LocalSkillsList {
    param([string]$SkillsRoot)

    $manifestPath = Join-Path $SkillsRoot "manifest.txt"
    if (Test-Path $manifestPath -PathType Leaf) {
        return Get-Content $manifestPath | Where-Object { $_.Trim() -ne "" }
    }

    return Get-ChildItem -Path $SkillsRoot -Directory | Sort-Object Name | ForEach-Object { $_.Name }
}

function Get-RemoteSkillsList {
    $manifestUrls = @(
        "$NexusBaseUrl/manifest.txt",
        "https://$GitLabHost/$GitLabProject/-/raw/$Branch/skills/manifest.txt"
    )

    foreach ($url in $manifestUrls) {
        try {
            $response = Invoke-WebRequest -Uri $url -ErrorAction Stop
            $lines = $response.Content -split '\r?\n' | Where-Object { $_.Trim() -ne "" }
            if ($lines.Count -gt 0) {
                return $lines
            }
        }
        catch {
        }
    }

    throw "manifest.txt를 가져올 수 없습니다."
}

function Get-SkillsList {
    if ($LocalSkillsRoot) {
        return Get-LocalSkillsList -SkillsRoot $LocalSkillsRoot
    }
    return Get-RemoteSkillsList
}

if ($env:TASKSMITH_SKILLS -and -not $Skills) {
    $Skills = $env:TASKSMITH_SKILLS
}
if ($env:TASKSMITH_LIST -match "^(?i:true|1|yes|y)$") {
    $List = $true
}
if ($env:TASKSMITH_NO_INTERACTIVE -match "^(?i:true|1|yes|y)$") {
    $NoInteractive = $true
}

$SelectedAgents = @()
if ($env:TASKSMITH_AGENTS) {
    if ($env:TASKSMITH_AGENTS -eq "all") {
        $SelectedAgents = $AgentOrder.Clone()
    }
    else {
        $SelectedAgents = $env:TASKSMITH_AGENTS -split ',' | ForEach-Object { $_.Trim().ToLower() }
    }
}
if ($Claude) { $SelectedAgents += "claude" }
if ($Cursor) { $SelectedAgents += "cursor" }
if ($Codex) { $SelectedAgents += "codex" }
if ($Opencode) { $SelectedAgents += "opencode" }
if ($Gemini) { $SelectedAgents += "gemini" }
if ($Antigravity) { $SelectedAgents += "antigravity" }
if ($Copilot) { $SelectedAgents += "copilot" }
if ($All) { $SelectedAgents = $AgentOrder.Clone() }
$SelectedAgents = $SelectedAgents | Select-Object -Unique

$InvalidAgents = @($SelectedAgents | Where-Object { $_ -and -not $AgentConfig.ContainsKey($_) })
if ($InvalidAgents.Count -gt 0) {
    Write-Err "지원하지 않는 에이전트: $($InvalidAgents -join ', ')"
    exit 1
}

if ($List) {
    Write-Host ""
    Write-Host "사용 가능한 Tasksmith 스킬:" -ForegroundColor Cyan
    Write-Host "==============================" 
    foreach ($skill in (Get-SkillsList)) {
        Write-Host "  - $skill"
    }
    exit 0
}

function Show-MultiSelectMenu {
    $selected = @{}
    foreach ($agent in $AgentOrder) {
        $selected[$agent] = $false
    }

    $cursor = 0
    [Console]::CursorVisible = $false
    try {
        while ($true) {
            Clear-Host
            Write-Host ""
            Write-Host "================================" -ForegroundColor Cyan
            Write-Host "   Tasksmith 스킬 설치기" -ForegroundColor Cyan
            Write-Host "================================" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "스킬을 설치할 코딩 에이전트를 선택하세요."
            Write-Host ""
            Write-Host "  [Space] 선택/해제  [Enter] 확인  [A] 전체 선택  [N] 전체 해제  [Q] 종료" -ForegroundColor DarkGray
            Write-Host ""

            for ($i = 0; $i -lt $AgentOrder.Count; $i++) {
                $agent = $AgentOrder[$i]
                $prefix = if ($i -eq $cursor) { "> " } else { "  " }
                $check = if ($selected[$agent]) { "[✓]" } else { "[ ]" }
                $color = if ($selected[$agent]) { "Green" } else { "White" }

                Write-Host -NoNewline $prefix
                Write-Host -NoNewline $check -ForegroundColor $color
                Write-Host " $($AgentConfig[$agent].Name)"
                Write-Host "      $($AgentConfig[$agent].Path)" -ForegroundColor DarkGray
                Write-Host ""
            }

            $key = [Console]::ReadKey($true)
            switch ($key.Key) {
                "UpArrow" { $cursor = ($cursor - 1 + $AgentOrder.Count) % $AgentOrder.Count }
                "DownArrow" { $cursor = ($cursor + 1) % $AgentOrder.Count }
                "Spacebar" {
                    $agent = $AgentOrder[$cursor]
                    $selected[$agent] = -not $selected[$agent]
                }
                "Enter" { break }
                "A" {
                    foreach ($agent in $AgentOrder) { $selected[$agent] = $true }
                }
                "N" {
                    foreach ($agent in $AgentOrder) { $selected[$agent] = $false }
                }
                "Q" {
                    Write-Info "설치를 취소했습니다"
                    exit 0
                }
                "J" { $cursor = ($cursor + 1) % $AgentOrder.Count }
                "K" { $cursor = ($cursor - 1 + $AgentOrder.Count) % $AgentOrder.Count }
            }
        }
    }
    finally {
        [Console]::CursorVisible = $true
    }

    $result = @()
    foreach ($agent in $AgentOrder) {
        if ($selected[$agent]) {
            $result += $agent
        }
    }
    return $result
}

if ($SelectedAgents.Count -eq 0 -and (Test-CanPrompt)) {
    $SelectedAgents = Show-MultiSelectMenu
}

if ($SelectedAgents.Count -eq 0) {
    Write-Err "설치 대상 에이전트를 선택하세요. 예: -Codex 또는 -All"
    exit 1
}

function Resolve-ArchiveRoot {
    param([string]$ExtractedDir)

    $manifestPath = Join-Path $ExtractedDir "manifest.txt"
    if (Test-Path $manifestPath -PathType Leaf) {
        return $ExtractedDir
    }

    $skillsDir = Get-ChildItem -Path $ExtractedDir -Recurse -Directory -Filter "skills" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($skillsDir) {
        return $skillsDir.FullName
    }

    return $ExtractedDir
}

function Copy-SelectedSkills {
    param(
        [string]$SourceRoot,
        [string]$TargetDir
    )

    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null

    $skillsToInstall = if ($Skills) {
        $Skills -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    }
    else {
        Get-SkillsList
    }

    foreach ($skill in $skillsToInstall) {
        $sourceDir = Join-Path $SourceRoot $skill
        $sourceFile = Join-Path $SourceRoot "$skill.skill"
        $targetSkillDir = Join-Path $TargetDir $skill
        $targetSkillFile = Join-Path $TargetDir "$skill.skill"

        if (Test-Path $sourceDir -PathType Container) {
            if (Test-Path $targetSkillDir) {
                Remove-Item $targetSkillDir -Recurse -Force
            }
            Copy-Item $sourceDir -Destination $targetSkillDir -Recurse -Force
            Get-ChildItem -Path $targetSkillDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
                Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
            Write-Success "설치 완료: $skill"
        }
        elseif (Test-Path $sourceFile -PathType Leaf) {
            Copy-Item $sourceFile -Destination $targetSkillFile -Force
            Write-Success "설치 완료: $skill.skill"
        }
        else {
            Write-Warn "찾을 수 없음: $skill"
        }
    }
}

function Get-RemoteSkillsRoot {
    $tempDir = Join-Path ([IO.Path]::GetTempPath()) "tasksmith_install_$([guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    $archiveFile = Join-Path $tempDir $ArchiveName
    $archiveUrls = @(
        "$NexusBaseUrl/$ArchiveName",
        "https://$GitLabHost/$GitLabProject/-/raw/$Branch/$ArchiveName"
    )

    $downloaded = $false
    foreach ($url in $archiveUrls) {
        try {
            Invoke-WebRequest -Uri $url -OutFile $archiveFile -ErrorAction Stop
            $downloaded = $true
            break
        }
        catch {
        }
    }

    if (-not $downloaded) {
        Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        throw "스킬 아카이브를 다운로드할 수 없습니다."
    }

    Expand-Archive -Path $archiveFile -DestinationPath $tempDir -Force
    return @{
        TempDir = $tempDir
        SkillsRoot = (Resolve-ArchiveRoot -ExtractedDir $tempDir)
    }
}

$RemoteContext = $null
try {
    if (-not $LocalSkillsRoot) {
        $RemoteContext = Get-RemoteSkillsRoot
    }

    $SourceRoot = if ($LocalSkillsRoot) { $LocalSkillsRoot } else { $RemoteContext.SkillsRoot }
    foreach ($agent in $SelectedAgents) {
        $target = $AgentConfig[$agent].Path
        Write-Info "$($AgentConfig[$agent].Name)에 설치합니다: $target"
        Copy-SelectedSkills -SourceRoot $SourceRoot -TargetDir $target
    }
}
finally {
    if ($RemoteContext -and (Test-Path $RemoteContext.TempDir)) {
        Remove-Item $RemoteContext.TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Success "Tasksmith 스킬 설치가 완료되었습니다."
