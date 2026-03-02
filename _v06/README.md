# PAS Assistant — v06

## Contenu de cette itération

Corrections de bugs et améliorations identifiées après revue complète du code de _v06.

---

## Bug #1 — `parser_xlsx.py` : `write_responses` migré vers `iter_rows()`

**Problème :** `write_responses` bouclait sur `range(first_data_row, ws.max_row + 1)`. Pour les xlsx avec un tag `<dimension>` périmé (courant), `ws.max_row` peut retourner 1 048 576 → boucle quasi-infinie et écriture dans des cellules vides.

**Fix :** Migré vers `iter_rows(min_row=first_data_row)` avec le même mécanisme de stop `_MAX_EMPTY_ROWS` que `extract_questions`. Cohérence garantie entre les deux fonctions.

**Fichier :** [app/services/parser_xlsx.py](app/services/parser_xlsx.py)

---

## Bug #2 — `parser_docx.py` : extraction de question dans les tableaux

**Problème :** Lors du scan des tableaux pour les marqueurs de réponse, la question était définie à `para.text.strip()` — c'est-à-dire le texte du marqueur lui-même, pas la question. Claude recevait donc des questions incorrectes pour les docx tabulaires.

**Fix :** Quand un marqueur est trouvé dans une ligne de tableau, on cherche le texte de la question dans les autres cellules non-marqueur de la même ligne. Si rien n'est trouvé, on remonte à la ligne précédente.

**Fichier :** [app/services/parser_docx.py](app/services/parser_docx.py)

---

## Bug #3 — `reference_selector.py` : filtre des fichiers à score 0

**Problème :** Même quand aucun fichier du corpus ne correspond au cadrage (tous à score 0), les `max_files` premiers fichiers étaient quand même envoyés à Claude comme références — du bruit sans valeur.

**Fix :** Ajout d'un filtre `score > 0`. Si aucun fichier n'est pertinent, la liste de références est vide et un message de log l'indique.

**Fichier :** [app/services/reference_selector.py](app/services/reference_selector.py)

---

## Amélioration #4 — `response_generator.py` : `_format_cadrage` avec labels lisibles

**Problème :** Le contexte cadrage envoyé à Claude utilisait les clés brutes du dict (ex. `"1 : Dispositif à engagement"`) au lieu du texte de la question correspondante.

**Fix :** `_format_cadrage` lit maintenant la config pour construire un `label_map` `{id → texte_question}` et utilise le texte de la question comme label. Fallback sur la clé brute si non trouvée.

**Fichier :** [app/services/response_generator.py](app/services/response_generator.py)

---

## Amélioration #5 — `web.py` : suppression de la double sérialisation dans `_project_dict`

**Problème :** `_project_dict` appelait `project.model_dump()` (qui sérialise déjà récursivement les modèles imbriqués) puis re-sérialisait `project.structure` avec un second `.model_dump()` — redondant.

**Fix :** `_project_dict` retourne directement `project.model_dump()`.

**Fichier :** [app/api/web.py](app/api/web.py)

---

## Bug #8 — Scoring corpus toujours 0 (clés numériques vs clés sémantiques)

**Problème :** `_score()` dans `reference_selector.py` attend des clés sémantiques dans le cadrage (`"type_prestation"`, `"hebergement_donnees"`…), mais le cadrage est stocké avec des clés numériques (IDs de questions : `"1"`, `"6"`…). Score toujours 0 → depuis Bug #3, le corpus entier était filtré → `0 références` dans les logs.

**Fix en 3 fichiers :**
- `questions.txt` : ajout d'une directive `KEY: nom_clé` sur les questions qui contribuent au scoring
- `config.py` : parsing de `KEY:` dans `_load_questions()` (champ `"key"` dans chaque question)
- `reference_selector.py` : ajout de `_translate_cadrage(cadrage)` qui construit le dict `{clé_sémantique: valeur}` à partir du mapping `{id_question → key}` lu depuis la config. `select_references` appelle `_translate_cadrage` avant `_score`.

**Fichiers :** [data/config/questions.txt](data/config/questions.txt), [app/config.py](app/config.py), [app/services/reference_selector.py](app/services/reference_selector.py)

---

## Bug #7 — `claude_client.py` : `JSONDecodeError` sur réponse tronquée (attention points)

**Problème (production) :** `generate_attention_points` utilisait `max_tokens=4000` codé en dur. Sur un gros questionnaire (129 questions), Claude tronquait sa réponse JSON en plein milieu → `JSONDecodeError: Unterminated string` → pipeline en erreur.

**Fix :**
- `generate_attention_points` utilise maintenant `config["claude"]["max_tokens"]` (16 000) comme `generate_responses`.
- `_parse_json` accepte un paramètre `stop_reason` : logue un WARNING si `stop_reason == "max_tokens"` (troncature détectée), et en cas d'échec JSON logue les 500 derniers caractères de la réponse brute pour faciliter le diagnostic.
- `stop_reason` passé aux trois appels : `analyze_structure`, `generate_responses`, `generate_attention_points`.

**Fichier :** [app/services/claude_client.py](app/services/claude_client.py)

---

## Amélioration #6 — `project_manager.py` : `get_corrections_dir()` public

**Problème :** `web.py` accédait à `project_manager._project_dir(project.id)` (fonction "privée" par convention) pour construire le chemin du dossier corrections.

**Fix :** Ajout d'une fonction publique `get_corrections_dir(project_id: str) -> Path` dans `project_manager.py`. `web.py` mis à jour pour l'utiliser.

**Fichiers :** [app/services/project_manager.py](app/services/project_manager.py), [app/api/web.py](app/api/web.py)
