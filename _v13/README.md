# PAS Assistant — v13

## Prompt 28 — Injection de POLITIQUES.md dans le prompt Claude

### Ce qui a été fait

Ajout des politiques de sécurité du FOURNISSEUR comme source de contexte dans la génération de réponses, avec mise en cache via l'API Files d'Anthropic.

### Fichiers modifiés

#### `data/config/prompts/system_response.txt`

Nouvelles règles ajoutées au system prompt :

- **Ordre de priorité des sources** : cadrage (priorité max) > corpus > POLITIQUES.md
- **Règle d'applicabilité** : pour chaque question, Claude évalue si elle est dans le périmètre de la prestation en se basant sur les métadonnées de cadrage. Si hors périmètre → réponse "Non applicable sur le périmètre de la prestation." + justification courte + statut N/A.
- **Cas `pas_niveau_entreprise = Oui`** : toutes les questions sont applicables, POLITIQUES.md est utilisé systématiquement.

#### `app/services/response_generator.py`

Trois ajouts :

**`_get_policies_file_id(client)`**
- Lit `data/policies/politiques.md`
- Calcule le MD5 du contenu
- Si le MD5 correspond au cache (`data/policies/file_id_cache.json`) → retourne le `file_id` en cache
- Sinon → upload via `client.beta.files.upload()`, sauvegarde le cache, retourne le nouveau `file_id`
- Si le fichier n'existe pas → retourne `None` (la génération continue sans POLITIQUES.md)

**`_call_claude_json()`**
- Accepte désormais `client` et `file_id` en paramètres optionnels
- Si `file_id` fourni → utilise `client.beta.messages.create()` avec `betas=["files-api-2025-04-14"]` et passe POLITIQUES.md comme `document` dans le message utilisateur
- Sinon → appel standard `client.messages.create()`

**`_do_generation()`**
- Crée le client Anthropic une seule fois (réutilisé pour le cache Files + les appels de génération)
- Appelle `_get_policies_file_id()` avant la génération
- Passe `has_policies` à `_build_user_prompt_responses()` pour injecter la mention du document dans le prompt utilisateur
- Passe `file_id` à l'appel de génération des réponses (pas aux points d'attention)

### Cache du file_id

```
data/policies/
├── politiques.md          ← fichier uploadé par l'admin
└── file_id_cache.json     ← {"md5": "abc123...", "file_id": "file-..."}
```

Le cache évite de ré-uploader le fichier à chaque génération. Il est invalidé automatiquement si le contenu de `politiques.md` change.
