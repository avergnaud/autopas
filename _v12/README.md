# PAS Assistant — v12

## Prompt 22 — Correction articles FOURNISSEUR/CLIENT (traitements A + B)

### Problème

Après dé-anonymisation, certaines réponses générées par Claude contenaient des
formulations grammaticalement incorrectes : `"le Sun Microsystems"`, `"au Enron"`,
`"du Enron"`. Claude générait correctement `"le FOURNISSEUR"` / `"du CLIENT"`, mais
la dé-anonymisation remplaçait mécaniquement sans corriger le contexte grammatical.

### Traitement A — Prompt engineering

Ajout dans les deux prompts système de consignes explicites pour que Claude n'utilise
pas d'articles définis ni de contractions devant FOURNISSEUR/CLIENT :

- `data/config/prompts/system_response.txt` — section CONSIGNES
- `data/config/prompts/system_attention.txt` — section CONSIGNES

Règles ajoutées :
- FOURNISSEUR et CLIENT sont des placeholders (remplacés plus tard par de vrais noms).
- Noms propres masculins : pas d'article défini ("le", "la") devant eux.
- Écrire "de FOURNISSEUR" (pas "du FOURNISSEUR"), "à CLIENT" (pas "au CLIENT").

### Traitement B — Post-traitement regex (avant dé-anonymisation)

Ajout de la fonction `fix_french_token_articles()` dans `app/services/response_generator.py`.

Applique 4 règles regex dans l'ordre :

| Pattern | Remplacement |
|---|---|
| `au FOURNISSEUR` / `au CLIENT` | `à FOURNISSEUR` / `à CLIENT` |
| `du FOURNISSEUR` / `du CLIENT` | `de FOURNISSEUR` / `de CLIENT` |
| `le FOURNISSEUR` / `le CLIENT` | `FOURNISSEUR` / `CLIENT` |
| `la FOURNISSEUR` / `la CLIENT` | `FOURNISSEUR` / `CLIENT` |

Points d'intégration dans `_do_generation()` :
1. Sur chaque `response` retournée par Claude, **avant** `write_responses` (step 6).
2. Sur `description` et `recommendation` de chaque point d'attention, **avant** la
   dé-anonymisation (step 8).

Ainsi la dé-anonymisation reçoit un texte déjà corrigé et produit un résultat
grammaticalement correct (`"à Enron"`, `"de Sun Microsystems"`, etc.).

## Prompt 26 — Consigne anonymisation : tokens distincts obligatoires

### Règle

Si deux mots-clés différents sont mappés vers le **même token**, la dé-anonymisation
est impossible : le dict inverse ne peut avoir qu'une seule entrée par token, l'une
des deux origines est donc perdue.

**Exemple problématique :**

| Original | Token |
|---|---|
| `Enron Groupe` | `CLIENT` |
| `Enron` | `CLIENT` |

L'anonymisation fonctionne (tri longueur décroissante : `Enron Groupe` remplacé avant
`Enron`), mais lors de la dé-anonymisation tous les `CLIENT` sont restaurés en `Enron`
— les occurrences qui étaient `Enron Groupe` sont perdues.

### Consigne utilisateur

**Chaque original doit avoir un token unique.** Utiliser des tokens distincts :

| Original | Token |
|---|---|
| `Enron Groupe` | `CLIENT_GROUPE` |
| `Enron` | `CLIENT` |

## Prompt 26 (suite) — Verbosité absente du wizard corpus

### Problème

Le wizard "Base de connaissances" posait la question de verbosité à l'utilisateur lors
de l'upload d'un fichier corpus. La verbosité pilote la génération des réponses au
questionnaire — elle n'a pas de sens lors de l'indexation d'un fichier de référence.

### Fix

`web/private.html` — filtrer la question `verbosity` avant de construire le wizard corpus :

```js
questions: qData.questions.filter(q => q.key !== 'verbosity'),
```

La question de verbosité reste présente uniquement dans le wizard de cadrage PAS.
