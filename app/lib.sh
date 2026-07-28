#!/bin/bash
# cutsheet.sh と セットアップ.command が共有する処理。
# 単体で実行するものではなく、source して使う。

CUTSHEET_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CUTSHEET_LIB_DIR/.." && pwd)"
VENV="$REPO_ROOT/.venv"

# ---- Python ----

python_bin() {
    command -v python3 2>/dev/null || true
}

# 「入っているか」の判定は実際に import できるかどうかだけで行う。
# インストール済みフラグのような間接的な目印は、途中で失敗した状態を
# 見逃してしまうので使わない。
venv_ready() {
    [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import scenedetect" >/dev/null 2>&1
}

# 成功時は黙り、失敗したときだけログの末尾を見せる。
install_deps() {
    local log="$REPO_ROOT/.setup.log"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip > "$log" 2>&1
    if "$VENV/bin/python" -m pip install --quiet -r "$REPO_ROOT/requirements.txt" >> "$log" 2>&1; then
        return 0
    fi
    echo ""
    echo "  pip のエラー(末尾 20 行 / 全文は .setup.log):"
    tail -n 20 "$log" 2>/dev/null | sed 's/^/    /'
    return 1
}

# 依存をそろえる。すでに使える状態なら何もしない。
# 戻り値 0 = 高精度なカット検出が使える状態。
ensure_venv() {
    if venv_ready; then
        return 0
    fi

    local python
    python="$(python_bin)"
    if [ -z "$python" ]; then
        echo "❌ python3 が見つからない。Xcode Command Line Tools を入れる:"
        echo "   xcode-select --install"
        return 1
    fi

    echo "必要なライブラリを入れる(数分かかることがある)…"
    if [ ! -x "$VENV/bin/python" ]; then
        "$python" -m venv "$VENV"
    fi
    install_deps

    if ! venv_ready; then
        # 仮想環境が壊れている可能性があるので、作り直して一度だけやり直す。
        echo ""
        echo "仮想環境を作り直して再試行する…"
        rm -rf "$VENV"
        "$python" -m venv "$VENV" && install_deps
    fi

    venv_ready
}

# 依存が入らなかった場合でも動かせるように、使える Python を返す。
resolved_python() {
    if [ -x "$VENV/bin/python" ]; then
        echo "$VENV/bin/python"
    else
        python_bin
    fi
}

# ---- Claude Code ----

# インストール方法によって場所が大きく違ううえ、ログインシェル(zsh)にだけ
# PATH が通っていることも多いので、順に広く探す。
find_claude() {
    local found candidate prefix
    found="$(command -v claude 2>/dev/null || true)"
    if [ -n "$found" ]; then
        echo "$found"
        return 0
    fi

    for candidate in \
        "$HOME/.local/bin/claude" \
        "$HOME/.claude/local/claude" \
        "$HOME/.npm-global/bin/claude" \
        "$HOME/.bun/bin/claude" \
        "$HOME/.volta/bin/claude" \
        "/opt/homebrew/bin/claude" \
        "/usr/local/bin/claude"; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    for candidate in "$HOME"/.nvm/versions/node/*/bin/claude; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    if command -v npm >/dev/null 2>&1; then
        prefix="$(npm config get prefix 2>/dev/null)"
        if [ -n "$prefix" ] && [ -x "$prefix/bin/claude" ]; then
            echo "$prefix/bin/claude"
            return 0
        fi
    fi

    # bash から起動された場合、zsh 側にだけ通っている PATH を拾う。
    if command -v zsh >/dev/null 2>&1; then
        found="$(zsh -lic 'command -v claude' 2>/dev/null | tail -n 1)"
        if [ -n "$found" ] && [ -x "$found" ]; then
            echo "$found"
            return 0
        fi
    fi

    return 1
}

# ---- デスクトップアプリ ----

# デスクトップにドロップレットを作る。成功したらそのパスを標準出力に返す。
build_desktop_app() {
    local app_name="${1:-カット表}"
    local dest="$HOME/Desktop/${app_name}.app"

    if [ "$(uname)" != "Darwin" ]; then
        echo "macOS 専用の処理なのでスキップする" >&2
        return 1
    fi
    if ! command -v osacompile >/dev/null 2>&1; then
        echo "osacompile が見つからない。Xcode Command Line Tools を入れる: xcode-select --install" >&2
        return 1
    fi

    chmod +x "$CUTSHEET_LIB_DIR/cutsheet.sh" 2>/dev/null

    local tmp
    tmp="$(mktemp -d)" || return 1
    # アプリはデスクトップに置かれてリポジトリから離れるので、場所を焼き込む。
    sed "s|__REPO_ROOT__|${REPO_ROOT}|g" \
        "$CUTSHEET_LIB_DIR/droplet.applescript" > "$tmp/droplet.applescript"

    rm -rf "$dest"
    if ! osacompile -o "$dest" "$tmp/droplet.applescript" >&2; then
        rm -rf "$tmp"
        return 1
    fi
    rm -rf "$tmp"
    echo "$dest"
}

# ---- Claude Code のインストール ----

# Claude Code CLI を入れる。成功したらパスを標準出力に返す。
install_claude() {
    if ! command -v npm >/dev/null 2>&1; then
        return 1
    fi

    npm install -g @anthropic-ai/claude-code >&2
    if [ $? -ne 0 ]; then
        # 多くは /usr/local への書き込み権限で失敗する。ユーザー領域に入れ直す。
        echo "権限エラーのようなので、ホーム配下に入れ直す…" >&2
        local prefix="$HOME/.npm-global"
        mkdir -p "$prefix"
        npm config set prefix "$prefix" >&2 2>/dev/null
        npm install -g @anthropic-ai/claude-code >&2 || return 1
    fi

    find_claude
}
