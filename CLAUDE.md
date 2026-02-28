# CLAUDE.md — Instructions pour Claude Code

## Projet : PAS Assistant

### Description

PAS Assistant est un outil d'aide au remplissage de questionnaires de sécurité (Plans d'Assurance Sécurité) pour une ESN (FOURNISSEUR). L'outil parse un questionnaire sécurité (xlsx ou docx), pose des questions de cadrage, anonymise les données confidentielles, appelle l'API Claude pour pré-remplir les réponses, puis génère un document complété avec des points d'attention.

### Méthode de développement — Baby Steps

Le développement se fait par itérations successives appelées **baby steps** :

1. **Un dossier par itération** — chaque itération vit dans un dossier `_vXX` à la racine du projet (ex : `_v01`, `_v02`, ...). Tout le code de l'itération est dans ce dossier.
2. **Suivi des prompts** — chaque prompt de la conversation est sauvegardé sous `_vXX/_prompts/NN.md` (ex : `_v01/_prompts/01.md`, `_v01/_prompts/02.md`, ...).
3. **Le dossier `_vXX`** à la racine sert de template vide (avec son sous-dossier `_prompts/`).

### Documents de référence

Lis impérativement avant de commencer :
- `SPECIFICATIONS_FONCTIONNELLES.md` — Ce que l'outil doit faire (workflow, fonctionnalités, règles métier)
- `SPECIFICATIONS_TECHNIQUES.md` — Comment le construire (architecture, arborescence, config, API, Ansible)

### Stack technique

- **Serveur** : Ubuntu 24.04 sur DigitalOcean (2 GB RAM, 1 CPU)
- **Backend** : Python 3.12 + FastAPI + Uvicorn
- **Reverse proxy** : Nginx + Let's Encrypt (domaine : appsec.cc)
- **Bot Teams** : Bot Framework SDK Python (botbuilder-python)
- **LLM** : API Claude (SDK `anthropic`)
- **Parsing** : `openpyxl` (xlsx), `python-docx` (docx)
- **Auth** : OAuth2 via Azure AD / M365 (librairie `msal`)
- **Stockage** : Filesystem uniquement (pas de BDD)
- **Provisioning** : Ansible
- **Configuration** : YAML + fichiers texte + JSON
- **Secrets** : Variables d'environnement (fichier `.env`)

### Arborescence cible

```
/opt/pas-assistant/
├── app/                          # Code backend
│   ├── main.py                   # FastAPI app
│   ├── config.py                 # Chargement config
│   ├── auth/                     # OAuth2, users
│   ├── api/                      # Endpoints (bot, web, admin)
│   ├── services/                 # Logique métier
│   └── models/                   # Modèles Pydantic
├── data/
│   ├── corpus/                   # Base de connaissances (fichiers + JSON)
│   ├── projects/                 # Projets utilisateurs
│   └── config/                   # Configuration (app.yaml, questions.txt, users.yaml, prompts/)
├── web/                          # Frontend HTML/JS/CSS statique
├── ansible/                      # Playbook Ansible
├── requirements.txt
├── .env
└── README.md
```

### Principes de développement

1. **KISS** — Keep It Simple Stupid. Pas de sur-ingénierie. Filesystem pour le stockage, pas de BDD. JSON/YAML pour la config, pas d'ORM.

2. **Sécurité d'abord** — JAMAIS envoyer de données non anonymisées à l'API Claude. JAMAIS modifier le document original. Clés API en variables d'environnement uniquement.

3. **Configuration externalisée** — Tout ce qui peut être configuré doit être dans des fichiers sous `data/config/`, pas en dur dans le code : questions de cadrage, prompts système, liste d'utilisateurs, paramètres de verbosité, modèle Claude.

4. **Un seul utilisateur à la fois** par questionnaire. Pas besoin de concurrence.

5. **Pas d'intelligence dans le bot Teams** — Le bot est un proxy pur qui transmet les messages entre Teams et le backend FastAPI. Toute la logique est côté backend.

### Ordre de développement recommandé

#### Phase 1 — Fondations
1. Structure du projet et arborescence
2. `config.py` — chargement de `app.yaml`, `.env`, `questions.txt`, `users.yaml`
3. `main.py` — FastAPI app de base avec health check
4. `auth/` — OAuth2 Azure AD + vérification utilisateurs autorisés

#### Phase 2 — Parsing et anonymisation
5. `parser_xlsx.py` — extraction contenu xlsx (openpyxl)
6. `parser_docx.py` — extraction contenu docx (python-docx)
7. `claude_client.py` — client API Claude (SDK anthropic)
8. Analyse de structure via API Claude (`system_structure.txt`)
9. `anonymizer.py` — rechercher/remplacer + dé-anonymisation

#### Phase 3 — Cœur métier
10. `project_manager.py` — gestion cycle de vie projet (états, filesystem)
11. `reference_selector.py` — sélection fichiers de référence par similarité
12. `response_generator.py` — orchestration génération réponses (appel API Claude avec contexte + corpus + verbosité)
13. `attention_generator.py` — génération points d'attention (appel API séparé)
14. `document_writer.py` — insertion réponses dans xlsx/docx
15. `diff_detector.py` — détection corrections (comparaison versions)

#### Phase 4 — API REST
16. `api/web.py` — tous les endpoints interface web (CRUD projets, upload, download, cadrage, génération)
17. `api/admin.py` — endpoints administration corpus
18. `api/bot.py` — endpoint Bot Framework

#### Phase 5 — Interface web
19. `web/index.html`, `web/app.js`, `web/style.css` — interface web basique (upload, cadrage, résultats)

#### Phase 6 — Bot Teams
20. Intégration Bot Framework SDK dans le backend
21. Gestion upload/download fichiers via Teams

#### Phase 7 — Infrastructure
22. Playbook Ansible complet (roles: base, nginx, app)
23. Templates Nginx, systemd, config

### Conventions de code

- **Python** : PEP 8, type hints partout, docstrings Google style
- **Modèles** : Pydantic v2 pour tous les modèles de données
- **Async** : utiliser `async/await` pour les endpoints FastAPI et les appels API Claude
- **Erreurs** : HTTPException avec codes appropriés (400, 401, 403, 404, 500)
- **Logs** : module `logging` standard Python, logger par module

### Points d'attention techniques

#### Parsing xlsx — Structure variable
La structure des xlsx varie d'un CLIENT à l'autre. Ne PAS coder en dur les numéros de colonnes. Utiliser l'API Claude pour analyser la structure (voir `system_structure.txt`). Demander confirmation à l'utilisateur.

#### Parsing docx — Structure variable
Même logique que xlsx. Les documents docx n'ont pas tous le même pattern. Certains utilisent des tableaux, d'autres des paragraphes avec styles. L'API Claude analyse et identifie le pattern.

#### Anonymisation — Ordre de remplacement
Trier les mots-clés à anonymiser par longueur décroissante pour éviter les remplacements partiels. Exemple : "Ministère des Armées" doit être remplacé avant "Armées".

#### Appel API Claude — Taille du contexte
Un questionnaire complet + fichiers de référence peut représenter beaucoup de tokens. Vérifier que la taille totale ne dépasse pas la fenêtre de contexte du modèle. Si c'est le cas, réduire le nombre de fichiers de référence ou envoyer les questions par lots.

#### Bot Teams — Upload de fichiers
Les fichiers uploadés dans Teams sont accessibles via une URL temporaire. Le bot doit télécharger le fichier depuis cette URL avant de le transmettre au backend.

#### Bot Teams — Messages longs
Teams a une limite de taille sur les messages. Pour les points d'attention longs, envoyer en pièce jointe plutôt qu'en texte dans le chat.

### Fichiers de test

Le projet contient des exemples de questionnaires déjà anonymisés dans le corpus :
- `FOURNISSEUR_Security_Requirements_20240220_01.xlsx` — format international, 129 questions
- `A_15FOURNISSEURQuestionnaire_SSIAVE_V2_31.xlsx` — format multi-onglets, ~110 questions
- `2MAIN_Plan-Assurance-Securite_lot2-SOCIETE-FOURNISSEUR-v0_7.docx` — format PAS docx

Les fichiers `.txt` associés contiennent les entrées (réponses de cadrage) et les sorties attendues (points d'attention). Utiliser ces fichiers pour tester le workflow complet.

### Variables d'environnement nécessaires

```
ANTHROPIC_API_KEY          # Clé API Anthropic
AZURE_TENANT_ID            # ID du tenant M365 (TENANT_365)
AZURE_CLIENT_ID            # ID de l'app registration Azure AD
AZURE_CLIENT_SECRET        # Secret de l'app registration
TEAMS_BOT_APP_ID           # ID de l'app bot Teams
TEAMS_BOT_APP_PASSWORD     # Password de l'app bot Teams
```

### Commandes utiles

```bash
# Lancer le backend en dev
cd /opt/pas-assistant
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Lancer le playbook Ansible
cd ansible
ansible-playbook -i inventory.ini playbook.yml

# Tester le health check
curl https://appsec.cc/api/health
```

### Ce qui est hors scope (V1)

- Support .doc (l'utilisateur convertit en .docx)
- Support PDF éditable
- Exploitation des autres documents de l'AO
- Multi-utilisateurs simultanés sur un même questionnaire
- Fine-tuning / RAG
- Détection automatique NER des données personnelles
- Interface web avancée (Adaptive Cards)
