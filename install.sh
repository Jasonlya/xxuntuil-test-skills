#!/usr/bin/env sh
# 把 skills/ 下的 skill 安装到 Agent 的 skills 目录（默认 ~/.workbuddy/skills）。
# 覆盖时不删除旧版本，而是改名为 <name>.bak.<时间戳>，可随时回滚。
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC="$REPO_DIR/skills"
TARGET="${WORKBUDDY_SKILLS_DIR:-$HOME/.workbuddy/skills}"
FORCE=0
LIST_ONLY=0
SELECTED=""

usage() {
  cat <<'EOF'
用法: ./install.sh [选项] [skill 名称...]

  不带名称      安装 skills/ 下全部 skill
  <name> ...    只安装指定 skill
  -d, --dir     目标目录，默认 $HOME/.workbuddy/skills
  -f, --force   目标已存在时覆盖（旧版改名备份，不删除）
  -l, --list    列出仓库内所有 skill
  -h, --help    显示本帮助

环境变量 WORKBUDDY_SKILLS_DIR 可替代 --dir。
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    -d|--dir)
      [ $# -ge 2 ] || die "$1 需要一个目录参数"
      TARGET="$2"; shift 2 ;;
    -f|--force) FORCE=1; shift ;;
    -l|--list)  LIST_ONLY=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    -*)         printf '未知选项: %s\n' "$1" >&2; usage; exit 2 ;;
    *)          SELECTED="$SELECTED $1"; shift ;;
  esac
done

[ -d "$SRC" ] || die "找不到 skills 目录: $SRC"

all_skills() {
  for d in "$SRC"/*/; do
    [ -f "$d/SKILL.md" ] && basename "$d"
  done
}

if [ "$LIST_ONLY" -eq 1 ]; then
  printf '仓库内 skill：\n'
  all_skills | sed 's/^/  - /'
  exit 0
fi

[ -n "$(all_skills)" ] || die "$SRC 下没有可安装的 skill"

if [ -z "$SELECTED" ]; then
  SELECTED=$(all_skills)
fi

mkdir -p "$TARGET"
printf '目标目录: %s\n\n' "$TARGET"

installed=0
skipped=0

for name in $SELECTED; do
  src="$SRC/$name"
  if [ ! -f "$src/SKILL.md" ]; then
    printf '跳过 %-28s 仓库内没有这个 skill\n' "$name"
    skipped=$((skipped + 1))
    continue
  fi

  dest="$TARGET/$name"
  if [ -e "$dest" ]; then
    if [ "$FORCE" -ne 1 ]; then
      printf '跳过 %-28s 已存在（加 --force 覆盖）\n' "$name"
      skipped=$((skipped + 1))
      continue
    fi
    backup="$dest.bak.$(date +%Y%m%d%H%M%S)"
    mv "$dest" "$backup"
    printf '备份 %-28s → %s\n' "$name" "$backup"
  fi

  cp -R "$src" "$dest"
  printf '安装 %-28s → %s\n' "$name" "$dest"
  installed=$((installed + 1))
done

printf '\n完成: 安装 %d 个，跳过 %d 个。新开一个会话即可识别。\n' "$installed" "$skipped"
