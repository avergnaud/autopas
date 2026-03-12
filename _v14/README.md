# PAS Assistant — v14

## Changements par rapport à v13

### Prompt 29

**1. Mots-clés d'anonymisation fixes**

`Catamania → FOURNISSEUR` et `Cat-Amania → FOURNISSEUR` sont toujours pré-remplis en lecture seule dans la liste des mots-clés à anonymiser, aussi bien côté PAS que côté Corpus. L'utilisateur ne peut pas les supprimer. Il peut toujours ajouter d'autres lignes.

Implémentation :
- `addKwRow(containerId, original, replacement, fixed)` — nouveau paramètre `fixed` : si `true`, les deux champs sont `readonly` et il n'y a pas de bouton de suppression
- `addFixedKeywords(containerId)` — ajoute les deux paires fixes
- Appelé dans `pasLoadAnonSuggestions()` et `corpusLoadAnonSuggestions()` avant le chargement des suggestions

**2. Tags corpus enrichis + logique de pré-sélection Atlassian**

Dans `div.corpus-entry-meta` (liste corpus et sélection de références) :
- Affichage : `type_prestation · Atlassian|Non-Atlassian · poste_travail · N ETP · date`
- `secteur_client` n'est plus affiché

Côté backend (`GET /api/projects/{id}/corpus-selection`) :
- Champs `expertise_atlassian` et `poste_travail` ajoutés dans la réponse
- `secteur_client` retiré de la réponse
- Nouveau champ `project_is_atlassian` (bool) dans la réponse

Logique de pré-sélection des checkboxes :
- Si `project_is_atlassian = true` → cochés uniquement les entrées où `expertise_atlassian = true`
- Si `project_is_atlassian = false` → cochés les entrées avec `score > 0` ET `expertise_atlassian != true`
