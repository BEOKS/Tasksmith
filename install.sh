#!/usr/bin/env bash

set -euo pipefail

TASKSMITH_NEXUS_URL="${TASKSMITH_NEXUS_URL:-https://repo.gabia.com/repository/raw-repository/tasksmith}"
TASKSMITH_GITLAB_HOST="${TASKSMITH_GITLAB_HOST:-gitlab.gabia.com}"
TASKSMITH_GITLAB_PROJECT="${TASKSMITH_GITLAB_PROJECT:-gabia/idc/tasksmith}"
TASKSMITH_BRANCH="${TASKSMITH_BRANCH:-main}"
ARCHIVE_NAME="tasksmith-skills.zip"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

SCRIPT_PATH="${BASH_SOURCE[0]:-}"
SCRIPT_DIR=""
LOCAL_SKILLS_ROOT=""
TEMP_DIR=""
SELECTED_AGENTS=""
SELECTED_SKILLS=""
LIST_ONLY=false
INTERACTIVE=true

if [ -n "$SCRIPT_PATH" ] && [ "$SCRIPT_PATH" != "bash" ] && [ "$SCRIPT_PATH" != "stdin" ] && [ -e "$SCRIPT_PATH" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
    if [ -d "${SCRIPT_DIR}/skills" ]; then
        LOCAL_SKILLS_ROOT="${SCRIPT_DIR}/skills"
    fi
fi

cleanup() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
    if [ -t 0 ]; then
        stty echo 2>/dev/null || true
    fi
    if [ -t 1 ]; then
        tput cnorm 2>/dev/null || true
    fi
}
trap cleanup EXIT

get_agent_path() {
    case "$1" in
        claude) echo "$HOME/.claude/skills" ;;
        cursor) echo "$HOME/.claude/skills" ;;
        codex) echo "$HOME/.codex/skills" ;;
        opencode) echo "$HOME/.config/opencode/skills" ;;
        gemini) echo "$HOME/.gemini/skills" ;;
        antigravity) echo "$HOME/.gemini/antigravity/global_skills" ;;
        copilot) echo "$HOME/.claude/skills" ;;
        *) return 1 ;;
    esac
}

get_agent_name() {
    case "$1" in
        claude) echo "Claude Code" ;;
        cursor) echo "Cursor" ;;
        codex) echo "Codex CLI" ;;
        opencode) echo "OpenCode" ;;
        gemini) echo "Gemini CLI" ;;
        antigravity) echo "Antigravity" ;;
        copilot) echo "GitHub Copilot" ;;
        *) return 1 ;;
    esac
}

show_help() {
    cat <<'EOF'
Tasksmith 스킬 설치기

사용법:
  curl -fsSL <url>/install.sh | bash
  curl -fsSL <url>/install.sh | bash -s -- [옵션]
  ./install.sh [옵션]

옵션:
  --claude           Claude Code에 설치 (~/.claude/skills)
  --cursor           Cursor에 설치 (~/.claude/skills)
  --codex            Codex CLI에 설치 (~/.codex/skills)
  --opencode         OpenCode에 설치 (~/.config/opencode/skills)
  --gemini           Gemini CLI에 설치 (~/.gemini/skills)
  --antigravity      Antigravity에 설치 (~/.gemini/antigravity/global_skills)
  --copilot          GitHub Copilot에 설치 (~/.claude/skills)
  --all              모든 에이전트에 설치
  --skills "a,b,c"   지정한 스킬만 설치
  --list             사용 가능한 스킬 목록 출력
  --no-interactive   선택 메뉴 없이 실행
  -h, --help         도움말 표시

환경변수:
  TASKSMITH_NEXUS_URL      배포 산출물 기준 URL
  TASKSMITH_GITLAB_HOST    fallback GitLab 호스트
  TASKSMITH_GITLAB_PROJECT fallback GitLab 프로젝트 경로
  TASKSMITH_BRANCH         fallback 브랜치
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --claude|--cursor|--codex|--opencode|--gemini|--antigravity|--copilot)
            SELECTED_AGENTS="${SELECTED_AGENTS} ${1#--}"
            INTERACTIVE=false
            shift
            ;;
        --all)
            SELECTED_AGENTS=" claude cursor codex opencode gemini antigravity copilot"
            INTERACTIVE=false
            shift
            ;;
        --skills)
            SELECTED_SKILLS="${2:-}"
            shift 2
            ;;
        --skills=*)
            SELECTED_SKILLS="${1#*=}"
            shift
            ;;
        --list)
            LIST_ONLY=true
            INTERACTIVE=false
            shift
            ;;
        --no-interactive)
            INTERACTIVE=false
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            error "알 수 없는 옵션: $1"
            exit 1
            ;;
    esac
done

check_requirements() {
    local missing=""
    command -v cp >/dev/null 2>&1 || missing="${missing} cp"
    command -v mkdir >/dev/null 2>&1 || missing="${missing} mkdir"
    if [ -z "$LOCAL_SKILLS_ROOT" ]; then
        command -v curl >/dev/null 2>&1 || missing="${missing} curl"
        command -v unzip >/dev/null 2>&1 || missing="${missing} unzip"
    fi
    if [ -n "$missing" ]; then
        error "필수 도구가 없습니다:${missing}"
        exit 1
    fi
}

normalize_selected_agents() {
    local normalized=""
    local seen=" "
    for agent in $SELECTED_AGENTS; do
        case "$agent" in
            claude|cursor|codex|opencode|gemini|antigravity|copilot) ;;
            *)
                error "지원하지 않는 에이전트: $agent"
                exit 1
                ;;
        esac
        if [[ "$seen" != *" $agent "* ]]; then
            normalized="${normalized} ${agent}"
            seen="${seen}${agent} "
        fi
    done
    SELECTED_AGENTS="$normalized"
}

get_local_skills_list() {
    if [ -f "${LOCAL_SKILLS_ROOT}/manifest.txt" ]; then
        cat "${LOCAL_SKILLS_ROOT}/manifest.txt"
    else
        find "$LOCAL_SKILLS_ROOT" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort
    fi
}

get_remote_skills_list() {
    local manifest_url
    manifest_url="${TASKSMITH_NEXUS_URL}/manifest.txt"
    if curl -fsSL "$manifest_url" 2>/dev/null; then
        return 0
    fi

    manifest_url="https://${TASKSMITH_GITLAB_HOST}/${TASKSMITH_GITLAB_PROJECT}/-/raw/${TASKSMITH_BRANCH}/skills/manifest.txt"
    if curl -fsSL "$manifest_url" 2>/dev/null; then
        return 0
    fi

    error "manifest.txt를 가져올 수 없습니다"
    return 1
}

get_skills_list() {
    if [ -n "$LOCAL_SKILLS_ROOT" ]; then
        get_local_skills_list
    else
        get_remote_skills_list
    fi
}

list_skills() {
    local skills
    skills="$(get_skills_list)"
    echo ""
    echo -e "${CYAN}사용 가능한 Tasksmith 스킬:${NC}"
    echo "=============================="
    while IFS= read -r skill; do
        [ -z "$skill" ] && continue
        echo "  - $skill"
    done <<EOF
$skills
EOF
    echo ""
}

show_multiselect_menu() {
    local cursor=0
    local num_options=7
    local sel_claude=0 sel_cursor=0 sel_codex=0 sel_opencode=0 sel_gemini=0 sel_antigravity=0 sel_copilot=0

    tput civis 2>/dev/null || true
    stty -echo 2>/dev/null || true

    while true; do
        clear
        echo ""
        echo -e "${CYAN}================================${NC}"
        echo -e "${CYAN}   Tasksmith 스킬 설치기${NC}"
        echo -e "${CYAN}================================${NC}"
        echo ""
        echo -e "${BOLD}스킬을 설치할 코딩 에이전트를 선택하세요:${NC}"
        echo ""
        echo -e "${DIM}  [Space] 선택/해제  [Enter] 확인  [a] 전체 선택  [n] 전체 해제  [q] 종료${NC}"
        echo ""

        local i=0
        for agent in claude cursor codex opencode gemini antigravity copilot; do
            local name path prefix checkbox highlight is_selected
            name="$(get_agent_name "$agent")"
            path="$(get_agent_path "$agent")"
            prefix="  "
            checkbox="[ ]"
            highlight=""
            if [ $i -eq $cursor ]; then
                prefix="> "
                highlight="${BOLD}"
            fi

            is_selected=0
            case "$agent" in
                claude) is_selected=$sel_claude ;;
                cursor) is_selected=$sel_cursor ;;
                codex) is_selected=$sel_codex ;;
                opencode) is_selected=$sel_opencode ;;
                gemini) is_selected=$sel_gemini ;;
                antigravity) is_selected=$sel_antigravity ;;
                copilot) is_selected=$sel_copilot ;;
            esac
            if [ $is_selected -eq 1 ]; then
                checkbox="${GREEN}[✓]${NC}"
            fi

            echo -e "${highlight}${prefix}${checkbox} ${name}${NC}"
            echo -e "${DIM}      ${path}${NC}"
            echo ""
            i=$((i + 1))
        done

        local key=""
        IFS= read -rsn1 key
        case "$key" in
            $'\x1b')
                local key2="" key3=""
                read -rsn1 -t 1 key2 || true
                read -rsn1 -t 1 key3 || true
                case "${key2}${key3}" in
                    '[A') cursor=$((cursor - 1)); [ $cursor -lt 0 ] && cursor=$((num_options - 1)) ;;
                    '[B') cursor=$((cursor + 1)); [ $cursor -ge $num_options ] && cursor=0 ;;
                esac
                ;;
            ' ')
                case $cursor in
                    0) sel_claude=$((1 - sel_claude)) ;;
                    1) sel_cursor=$((1 - sel_cursor)) ;;
                    2) sel_codex=$((1 - sel_codex)) ;;
                    3) sel_opencode=$((1 - sel_opencode)) ;;
                    4) sel_gemini=$((1 - sel_gemini)) ;;
                    5) sel_antigravity=$((1 - sel_antigravity)) ;;
                    6) sel_copilot=$((1 - sel_copilot)) ;;
                esac
                ;;
            'a'|'A')
                sel_claude=1; sel_cursor=1; sel_codex=1; sel_opencode=1; sel_gemini=1; sel_antigravity=1; sel_copilot=1
                ;;
            'n'|'N')
                sel_claude=0; sel_cursor=0; sel_codex=0; sel_opencode=0; sel_gemini=0; sel_antigravity=0; sel_copilot=0
                ;;
            'q'|'Q')
                clear
                info "설치를 취소했습니다"
                exit 0
                ;;
            '')
                break
                ;;
            'j')
                cursor=$((cursor + 1)); [ $cursor -ge $num_options ] && cursor=0
                ;;
            'k')
                cursor=$((cursor - 1)); [ $cursor -lt 0 ] && cursor=$((num_options - 1))
                ;;
        esac
    done

    tput cnorm 2>/dev/null || true
    stty echo 2>/dev/null || true
    clear

    SELECTED_AGENTS=""
    [ $sel_claude -eq 1 ] && SELECTED_AGENTS="${SELECTED_AGENTS} claude"
    [ $sel_cursor -eq 1 ] && SELECTED_AGENTS="${SELECTED_AGENTS} cursor"
    [ $sel_codex -eq 1 ] && SELECTED_AGENTS="${SELECTED_AGENTS} codex"
    [ $sel_opencode -eq 1 ] && SELECTED_AGENTS="${SELECTED_AGENTS} opencode"
    [ $sel_gemini -eq 1 ] && SELECTED_AGENTS="${SELECTED_AGENTS} gemini"
    [ $sel_antigravity -eq 1 ] && SELECTED_AGENTS="${SELECTED_AGENTS} antigravity"
    [ $sel_copilot -eq 1 ] && SELECTED_AGENTS="${SELECTED_AGENTS} copilot"
}

resolve_remote_root() {
    local extract_dir="$1"
    if [ -f "${extract_dir}/manifest.txt" ]; then
        echo "$extract_dir"
        return 0
    fi

    local nested
    nested="$(find "$extract_dir" -mindepth 1 -maxdepth 2 -type d -name skills | head -1)"
    if [ -n "$nested" ]; then
        echo "$nested"
        return 0
    fi

    echo "$extract_dir"
}

prepare_remote_skills_root() {
    TEMP_DIR="$(mktemp -d)"
    local archive_file="${TEMP_DIR}/${ARCHIVE_NAME}"
    local archive_url="${TASKSMITH_NEXUS_URL}/${ARCHIVE_NAME}"

    info "배포된 스킬 아카이브를 다운로드합니다"
    if ! curl -fsSL "$archive_url" -o "$archive_file"; then
        archive_url="https://${TASKSMITH_GITLAB_HOST}/${TASKSMITH_GITLAB_PROJECT}/-/raw/${TASKSMITH_BRANCH}/${ARCHIVE_NAME}"
        curl -fsSL "$archive_url" -o "$archive_file"
    fi

    unzip -q "$archive_file" -d "$TEMP_DIR"
    LOCAL_SKILLS_ROOT="$(resolve_remote_root "$TEMP_DIR")"
}

copy_selected_skills() {
    local target_dir="$1"
    local skills_to_install skill source_dir source_file target_skill_dir target_skill_file

    mkdir -p "$target_dir"

    if [ -n "$SELECTED_SKILLS" ]; then
        skills_to_install="$(printf '%s\n' "$SELECTED_SKILLS" | tr ',' '\n')"
    else
        skills_to_install="$(get_skills_list)"
    fi

    while IFS= read -r skill; do
        skill="$(echo "$skill" | tr -d '[:space:]')"
        [ -z "$skill" ] && continue

        source_dir="${LOCAL_SKILLS_ROOT}/${skill}"
        source_file="${LOCAL_SKILLS_ROOT}/${skill}.skill"
        target_skill_dir="${target_dir}/${skill}"
        target_skill_file="${target_dir}/${skill}.skill"

        if [ -d "$source_dir" ]; then
            rm -rf "$target_skill_dir"
            cp -R "$source_dir" "$target_skill_dir"
            find "$target_skill_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
            find "$target_skill_dir" -name ".DS_Store" -delete 2>/dev/null || true
            success "설치 완료: $skill"
        elif [ -f "$source_file" ]; then
            cp "$source_file" "$target_skill_file"
            success "설치 완료: ${skill}.skill"
        else
            warn "찾을 수 없음: $skill"
        fi
    done <<EOF
$skills_to_install
EOF
}

install_to_agent() {
    local agent="$1"
    local target_dir
    target_dir="$(get_agent_path "$agent")"

    echo ""
    info "$(get_agent_name "$agent")에 설치합니다: $target_dir"
    copy_selected_skills "$target_dir"
}

check_requirements
normalize_selected_agents

if [ "$LIST_ONLY" = true ]; then
    list_skills
    exit 0
fi

if [ -z "$SELECTED_AGENTS" ]; then
    if [ "$INTERACTIVE" = true ] && [ -t 0 ] && [ -t 1 ]; then
        show_multiselect_menu
        normalize_selected_agents
    fi
fi

if [ -z "$SELECTED_AGENTS" ]; then
    error "설치 대상 에이전트를 선택하세요. 예: --codex 또는 --all"
    exit 1
fi

if [ -z "$LOCAL_SKILLS_ROOT" ]; then
    prepare_remote_skills_root
fi

for agent in $SELECTED_AGENTS; do
    install_to_agent "$agent"
done

echo ""
success "Tasksmith 스킬 설치가 완료되었습니다"
