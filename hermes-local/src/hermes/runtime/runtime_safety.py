"""
Runtime Safety — prevents ordinary chatbot users from issuing system admin
commands through the reimbursement entry point.

This module inspects user-submitted text and blocks requests that resemble
code modification, shell execution, secret/config access, or system admin
operations.
"""

_CODE_MODIFICATION_TERMS = [
    "修改代码", "改代码", "修改 handler", "修改 validator",
    "修改 prompt", "写脚本", "patch", "git commit",
    "git push", "git pull", "新建文件", "创建文件",
    "删除文件", "写一个", "实现一个",
]

_SHELL_EXECUTION_TERMS = [
    "执行命令", "运行命令", "执行脚本", "运行脚本",
    "运行测试", "跑测试", "run tests", "运行 python",
    "pip install", "brew install", "chmod", "kill",
    "rm -rf", "重启", "重启服务", "停止服务",
    "stop bridge", "start bridge", "restart",
    "npm install", "yarn add",
]

_CONFIG_SECRET_TERMS = [
    "查看 token", "查看 secret", "查看 API key",
    "打印 API key", "打开 .env", "显示 .env",
    "输出密钥", "显示密码", "reveal", "token 是什么",
    "api key 是什么", "secret key", "open .env",
    "show .env", "print token",
]

_SYSTEM_ADMIN_TERMS = [
    "重启 Hermes", "配置 ngrok", "修改环境变量",
    "管理 agent", "启用 agent", "禁用 agent",
    "agent 管理", "注册 agent", "注销 agent",
    "修改权限", "设置权限", "查看配置",
]

_SAFETY_MESSAGE = (
    "当前微信入口仅用于业务处理，不能执行系统维护、代码修改或敏感配置操作。"
    "如需维护系统，请使用 System Admin Agent。"
)

_CATEGORY_MAP = {
    "code_modification": _CODE_MODIFICATION_TERMS,
    "shell_execution": _SHELL_EXECUTION_TERMS,
    "config_secret": _CONFIG_SECRET_TERMS,
    "system_admin": _SYSTEM_ADMIN_TERMS,
}


def detect_forbidden_runtime_command(text: str) -> dict:
    """Inspect *text* for forbidden runtime commands.

    Returns a dict with:
        blocked       — ``True`` if a match was found, ``False`` otherwise
        category      — one of ``"code_modification"``, ``"shell_execution"``,
                        ``"config_secret"``, ``"system_admin"``, or ``""``
        matched_terms — list of the term(s) that triggered the block
        user_message  — the safety message to show the user when blocked
    """
    default = {
        "blocked": False,
        "category": "",
        "matched_terms": [],
        "user_message": "",
    }

    if not text:
        return default

    normalized = text.strip().lower()

    for category, terms in _CATEGORY_MAP.items():
        matched = [term for term in terms if term in normalized]
        if matched:
            return {
                "blocked": True,
                "category": category,
                "matched_terms": matched,
                "user_message": _SAFETY_MESSAGE,
            }

    return default


def is_safe_user_text(text: str) -> bool:
    """Return ``True`` if *text* does not contain any forbidden command."""
    return not detect_forbidden_runtime_command(text)["blocked"]
