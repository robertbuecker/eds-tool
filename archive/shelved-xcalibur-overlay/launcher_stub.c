#define UNICODE
#define _UNICODE

#include <windows.h>
#include <shellapi.h>
#include <strsafe.h>
#include <wchar.h>

#define PYTHON_PATH L"C:\\Xcalibur\\Python312\\pythonw.exe"

static int show_error(const wchar_t *message) {
    MessageBoxW(NULL, message, L"EDS Tool Launcher", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE prev, PWSTR cmd_line, int show_cmd) {
    wchar_t module_path[MAX_PATH];
    DWORD len = GetModuleFileNameW(NULL, module_path, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) {
        return show_error(L"Could not determine launcher location.");
    }

    wchar_t *last_slash = wcsrchr(module_path, L'\\');
    if (last_slash == NULL) {
        return show_error(L"Could not resolve launcher directory.");
    }
    *last_slash = L'\0';

    wchar_t script_path[MAX_PATH];
    if (FAILED(StringCchPrintfW(script_path, MAX_PATH, L"%s\\launch_eds_tool.py", module_path))) {
        return show_error(L"Could not build launch script path.");
    }

    wchar_t params[32768];
    if (cmd_line != NULL && cmd_line[0] != L'\0') {
        if (FAILED(StringCchPrintfW(params, 32768, L"\"%s\" %s", script_path, cmd_line))) {
            return show_error(L"Command line is too long.");
        }
    } else {
        if (FAILED(StringCchPrintfW(params, 32768, L"\"%s\"", script_path))) {
            return show_error(L"Could not build command line.");
        }
    }

    HINSTANCE result = ShellExecuteW(NULL, L"open", PYTHON_PATH, params, module_path, SW_SHOWNORMAL);
    if ((INT_PTR)result <= 32) {
        return show_error(L"Failed to start the fixed Xcalibur Python runtime.");
    }

    return 0;
}
