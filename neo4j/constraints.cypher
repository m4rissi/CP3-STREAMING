// Regras para evitar dados duplicados no Neo4j.

// Usuários: cada nome deve ser único.
CREATE CONSTRAINT user_name_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.name IS UNIQUE;

// Filmes: cada título deve ser único.
CREATE CONSTRAINT movie_title_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.title IS UNIQUE;

// Gêneros: cada nome deve ser único.
CREATE CONSTRAINT genre_name_unique IF NOT EXISTS
FOR (g:Genre)
REQUIRE g.name IS UNIQUE;