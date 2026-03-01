# PAS Assistant — v04

## Contenu de cette itération

Phase 1 — Fondations :

- Structure du projet et arborescence
- `config.py` — chargement de `app.yaml`, `.env`, `questions.txt`, `users.yaml`
- `main.py` — FastAPI app avec health check et page privée
- `auth/` — OAuth2 Azure AD (Authorization Code Flow) + vérification utilisateurs autorisés
- `web/` — Interface HTML/CSS minimale (page publique + page privée)
- `ansible/` — Playbook de déploiement complet (Ubuntu 24.04, Nginx, Let's Encrypt, systemd)

## Lancer en développement

```bash
cd _v04
export PAS_BASE_DIR=.
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Accès : `http://localhost:8000/`
