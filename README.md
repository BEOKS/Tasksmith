# Tasksmith

LLM 기반 재귀적 작업 분해 및 실행 엔진

![Tasksmith Demo](tasksmith-demo.gif)

## 개요

코딩 에이전트는 간단한 요청에는 강하지만, 복잡한 요청에서는 잘못 처리하거나 일부 단계를 누락하는 등 다양한 문제가 발생할 수 있습니다.
Tasksmith는 이런 한계를 줄이기 위해 복잡한 요청을 단일 에이전트가 안정적으로 처리할 수 있는 단위까지 분할하고, 각 단위를 독립적인 에이전트가 처리하도록 설계된 장기/대규모 작업 처리 하네스입니다.

복잡한 요청을 원자적 작업 단위로 재귀 분할하고, 의존성 기반 DAG 순서로 자동 실행합니다.
각 작업은 Worker-Evaluator 루프를 통해 통과할 때까지 반복 검증됩니다.

## 스킬 설치

배포된 Tasksmith 스킬은 `install.sh` 또는 `install.ps1`로 Claude Code, Codex, Cursor 같은 에이전트 스킬 디렉터리에 바로 설치할 수 있습니다.

### macOS / Linux

```bash
curl -fsSL https://repo.gabia.com/repository/raw-repository/tasksmith/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://repo.gabia.com/repository/raw-repository/tasksmith/install.ps1 | iex
```

## 핵심 흐름

```
사용자 요청 → Unit 계측 → 재귀 분할 → DAG 태스크 생성 → Dispatcher → Processor(Worker ⇄ Evaluator) → 완료
```

## 구성 요소

| 컴포넌트 | 역할 |
|----------|------|
| **Tasksmith** | 전체 워크플로우 오케스트레이터 |
| **Unit** | 작업 복잡도 계측 (6개 버킷 스코어링) |
| **Divider** | 재귀적 분할 (1 unit이 될 때까지) |
| **Task Create** | 태스크 계약 디렉토리 생성 |
| **Dispatcher** | 실행 가능한 태스크 감지 및 배정 |
| **Processor** | Worker→Evaluator 루프 관리 |
| **Worker** | 태스크 실행 |
| **Evaluator** | 결과 판정 (통과/수정필요/차단됨) |

## 사용법

```
tasksmith
```

또는 Claude Code에서:

```
복잡한 요청을 tasksmith로 실행해줘
```

## 배포 파이프라인

`main` 브랜치에서 `skills/`, `install.sh`, `install.ps1`, `README.md`, `.gitlab-ci.yml` 변경이 발생하면 GitLab CI가 다음 파일을 패키징/업로드합니다.

- `tasksmith-skills.zip`
- `install.sh`
- `install.ps1`
- `skills/manifest.txt`

필수 CI 변수:

- `NEXUS_USERNAME`
- `NEXUS_PASSWORD`

선택 CI 변수:

- `TASKSMITH_NEXUS_URL`
  기본값은 `https://repo.gabia.com/repository/raw-repository/tasksmith` 입니다.
