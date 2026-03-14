# PAS Assistant — v17

## Prompt 39 — Sauvegarde et téléchargement des prompts Claude

### Fonctionnalité

Lors de la génération, les prompts envoyés à l'API Claude sont sauvegardés dans le dossier projet côté serveur. Un lien de téléchargement est affiché sur l'écran "Génération terminée avec succès !".

### Fichier généré

`data/projects/{project_id}/prompt_debug.txt` — contient les 4 sections dans l'ordre :

```
=== SYSTEM (responses) ===
...
=== USER (responses) ===
...
=== SYSTEM (attention) ===
...
=== USER (attention) ===
...
```

### Fichiers modifiés

| Fichier | Modification |
|---|---|
| `app/services/response_generator.py` | Écriture de `prompt_debug.txt` après construction de chaque prompt (responses en write, attention en append) |
| `app/api/web.py` | Nouvel endpoint `GET /api/projects/{project_id}/prompt` — sert `prompt_debug.txt` en `text/plain` |
| `web/private.html` | Nouvelle download card "Prompts Claude (debug)" + assignment JS du `href` au statut `completed` |
