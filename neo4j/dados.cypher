// =========================
// USUÁRIOS
// =========================

MERGE (u1:User {name: 'Julia'})
MERGE (u2:User {name: 'Carlos'})
MERGE (u3:User {name: 'Ana'})

// =========================
// FILMES
// =========================

MERGE (m1:Movie {title: 'Interestelar'})
MERGE (m2:Movie {title: 'Matrix'})
MERGE (m3:Movie {title: 'O Senhor dos Anéis'})
MERGE (m4:Movie {title: 'Toy Story'})
MERGE (m5:Movie {title: 'Titanic'});

// =========================
// GÊNEROS
// =========================

MERGE (g1:Genre {name: 'Ficção Científica'})
MERGE (g2:Genre {name: 'Fantasia'})
MERGE (g3:Genre {name: 'Animação'})
MERGE (g4:Genre {name: 'Romance'});

// =========================
// FILME → GÊNERO
// =========================

MATCH (m1:Movie {title: 'Interestelar'})
MATCH (m2:Movie {title: 'Matrix'})
MATCH (m3:Movie {title: 'O Senhor dos Anéis'})
MATCH (m4:Movie {title: 'Toy Story'})
MATCH (m5:Movie {title: 'Titanic'})

MATCH (g1:Genre {name: 'Ficção Científica'})
MATCH (g2:Genre {name: 'Fantasia'})
MATCH (g3:Genre {name: 'Animação'})
MATCH (g4:Genre {name: 'Romance'})

MERGE (m1)-[:HAS_GENRE]->(g1)
MERGE (m2)-[:HAS_GENRE]->(g1)
MERGE (m3)-[:HAS_GENRE]->(g2)
MERGE (m4)-[:HAS_GENRE]->(g3)
MERGE (m5)-[:HAS_GENRE]->(g4);

// =========================
// FILMES ASSISTIDOS
// =========================

MATCH (j:User {name: 'Julia'})
MATCH (c:User {name: 'Carlos'})
MATCH (a:User {name: 'Ana'})

MATCH (i:Movie {title: 'Interestelar'})
MATCH (ma:Movie {title: 'Matrix'})
MATCH (s:Movie {title: 'O Senhor dos Anéis'})
MATCH (t:Movie {title: 'Toy Story'})
MATCH (ti:Movie {title: 'Titanic'})

MERGE (j)-[:WATCHED]->(i)
MERGE (j)-[:WATCHED]->(ma)

MERGE (c)-[:WATCHED]->(i)
MERGE (c)-[:WATCHED]->(ma)
MERGE (c)-[:WATCHED]->(s)

MERGE (a)-[:WATCHED]->(t)
MERGE (a)-[:WATCHED]->(ti)

// =========================
// AVALIAÇÕES
// =========================

MERGE (j)-[:RATED {rating: 5}]->(i)
MERGE (j)-[:RATED {rating: 5}]->(ma)

MERGE (c)-[:RATED {rating: 5}]->(i)
MERGE (c)-[:RATED {rating: 4}]->(ma)
MERGE (c)-[:RATED {rating: 5}]->(s)

MERGE (a)-[:RATED {rating: 5}]->(t)
MERGE (a)-[:RATED {rating: 4}]->(ti);