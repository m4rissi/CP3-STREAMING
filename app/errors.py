"""Erros de negócio da aplicação e o tratamento deles na API."""


class AppError(Exception):
    """Erro de negócio. Vira uma resposta HTTP com {"detail": "mensagem"}."""

    status_code = 400


class NotFoundError(AppError):
    """Usuário, filme ou gênero inexistente."""

    status_code = 404


class ConflictError(AppError):
    """Operação incompatível com o estado atual (duplicidade, etc.)."""

    status_code = 409
