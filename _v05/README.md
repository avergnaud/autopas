# PAS Assistant — v05

## Contenu de cette itération

Phase 2 à 5 — Interface web complète + backend API :

- `web/private.html` + `web/app.js` — Wizard complet (5 étapes : upload, structure, cadrage, anonymisation, génération/téléchargement)
- `web/style.css` — Styles mis à jour
- `app/api/web.py` — Endpoints REST : projets, structure, questions, cadrage, anonymisation, génération, status, output, attention
- `app/services/project_manager.py` — Gestion cycle de vie d'un projet (états, filesystem)
- `app/services/parser_xlsx.py` — Parsing questionnaires xlsx (openpyxl)
- `app/services/parser_docx.py` — Parsing questionnaires docx (python-docx)
- `app/services/anonymizer.py` — Anonymisation / dé-anonymisation
- `app/services/reference_selector.py` — Sélection fichiers de référence par similarité
- `app/services/claude_client.py` — Client API Claude (appel principal + points d'attention)
- `app/models/` — Modèles Pydantic (projet, questions, métadonnées)

## Décisions UX/techniques

- **Wizard step-by-step** : une question de cadrage par écran, navigation Précédent/Suivant
- **Frontend vanilla** : HTML/CSS/JS sans framework, sans build step
- **Anonymisation** : tableau de paires clé→valeur dynamiques
- **Génération async** : polling toutes les 3s sur GET /api/projects/{id}/status
- **Confirmation de structure** : étape simplifiée affichant les colonnes détectées par Claude

## Lancer en développement

```bash
cd _v05
export PAS_BASE_DIR=.
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Accès : `http://localhost:8000/`

