// Consulta de recomendação baseada em usuários com
// filmes assistidos em comum.

// O parâmetro $userName identifica o usuário que receberá
// a recomendação.

MATCH (u:User {name: $userName})-[:WATCHED]->(filmeComum:Movie)<-[:WATCHED]-(outro:User)
MATCH (outro)-[avaliacao:RATED]->(filmeComum)
MATCH (outro)-[:WATCHED]->(recomendado:Movie)

WHERE NOT (u)-[:WATCHED]->(recomendado)

WITH recomendado, outro,
     COUNT(DISTINCT filmeComum) AS filmesEmComum,
     AVG(avaliacao.rating) AS mediaNotas

RETURN recomendado.title AS filme_recomendado,
       outro.name AS usuario_referencia,
       filmesEmComum,
       round(mediaNotas, 2) AS media_notas

ORDER BY filmesEmComum DESC, mediaNotas DESC