#!/bin/sh
# Source this helper from the project scripts to activate ESP-IDF locally.

_esp_idf_source() {
    _esp_idf_file=$1
    if [ ! -f "$_esp_idf_file" ]; then
        printf 'No existe el script de activación de ESP-IDF: %s\n' "$_esp_idf_file" >&2
        return 1
    fi

    _esp_idf_force_was_set=${IDF_PATH_FORCE+x}
    _esp_idf_force_previous=${IDF_PATH_FORCE:-}
    case $_esp_idf_file in
        */export.sh)
            if [ -z "${IDF_PATH:-}" ]; then
                IDF_PATH=${_esp_idf_file%/export.sh}
                export IDF_PATH
            fi
            IDF_PATH_FORCE=1
            export IDF_PATH_FORCE
            ;;
    esac

    # EIM's activation script inspects shell variables that may be unset. Keep
    # the caller's nounset setting, but disable it while sourcing the script.
    _esp_idf_restore_nounset=0
    case $- in
        *u*) _esp_idf_restore_nounset=1; set +u ;;
    esac
    # shellcheck disable=SC1090 # This path is discovered at runtime.
    . "$_esp_idf_file" || :
    if [ "$_esp_idf_restore_nounset" -eq 1 ]; then
        set -u
    fi
    if [ -z "$_esp_idf_force_was_set" ]; then
        unset IDF_PATH_FORCE
    else
        IDF_PATH_FORCE=$_esp_idf_force_previous
        export IDF_PATH_FORCE
    fi
}

_esp_idf_import_eim_environment() {
    _esp_idf_file=$1
    _esp_idf_environment=$("$_esp_idf_file" -e) || {
        printf 'No se pudieron leer las variables de ESP-IDF desde %s\n' "$_esp_idf_file" >&2
        return 1
    }
    _esp_idf_path_prefix=

    while IFS= read -r _esp_idf_line; do
        case $_esp_idf_line in
            PATH=*) _esp_idf_path_prefix=${_esp_idf_line#PATH=} ;;
            ESP_IDF_VERSION=*) ESP_IDF_VERSION=${_esp_idf_line#ESP_IDF_VERSION=}; export ESP_IDF_VERSION ;;
            IDF_VERSION=*) IDF_VERSION=${_esp_idf_line#IDF_VERSION=}; export IDF_VERSION ;;
            IDF_TOOLS_PATH=*) IDF_TOOLS_PATH=${_esp_idf_line#IDF_TOOLS_PATH=}; export IDF_TOOLS_PATH ;;
            IDF_COMPONENT_LOCAL_STORAGE_URL=*) IDF_COMPONENT_LOCAL_STORAGE_URL=${_esp_idf_line#IDF_COMPONENT_LOCAL_STORAGE_URL=}; export IDF_COMPONENT_LOCAL_STORAGE_URL ;;
            IDF_PATH=*) IDF_PATH=${_esp_idf_line#IDF_PATH=}; export IDF_PATH ;;
            ESP_ROM_ELF_DIR=*) ESP_ROM_ELF_DIR=${_esp_idf_line#ESP_ROM_ELF_DIR=}; export ESP_ROM_ELF_DIR ;;
            OPENOCD_SCRIPTS=*) OPENOCD_SCRIPTS=${_esp_idf_line#OPENOCD_SCRIPTS=}; export OPENOCD_SCRIPTS ;;
            IDF_PYTHON_ENV_PATH=*) IDF_PYTHON_ENV_PATH=${_esp_idf_line#IDF_PYTHON_ENV_PATH=}; export IDF_PYTHON_ENV_PATH ;;
        esac
    done <<EOF
$_esp_idf_environment
EOF

    if [ -z "$_esp_idf_path_prefix" ] || [ -z "${IDF_PATH:-}" ] || [ -z "${IDF_PYTHON_ENV_PATH:-}" ]; then
        printf 'El activador de ESP-IDF no devolvió PATH, IDF_PATH e IDF_PYTHON_ENV_PATH.\n' >&2
        return 1
    fi

    PATH="$_esp_idf_path_prefix:$PATH"
    export PATH
}

_esp_idf_configure_cli() {
    if [ -z "${IDF_PATH:-}" ] || [ ! -f "$IDF_PATH/tools/idf.py" ]; then
        printf 'IDF_PATH no apunta a una instalación válida de ESP-IDF.\n' >&2
        return 1
    fi

    if [ -n "${IDF_PYTHON_ENV_PATH:-}" ] && [ -x "$IDF_PYTHON_ENV_PATH/bin/python" ]; then
        ESP_IDF_PYTHON="$IDF_PYTHON_ENV_PATH/bin/python"
    elif [ -n "${ESP_PYTHON:-}" ] && [ -x "$ESP_PYTHON" ]; then
        ESP_IDF_PYTHON=$ESP_PYTHON
    elif [ -n "${IDF_PYTHON:-}" ] && [ -x "$IDF_PYTHON" ]; then
        ESP_IDF_PYTHON=$IDF_PYTHON
    elif command -v python3 >/dev/null 2>&1; then
        ESP_IDF_PYTHON=$(command -v python3)
    else
        printf 'No se encontró Python para ejecutar ESP-IDF.\n' >&2
        return 1
    fi
    export ESP_IDF_PYTHON
}

if [ -n "${IDF_PATH:-}" ] && [ -f "$IDF_PATH/tools/idf.py" ]; then
    _esp_idf_configure_cli || return 1
    return 0
fi

_esp_idf_activation=${ESP_IDF_ACTIVATE:-}
_esp_idf_tools=${IDF_TOOLS_PATH:-${HOME:-}/.espressif/tools}
_esp_idf_mode=source

if [ -z "$_esp_idf_activation" ] && [ -n "${IDF_VERSION:-}" ]; then
    _esp_idf_candidate="$_esp_idf_tools/activate_idf_v${IDF_VERSION}.sh"
    if [ -f "$_esp_idf_candidate" ]; then
        _esp_idf_activation=$_esp_idf_candidate
        _esp_idf_mode=eim
    fi
fi

if [ -z "$_esp_idf_activation" ] && [ -n "${IDF_PATH:-}" ] && [ -f "$IDF_PATH/export.sh" ]; then
    _esp_idf_activation="$IDF_PATH/export.sh"
fi

if [ -z "$_esp_idf_activation" ]; then
    _esp_idf_count=0
    for _esp_idf_candidate in "$_esp_idf_tools"/activate_idf_v*.sh; do
        [ -f "$_esp_idf_candidate" ] || continue
        _esp_idf_count=$((_esp_idf_count + 1))
        _esp_idf_activation=$_esp_idf_candidate
    done

    if [ "$_esp_idf_count" -gt 1 ]; then
        printf 'Hay varias versiones de ESP-IDF en %s. Define ESP_IDF_ACTIVATE con la ruta del script que quieres usar.\n' \
            "$_esp_idf_tools" >&2
        return 1
    fi
    if [ "$_esp_idf_count" -eq 1 ]; then
        _esp_idf_mode=eim
    fi
fi

if [ -z "$_esp_idf_activation" ] && [ -f "${HOME:-}/esp/esp-idf/export.sh" ]; then
    _esp_idf_activation="${HOME}/esp/esp-idf/export.sh"
fi

if [ -z "$_esp_idf_activation" ]; then
    printf 'No se encontró la activación de ESP-IDF. Define ESP_IDF_ACTIVATE o IDF_PATH.\n' >&2
    return 1
fi

case ${_esp_idf_activation##*/} in
    activate_idf_v*.sh) _esp_idf_mode=eim ;;
esac

if [ "$_esp_idf_mode" = eim ]; then
    _esp_idf_import_eim_environment "$_esp_idf_activation" || return 1
else
    _esp_idf_source "$_esp_idf_activation" || return 1
fi

_esp_idf_configure_cli || return 1

unset _esp_idf_activation _esp_idf_tools _esp_idf_candidate _esp_idf_count _esp_idf_mode
unset _esp_idf_file _esp_idf_restore_nounset _esp_idf_environment _esp_idf_path_prefix _esp_idf_line
unset _esp_idf_force_was_set _esp_idf_force_previous
