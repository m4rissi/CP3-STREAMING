"""Endpoints de usuários, filmes assistidos e avaliações."""
from fastapi import APIRouter, Response, status

from app import cache, repository
from app.database import SessionDep
from app.schemas import (
    RatingCreate,
    RatingOut,
    RatingRegisterOut,
    UserCreate,
    UserOut,
    WatchedCreate,
    WatchedOut,
    WatchedRegisterOut,
)

router = APIRouter(prefix="/users", tags=["Usuários"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             summary="Cadastrar usuário")
def create_user(payload: UserCreate, session: SessionDep):
    return session.execute_write(repository.create_user, payload.name)


@router.get("", response_model=list[UserOut], summary="Listar usuários")
def list_users(session: SessionDep):
    return session.execute_read(repository.list_users)


@router.get("/{user_name}", response_model=UserOut, summary="Consultar usuário")
def get_user(user_name: str, session: SessionDep):
    return session.execute_read(repository.get_user, user_name)


@router.post("/{user_name}/watched", response_model=WatchedRegisterOut,
             status_code=status.HTTP_201_CREATED,
             summary="Registrar filme assistido",
             responses={200: {"description": "O filme já estava registrado como assistido."}})
def register_watched(user_name: str, payload: WatchedCreate,
                     response: Response, session: SessionDep):
    """Registra o filme assistido e invalida o cache de recomendações do usuário.

    Assistir a um filme muda o histórico que alimenta a recomendação, então a
    versão guardada no Redis ficou desatualizada e é apagada na hora. A próxima
    consulta será um CACHE MISS e recalculará o resultado no Neo4j.
    """
    result = session.execute_write(repository.register_watched, user_name, payload.movie_title)
    if not result["created"]:
        response.status_code = status.HTTP_200_OK
    return {**result, "cache_invalidated": cache.invalidate_user(user_name)}


@router.get("/{user_name}/watched", response_model=list[WatchedOut],
            summary="Listar filmes assistidos")
def list_watched(user_name: str, session: SessionDep):
    return session.execute_read(repository.list_watched, user_name)


@router.post("/{user_name}/ratings", response_model=RatingRegisterOut,
             status_code=status.HTTP_201_CREATED,
             summary="Registrar ou atualizar avaliação",
             responses={200: {"description": "Avaliação existente atualizada."},
                        409: {"description": "O usuário ainda não assistiu ao filme."}})
def register_rating(user_name: str, payload: RatingCreate,
                    response: Response, session: SessionDep):
    """Registra a avaliação e invalida o cache de recomendações do usuário.

    A nota entra no cálculo da recomendação (média das notas dos usuários de
    referência), portanto o resultado guardado no Redis deixa de valer.
    """
    result = session.execute_write(
        repository.register_rating, user_name, payload.movie_title, payload.rating
    )
    if not result["created"]:
        response.status_code = status.HTTP_200_OK
    return {**result, "cache_invalidated": cache.invalidate_user(user_name)}


@router.get("/{user_name}/ratings", response_model=list[RatingOut],
            summary="Listar avaliações do usuário")
def list_ratings(user_name: str, session: SessionDep):
    return session.execute_read(repository.list_ratings, user_name)
