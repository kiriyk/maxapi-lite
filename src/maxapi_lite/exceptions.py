"""
Исключения для Max API Lite
"""


class MaxApiError(Exception):
    """Базовое исключение Max API"""

    def __init__(self, message: str = "Unknown error", code: int = 500):
        self.message = message
        self.code = code
        super().__init__(f"[{code}] {message}")


class InvalidToken(MaxApiError):
    """Неверный токен авторизации"""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message, 401)
