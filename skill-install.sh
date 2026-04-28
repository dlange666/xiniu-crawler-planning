#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Install repository skills into Codex, Claude Code, and generic agent (e.g. OpenCode).

By default installs every skill under skills/ into all six targets:
  codex-user, codex-project, claude-user, claude-project, agent-user, agent-project

Usage:
  ./skill-install.sh [--copy|--link] [--force] [--target TARGET]... [--target-dir DIR] [skill-name ...]

Examples:
  ./skill-install.sh                                # all 6 targets, copy mode
  ./skill-install.sh --link                         # symlink instead of copy
  ./skill-install.sh --target claude-user           # one target only
  ./skill-install.sh --target codex-user --target claude-user --target agent-user
  ./skill-install.sh --force crawler-workflow       # replace existing install of one skill

Target shorthands:
  codex-user       ${CODEX_HOME:-$HOME/.codex}/skills
  codex-project    <repo-root>/.codex/skills
  claude-user      $HOME/.claude/skills
  claude-project   <repo-root>/.claude/skills
  agent-user       $HOME/.agent/skills          (e.g. OpenCode 全局)
  agent-project    <repo-root>/.agent/skills    (e.g. OpenCode 项目级)
  user             codex-user + claude-user + agent-user
  project          codex-project + claude-project + agent-project
  all              user + project (default)

Options:
  --copy           Copy skill directories into the target (default)
  --link           Symlink skill directories into the target
  --force          Replace existing installed skills
  --target TARGET  Named target shorthand (may be repeated)
  --target-dir DIR Override with an explicit path (bypasses named targets)
  -h, --help       Show this help message
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$SCRIPT_DIR/skills"
MODE="copy"
FORCE="0"
declare -a REQUESTED_SKILLS=()
declare -a TARGET_NAMES=()
EXPLICIT_TARGET_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy)            MODE="copy"; shift ;;
    --link)            MODE="link"; shift ;;
    --force)           FORCE="1"; shift ;;
    --target)          TARGET_NAMES+=("${2:?missing value for --target}"); shift 2 ;;
    --target-dir)      EXPLICIT_TARGET_DIR="${2:?missing value for --target-dir}"; shift 2 ;;
    -h|--help)         usage; exit 0 ;;
    *)                 REQUESTED_SKILLS+=("$1"); shift ;;
  esac
done

if [[ ! -d "$SOURCE_ROOT" ]]; then
  echo "skills source directory not found: $SOURCE_ROOT" >&2
  exit 1
fi

declare -a TARGET_ROOTS=()

_add_named_target() {
  local name="$1"
  case "$name" in
    codex-user)      TARGET_ROOTS+=("${CODEX_HOME:-$HOME/.codex}/skills") ;;
    codex-project)   TARGET_ROOTS+=("$SCRIPT_DIR/.codex/skills") ;;
    claude-user)     TARGET_ROOTS+=("$HOME/.claude/skills") ;;
    claude-project)  TARGET_ROOTS+=("$SCRIPT_DIR/.claude/skills") ;;
    agent-user)      TARGET_ROOTS+=("$HOME/.agent/skills") ;;
    agent-project)   TARGET_ROOTS+=("$SCRIPT_DIR/.agent/skills") ;;
    user)
      _add_named_target codex-user
      _add_named_target claude-user
      _add_named_target agent-user
      ;;
    project)
      _add_named_target codex-project
      _add_named_target claude-project
      _add_named_target agent-project
      ;;
    all)
      _add_named_target user
      _add_named_target project
      ;;
    *)
      echo "unknown target: $name" >&2
      echo "valid: codex-user, codex-project, claude-user, claude-project, agent-user, agent-project, user, project, all" >&2
      return 1
      ;;
  esac
}

if [[ -n "$EXPLICIT_TARGET_DIR" ]]; then
  TARGET_ROOTS=("$EXPLICIT_TARGET_DIR")
elif [[ ${#TARGET_NAMES[@]} -gt 0 ]]; then
  for _name in "${TARGET_NAMES[@]}"; do _add_named_target "$_name"; done
else
  _add_named_target all
fi

list_available_skills() {
  find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1 -type d -print0 \
    | while IFS= read -r -d '' dir; do
        [[ -f "$dir/SKILL.md" ]] || continue
        basename "$dir"
      done \
    | LC_ALL=C sort
}

declare -a SKILLS_TO_INSTALL=()
if [[ ${#REQUESTED_SKILLS[@]} -eq 0 ]]; then
  while IFS= read -r skill_name; do
    [[ -n "$skill_name" ]] || continue
    SKILLS_TO_INSTALL+=("$skill_name")
  done < <(list_available_skills)
else
  SKILLS_TO_INSTALL=("${REQUESTED_SKILLS[@]}")
fi

if [[ ${#SKILLS_TO_INSTALL[@]} -eq 0 ]]; then
  echo "no skills found under $SOURCE_ROOT" >&2
  exit 1
fi

install_skill_to() {
  local skill_name="$1"
  local target_root="$2"
  local source_dir="$SOURCE_ROOT/$skill_name"
  local target_dir="$target_root/$skill_name"

  if [[ ! -f "$source_dir/SKILL.md" ]]; then
    echo "unknown skill: $skill_name" >&2
    return 1
  fi

  if [[ -e "$target_dir" || -L "$target_dir" ]]; then
    if [[ "$FORCE" != "1" ]]; then
      echo "target exists, use --force to replace: $target_dir" >&2
      return 1
    fi
    rm -rf "$target_dir"
  fi

  if [[ "$MODE" == "link" ]]; then
    ln -s "$source_dir" "$target_dir"
  else
    mkdir -p "$target_dir"
    cp -R "$source_dir"/. "$target_dir"/
  fi

  echo "installed $skill_name -> $target_dir"
}

for target_root in "${TARGET_ROOTS[@]}"; do
  mkdir -p "$target_root"
  for skill_name in "${SKILLS_TO_INSTALL[@]}"; do
    install_skill_to "$skill_name" "$target_root"
  done
done
