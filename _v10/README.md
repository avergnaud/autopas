# PAS Assistant — v10

## Statut au démarrage de l'itération

### Ce qui est implémenté

| Composant | État |
|-----------|------|
| Auth OAuth2 Azure AD | ✅ Complet |
| Config loading (app.yaml, questions.txt, users.yaml) | ✅ Complet |
| Upload + extraction métadonnées xlsx | ✅ Complet |
| Anonymisation (keywords + métadonnées) | ✅ Complet |
| Détection structure xlsx via Claude | ✅ Complet |
| Corpus CRUD | ✅ Complet |
| Project CRUD (filesystem, états) | ✅ Complet |
| Health check, roundtrip test | ✅ Complet |

### Ce qui manque (pipeline de génération)

| Composant | État |
|-----------|------|
| `claude_client.py` — wrapper API Claude | ❌ Absent |
| Endpoints cadrage (GET/POST answers) | ❌ Absent |
| `response_generator.py` — pipeline 9 étapes | ❌ Absent |
| `reference_selector.py` — sélection corpus | ❌ Absent |
| `attention_generator.py` — points d'attention | ❌ Absent |
| `document_writer.py` — écriture réponses dans xlsx | ❌ Absent |
| `GET /projects/{id}/status` — polling | ❌ Absent |
| `GET /projects/{id}/output` — téléchargement résultat | ❌ Absent |
| UI wizard cadrage + génération + download | ❌ Absent |

### Déviations des spécifications

Aucune déviation fonctionnelle — ce qui est implémenté respecte les specs. Le projet est incomplet plutôt que déviant.

- Fichiers prompts (`system_response.txt`, `system_attention.txt`) existent dans `data/config/prompts/` mais pas encore utilisés (normal, pipeline génération absent).
- docx hors scope V1 selon SPECIFICATIONS_FONCTIONNELLES.md §2.1 (xlsx uniquement) — conforme.

### Résumé

Base solide (~50% du workflow) : fondations, auth, anonymisation, détection structure.
**Le cœur manquant est le pipeline de génération** : cadrage → sélection corpus → appel Claude → écriture réponses → points d'attention → téléchargement.

---

## Statut après prompt 20

### Ce qui a été implémenté

| Composant | État |
|-----------|------|
| Endpoints cadrage (GET/POST answers) | ✅ Complet (prompt 19) |
| `reference_selector.py` — scoring corpus | ✅ Complet (prompt 20) |
| `GET /projects/{id}/corpus-selection` | ✅ Complet (prompt 20) |
| `POST /projects/{id}/corpus-selection` | ✅ Complet (prompt 20) |
| UI — sélection corpus avec scores et cases à cocher | ✅ Complet (prompt 20) |

### État du workflow

```
created → anonymized → structure_confirmed → cadrage_done → corpus_selected
```

### Ce qui manque (pipeline de génération)

| Composant | État |
|-----------|------|
| `claude_client.py` — wrapper API Claude | ❌ Absent |
| `response_generator.py` — pipeline génération | ❌ Absent |
| `attention_generator.py` — points d'attention | ❌ Absent |
| `document_writer.py` — écriture réponses dans xlsx | ❌ Absent |
| `GET /projects/{id}/status` — polling | ❌ Absent |
| `GET /projects/{id}/output` — téléchargement résultat | ❌ Absent |
| UI génération + polling + download | ❌ Absent |

