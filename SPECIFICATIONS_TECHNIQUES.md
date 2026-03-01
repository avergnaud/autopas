# Spécifications Techniques — PAS Assistant

**Version** : 1.0
**Date** : 2026-02-28
**Statut** : Draft

---

## 1. Architecture générale

### 1.1 Vue d'ensemble

```
┌────────────────────────────────────────────────────────────────────┐
│                        TENANT_365 (M365)                           │
│                                                                    │
│  ┌──────────────┐                                                  │
│  │  Utilisateur  │                                                  │
│  │  (Navigateur) │                                                  │
│  └──────────────┘                                                  │
│                                                                    │
│  ┌──────────────┐                                                  │
│  │  Azure AD     │                                                  │
│  │  (OAuth2 /    │                                                  │
│  │   SSO)        │                                                  │
│  └──────┬───────┘                                                  │
└─────────┼──────────────────────────────────────────────────────────┘
          │ OAuth2
          │ tokens
          ▼
┌────────────────────────────────────────────────────────────────────┐
│              Serveur DigitalOcean (165.232.65.179)               │
│              Ubuntu 24.04 — appsec.cc                              │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │                      Nginx (reverse proxy)                │     │
│  │                      HTTPS / Let's Encrypt                │     │
│  │                      appsec.cc:443                        │     │
│  └─────────────┬──────────────────────┬─────────────────────┘     │
│                │                      │                            │
│                ▼                      ▼                            │
│  ┌─────────────────────┐  ┌──────────────────────┐               │
│  │  FastAPI Backend     │  │  Interface Web        │               │
│  │  (API REST)          │  │  (HTML/JS statique)   │               │
│  │  Port 8000           │  │  Servie par Nginx     │               │
│  └──────────┬──────────┘  └──────────────────────┘               │
│             │                                                      │
│             ├───────────────┬──────────────────┐                  │
│             ▼               ▼                  ▼                  │
│  ┌───────────────┐  ┌────────────┐  ┌─────────────────┐         │
│  │  Filesystem    │  │  API Claude │  │  Microsoft       │         │
│  │  /opt/pas-     │  │  (Anthropic)│  │  Graph API       │         │
│  │  assistant/    │  │             │  │  (validation     │         │
│  │  data/         │  │             │  │   tokens OAuth2) │         │
│  └───────────────┘  └────────────┘  └─────────────────┘         │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 1.2 Composants

| Composant | Technologie | Rôle |
|---|---|---|
| Serveur | DigitalOcean Droplet, Ubuntu 24.04, 2 GB RAM / 1 CPU / 50 GB SSD ($12/mo) | Hébergement |
| Reverse proxy | Nginx | HTTPS, routage, fichiers statiques |
| Certificat SSL | Let's Encrypt (Certbot) | HTTPS pour appsec.cc |
| Backend | Python 3.12 + FastAPI + Uvicorn | API REST, logique métier |
| Interface Web | HTML/CSS/JS statique (vanilla ou Vue.js léger) | Frontend utilisateur |
| Authentification | OAuth2 / Azure AD (TENANT_365) | SSO M365 |
| Stockage | Filesystem local | Corpus, config, projets |
| LLM | API Claude (Anthropic) | Génération réponses |
| Provisioning | Ansible | Conf as Code |

### 1.3 Flux réseau

```
Web Browser  ──HTTPS──▶ appsec.cc:443 (interface web)
Backend      ──HTTPS──▶ api.anthropic.com (API Claude)
Backend      ──HTTPS──▶ login.microsoftonline.com (validation tokens)
```

Ports ouverts sur le serveur :
- 443 (HTTPS)
- 80 (HTTP — redirection vers HTTPS + ACME challenge)
- 22 (SSH — restreint par IP si possible)

---

## 2. Arborescence du projet

```
/opt/pas-assistant/
├── app/                          # Code source backend
│   ├── main.py                   # Point d'entrée FastAPI
│   ├── config.py                 # Chargement configuration
│   ├── auth/
│   │   ├── oauth2.py             # Validation tokens M365
│   │   └── users.py              # Vérification utilisateurs autorisés
│   ├── api/
│   │   ├── web.py                # Endpoints interface web
│   │   └── admin.py              # Endpoints administration
│   ├── services/
│   │   ├── parser_xlsx.py        # Parsing questionnaires xlsx
│   │   ├── parser_docx.py        # Parsing questionnaires docx
│   │   ├── anonymizer.py         # Anonymisation / dé-anonymisation
│   │   ├── reference_selector.py # Sélection fichiers de référence
│   │   ├── claude_client.py      # Client API Claude
│   │   ├── response_generator.py # Orchestration génération réponses
│   │   ├── attention_generator.py# Génération points d'attention
│   │   ├── document_writer.py    # Écriture réponses dans document
│   │   ├── diff_detector.py      # Détection différences (corrections)
│   │   └── project_manager.py    # Gestion cycle de vie d'un projet
│   └── models/
│       ├── project.py            # Modèle de données projet
│       ├── question.py           # Modèle question de cadrage
│       └── metadata.py           # Modèle métadonnées corpus
├── data/
│   ├── corpus/                   # Base de connaissances
│   │   ├── files/                # Fichiers questionnaires anonymisés
│   │   │   ├── ref_001.xlsx
│   │   │   ├── ref_001.json      # Métadonnées associées
│   │   │   ├── ref_002.docx
│   │   │   ├── ref_002.json
│   │   │   └── ...
│   │   └── index.json            # Index du corpus (liste des fichiers)
│   ├── projects/                 # Projets en cours et terminés
│   │   └── {project_id}/
│   │       ├── project.json      # État du projet (cadrage, anonymisation...)
│   │       ├── original.*        # Fichier d'origine (copie)
│   │       ├── working.*         # Copie de travail anonymisée
│   │       ├── output.*          # Document rempli (dé-anonymisé)
│   │       ├── attention.md      # Points d'attention
│   │       └── corrections/      # Fichiers corrigés ré-importés
│   │           ├── v1.*
│   │           └── ...
│   └── config/
│       ├── app.yaml              # Configuration générale
│       ├── questions.txt          # Questions de cadrage
│       ├── users.yaml            # Utilisateurs autorisés
│       └── prompts/
│           ├── system_response.txt    # Prompt système (génération réponses)
│           ├── system_attention.txt   # Prompt système (points d'attention)
│           └── system_structure.txt   # Prompt système (analyse structure)
├── web/                          # Interface web (fichiers statiques)
│   ├── index.html
│   ├── app.js
│   └── style.css
├── ansible/                      # Playbook Ansible
│   ├── playbook.yml
│   ├── inventory.ini
│   ├── roles/
│   │   ├── base/                 # Paquets système, users, firewall
│   │   ├── nginx/                # Nginx + Let's Encrypt
│   │   ├── app/                  # Déploiement application Python
│   │   └── monitoring/           # Logs, health check basique
│   └── templates/
│       ├── nginx.conf.j2
│       ├── pas-assistant.service.j2
│       └── app.yaml.j2
├── requirements.txt              # Dépendances Python
├── .env                          # Variables d'environnement (secrets)
└── README.md
```

---

## 3. Configuration

### 3.1 Configuration générale — `data/config/app.yaml`

```yaml
# PAS Assistant — Configuration

# API Claude
claude:
  api_key_env: "ANTHROPIC_API_KEY"    # Variable d'environnement
  model: "claude-sonnet-4-5-20250929" # Modèle par défaut
  max_tokens: 16000                   # Tokens max par appel
  temperature: 0.3                    # Température basse pour cohérence

# Verbosité
verbosity:
  default_level: 2
  levels:
    1:
      label: "Concis"
      max_words: 50
    2:
      label: "Standard"
      max_words: 100
    3:
      label: "Détaillé"
      max_words: 150

# Sélection des fichiers de référence
reference:
  max_files: 3                        # Nombre max de fichiers envoyés à l'API

# OAuth2 / Azure AD
oauth2:
  tenant_id_env: "AZURE_TENANT_ID"
  client_id_env: "AZURE_CLIENT_ID"
  client_secret_env: "AZURE_CLIENT_SECRET"

# Serveur
server:
  host: "0.0.0.0"
  port: 8000
  domain: "appsec.cc"
```

### 3.2 Variables d'environnement — `.env`

```bash
ANTHROPIC_API_KEY=sk-ant-...
AZURE_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_SECRET=...
```

### 3.3 Questions de cadrage — `data/config/questions.txt`

Format du fichier : chaque question commence par `+`. Les questions conditionnelles utilisent le mot-clé `IF` suivi de la condition.

```text
+ Est-ce que l'Appel d'Offre porte sur de l'Assistance Technique ou un dispositif à engagement ?
  OPTIONS: Assistance Technique, Dispositif à engagement

+ IF previous == "Dispositif à engagement": Si l'Appel d'Offre porte sur un dispositif à engagement, est-ce un CDR, CDC, CDS ?
  OPTIONS: CDR, CDC, CDS

+ Combien d'Equivalents Temps Plein sont mobilisés au début de la Prestation ?
  TYPE: number

+ Est-ce que la Prestation inclut des activités de développement, ou plutôt de l'analyse métier, du test, de la configuration ?
  TYPE: text

+ Est-ce que la Prestation fait partie du centre d'expertise Atlassian ?
  OPTIONS: Oui, Non

+ Sur le périmètre de la Prestation, est-ce que les données CLIENT seront hébergées par le SI du CLIENT, par FOURNISSEUR, ou par une solution Cloud ?
  OPTIONS: SI CLIENT, FOURNISSEUR, Cloud
  TYPE: text

+ Est-ce que le FOURNISSEUR est sous-traitant pour au-moins un traitement de données personnelles au sens RGPD ?
  OPTIONS: Oui, Non
  TYPE: text

+ Est-ce que les collaborateurs travailleront sur site CLIENT, en agence FOURNISSEUR, en télétravail ?
  OPTIONS: Site CLIENT, Agence FOURNISSEUR, Télétravail
  MULTI: true

+ IF previous contains "Agence FOURNISSEUR": Si les collaborateurs travaillent en agence FOURNISSEUR, depuis quelles agences exactement ?
  TYPE: text

+ Est-ce que les collaborateurs utilisent des postes de travail CLIENT ou FOURNISSEUR ?
  OPTIONS: CLIENT, FOURNISSEUR

+ Par quel moyen les collaborateurs se connectent à distance au SI CLIENT ?
  TYPE: text
```

### 3.4 Utilisateurs autorisés — `data/config/users.yaml`

```yaml
# Liste des utilisateurs autorisés (identifiants Azure AD / M365)
authorized_users:
  - email: "a.vergnaud@fournisseur.com"
    role: "admin"
  - email: "jm.orsini@fournisseur.com"
    role: "user"
  - email: "f.morin@fournisseur.com"
    role: "admin"
```

---

## 4. API REST — Endpoints

### 4.1 Interface Web

| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/auth/login` | Initie le flow OAuth2 (redirect vers Azure AD) |
| GET | `/api/auth/callback` | Callback OAuth2 |
| GET | `/api/auth/me` | Retourne l'utilisateur courant |
| POST | `/api/projects` | Crée un nouveau projet (upload questionnaire + analyse structure) |
| GET | `/api/projects` | Liste les projets de l'utilisateur |
| GET | `/api/projects/{id}` | Détail d'un projet |
| PUT | `/api/projects/{id}/structure` | Valide / corrige la structure détectée |
| GET | `/api/projects/{id}/questions` | Retourne la liste des questions de cadrage |
| POST | `/api/projects/{id}/cadrage` | Envoie les réponses de cadrage |
| POST | `/api/projects/{id}/anonymize` | Envoie les paires d'anonymisation (ou liste vide si étape passée) |
| POST | `/api/projects/{id}/generate` | Lance la génération en arrière-plan |
| GET | `/api/projects/{id}/status` | Statut du traitement (polling, toutes les 3s) |
| GET | `/api/projects/{id}/output` | Télécharge le document rempli |
| GET | `/api/projects/{id}/attention` | Télécharge le fichier points d'attention (.md) |
| POST | `/api/projects/{id}/corrections` | Upload du document corrigé (boucle correction) |

**Réponse de `POST /api/projects` (upload + analyse structure) :**
```json
{
  "id": "proj_20260301_143022_abc12",
  "status": "structure_detected",
  "original_filename": "Questionnaire_SSI.xlsx",
  "format": "xlsx",
  "structure": {
    "sheets": [
      {
        "name": "3 - Questionnaire",
        "has_questions": true,
        "id_column": "B",
        "question_column": "D",
        "response_columns": ["E", "G"],
        "header_row": 3,
        "first_data_row": 4
      }
    ]
  }
}
```

**Réponse de `GET /api/projects/{id}/status` (polling) :**
```json
{
  "id": "proj_20260301_143022_abc12",
  "status": "generating",
  "progress_step": "Génération des réponses...",
  "progress_pct": 60
}
```

Valeurs possibles de `status` : `created`, `structure_detected`, `cadrage`, `anonymizing`, `generating`, `completed`, `error`.

Valeurs possibles de `progress_step` (quand `status == "generating"`) :
- `"Anonymisation en cours..."`
- `"Sélection des fichiers de référence..."`
- `"Génération des réponses (appel Claude)..."`
- `"Génération des points d'attention..."`
- `"Finalisation du document..."`

**Réponse de `GET /api/projects/{id}/questions` :**
```json
{
  "questions": [
    {
      "id": 1,
      "text": "Est-ce que l'Appel d'Offre porte sur de l'Assistance Technique ou un dispositif à engagement ?",
      "type": "options",
      "options": ["Assistance Technique", "Dispositif à engagement"],
      "multi": false,
      "condition": null
    },
    {
      "id": 2,
      "text": "Si l'Appel d'Offre porte sur un dispositif à engagement, est-ce un CDR, CDC, CDS ?",
      "type": "options",
      "options": ["CDR", "CDC", "CDS"],
      "multi": false,
      "condition": {"question_id": 1, "equals": "Dispositif à engagement"}
    },
    {
      "id": 3,
      "text": "Combien d'Equivalents Temps Plein sont mobilisés au début de la Prestation ?",
      "type": "number",
      "options": null,
      "multi": false,
      "condition": null
    }
  ],
  "verbosity_question": {
    "id": 99,
    "text": "Quel niveau de détail souhaitez-vous pour les réponses ?",
    "type": "options",
    "options": ["Concis (50 mots max)", "Standard (100 mots max)", "Détaillé (150 mots max)"],
    "multi": false,
    "condition": null
  }
}
```

### 4.3 Administration

| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/admin/corpus` | Liste les fichiers du corpus |
| POST | `/api/admin/corpus` | Ajoute un fichier au corpus (+ métadonnées) |
| DELETE | `/api/admin/corpus/{ref_id}` | Supprime un fichier du corpus |
| PUT | `/api/admin/corpus/{ref_id}/metadata` | Modifie les métadonnées |
| GET | `/api/admin/config` | Lecture configuration |
| PUT | `/api/admin/config` | Mise à jour configuration |

---

## 4bis. Interface Web — Architecture Frontend

### Frontend — Technologie

**HTML/CSS/JS vanilla** (pas de framework, pas de build step).

Trois fichiers statiques servis par Nginx depuis `/opt/pas-assistant/web/` :
- `index.html` — page publique (accueil + bouton login)
- `private.html` — application wizard (accessible après authentification)
- `style.css` — feuille de styles commune
- `app.js` — logique wizard (inclus dans `private.html`)

### Frontend — Structure du wizard

Le wizard est géré entièrement côté client dans `app.js`. Un objet `state` central contient l'étape courante, l'ID de projet, et les données collectées.

```
state = {
  step: "upload" | "structure" | "cadrage" | "anonymisation" | "generation",
  projectId: null,
  structure: null,
  questions: [],
  questionIndex: 0,
  answers: {},
  anonymMappings: [],
  verbosityLevel: 2
}
```

Chaque étape est une `<section>` HTML masquée par défaut (`display: none`). Le wizard affiche la section correspondant à `state.step`.

### Frontend — Gestion des conditions (questions de cadrage)

Les conditions sont évaluées côté client lors de la navigation dans le wizard :

```javascript
function isQuestionVisible(question, answers) {
  if (!question.condition) return true;
  const previousAnswer = answers[question.condition.question_id];
  return previousAnswer === question.condition.equals;
}
```

Les questions non visibles sont sautées automatiquement (le wizard passe à la question suivante sans les afficher et sans les inclure dans les réponses envoyées au backend).

### Frontend — Polling de statut

Pendant l'étape de génération, un timer interroge le backend toutes les 3 secondes :

```javascript
async function pollStatus(projectId) {
  const res = await fetch(`/api/projects/${projectId}/status`);
  const data = await res.json();
  updateProgressUI(data.progress_step, data.progress_pct);
  if (data.status === "completed") {
    showDownloadButtons(projectId);
    return;
  }
  if (data.status === "error") {
    showErrorMessage();
    return;
  }
  setTimeout(() => pollStatus(projectId), 3000);
}
```

---

## 5. Modèle de données

### 5.1 Projet — `project.json`

```json
{
  "id": "proj_20260228_143022_abc12",
  "created_at": "2026-02-28T14:30:22Z",
  "updated_at": "2026-02-28T15:02:10Z",
  "user_email": "a.vergnaud@fournisseur.com",
  "status": "completed",
  "original_filename": "Questionnaire_SSI_ClientX.xlsx",
  "format": "xlsx",
  "cadrage": {
    "type_prestation": "CDS",
    "nb_etp": 5,
    "activites": "Développement",
    "expertise_atlassian": false,
    "hebergement_donnees": "cloud_fournisseur",
    "sous_traitance_rgpd": true,
    "lieu_travail": ["agence_fournisseur", "teletravail"],
    "agences": ["Tours"],
    "poste_travail": "fournisseur",
    "connexion_distante": "Aucune"
  },
  "anonymization": {
    "mappings": {
      "Ministère des Armées": "CLIENT",
      "Jean Dupont": "NOM_PERSONNE_1",
      "Marché SIAG": "MARCHE"
    }
  },
  "verbosity_level": 2,
  "claude_model": "claude-sonnet-4-5-20250929",
  "reference_files_used": ["ref_001", "ref_003"],
  "generation_started_at": "2026-02-28T14:45:00Z",
  "generation_completed_at": "2026-02-28T14:47:32Z",
  "corrections_count": 1
}
```

### 5.2 États du projet

```
  ┌──────────┐
  │  created  │  Upload du questionnaire
  └────┬─────┘
       │
       ▼
  ┌──────────┐
  │  cadrage  │  Questions de cadrage en cours
  └────┬─────┘
       │
       ▼
  ┌──────────────┐
  │  anonymizing  │  Saisie mots-clés, anonymisation
  └────┬─────────┘
       │
       ▼
  ┌──────────────┐
  │  generating   │  Appel API Claude en cours
  └────┬─────────┘
       │
       ▼
  ┌──────────────┐
  │  completed    │  Document rempli disponible
  └────┬─────────┘
       │ (optionnel)
       ▼
  ┌──────────────┐
  │  corrected    │  Corrections intégrées au corpus
  └──────────────┘
```

### 5.3 Métadonnées corpus — `ref_XXX.json`

Voir annexe 9.3 des spécifications fonctionnelles.

---

## 6. Services — Détail d'implémentation

### 6.1 Parsing (`parser_xlsx.py`, `parser_docx.py`)

**Librairies** :
- xlsx : `openpyxl`
- docx : `python-docx`

**Stratégie de détection de structure** :
La structure de chaque questionnaire varie d'un CLIENT à l'autre. La détection de structure se fait en deux passes :

1. **Extraction brute** : extraire tout le contenu textuel du document avec les coordonnées (numéro de ligne/colonne pour xlsx, numéro de section/paragraphe pour docx).

2. **Analyse par l'API Claude** : envoyer un extrait du contenu (les 10-20 premières lignes/sections) à l'API Claude avec le prompt `system_structure.txt` pour qu'il identifie :
   - Quelles colonnes/sections contiennent les questions.
   - Quelles colonnes/sections attendent les réponses.
   - Les identifiants de questions (le cas échéant).
   - Les onglets pertinents (pour xlsx multi-onglets).

3. **Validation** : l'utilisateur confirme ou corrige la structure détectée.

### 6.2 Anonymisation (`anonymizer.py`)

```python
class Anonymizer:
    def __init__(self, mappings: dict[str, str]):
        """mappings = {"Ministère des Armées": "CLIENT", ...}"""
        self.mappings = mappings
        # Trier par longueur décroissante pour éviter les remplacements partiels
        self.sorted_keys = sorted(mappings.keys(), key=len, reverse=True)

    def anonymize(self, text: str) -> str:
        """Rechercher/remplacer insensible à la casse."""
        for key in self.sorted_keys:
            pattern = re.compile(re.escape(key), re.IGNORECASE)
            text = pattern.sub(self.mappings[key], text)
        return text

    def deanonymize(self, text: str) -> str:
        """Remplacement inverse."""
        reverse = {v: k for k, v in self.mappings.items()}
        sorted_keys = sorted(reverse.keys(), key=len, reverse=True)
        for key in sorted_keys:
            text = text.replace(key, reverse[key])
        return text
```

### 6.3 Sélection des fichiers de référence (`reference_selector.py`)

**Algorithme de similarité** :

Pour chaque fichier du corpus, calculer un score de similarité avec le contexte courant :

```
score = 0

# Pondérations par critère
+3 si même type_prestation (AT, CDR, CDC, CDS)
+2 si même hébergement_donnees
+2 si activités similaires (intersection non vide)
+2 si même valeur sous_traitance_rgpd
+1 si même poste_travail
+1 si même expertise_atlassian
+1 si intersection lieu_travail non vide
+1 si même format de questionnaire
+1 si même secteur_client
```

Retourner les N fichiers avec les scores les plus élevés (N configurable, défaut 3).

### 6.4 Client API Claude (`claude_client.py`)

**Librairie** : `anthropic` (SDK Python officiel)

**Appel principal — Génération des réponses** :

```python
import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model=config.claude.model,
    max_tokens=config.claude.max_tokens,
    temperature=config.claude.temperature,
    system=load_prompt("system_response.txt"),
    messages=[
        {
            "role": "user",
            "content": [
                # Contexte de cadrage
                {"type": "text", "text": format_cadrage(project.cadrage)},
                # Contrainte de verbosité
                {"type": "text", "text": f"Verbosité : {verbosity.max_words} mots max par réponse."},
                # Fichiers de référence (en tant que documents)
                *reference_file_blocks,
                # Questionnaire à remplir
                {"type": "text", "text": anonymized_questionnaire_content},
                # Instruction finale
                {"type": "text", "text": "Remplis les réponses du questionnaire ci-dessus. Retourne le résultat au format JSON structuré."}
            ]
        }
    ]
)
```

**Appel secondaire — Points d'attention** :

Un appel séparé avec le prompt `system_attention.txt`, qui reçoit le questionnaire rempli et retourne les points d'attention au format structuré.

### 6.5 Format de réponse de l'API Claude

L'API Claude retourne les réponses au format JSON :

```json
{
  "responses": [
    {
      "question_id": "IS-AS-0001",
      "response": "Sur le périmètre de la prestation, FOURNISSEUR s'engage à..."
    },
    {
      "question_id": "IS-AS-0002",
      "response": "..."
    }
  ]
}
```

Pour les points d'attention :

```json
{
  "attention_points": [
    {
      "question_id": "COR2",
      "category": "DELAI_ANORMAL",
      "description": "Les SLA incident imposent un délai de notification de 1h.",
      "recommendation": "Négocier des délais réalistes ou préciser 'sur les heures ouvrées'."
    }
  ]
}
```

### 6.6 Écriture dans le document (`document_writer.py`)

**xlsx** : utiliser `openpyxl` pour écrire dans les cellules de réponse identifiées par le parsing.

**docx** : utiliser `python-docx` pour écrire dans les zones de réponse identifiées. Insérer le texte dans les paragraphes/tableaux appropriés.

### 6.7 Détection des différences (`diff_detector.py`)

Comparer le document de sortie (version générée) avec le document ré-importé (version corrigée) :

- **xlsx** : comparer cellule par cellule dans les colonnes de réponse.
- **docx** : comparer paragraphe par paragraphe dans les zones de réponse.

Stocker les différences détectées dans le fichier `project.json`.

---

## 7. Authentification

### 7.1 OAuth2 — Interface Web

```
Navigateur                  appsec.cc              Azure AD (TENANT_365)
    │                          │                          │
    │  GET /                   │                          │
    │─────────────────────────▶│                          │
    │  Redirect /api/auth/login│                          │
    │◀─────────────────────────│                          │
    │                          │                          │
    │  Redirect vers Azure AD  │                          │
    │──────────────────────────────────────────────────▶ │
    │                          │                          │
    │  Login M365              │                          │
    │◀──────────────────────────────────────────────────│
    │                          │                          │
    │  Redirect /api/auth/callback?code=...              │
    │─────────────────────────▶│                          │
    │                          │  Échange code → tokens   │
    │                          │─────────────────────────▶│
    │                          │◀─────────────────────────│
    │                          │                          │
    │  Set cookie session      │                          │
    │◀─────────────────────────│                          │
    │                          │                          │
    │  GET /api/projects       │                          │
    │  (cookie session)        │                          │
    │─────────────────────────▶│  Validate token          │
    │                          │  Check users.yaml        │
    │◀─────────────────────────│                          │
```

**Librairie** : `msal` (Microsoft Authentication Library for Python)

### 7.2 App Registration dans Azure AD

Créer une App Registration dans TENANT_365 avec :
- **Redirect URI** : `https://appsec.cc/api/auth/callback`
- **API permissions** : `User.Read` (Microsoft Graph)
- **Supported account types** : Single tenant (TENANT_365 uniquement)

---

## 8. Nginx — Configuration

```nginx
server {
    listen 80;
    server_name appsec.cc;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name appsec.cc;

    ssl_certificate /etc/letsencrypt/live/appsec.cc/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/appsec.cc/privkey.pem;

    # Interface web statique
    location / {
        root /opt/pas-assistant/web;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # API backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout long pour les appels API Claude
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;

        # Upload fichiers (jusqu'à 50 Mo)
        client_max_body_size 50M;
    }
}
```

---

## 9. Ansible — Playbook

### 9.1 Inventaire — `inventory.ini`

```ini
[pas_server]
appsec.cc ansible_host=165.232.65.179 ansible_user=root
```

### 9.2 Playbook principal — `playbook.yml`

```yaml
---
- name: Deploy PAS Assistant
  hosts: pas_server
  become: true
  vars:
    app_dir: /opt/pas-assistant
    app_user: pas-assistant
    domain: appsec.cc
    python_version: "3.12"

  roles:
    - base
    - nginx
    - app
```

### 9.3 Rôle `base`

Tâches :
- Mise à jour système (`apt update && apt upgrade`)
- Installation paquets : `python3.12`, `python3.12-venv`, `python3-pip`, `nginx`, `certbot`, `python3-certbot-nginx`, `git`, `ufw`
- Création utilisateur système `pas-assistant`
- Configuration firewall (UFW) : ports 22, 80, 443
- Configuration timezone et locale

### 9.4 Rôle `nginx`

Tâches :
- Déploiement configuration Nginx depuis template `nginx.conf.j2`
- Obtention certificat Let's Encrypt : `certbot --nginx -d appsec.cc --non-interactive --agree-tos -m admin@appsec.cc`
- Configuration renouvellement automatique (cron certbot)
- Activation et démarrage Nginx

### 9.5 Rôle `app`

Tâches :
- Création répertoire `/opt/pas-assistant` et sous-répertoires
- Création virtualenv Python
- Copie du code source et des fichiers de configuration
- Installation dépendances : `pip install -r requirements.txt`
- Copie du fichier `.env`
- Déploiement du fichier systemd `pas-assistant.service` depuis template
- Activation et démarrage du service

### 9.6 Service systemd — `pas-assistant.service`

```ini
[Unit]
Description=PAS Assistant Backend
After=network.target

[Service]
Type=exec
User=pas-assistant
Group=pas-assistant
WorkingDirectory=/opt/pas-assistant
EnvironmentFile=/opt/pas-assistant/.env
ExecStart=/opt/pas-assistant/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 10. Dépendances Python — `requirements.txt`

```
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.6
anthropic>=0.40
openpyxl>=3.1
python-docx>=1.1
msal>=1.26
pyyaml>=6.0
python-dotenv>=1.0
httpx>=0.27
pydantic>=2.5
```

---

## 11. Prompts système

### 11.1 `system_response.txt` — Génération des réponses

```
Tu es un assistant spécialisé dans la rédaction de réponses à des questionnaires
de sécurité (Plans d'Assurance Sécurité / PAS) pour le compte du FOURNISSEUR.

CONTEXTE :
Le FOURNISSEUR est une ESN qui répond à un Appel d'Offres. Le CLIENT demande
au FOURNISSEUR de remplir un questionnaire de sécurité. Chaque réponse
constitue un engagement contractuel.

OBJECTIFS :
1. Rassurer le CLIENT sur la maturité sécurité du FOURNISSEUR.
2. Limiter les engagements au périmètre de la prestation.

CONSIGNES :
- Rappeler systématiquement le périmètre de la prestation dans chaque réponse
  ("sur le périmètre de la prestation", "dans le cadre de la prestation").
- S'appuyer sur les exemples de questionnaires déjà remplis fournis en contexte.
- Ne jamais inventer d'information factuelle (noms de documents, certifications,
  outils) qui ne figure pas dans les exemples fournis.
- Ton professionnel et factuel.
- Respecter la contrainte de nombre de mots par réponse.
- Quand une question n'est pas applicable au périmètre de la prestation,
  répondre "Non applicable sur le périmètre de la prestation" suivi d'une
  justification courte.

FORMAT DE SORTIE :
Retourner un JSON valide avec la structure :
{
  "responses": [
    {"question_id": "...", "response": "..."},
    ...
  ]
}
```

### 11.2 `system_attention.txt` — Points d'attention

```
Tu es un expert sécurité SSI qui analyse un questionnaire de sécurité rempli
pour le compte du FOURNISSEUR. Tu dois identifier les points d'attention
à destination du chef de projet.

CATÉGORIES DE POINTS D'ATTENTION :
- CLAUSE_ENGAGEANTE : exigence qui crée un engagement contractuel fort ou risqué
- DELAI_ANORMAL : SLA ou délai de réponse particulièrement court ou contraignant
- DOCUMENT_MANQUANT : document réclamé par le CLIENT à fournir ou obtenir
- ACTION_A_PLANIFIER : action récurrente ou ponctuelle à mettre en place
- VERIFICATION_INTERNE : vérification à effectuer en interne avant de s'engager
- HORS_PERIMETRE : exigence qui semble hors du périmètre de la prestation

CONSIGNES :
- Être vigilant sur les clauses très engageantes.
- Identifier les délais anormalement courts.
- Repérer les documents que le FOURNISSEUR doit fournir ou réclamer au CLIENT.
- Signaler les actions récurrentes (audits annuels, revues périodiques).
- Alerter sur les exigences potentiellement hors périmètre.

FORMAT DE SORTIE :
{
  "attention_points": [
    {
      "question_id": "...",
      "category": "...",
      "description": "...",
      "recommendation": "..."
    }
  ]
}
```

### 11.3 `system_structure.txt` — Analyse de structure

```
Tu es un assistant qui analyse la structure d'un questionnaire de sécurité.

On te fournit un extrait du contenu du document (les premières lignes ou sections).

Tu dois identifier :
- Pour un fichier xlsx : quels onglets contiennent des questions, quelle colonne
  contient les identifiants, quelle colonne contient les questions/exigences,
  quelle(s) colonne(s) attendent les réponses du fournisseur.
- Pour un fichier docx : quel est le pattern de structure (ex: titre > exigence >
  commentaires > réponse du titulaire), comment identifier les zones de réponse.

FORMAT DE SORTIE :
{
  "format": "xlsx" ou "docx",
  "structure": {
    // Pour xlsx :
    "sheets": [
      {
        "name": "...",
        "has_questions": true/false,
        "id_column": "A" ou null,
        "question_column": "C",
        "response_columns": ["E", "G"],
        "header_row": 3,
        "first_data_row": 5
      }
    ],
    // Pour docx :
    "pattern": "description du pattern",
    "response_marker": "Réponse du titulaire"
  }
}
```

---

## 12. Sécurité

### 12.1 Mesures en place

- **HTTPS** obligatoire (Let's Encrypt, redirection HTTP→HTTPS).
- **Authentification** OAuth2 via Azure AD / TENANT_365.
- **Autorisation** par liste blanche d'utilisateurs (`users.yaml`).
- **Anonymisation** systématique avant envoi à l'API Claude.
- **Fichiers originaux** jamais modifiés (copie de travail).
- **Clé API Anthropic** stockée en variable d'environnement, jamais dans le code.
- **Firewall** (UFW) : seuls les ports 22, 80, 443 ouverts.
- **Secrets** dans `.env`, exclu du versioning (`.gitignore`).

### 12.2 Points de vigilance

- Le serveur DigitalOcean stocke des données potentiellement sensibles (questionnaires anonymisés, corpus). Le disque doit être considéré comme un actif à protéger.
- Les backups du corpus doivent être prévus (snapshot DigitalOcean ou rsync).
- Les logs du backend ne doivent pas contenir de données confidentielles.

---

## 13. Monitoring et logs

### 13.1 Logs applicatifs

- Logs FastAPI vers `/var/log/pas-assistant/app.log`
- Rotation des logs via `logrotate`
- Niveau de log configurable (INFO par défaut)

### 13.2 Health check

- Endpoint `GET /api/health` retourne `{"status": "ok"}` (sans authentification)
- Utilisable pour monitoring externe (UptimeRobot, etc.)

---

## 14. Évolutions futures (hors V1)

- Support PDF éditable
- Interface web avancée (Adaptive Cards, visualisation inline)
- Recherche sémantique dans le corpus (embeddings)
- Multi-utilisateurs simultanés
- Tableau de bord statistiques (nombre de questionnaires traités, temps moyen…)
- Détection automatique de données personnelles (NER) avant envoi API
- Intégration SharePoint pour stockage corpus
