# PAS Assistant — v11

## Ce qui a été fait — Prompt 21

### Nouveau service `parser_xlsx.py`
- `read_questions()` — extrait les questions du xlsx anonymisé selon la structure confirmée
- `write_responses()` — copie le xlsx source, insère les réponses Claude dans la colonne réponse (avec preservation des defined names / dropdowns)

### Nouveau service `response_generator.py`
Pipeline complet en 8 étapes (BackgroundTask) :
1. Chargement des références corpus
2. Lecture des questions
3. Appel Claude → réponses JSON
4. Écriture dans `output_anon.xlsx`
5. Appel Claude → points d'attention JSON
6. Dé-anonymisation → `output.xlsx`
7. Génération `attention.md` (Markdown dé-anonymisé)
8. Status → `completed`

### `anonymizer.py` — 2 nouvelles fonctions
- `deanonymize_xlsx()` — inverse l'anonymisation d'un xlsx
- `deanonymize_text()` — inverse les tokens dans une chaîne texte

### 4 nouveaux endpoints
- `POST /api/projects/{id}/generate` — déclenche la génération (202)
- `GET /api/projects/{id}/status` — polling
- `GET /api/projects/{id}/output` — télécharge le xlsx résultat
- `GET /api/projects/{id}/attention` — télécharge les points d'attention

### Frontend `web/private.html`
Section génération avec 4 états (initial / en cours / complété / erreur), polling toutes les 3s, boutons de téléchargement en fin de génération.

### `questions.txt` — question verbosité ajoutée
Les options Concis / Standard / Détaillé sont maintenant posées comme dernière question de cadrage.
