"""Endpoints de gêneros."""
from fastapi import APIRouter, status

from app import repository
from app.database import SessionDep
from app.schemas import GenreCreate, GenreOut

router = APIRouter(prefix="/genres", tags=["Gêneros"])


@router.post("", response_model=GenreOut, status_code=status.HTTP_201_CREATED,
             summary="Cadastrar gênero")
def create_genre(payload: GenreCreate, session: SessionDep):
    return session.execute_write(repository.create_genre, payload.name)


@router.get("", response_model=list[GenreOut], summary="Listar gêneros")
def list_genres(session: SessionDep):
    return session.execute_read(repository.list_genres)
