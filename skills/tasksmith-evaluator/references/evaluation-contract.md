# Evaluation Contract

Use one evaluator pass to answer a narrow question:

Does this one task satisfy its own contract right now?

## Inputs

Expect one task directory with these files:

```text
./tasksmith/tasks/{ID}-{title}
├── 현재상태.md
├── 의존하는-작업-ID.md
├── 의존되는-작업-ID.md
├── 목표.md
├── 통과기준-정량.md
└── 통과기준-정성.py
```

Treat the task directory as the authority.
Treat worker narration as evidence only.

## Verdicts

Use exactly one of these verdicts:

- `통과`: the task is complete and correctly evidenced
- `수정필요`: the task is not yet complete, or the evidence is not strong enough to prove completion
- `차단됨`: the task cannot validly pass because an upstream dependency or prerequisite remains unresolved

## Pass Conditions

Return `통과` only when all of the following are true:

1. every upstream dependency is present and `완료`
2. the repository work matches `목표.md`
3. every item in `통과기준-정량.md` is checked and supported by evidence
4. `통과기준-정성.py` runs and exits `0`

If any condition fails, do not pass the task.

## Feedback File

Write or replace `평가결과.md` in the task directory using this structure:

```md
# 평가 결과

- 작업 ID: TASK-001
- 판정: 수정필요

## 요약

- 목표 대비 현재 상태를 한두 문장으로 요약한다.

## 확인한 근거

- 확인한 파일, 명령, 테스트, 체크리스트 상태를 적는다.

## 미충족 항목

- 미완료 기준이나 불일치 내용을 적는다.

## 다음 작업 제안

- 다음 worker 가 바로 수행할 수 있는 작업만 적는다.
```

Leave `## 미충족 항목` empty only when the verdict is `통과`.

## State Mapping

After evaluation, keep `현재상태.md` aligned with the verdict:

- `통과` -> `완료`
- `수정필요` -> `보류`
- `차단됨` -> `차단됨`

Add a short note under `## 메모` that points to `평가결과.md` and names the main reason.
