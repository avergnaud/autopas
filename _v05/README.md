# PAS Assistant — v05

## Développement local (WSL Ubuntu)

### 1. Prérequis système (une seule fois)

```bash
sudo apt update && sudo apt install python3-pip python3-venv -y
```

### 2. Venv

```bash
cd _v05
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Fichier `.env`

```bash
cp .env.example .env
```

Avec `DEV_AUTH_BYPASS=true`, aucune variable n'est obligatoire pour tester l'upload/download.

### 5. Lancer

```bash
source venv/bin/activate
PAS_BASE_DIR=. uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Ouvrir : `http://localhost:8000`

---

> **Note Python :** Le projet cible Python 3.12. Si la version système (3.10) pose problème :
> `sudo apt install python3.12 python3.12-venv` puis remplacer `python3` par `python3.12`.
