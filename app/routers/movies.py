"""Endpoints de filmes."""
from fastapi import APIRouter, Response, status

from app import repository
from app.database import SessionDep
from app.schemas import MovieCreate, MovieGenreAdd, MovieOut

router = APIRouter(prefix="/movies", tags=["Filmes"])


@router.post("", response_model=MovieOut, status_code=status.HTTP_201_CREATED,
             summary="Cadastrar filme (opcionalmente já ligado a gêneros)")
def create_movie(payload: MovieCreate, session: SessionDep):
    return session.execute_write(repository.create_movie, payload.title, payload.genres)


@router.get("", response_model=list[MovieOut], summary="Listar filmes")
def list_movies(session: SessionDep):
    return session.execute_read(repository.list_movies)


@router.get("/{title}", response_model=MovieOut, summary="Consultar filme")
def get_movie(title: str, session: SessionDep):
    return session.execute_read(repository.get_movie, title)


@router.post("/{title}/genres", response_model=MovieOut, status_code=status.HTTP_200_OK,
             summary="Associar um gênero existente a um filme existente")
def add_genre_to_movie(title: str, payload: MovieGenreAdd, session: SessionDep):
    return session.execute_write(repository.add_genre_to_movie, title, payload.genre)
