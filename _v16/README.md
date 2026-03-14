# PAS Assistant — v16

## Changements depuis v15

### Problème résolu

En comparant un questionnaire rempli manuellement par un humain avec un questionnaire généré par l'application (cadrage : Assistance Technique, hébergement SI CLIENT, poste CLIENT), on constatait **~40 différences** sur la colonne statut : l'humain mettait `N/A` là où l'application générait une réponse longue marquée "Totalement conforme" ou "Partiellement conforme".

Cause : Claude recevait les valeurs du cadrage brut mais devait seul déduire quelles questions étaient hors périmètre. En pratique il ne tenait pas suffisamment compte de ces règles et répondait aux questions hors scope comme si elles étaient applicables — y compris en citant des politiques internes sans lien avec la prestation réelle.

---

### Solution : exclusions de périmètre explicites

#### 1. `app/services/response_generator.py`

Deux nouvelles fonctions :

**`_detect_na_value(status_choices)`**
Recherche dans les valeurs autorisées du dropdown statut la valeur correspondant à "N/A" (insensible à la casse, couvre "N/A", "Non applicable", "Not applicable", etc.). Retourne la valeur exacte du dropdown ou `None`.

**`build_constraints_block(cadrage, status_choices)`**
Traduit les valeurs du cadrage en déclarations d'exclusion explicites en français naturel, à injecter dans le prompt utilisateur. Couvre les cas suivants :

| Valeur cadrage | Exclusion générée |
|---|---|
| `type_prestation_base = "Assistance Technique"` | Pas de dispositif à engagement, pas de forfait, pas de livraison. Les intervenants travaillent en régie sur le SI CLIENT. |
| `hebergement_donnees = "SI CLIENT"` | FOURNISSEUR n'administre aucun serveur ni infrastructure. Questions hébergement, CMDB, patchs serveur, sauvegardes, logs infra, firewalls, IDS/IPS → hors périmètre. |
| `hebergement_donnees = "Cloud"` | Exclusion partielle : datacenter physique hors périmètre (relève du cloud provider), sécurité applicative et configuration cloud restent applicables. |
| `poste_travail = "CLIENT"` | FOURNISSEUR ne fournit aucun poste. Questions MDM, AV poste, chiffrement disque, durcissement poste → hors périmètre. |
| `sous_traitance_rgpd = "Non"` | Aucun sous-traitant RGPD. Questions gestion contractuelle sous-traitants → hors périmètre. |
| `lieu_travail` sans "Agence FOURNISSEUR" | FOURNISSEUR n'intervient pas depuis ses propres locaux. Questions sécurité physique locaux FOURNISSEUR → hors périmètre. |

La fonction génère également l'instruction de statut adaptée au questionnaire :
- Si une valeur N/A est disponible dans le dropdown → `utiliser "N/A"` (valeur exacte)
- Si un dropdown existe mais sans valeur N/A → `laisser le champ status null`
- Si pas de colonne statut → `commencer la réponse par "Sans objet — ..."`

Cas limite : `pas_niveau_entreprise = "Oui"` désactive toutes les exclusions (toutes les questions sont applicables).

Le bloc généré est injecté dans `_build_user_prompt_responses()` entre le contexte de cadrage et les exemples de référence, sous le titre `=== EXCLUSIONS DE PÉRIMÈTRE ===`.

#### 2. `data/config/prompts/system_response.txt`

Ajout d'une note en tête de la section `RÈGLE D'APPLICABILITÉ` :

> Les exclusions de périmètre spécifiques à cette prestation sont listées dans la section "=== EXCLUSIONS DE PÉRIMÈTRE ===" du message utilisateur (si présente). Ces exclusions sont prioritaires et exhaustives pour les domaines qu'elles couvrent. La présente règle s'applique en complément pour les cas non listés.

---

### Fichiers modifiés

| Fichier | Nature |
|---|---|
| `app/services/response_generator.py` | +2 fonctions, injection dans `_build_user_prompt_responses()` |
| `data/config/prompts/system_response.txt` | +4 lignes dans RÈGLE D'APPLICABILITÉ |

Tous les autres fichiers sont identiques à v15.
