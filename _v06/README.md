# PAS Assistant — v06

## Objectif de cette itération

Implémenter le wizard d'anonymisation (étape 1) : définition des mots-clés et suppression des métadonnées du fichier xlsx avant envoi à Claude.

## Fonctionnalités

### Wizard en 3 étapes

1. **Upload** — envoi du fichier `.xlsx`, création de `original.xlsx` et `working.xlsx`
2. **Mots-clés** — extraction automatique des métadonnées (auteur, société, titre…) proposées comme suggestions pre-cochées + saisie de mots-clés supplémentaires
3. **Résultat** — table de correspondance (`keyword → [CONFIDENTIEL_N]`) + téléchargement de `anonymized.xlsx`

### Anonymisation

- Remplacement des mots-clés dans **toutes les cellules** de tous les onglets
- Tri par longueur décroissante pour éviter les remplacements partiels
- Suppression des métadonnées PII :
  - `docProps/core.xml` : creator, lastModifiedBy, title, subject, description, keywords (via openpyxl `core_properties`)
  - `docProps/app.xml` : Company, Application (via patch ZIP direct)
- Préservation des named ranges locaux (dropdowns Excel) — même technique que le roundtrip v05
- Sauvegarde du mapping dans `anonymized_map.json` pour la dé-anonymisation future

## Arborescence

```
_v06/
├── app/
│   ├── api/web.py              # 7 endpoints REST (upload, working, roundtrip, metadata, anonymize, anonymized)
│   ├── auth/                   # OAuth2 Azure AD (inchangé)
│   ├── services/
│   │   └── anonymizer.py       # extract_metadata(), anonymize_xlsx(), safe_local_defined_names()
│   ├── config.py
│   └── main.py
├── web/
│   ├── private.html            # Wizard 3 étapes (inline JS)
│   ├── style.css
│   └── index.html
├── data/
│   ├── config/
│   └── projects/               # {project_id}/original.xlsx, working.xlsx, anonymized.xlsx, anonymized_map.json
└── requirements.txt
```

## Lancer en développement

```bash
cd _v06
source venv/bin/activate
SESSION_HTTPS_ONLY=false uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints

| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/api/upload` | Upload xlsx → crée original.xlsx + working.xlsx |
| GET | `/api/projects/{id}/working` | Télécharger working.xlsx |
| POST | `/api/projects/{id}/roundtrip` | Test openpyxl round-trip |
| GET | `/api/projects/{id}/roundtrip` | Télécharger roundtrip.xlsx |
| GET | `/api/projects/{id}/metadata` | Extraire métadonnées → suggestions |
| POST | `/api/projects/{id}/anonymize` | Anonymiser → anonymized.xlsx + map |
| GET | `/api/projects/{id}/anonymized` | Télécharger anonymized.xlsx |

---

Pour utiliser le bon venv :
```
deactivate
source /root/dev/autopas/_v06/venv/bin/activate
PAS_BASE_DIR=. uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```