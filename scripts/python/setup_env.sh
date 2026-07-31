#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

python_path=""
use_dev_dependencies="true"
dev_option=""

write_step() {
    printf '%s\n' "$1"
}

write_phase() {
    printf '\n=== %s ===\n' "$1"
}

usage() {
    cat <<'EOF'
Usage: ./scripts/python/setup_env.sh [options]

Options:
  --python-path PATH  Use this Python interpreter explicitly.
  --include-dev       Install requirements-dev.txt explicitly.
  --no-dev            Skip requirements-dev.txt.
  -h, --help          Show this help text.
EOF
}

test_command() {
    local command="$1"
    shift
    "${command}" "$@" --version >/dev/null 2>&1
}

resolve_venv_python() {
    local venv_dir="$1"
    if [[ -x "${venv_dir}/bin/python" ]]; then
        printf '%s\n' "${venv_dir}/bin/python"
    elif [[ -x "${venv_dir}/Scripts/python.exe" ]]; then
        printf '%s\n' "${venv_dir}/Scripts/python.exe"
    else
        printf "No python interpreter found under '%s' (checked bin/python and Scripts/python.exe).\n" "${venv_dir}" >&2
        exit 1
    fi
}

resolve_python_command() {
    if [[ -n "${python_path}" ]]; then
        if [[ ! -x "${python_path}" ]]; then
            printf "Python not found at '%s'.\n" "${python_path}" >&2
            exit 1
        fi
        if ! test_command "${python_path}"; then
            printf "Python at '%s' did not respond correctly.\n" "${python_path}" >&2
            exit 1
        fi
        printf '%s\n' "${python_path}"
        return
    fi

    local candidates=("python3" "python")
    local candidate=""
    for candidate in "${candidates[@]}"; do
        if command -v "${candidate}" >/dev/null 2>&1 && test_command "${candidate}"; then
            printf '%s\n' "${candidate}"
            return
        fi
    done

    printf "Unable to resolve a working Python interpreter. Tried: python3, python.\n" >&2
    exit 1
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --python-path)
                if [[ $# -lt 2 ]]; then
                    printf "Expected a value after --python-path.\n" >&2
                    exit 1
                fi
                python_path="$2"
                shift 2
                ;;
            --include-dev)
                if [[ "${dev_option}" == "no-dev" ]]; then
                    printf "Use either --include-dev or --no-dev, but not both.\n" >&2
                    exit 1
                fi
                use_dev_dependencies="true"
                dev_option="include-dev"
                shift
                ;;
            --no-dev)
                if [[ "${dev_option}" == "include-dev" ]]; then
                    printf "Use either --include-dev or --no-dev, but not both.\n" >&2
                    exit 1
                fi
                use_dev_dependencies="false"
                dev_option="no-dev"
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                printf "Unknown argument: %s\n" "$1" >&2
                usage >&2
                exit 1
                ;;
        esac
    done
}

parse_args "$@"
selected_python="$(resolve_python_command)"

write_step "Starting pip environment setup for this repository."

write_phase "Phase 1: Resolve Python"
write_step "[Python] Using interpreter: ${selected_python}"
"${selected_python}" --version

write_phase "Phase 2: Create Virtual Environment"
if [[ ! -d "${REPO_ROOT}/.venv" ]]; then
    write_step "[venv] Creating .venv with ${selected_python} -m venv"
    "${selected_python}" -m venv "${REPO_ROOT}/.venv"
else
    write_step "[venv] Reusing existing .venv"
fi
venv_python="$(resolve_venv_python "${REPO_ROOT}/.venv")"

write_phase "Phase 3: Install Dependencies"
if [[ ! -f "${REPO_ROOT}/requirements.txt" ]]; then
    printf "requirements.txt is required for the pip setup flow.\n" >&2
    exit 1
fi

"${venv_python}" -m pip install --upgrade pip
command=("${venv_python}" "-m" "pip" "install" "-r" "requirements.txt")
if [[ "${use_dev_dependencies}" == "true" && -f "${REPO_ROOT}/requirements-dev.txt" ]]; then
    command+=("-r" "requirements-dev.txt")
fi
write_step "[Dependencies] Running: ${command[*]}"
(
    cd "${REPO_ROOT}"
    "${command[@]}"
)

write_phase "Phase 4: Summary"
write_step "Environment setup completed successfully."
printf 'Suggested interpreter path: %s\n' "${venv_python}"
