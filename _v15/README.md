# PAS Assistant — v15

Évolutions par rapport à la v14.

---

## Prompt 30 — Amélioration UX anonymisation

- **Ligne « → CLIENT » pré-remplie** : dans les deux wizards (PAS et Corpus), une ligne normale (supprimable) `"" → CLIENT` est automatiquement ajoutée après les lignes fixes, avant les suggestions extraites du fichier. L'utilisateur n'a plus qu'à saisir le nom du client dans le champ original.
- **Bouton "Anonymiser →" désactivé tant qu'un champ original est vide** : validation temps réel via écouteurs `input` et `click` sur les conteneurs de lignes. Le bouton redevient actif dès que tous les champs originaux sont remplis. CSS `button:disabled` ajouté dans `style.css`.

## Prompt 31 — Fixes configuration

- **Ordre des remplacements fixes FOURNISSEUR** : les deux entrées `Cat-Amania → FOURNISSEUR` et `Catamania → FOURNISSEUR` sont toujours présentes, non supprimables, dans cet ordre, dans les deux wizards.
- **Suppression de la question "Combien d'ETP"** : retirée de `data/config/questions.txt`.
- **Condition sur la question "connexion à distance"** : la question "Par quel moyen les collaborateurs se connectent à distance au SI CLIENT ?" n'est affichée que si la réponse à "poste de travail" est `FOURNISSEUR` (condition `IF previous: FOURNISSEUR` dans `questions.txt`).

## Prompt 32 — Qualité des réponses Claude

- **Dé-anonymisation "Cat-Amania"** : après le remplacement des mots-clés habituels, une passe supplémentaire remplace toutes les occurrences de `Cat-Amania` (insensible à la casse) par `Catamania`.
- **Règle pentest / hébergement** : ajout dans `system_response.txt` d'un cas particulier — si la question porte sur des pentests du SI FOURNISSEUR et que `hebergement_donnees` vaut `SI CLIENT` ou `Cloud`, Claude répond "Non applicable sur le périmètre de la Prestation".
- **Date du jour injectée dans le prompt** : la date courante est transmise à Claude avec une instruction pour utiliser des formulations relatives ("dans les 12 prochains mois") plutôt que des années absolues.
- **Références aux politiques sécurité plus précises** : le prompt système exige que Claude cite le titre exact de la section et au moins un élément de contenu de `POLITIQUES.md`, sans formulation vague.

## Prompt 33 — Fixes mineurs

- **Question secteur CLIENT** : suppression de l'option "Parapublic" (options restantes : Public, Privé).
- **Formulation pentest améliorée** : la phrase modèle dans `system_response.txt` pour le cas particulier pentest est remplacée par : "Sur le périmètre de la prestation, aucun composant SI n'est hébergé par FOURNISSEUR. Dans ces conditions, des tests d'intrusion sur le SI de FOURNISSEUR ne semblent pas pertinents."

## Prompt 34 — Fix : lignes de titre de catégorie écrasées

- **Problème** : les lignes de séparation de catégorie (titres de section avec cellules fusionnées) étaient incluses comme des questions et leur contenu était écrasé lors de l'écriture des réponses.
- **Cause** : `_write_cell` remontait au coin supérieur gauche d'une plage fusionnée et écrasait le titre.
- **Fix `parser_xlsx.py`** :
  - Nouvelle fonction `_merged_header_rows(ws, col_r_idx)` : détecte les lignes où la colonne réponse est une slave `MergedCell` avec top-left dans une colonne différente.
  - Stratégie deux passes : pass 1 sans `read_only` pour lire les plages fusionnées (puis `del wb`), pass 2 en `read_only=True` pour l'extraction — évite la surconsommation mémoire (>1,5 GB sur le droplet 2 GB).
  - `read_questions` et `write_responses` sautent les lignes détectées comme en-têtes de section.
- **Fix `system_structure.txt`** : ajout d'une note expliquant le concept de lignes de séparation de catégorie.

## Prompt 35 — Règle Assistance Technique dans les réponses

- **Cas particulier AT dans `system_response.txt`** : si `type_prestation_base = "Assistance Technique"`, les questions portant sur "le système d'information délivrant le service", "le dispositif", "le produit livré" ou "le cycle de vie du projet" sont reformulées du point de vue des intervenants humains (obligations, habilitations, sensibilisation, règles de conduite sur le SI CLIENT). Claude ne répond jamais comme si FOURNISSEUR opérait ou possédait le SI délivrant le service en contexte AT.

## Prompt 36 — Upload et anonymisation du contrat

Nouvelle fonctionnalité permettant d'associer un contrat (`.docx`) à un questionnaire dans les deux wizards.

### Wizard "Analyser un nouveau PAS"

- **Champ contrat optionnel** à l'étape Upload, sous le champ questionnaire `.xlsx`.
- Si un contrat est sélectionné, il est uploadé en second appel (`POST /api/projects/{id}/contract`) après la création du projet.
- Les métadonnées PII du contrat sont fusionnées avec celles du questionnaire dans le formulaire d'anonymisation (même passe, même mapping).
- Le contrat est anonymisé automatiquement lors de `POST /api/projects/{id}/anonymize` → `contract_anonymized.docx`.
- Le texte du contrat anonymisé est injecté dans le prompt Claude lors de la génération (section `=== CONTRAT ===`, plafond 50 000 caractères).

### Wizard "Base de connaissances"

- Même champ contrat optionnel à l'étape Upload.
- Même upload séquentiel (`POST /api/corpus/{id}/contract`).
- Même fusion des métadonnées et anonymisation automatique.
- Le contrat anonymisé est persisté dans le dossier corpus (`contract_anonymized.docx`).
- La liste corpus affiche le tag **Contrat** dans la ligne de métadonnées de chaque entrée qui possède un contrat associé.

### Nouveaux endpoints

| Endpoint | Description |
|---|---|
| `POST /api/projects/{id}/contract` | Upload du contrat pour un projet |
| `POST /api/corpus/{id}/contract` | Upload du contrat pour une entrée corpus |
