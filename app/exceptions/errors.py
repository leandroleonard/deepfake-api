class DeepFakeApiError(Exception):
    """base exception class"""
    def __init__(self, message: str = "Service is unavailable", name: str = "DeepFake", status: int = 500):
        self.message = message
        self.name = name
        self.status = status
        super().__init__(message)  # ⚡ apenas message

class EntityAlreadyExistsError(DeepFakeApiError):
    """conflict detected, like trying to create a resource that already exists"""
    def __init__(self, message="Usuário já existe", name="Dados duplicados"):
        super().__init__(message=message, name=name, status=409)

class EntityDoesNotExistError(DeepFakeApiError):
    def __init__(self, message="Resource not found", name="NotFound"):
        super().__init__(message=message, name=name, status=404)

class InvalidOperationError(DeepFakeApiError):
    def __init__(self, message="Invalid operation", name="InvalidOperation"):
        super().__init__(message=message, name=name, status=400)

class AuthenticationFailed(DeepFakeApiError):
    def __init__(self, message="Invalid credentials", name="AuthenticationFailed"):
        super().__init__(message=message, name=name, status=401)

class InvalidTokenError(DeepFakeApiError):
    def __init__(self, message="Invalid token", name="InvalidToken"):
        super().__init__(message=message, name=name, status=401)

class UnauthorizedError(DeepFakeApiError):
    def __init__(self, message="Unauthorized", name="Unauthorized"):
        super().__init__(message=message, name=name, status=403)

class BadRequestError(DeepFakeApiError):
    def __init__(self, message="Bad request", name="BadRequest"):
        super().__init__(message=message, name=name, status=400)

class WeakPasswordError(DeepFakeApiError):
    def __init__(self, message: str, name: str = "WeakPassword"):
        super().__init__(message=message, name=name, status=403)
        
class PaymentRequiredError(DeepFakeApiError):
    def __init__(self, message: str, name: str = "PaymentRequired"):
        super().__init__(message=message, name=name, status=402)