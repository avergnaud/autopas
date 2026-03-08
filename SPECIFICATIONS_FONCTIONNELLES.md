# Spécifications Fonctionnelles — PAS Assistant

**Version** : 1.0
**Date** : 2026-02-28
**Statut** : Draft

---

## 1. Présentation générale

### 1.1 Contexte

Le FOURNISSEUR (ESN) répond régulièrement à des Appels d'Offres. Dans ce cadre, le CLIENT impose au FOURNISSEUR de remplir un **questionnaire de sécurité** (aussi appelé **Plan d'Assurance Sécurité** ou **PAS**). Ce document contient des exigences de sécurité auxquelles le FOURNISSEUR doit répondre. Chaque réponse constitue un **engagement contractuel**.

Remplir ces questionnaires est une tâche chronophage et répétitive. Les thématiques sont souvent similaires d'un CLIENT à l'autre (politique SSI, gestion des incidents, RGPD, sécurité physique, accès distants…), mais les réponses doivent être contextualisées au périmètre de chaque prestation.

### 1.2 Objectif de l'outil

**PAS Assistant** est un outil d'aide au remplissage de questionnaires de sécurité. Il permet au FOURNISSEUR de :

1. Pré-remplir automatiquement les réponses grâce à un LLM (API Claude), en s'appuyant sur un corpus de questionnaires déjà remplis.
2. Contextualiser les réponses en fonction du périmètre exact de la prestation.
3. Identifier les points d'attention (clauses engageantes, actions à mener, documents manquants).

### 1.3 Double objectif stratégique

Les réponses générées servent deux objectifs :

- **Rassurer le CLIENT** sur les dispositifs de sécurité du FOURNISSEUR.
- **Limiter les engagements** en rappelant systématiquement le périmètre de la prestation et en évitant de s'engager sur des sujets hors scope.

### 1.4 Utilisateurs cibles

- Le RSSI du FOURNISSEUR.
- Les chefs de projet et responsables avant-vente.
- Accès restreint à une liste d'utilisateurs définie en configuration.

---

## 2. Périmètre V1

### 2.1 Inclus dans la V1

- Formats d'entrée : `.xlsx` uniquement (wizard "Analyser un nouveau PAS")
- Interface web basique sur `appsec.cc`
- Questions de cadrage configurables (fichier texte)
- Anonymisation par rechercher/remplacer (mots-clés fournis par l'utilisateur)
- 3 niveaux de verbosité
- Points d'attention automatiques
- Stockage fichier sur le filesystem du serveur
- Boucle de correction (ré-import du document corrigé)
- Base de connaissances avec métadonnées JSON

### 2.2 Hors V1

- Format `.doc` (sera converti en `.docx` par l'utilisateur en amont)
- Format `.pdf` éditable
- Exploitation des autres documents de l'Appel d'Offres (CCTP, PSSI CLIENT…)
- Multi-utilisateurs simultanés sur un même questionnaire
- Fine-tuning / RAG évolutif

---

## 3. Glossaire

| Terme | Définition |
|---|---|
| PAS | Plan d'Assurance Sécurité. Questionnaire sécurité imposé par le CLIENT |
| FOURNISSEUR | L'ESN qui répond à l'Appel d'Offres |
| CLIENT | L'organisation qui émet l'Appel d'Offres |
| Questionnaire | Document contenant les exigences sécurité et les réponses du FOURNISSEUR |
| Base de connaissances | Corpus de ~20 questionnaires déjà remplis et anonymisés |
| Questions de cadrage | Série de questions posées à l'utilisateur pour définir le contexte de la prestation |
| Points d'attention | Alertes à destination du chef de projet (clauses engageantes, actions…) |
| AT | Assistance Technique |
| CDR / CDC / CDS | Centre de Ressources / Centre de Compétences / Centre de Services |
| ETP | Équivalent Temps Plein |

---

## 4. Acteurs et rôles

| Acteur | Rôle |
|---|---|
| Utilisateur | Uploade le questionnaire, répond aux questions de cadrage, corrige les réponses, valide le document final |
| PAS Assistant (Backend) | Orchestre le workflow : parsing, anonymisation, appel API Claude, génération des points d'attention, dé-anonymisation |
| API Claude | Génère les réponses aux questions du questionnaire |
| Interface Web | Interface web (upload, cadrage, téléchargement du résultat) |
| Administrateur | Configure les questions de cadrage, gère la base de connaissances, gère la liste des utilisateurs autorisés |

---

## 5. Workflow principal

### 5.1 Vue d'ensemble

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│  Utilisateur │────▶│  Interface  │────▶│   Backend       │
│              │◀────│  Web        │◀────│   (FastAPI)     │
└─────────────┘     └─────────────┘     │                 │
                                         │  ┌───────────┐  │
                                         │  │ Parsing   │  │
                                         │  │ Anonymis. │  │
                                         │  │ API Claude│  │
                                         │  │ Points    │  │
                                         │  │ d'attent. │  │
                                         │  └───────────┘  │
                                         │                 │
                                         │  ┌───────────┐  │
                                         │  │ Filesystem│  │
                                         │  │ (corpus,  │  │
                                         │  │ config,   │  │
                                         │  │ projets)  │  │
                                         │  └───────────┘  │
                                         └─────────────────┘
```

### 5.2 Workflow détaillé — étape par étape

```
 UTILISATEUR                          OUTIL (Backend)
     │                                     │
     │  1. Upload questionnaire             │
     │────────────────────────────────────▶│
     │                                     │  2. Détection format (xlsx/docx)
     │                                     │  3. Extraction structure
     │                                     │     (questions, colonnes, onglets)
     │  4. Questions de cadrage            │
     │◀────────────────────────────────────│
     │                                     │
     │  5. Réponses de cadrage             │
     │────────────────────────────────────▶│
     │                                     │
     │  6. Demande mots à anonymiser       │
     │◀────────────────────────────────────│
     │                                     │
     │  7. Liste mots-clés à anonymiser    │
     │────────────────────────────────────▶│
     │                                     │  8. Création copie de travail
     │                                     │  9. Anonymisation (rechercher/remplacer)
     │                                     │ 10. Sélection fichiers de référence
     │                                     │     (corpus similaire)
     │                                     │ 11. Appel API Claude
     │  "Traitement en cours..."           │     (questionnaire + contexte + corpus)
     │◀────────────────────────────────────│
     │                                     │ 12. Insertion réponses dans copie
     │                                     │ 13. Appel API Claude séparé
     │                                     │     (génération points d'attention)
     │                                     │ 14. Dé-anonymisation du document
     │  15. Document rempli + points       │
     │◀────────────────────────────────────│
     │                                     │
     │  === BOUCLE OPTIONNELLE ===         │
     │                                     │
     │  16. Correction document (externe)  │
     │  17. Ré-upload document corrigé     │
     │────────────────────────────────────▶│
     │                                     │ 18. Détection des différences
     │                                     │ 19. Persistance corrections
     │                                     │     (ajout au corpus)
     │  20. Confirmation                   │
     │◀────────────────────────────────────│
```

---

## 6. Fonctionnalités détaillées

### 6.1 Upload et parsing du questionnaire

**F-PARSE-01 — Format d'entrée**
Le wizard "Analyser un nouveau PAS" accepte uniquement les fichiers `.xlsx`. Le format `.docx` est supporté pour le corpus (wizard "Base de connaissances").

**F-PARSE-02 — Extraction de la structure (xlsx)**
Pour les fichiers `.xlsx` :
- L'outil liste les onglets disponibles.
- Pour chaque onglet, l'outil identifie les colonnes qui contiennent :
  - Les identifiants de question (ex: "Req. Nr.", "ID")
  - Les exigences / questions
  - Les colonnes de réponse à remplir
  - La colonne de statut (liste déroulante : Oui, Non, Partiel, NA…) si présente
  - La ligne d'en-tête et la première ligne de données
- La structure des fichiers `.xlsx` varie d'un CLIENT à l'autre. L'outil utilise l'API Claude pour analyser la structure et identifier les colonnes pertinentes.
- **La détection de structure s'effectue impérativement sur le fichier anonymisé**, jamais sur le fichier original, afin de ne transmettre aucune donnée confidentielle à l'API Claude (R-02).
- L'utilisateur valide ou corrige la structure détectée avant de continuer.

**F-PARSE-03 — Extraction de la structure (docx)**
Pour les fichiers `.docx` :
- L'outil identifie les sections qui contiennent des exigences et des zones de réponse.
- Le pattern typique est : Exigence → Commentaires/preuves attendues → Réponse du titulaire.
- La structure varie d'un CLIENT à l'autre. L'outil doit utiliser l'API Claude pour analyser la structure.

**F-PARSE-04 — Copie de travail**
L'outil crée systématiquement une copie de travail du document uploadé. Le document d'origine n'est JAMAIS modifié.

### 6.2 Questions de cadrage

**F-CADRAGE-01 — Liste configurable**
Les questions de cadrage sont stockées dans un fichier texte sur le serveur, éditable par l'administrateur sans modifier le code. Le format du fichier est défini dans les spécifications techniques.

**F-CADRAGE-02 — Questions initiales (liste par défaut)**
Voici la liste par défaut des questions de cadrage :

0. *(Spécial)* S'agit-il d'un PAS niveau entreprise (questions générales) ? *(voir F-CADRAGE-05)*
1. Est-ce que l'Appel d'Offre porte sur de l'Assistance Technique ou un dispositif à engagement ?
2. Si l'Appel d'Offre porte sur un dispositif à engagement, est-ce un CDR, CDC, CDS ?
3. Combien d'Equivalents Temps Plein sont mobilisés au début de la Prestation ?
4. Est-ce que la Prestation inclut des activités de développement, ou plutôt de l'analyse métier, du test, de la configuration ?
5. Est-ce que la Prestation fait partie du centre d'expertise Atlassian ?
6. Sur le périmètre de la Prestation, est-ce que les données CLIENT seront hébergées par le SI du CLIENT, par FOURNISSEUR, ou par une solution Cloud ?
6b. *(Conditionnel)* Si Cloud : quel est le nom du fournisseur Cloud ?
7. Est-ce que le FOURNISSEUR est sous-traitant pour au-moins un traitement de données personnelles au sens RGPD ?
8. Est-ce que les collaborateurs travailleront sur site CLIENT, en agence FOURNISSEUR, en télétravail ?
9. Si les collaborateurs travaillent en agence FOURNISSEUR, depuis quelles agences exactement ?
10. Est-ce que les collaborateurs utilisent des postes de travail CLIENT ou FOURNISSEUR ?
11. Par quel moyen les collaborateurs se connectent à distance au SI CLIENT ? (VPN fourni par le CLIENT, configuration flux réseau DSI FOURNISSEUR depuis les agences ?)
12. Quel est le secteur du CLIENT ? (Public, Parapublic, Privé)

**F-CADRAGE-03 — Questions conditionnelles**
Certaines questions ne sont posées que si une réponse précédente le justifie. Exemple : la question 2 n'est posée que si la réponse à la question 1 est "dispositif à engagement". Ce mécanisme de conditions est configurable dans le fichier `questions.txt` via la directive `IF previous == "X"` ou `IF previous contains "X"`. La directive `DEFAULT:` permet de pré-sélectionner une valeur par défaut à l'affichage.

**F-CADRAGE-05 — Cas spécial : PAS niveau entreprise**
Certains questionnaires sont des "PAS niveau entreprise" (questions générales sur la politique de sécurité du FOURNISSEUR, sans lien avec une prestation spécifique). Pour ce type, les questions de cadrage relatives à la prestation (ETP, lieu de travail, connexion distante…) ne sont pas pertinentes.

La première question du wizard est un interrupteur "PAS niveau entreprise (questions générales)" avec la valeur "Non" pré-sélectionnée par défaut. Si l'utilisateur sélectionne "Oui", toutes les questions suivantes sont ignorées et le wizard se termine immédiatement. Ce comportement est configuré via la directive `SKIP_ALL_IF: Oui` dans `questions.txt`.

**F-CADRAGE-04 — Interaction wizard**
Les questions sont posées une par une dans l'interface web (wizard). L'utilisateur répond via le contrôle adapté au type de question (radio, checkbox, champ texte, champ numérique). Voir F-WEB-05 pour le détail UX.

### 6.3 Anonymisation

**F-ANON-01 — Mots-clés à anonymiser**
L'outil demande à l'utilisateur la liste des mots-clés à anonymiser. Exemple typique :
- Nom du CLIENT réel → "CLIENT"
- Nom du marché → "MARCHE"
- Noms de personnes → "NOM_PERSONNE_1", "NOM_PERSONNE_2"…

**F-ANON-02 — Rechercher/remplacer**
L'anonymisation s'effectue par un simple rechercher/remplacer sur l'ensemble du contenu textuel du document. Le remplacement est insensible à la casse.

**F-ANON-03 — Périmètre d'anonymisation**
L'anonymisation s'applique :
- Au questionnaire en cours de traitement (avant envoi à l'API Claude).
- Aux réponses pré-remplies éventuellement présentes dans le document.
- Aux fichiers ajoutés à la base de connaissances via le wizard d'alimentation du corpus (voir section 6.10) : chaque fichier est anonymisé dans l'outil avant d'être stocké définitivement.

**F-ANON-04 — Table de correspondance**
L'outil persiste la table de correspondance (mot réel → mot anonymisé) pour chaque projet, afin de pouvoir dé-anonymiser le document en sortie.

**F-ANON-05 — Dé-anonymisation**
En fin de traitement, l'outil effectue le remplacement inverse (mot anonymisé → mot réel) pour produire le document final.

### 6.4 Sélection des fichiers de référence

**F-REF-01 — Base de connaissances**
La base de connaissances est un ensemble de questionnaires déjà remplis et anonymisés, stockés sur le filesystem du serveur. Chaque fichier est accompagné d'un fichier JSON de métadonnées.

**F-REF-02 — Métadonnées**
Les métadonnées de chaque document de référence décrivent le contexte de la prestation correspondante.

Champs **toujours présents** :
- PAS niveau entreprise (booléen)
- Type de prestation (AT, CDR, CDC, CDS, Entreprise)
- Activités (développement, analyse, test, configuration…)
- Secteur CLIENT (public, parapublic, privé)
- Format du questionnaire (xlsx, docx)
- Date de remplissage
- Tags libres (indexation complémentaire)

Champs présents **uniquement si `pas_niveau_entreprise` est faux** (non pertinents pour un PAS niveau entreprise, exclus pour ne pas polluer la recherche par similarité) :
- Nombre d'ETP
- Expertise Atlassian (oui/non)
- Hébergement des données (SI CLIENT, FOURNISSEUR, Cloud)
- Fournisseur Cloud (si applicable)
- Sous-traitance RGPD (oui/non)
- Lieu de travail (site CLIENT, agence FOURNISSEUR, télétravail)
- Agences concernées
- Type de poste de travail (CLIENT, FOURNISSEUR)
- Mode de connexion distante

Champ technique :
- Structure du questionnaire (onglet, colonnes, lignes — voir F-PARSE-02)

**F-REF-03 — Sélection automatique**
L'outil sélectionne les fichiers de référence les plus similaires au contexte courant, en comparant les réponses de cadrage de l'utilisateur avec les métadonnées des fichiers de référence. L'algorithme de similarité compare les métadonnées champ par champ et produit un score de pertinence.

**F-REF-04 — Nombre de fichiers sélectionnés**
L'outil sélectionne les 2 à 3 fichiers les plus pertinents pour les envoyer en exemple à l'API Claude. Ce nombre doit être configurable.

### 6.5 Appel à l'API Claude — Génération des réponses

**F-API-01 — Envoi global**
Le questionnaire est envoyé dans son intégralité à l'API Claude, en un seul appel. L'appel inclut :
- Le contenu anonymisé du questionnaire (questions + structure).
- Le contexte de cadrage (réponses de l'utilisateur).
- Les fichiers de référence sélectionnés (questionnaires similaires déjà remplis).
- Le niveau de verbosité.
- Les consignes de rédaction (double objectif : rassurer le CLIENT, limiter les engagements).

**F-API-02 — Niveau de verbosité**
Trois niveaux configurables :

| Niveau | Libellé | Contrainte |
|---|---|---|
| 1 | Concis | 50 mots maximum par réponse |
| 2 | Standard | 100 mots maximum par réponse |
| 3 | Détaillé | 150 mots maximum par réponse |

Le niveau par défaut est 2. L'utilisateur choisit le niveau au moment des questions de cadrage.

**F-API-03 — Modèle configurable**
Le modèle Claude utilisé (Sonnet, Opus, Haiku…) est configurable dans un fichier de configuration sur le serveur.

**F-API-04 — Consignes au LLM**
Le prompt système envoyé à l'API Claude inclut les directives suivantes :
- Répondre en tant que FOURNISSEUR (ESN) à un questionnaire de sécurité CLIENT.
- S'appuyer sur les exemples de questionnaires déjà remplis fournis en contexte.
- Adapter les réponses au contexte de la prestation (cadrage).
- Respecter la contrainte de verbosité.
- Objectif 1 : Rassurer le CLIENT sur la maturité sécurité du FOURNISSEUR.
- Objectif 2 : Limiter les engagements au périmètre de la prestation. Rappeler systématiquement "sur le périmètre de la prestation" ou équivalent.
- Ne jamais inventer d'information factuelle (noms de documents, certifications, outils).
- Conserver un ton professionnel et factuel.

### 6.6 Appel à l'API Claude — Points d'attention

**F-ATTENTION-01 — Appel séparé**
Les points d'attention sont générés par un appel API séparé du remplissage des réponses.

**F-ATTENTION-02 — Catégories de points d'attention**
L'outil doit identifier les types suivants :
- **Clause engageante** : exigence qui crée un engagement contractuel fort ou risqué.
- **Délai anormal** : SLA ou délai de réponse particulièrement court ou contraignant.
- **Document manquant** : document réclamé par le CLIENT que le FOURNISSEUR doit fournir ou obtenir.
- **Action à planifier** : action récurrente ou ponctuelle à mettre en place (audit annuel, revue périodique…).
- **Vérification interne** : vérification que l'équipe projet doit effectuer en interne avant de s'engager.
- **Hors périmètre** : exigence qui semble hors du périmètre de la prestation.

**F-ATTENTION-03 — Format de sortie**
Chaque point d'attention inclut :
- La référence de la question concernée (ID ou numéro).
- La catégorie du point d'attention.
- Une description courte du point d'attention.
- Une recommandation d'action.

### 6.7 Document de sortie

**F-SORTIE-01 — Document rempli**
L'outil produit une copie du questionnaire avec les réponses pré-remplies par l'API Claude, au même format que l'entrée (xlsx ou docx).

**F-SORTIE-02 — Fidélité au format**
Le document de sortie doit conserver la structure d'origine (onglets, colonnes, mise en forme). Des différences mineures de mise en forme sont acceptables. L'utilisateur pourra copier-coller les réponses dans le document d'origine si nécessaire.

**F-SORTIE-03 — Points d'attention**
Les points d'attention sont fournis séparément, soit dans un onglet/section dédié du document, soit dans un fichier texte/markdown annexe.

**F-SORTIE-04 — Livraison**
Le document rempli et les points d'attention sont téléchargeables via l'interface web.

### 6.8 Boucle de correction

**F-CORRECTION-01 — Ré-import**
L'utilisateur peut modifier le document de sortie en dehors de l'outil (dans Excel ou Word), puis le ré-uploader via l'interface web. Cette étape est optionnelle.

**F-CORRECTION-02 — Détection des différences**
L'outil compare le document ré-importé avec la version qu'il avait générée, et identifie les réponses modifiées par l'utilisateur.

**F-CORRECTION-03 — Persistance des corrections**
Les corrections détectées sont persistées. Le document corrigé est ajouté à la base de connaissances (corpus de référence), avec ses métadonnées, pour améliorer les réponses futures.

**F-CORRECTION-04 — Ajout volontaire au corpus**
L'ajout au corpus de référence est automatique après correction. L'utilisateur peut aussi ajouter un questionnaire terminé au corpus sans passer par la boucle de correction.

### 6.9 Interface Web

**F-WEB-01 — Interface à deux onglets**
L'interface web sur `appsec.cc` propose deux onglets distincts :
- **"Analyser un nouveau PAS"** — wizard de traitement d'un nouveau questionnaire
- **"Base de connaissances"** — wizard d'alimentation du corpus (voir section 6.10)

**Étapes du wizard "Analyser un nouveau PAS" :**

| # | Étape | Déclencheur backend |
|---|---|---|
| 1 | **Upload** — Déposer le fichier questionnaire (.xlsx) | `POST /api/projects` |
| 2 | **Anonymisation** — Saisir les paires mot réel → alias | `POST /api/projects/{id}/anonymize` |
| 3 | **Structure** — Confirmer la structure détectée par Claude sur le fichier anonymisé | `POST /api/projects/{id}/detect-structure` + `POST /api/projects/{id}/structure` |
| 4 | **Cadrage** — Répondre aux questions de cadrage une par une | *(à venir)* |
| 5 | **Génération** — Traitement en cours (polling) + téléchargement du résultat | `POST /api/projects/{id}/generate` + polling `GET /api/projects/{id}/status` |

> **Note** : L'anonymisation précède la détection de structure afin de ne jamais transmettre de données confidentielles à l'API Claude (R-02).

**F-WEB-02 — Authentification**
L'accès est protégé par SSO via le tenant M365 du FOURNISSEUR (OAuth2).

**F-WEB-03 — Étape Upload**
- Zone de dépôt (drag & drop) acceptant .xlsx, taille max 50 Mo.
- Un bouton "Parcourir" en complément.
- Affichage du nom du fichier sélectionné avant envoi.
- Bouton "Envoyer" — déclenche la création du projet et l'analyse de structure par Claude.
- Indicateur de chargement pendant l'analyse de structure.

**F-WEB-04 — Étape Structure (confirmation)**
- La détection de structure est lancée automatiquement sur le fichier anonymisé après l'étape d'anonymisation.
- Un indicateur de chargement est affiché pendant l'appel à l'API Claude.
- Le résultat est affiché sous forme de formulaire éditable :
  - Pour xlsx : onglet principal (sélecteur parmi tous les onglets), ligne d'en-tête, première ligne de données, colonne ID question, colonne question/exigence, colonne réponse, colonne statut (optionnel).
  - Un badge indique le niveau de confiance de Claude (élevée / moyenne / faible).
- L'utilisateur peut corriger les champs incorrects avant de confirmer.
- Si la détection automatique est indisponible (clé API absente, erreur réseau), le formulaire s'affiche vide pour saisie manuelle.

**F-WEB-05 — Étape Cadrage (wizard question par question)**
- Les questions sont chargées depuis le backend (`GET /api/questions`).
- Une seule question est affichée à la fois avec un numéro de progression (ex: "Question 3 / ~12").
- Rendu du champ selon le type déclaré dans `questions.txt` :
  - `OPTIONS` (simple) : boutons radio.
  - `OPTIONS` + `MULTI: true` : cases à cocher.
  - `TYPE: number` : champ numérique.
  - `TYPE: text` (défaut) : champ texte libre.
  - `DEFAULT: X` : valeur pré-sélectionnée à l'affichage.
- Les questions conditionnelles (`IF previous == "X"` ou `IF previous contains "X"`) sont évaluées côté client.
- La directive `SKIP_ALL_IF: X` sur une question court-circuite toutes les questions restantes si la réponse correspond (ex: PAS niveau entreprise).
- Le niveau de verbosité (1/2/3) est posé comme dernière question de cadrage.
- Boutons "Précédent" et "Suivant". Sur la dernière question : bouton "Valider le cadrage".
- **Ce composant wizard est partagé** entre l'onglet PAS (cadrage) et l'onglet Base de connaissances (indexation du corpus).

**F-WEB-06 — Étape Anonymisation**
- Tableau de paires : colonne "Mot réel" / colonne "Alias anonymisé".
- Alias anonymisés préremplis avec des suggestions (CLIENT, MARCHE, PERSONNE_1…).
- Bouton "Ajouter une ligne" pour ajouter une nouvelle paire.
- Bouton "✕" sur chaque ligne pour la supprimer.
- Cette étape est **obligatoire** : au moins un mot-clé doit être fourni avant de continuer.
- Bouton "Anonymiser et continuer" déclenche l'anonymisation.

**F-WEB-07 — Étape Génération (traitement en cours)**
- Message "Traitement en cours…" avec un indicateur de progression animé.
- Détail des étapes affichées au fur et à mesure : "Anonymisation…", "Sélection des références…", "Génération des réponses…", "Points d'attention…", "Finalisation…".
- Le frontend interroge `GET /api/projects/{id}/status` toutes les 3 secondes (polling).
- Quand `status == "completed"` :
  - Afficher un message de succès.
  - Bouton de téléchargement du document rempli.
  - Bouton de téléchargement des points d'attention (fichier Markdown).
  - Bouton optionnel "Ré-importer un document corrigé" (boucle de correction).

**F-WEB-08 — Gestion des erreurs**
- Si une étape échoue (parse error, API Claude indisponible…), afficher un message d'erreur clair et un bouton "Réessayer".
- Le projet reste dans son état intermédiaire sur le serveur : l'utilisateur peut reprendre depuis l'étape en cours.

**F-WEB-09 — Reprise d'un projet existant**
- La page privée liste les projets de l'utilisateur avec leur statut et leur date.
- Un clic sur un projet en cours reprend le wizard à l'étape correspondante au statut actuel du projet.

### 6.10 Alimentation de la base de connaissances

**F-CORPUS-01 — Wizard d'ajout au corpus**
L'interface web propose un onglet dédié "Base de connaissances" permettant d'ajouter un questionnaire déjà rempli au corpus de référence. L'ajout suit un wizard en 5 étapes :

| # | Étape | Déclencheur backend |
|---|---|---|
| 1 | **Upload** — Déposer le fichier déjà rempli (.xlsx ou .docx) | `POST /api/corpus` |
| 2 | **Cadrage** — Wizard de questions (même composant que le cadrage PAS) | client-side |
| 3 | **Anonymisation** — Saisir les paires mot réel → alias | `POST /api/corpus/{id}/anonymize` |
| 4 | **Structure** — Confirmation de la structure détectée par Claude (xlsx uniquement) | `POST /api/corpus/{id}/detect-structure` + `POST /api/corpus/{id}/structure` |
| 5 | **Informations** — Date de remplissage + tags libres | `POST /api/corpus/{id}/metadata` |

**F-CORPUS-02 — Wizard de cadrage partagé**
Le wizard de questions de cadrage (F-CADRAGE-04) est le même composant réutilisé dans les deux contextes : analyse d'un nouveau PAS et ajout au corpus. Les réponses sont stockées comme métadonnées du fichier corpus.

**F-CORPUS-03 — Anonymisation obligatoire**
L'anonymisation est obligatoire avant tout stockage d'un fichier dans le corpus. Elle est réalisée par l'outil pendant le wizard (étape 3). Le fichier `anonymized.{ext}` est le seul fichier utilisé pour la détection de structure et comme référence LLM. Le fichier `original.{ext}` est conservé mais jamais transmis à l'API Claude.

**F-CORPUS-04 — Détection de structure du corpus**
Pour les fichiers `.xlsx`, la structure est détectée automatiquement via l'API Claude sur le fichier anonymisé, puis proposée à la confirmation de l'utilisateur. Pour les fichiers `.docx`, cette étape est ignorée (la structure textuelle est interprétée directement par le LLM).

**F-CORPUS-05 — Gestion du corpus**
L'onglet "Base de connaissances" affiche la liste des entrées du corpus avec leurs métadonnées principales (nom, type de prestation, secteur, ETP, date). L'utilisateur peut supprimer une entrée. La liste est mise à jour en temps réel.

**F-CORPUS-06 — Arborescence filesystem**
Chaque entrée corpus est stockée dans un répertoire dédié :
```
data/corpus/{uuid}/
  original.{ext}         ← fichier original (conservé, jamais transmis à Claude)
  anonymized.{ext}       ← fichier anonymisé (utilisé comme référence LLM)
  anonymized_map.json    ← table de correspondance original → alias
  structure.json         ← structure détectée et confirmée (xlsx uniquement)
  metadata.json          ← métadonnées complètes (cadrage + date + tags)
```

### 6.11 Administration

**F-ADMIN-01 — Questions de cadrage**
Les questions de cadrage sont éditables dans un fichier texte sur le serveur.

**F-ADMIN-02 — Base de connaissances**
L'administrateur peut ajouter, supprimer et modifier les métadonnées des fichiers de référence.

**F-ADMIN-03 — Liste des utilisateurs**
La liste des utilisateurs autorisés est définie dans un fichier de configuration sur le serveur.

**F-ADMIN-04 — Configuration générale**
Un fichier de configuration permet de régler :
- Le modèle Claude (Sonnet, Opus, Haiku…)
- La clé API Anthropic
- Le niveau de verbosité par défaut
- Le nombre de fichiers de référence à sélectionner
- Les seuils de verbosité (nombre de mots par niveau)

---

## 7. Règles métier

**R-01** — Le document d'origine ne doit JAMAIS être modifié. Toute opération se fait sur une copie de travail.

**R-02** — Aucune information confidentielle ou donnée personnelle ne doit être envoyée à l'API Claude. L'anonymisation est obligatoire avant tout appel API.

**R-03** — Les réponses générées doivent systématiquement rappeler le périmètre de la prestation ("sur le périmètre de la prestation", "dans le cadre de la prestation").

**R-04** — L'outil ne doit jamais inventer de fait (nom de document, certification, outil) qui n'existe pas dans le corpus de référence.

**R-05** — Un seul utilisateur peut travailler sur un même questionnaire à la fois.

**R-06** — L'ensemble de la configuration (questions de cadrage, utilisateurs autorisés, paramètres) est stocké dans des fichiers sur le filesystem, sans base de données.

---

## 8. Exigences non fonctionnelles

**ENF-01 — Temps de traitement**
Le traitement d'un questionnaire complet (parsing + anonymisation + appel API + points d'attention + dé-anonymisation) doit s'exécuter en moins de 5 minutes pour un questionnaire de 100 questions. Un message "Traitement en cours…" est affiché pendant le traitement.

**ENF-02 — Sécurité**
- Authentification OAuth2 via le tenant M365 du FOURNISSEUR.
- HTTPS obligatoire (Let's Encrypt).
- Liste blanche d'utilisateurs autorisés.
- Pas de stockage de mots de passe.

**ENF-03 — Disponibilité**
L'outil est hébergé sur un serveur DigitalOcean. Pas d'exigence de haute disponibilité pour la V1.

**ENF-04 — Maintenabilité**
- Infrastructure as Code (Ansible).
- Code Python avec FastAPI.
- Configuration externalisée (fichiers YAML/JSON).
- Pas de base de données (filesystem uniquement).

---

## 9. Annexes

### 9.1 Exemples de structures de questionnaires

**Structure xlsx type 1 — "Security Requirements" (international)**

| Colonne | Contenu |
|---|---|
| A | Req. Nr. (ex: IS-AS-0001) |
| B | Security Objective |
| C | Requirement (l'exigence) |
| D | Relevant Objects |
| E | Vendor's Response (**à remplir**) |

**Structure xlsx type 2 — "Questionnaire SSI-AVE" (multi-onglets)**

Onglet "3 - Questionnaire" :

| Colonne | Contenu |
|---|---|
| A | Chapitre |
| B | ID (ex: LEG1, CAG9) |
| C | Exigence |
| D | Question |
| E | Réponse (**à remplir**) |
| F | Justifications |
| G | Commentaires (**à remplir**) |

Onglets "4 - SLA Vulnérabilité" et "5 - SLA Incident de sécurité" : grilles de SLA spécifiques.

**Structure docx type — "PAS" (secteur public)**

Pour chaque exigence, un bloc :
1. Titre de section (ex: "Responsabilités et rôles sécurité")
2. Encadré **Exigence** (texte de l'exigence)
3. Encadré **Commentaires et exemple de preuves attendues**
4. Encadré **Réponse du titulaire** (**à remplir**)

### 9.2 Exemple de points d'attention (sortie)

```
Points d'attention — Questionnaire SSI-AVE CLIENT

1. [CLAUSE ENGAGEANTE] CAG10 — L'exigence impose un engagement ferme
   sur les délais de correction des vulnérabilités critiques.
   → Recommandation : Vérifier la faisabilité avec la DSI FOURNISSEUR
   avant de s'engager.

2. [DELAI ANORMAL] COR2 — Les SLA incident de sécurité (onglet 5)
   imposent des délais de notification extrêmement courts (1h).
   → Recommandation : Négocier des délais réalistes ou préciser
   "sur les heures ouvrées".

3. [DOCUMENT MANQUANT] COR4 — L'exigence requiert un NDA signé
   par chaque collaborateur.
   → Recommandation : Réclamer le modèle NDA au CLIENT et planifier
   la signature.

4. [ACTION A PLANIFIER] CAG9 — Audit de sécurité annuel à programmer.
   → Recommandation : Inscrire dans le plan de charge du dispositif.

5. [VERIFICATION INTERNE] COR9 — L'exigence impose des vérifications
   de casier judiciaire.
   → Recommandation : Vérifier la faisabilité juridique et RH
   en interne.
```

### 9.3 Exemple de fichier de métadonnées (base de connaissances)

```json
{
  "filename": "FOURNISSEUR_Security_Requirements_20240220_01.xlsx",
  "format": "xlsx",
  "pas_niveau_entreprise": false,
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
