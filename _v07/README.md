# PAS Assistant — v07

## Lancer l'application

```bash
cd /root/dev/autopas/_v07
source venv/bin/activate
PAS_BASE_DIR=. uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Accès : http://localhost:8000/private (bypass auth activé via `DEV_AUTH_BYPASS=true` dans `.env`)

---

## Fonctionnalités implémentées

### Onglet "Analyser un nouveau PAS"

Flux : **Upload** → **Anonymisation** → **Téléchargement**

1. Upload d'un `.xlsx`
2. Extraction des suggestions de mots-clés (métadonnées du fichier)
3. Saisie des paires mot réel → alias
4. Téléchargement de `anonymized.xlsx`

### Onglet "Base de connaissances"

Flux : **Upload** → **Wizard cadrage** → **Anonymisation** → **Infos complémentaires** → **Enregistrement**

1. Upload d'un questionnaire déjà rempli (`.xlsx` ou `.docx`)
2. Wizard de cadrage (13 questions, conditions dynamiques)
3. Anonymisation du fichier (même logique que l'onglet PAS)
4. Date de remplissage + tags libres
5. Enregistrement dans `data/corpus/`
6. Liste du corpus avec suppression

---

## Architecture

```
_v07/
├── app/
│   ├── main.py                  — FastAPI app, SessionMiddleware, lifespan
│   ├── config.py                — chargement app.yaml + questions.txt + users.yaml
│   ├── auth/
│   │   ├── azure_ad.py          — OAuth2 Azure AD (MSAL)
│   │   ├── router.py            — routes /auth/login, /auth/callback, /auth/logout
│   │   └── session.py           — get_current_user, get_optional_user
│   ├── api/
│   │   └── web.py               — tous les endpoints REST
│   └── services/
│       ├── anonymizer.py        — anonymize_xlsx, anonymize_docx, extract_metadata*
│       └── structure_analyzer.py — detect_xlsx_structure (appel Claude)
├── data/
│   ├── config/
│   │   ├── app.yaml         — config générale (modèle Claude, verbosité…)
│   │   ├── questions.txt    — questions de cadrage (format KEY/OPTIONS/TYPE/MULTI/IF)
│   │   └── users.yaml       — liste des utilisateurs autorisés
│   ├── projects/            — projets PAS (créés à l'upload)
│   └── corpus/              — base de connaissances (créés à l'upload corpus)
└── web/
    ├── index.html           — page publique (login)
    ├── private.html         — application (tabs + wizard + anonymisation)
    └── style.css            — styles globaux
```

---

## Endpoints REST

### Questions
| Méthode | URL | Description |
|---|---|---|
| `GET` | `/api/questions` | Liste des questions de cadrage (avec KEY) |

### Projets PAS
| Méthode | URL | Description |
|---|---|---|
| `POST` | `/api/upload` | Upload xlsx → crée un projet |
| `GET` | `/api/projects/{id}/working` | Télécharge la copie de travail |
| `GET` | `/api/projects/{id}/metadata` | Suggestions de mots-clés (métadonnées fichier) |
| `POST` | `/api/projects/{id}/anonymize` | Anonymise le fichier |
| `GET` | `/api/projects/{id}/anonymized` | Télécharge le fichier anonymisé |
| `POST` | `/api/projects/{id}/detect-structure` | Détecte la structure via Claude (sur anonymized.xlsx) |
| `POST` | `/api/projects/{id}/structure` | Sauvegarde la structure confirmée |
| `POST` | `/api/projects/{id}/roundtrip` | Test roundtrip openpyxl (dev) |
| `GET` | `/api/projects/{id}/roundtrip` | Télécharge le résultat roundtrip (dev) |

### Corpus
| Méthode | URL | Description |
|---|---|---|
| `GET` | `/api/corpus` | Liste les entrées du corpus |
| `POST` | `/api/corpus` | Upload xlsx/docx → crée une entrée |
| `GET` | `/api/corpus/{id}/anon-suggestions` | Suggestions de mots-clés pour anonymisation |
| `POST` | `/api/corpus/{id}/anonymize` | Anonymise le fichier corpus |
| `POST` | `/api/corpus/{id}/detect-structure` | Détecte la structure via Claude (xlsx uniquement) |
| `POST` | `/api/corpus/{id}/structure` | Sauvegarde la structure confirmée |
| `POST` | `/api/corpus/{id}/metadata` | Sauvegarde les métadonnées (réponses wizard) |
| `DELETE` | `/api/corpus/{id}` | Supprime une entrée du corpus |

---

## Format questions.txt

```
+ Texte de la question
  OPTIONS: Option A, Option B, Option C   ← optionnel
  TYPE: text|number                        ← défaut: text
  MULTI: true                              ← cases à cocher (avec OPTIONS)
  KEY: nom_du_champ                        ← clé JSON pour les métadonnées
  IF previous == "Valeur": ...             ← condition sur la question précédente
  IF previous contains "Valeur": ...       ← condition sur multi-select
```

---

## Cycle de vie d'un projet PAS

```
data/projects/{uuid}/
  original.xlsx          ← fichier original (jamais modifié)
  working.xlsx           ← copie de travail
  anonymized.xlsx        ← fichier anonymisé (entrée Claude)
  anonymized_map.json    ← table original → alias
  structure.json         ← structure détectée et confirmée
```

## Cycle de vie d'une entrée corpus

```
data/corpus/{uuid}/
  original.{ext}         ← fichier original (jamais modifié)
  anonymized.{ext}       ← fichier anonymisé (envoyé au LLM)
  anonymized_map.json    ← table original → alias
  structure.json         ← structure détectée et confirmée (xlsx uniquement)
  metadata.json          ← métadonnées complètes (cadrage + date + tags)
```

### Structure de metadata.json
```json
{
  "filename": "questionnaire.xlsx",
  "format": "xlsx",
  "type_prestation": "CDS",
  "nb_etp": 5,
  "activites": "développement, infogérance",
  "expertise_atlassian": false,
  "hebergement_donnees": "Cloud",
  "cloud_provider": "Oracle Cloud Infrastructure",
  "sous_traitance_rgpd": true,
  "lieu_travail": ["Agence FOURNISSEUR", "Télétravail"],
  "agences": "Tours",
  "poste_travail": "FOURNISSEUR",
  "connexion_distante": "VPN CLIENT",
  "secteur_client": "Privé",
  "date_remplissage": "2024-02-20",
  "tags_supplementaires": ["cloud", "OCI"]
}
```

---

## Composant QuestionWizard (JS)

Classe partagée entre les deux onglets. Instanciation :

```javascript
const wizard = new QuestionWizard({
  container: document.getElementById('mon-container'),
  questions: questionsFromApi,   // GET /api/questions
  onComplete: (answers) => {
    // answers = { type_prestation_base: "AT", nb_etp: "3", ... }
  },
});
wizard.start();
```

Gère : radio, checkbox (MULTI), number, textarea, conditions `previous == X` / `previous contains X`, navigation avant/arrière avec historique.

---

## Variables d'environnement (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
AZURE_CLIENT_SECRET=...
SESSION_SECRET_KEY=...          # openssl rand -hex 32
DEV_AUTH_BYPASS=true            # désactive OAuth2 en dev local
```
