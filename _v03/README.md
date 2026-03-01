# Note sécurité

[https://login.microsoftonline.com/catamania.com/.well-known/openid-configuration](https://login.microsoftonline.com/catamania.com/.well-known/openid-configuration)

Les informations suivantes sont publiques :
* relation catamania.com et le tenant_id
* tenant_id

L'information suivante n'est pas considérée comme un secret dans la spécification OAuth 2.0 (RFC 6749) :
* client_id. Pour les clients confidentiels (côté serveur), le client_id seul est inexploitable sans le secret..

# `.env` files

Trois fichiers interviennent dans la gestion des variables d'environnement :

| Fichier | Rôle | Commité ? |
|---|---|---|
| `_v03/.env.example` | Documentation — liste les variables attendues, avec des valeurs fictives | Oui (normal) |
| `_v03/ansible/templates/.env.j2` | Template Jinja2 — génère le vrai `.env` sur le serveur en injectant les secrets depuis `vault.yml` | Oui (normal) |
| `/opt/pas-assistant/.env` | Fichier réel sur le serveur, produit par Ansible à partir du template | **Non** (jamais commité) |

Le flux de déploiement est le suivant :

```
vault.yml  (secrets chiffrés, commités)
    ↓  ansible-vault déchiffre
.env.j2    (template Jinja2, commité)
    ↓  ansible task: template
/opt/pas-assistant/.env  (sur le serveur, jamais commité)
```

`.env.example` sert uniquement de référence pour un développeur qui veut faire tourner l'application en local : il le copie en `.env` et renseigne ses propres valeurs.


# `~/.vault_pass` vs `_v03/ansible/vars/vault.yml`

## `~/.vault_pass` — le mot de passe de chiffrement

C'est un simple fichier texte contenant le mot de passe qui sert à chiffrer/déchiffrer le vault. Ansible l'utilise automatiquement grâce à ansible.cfg.
```
mon_mot_de_passe_super_secret
```
Il ne contient qu'une seule ligne. Il n'est jamais commité, jamais partagé — il reste sur ta machine locale.

## `_v03/ansible/vars/vault.yml` — les secrets de l'application

C'est le fichier qui contient les vraies valeurs des secrets (clés API, etc.). Il est chiffré par Ansible Vault en utilisant le mot de passe de `~/.vault_pass`.

En clair (avant chiffrement), il ressemble à ça :

```
vault_anthropic_api_key: "sk-ant-api03-..."
vault_azure_client_secret: "AbCdEf12..."
vault_session_secret_key: "a3f8c2d1e4b9..."
```

Une fois chiffré (ansible-vault encrypt), son contenu devient illisible :
```
$ANSIBLE_VAULT;1.1;AES256
34623133373339333036363462333532...
C'est ce fichier chiffré qui est commité dans le dépôt git.
```

L'analogie : ~/.vault_pass est la clé du coffre. vault.yml est le coffre (commité, mais verrouillé).

## Explication de vault_session_secret_key

`vault_session_secret_key` est la variable Ansible Vault qui contient la valeur de `SESSION_SECRET_KEY` — la clé secrète utilisée par **Starlette `SessionMiddleware`** pour signer cryptographiquement les cookies de session.

Concrètement :

1. Quand un utilisateur se connecte, FastAPI stocke ses infos (`email`, `name`, `role`) dans un cookie signé envoyé au navigateur.
2. À chaque requête suivante, le navigateur renvoie ce cookie.
3. FastAPI vérifie la signature avec `SESSION_SECRET_KEY` — si le cookie a été modifié côté client, la signature ne correspond plus et la session est rejetée.

**Ce qui se passe si la clé est faible ou connue :** un attaquant pourrait forger un cookie valide avec n'importe quel email/rôle et se faire passer pour un admin.

**Ce qui se passe si la clé change :** toutes les sessions existantes sont immédiatement invalidées — tous les utilisateurs connectés sont déconnectés.

La clé doit donc être longue, aléatoire et stable. La générer avec :

```bash
openssl rand -hex 32
```

## Workflow concret :

1. Créer la clé (une seule fois)
```
echo "mon_mot_de_passe" > ~/.vault_pass
chmod 600 ~/.vault_pass
```

2. Remplir le vault en clair, puis le chiffrer
```
ansible-vault encrypt _v03/ansible/vars/vault.yml
```
→ Ansible lit ~/.vault_pass et chiffre le fichier sur place

3. Commiter le vault chiffré (sans risque)
```
git add _v03/ansible/vars/vault.yml
```

4. Pour modifier un secret plus tard
```
ansible-vault edit _v03/ansible/vars/vault.yml
```
→ Ouvre le fichier déchiffré dans $EDITOR, rechiffre à la sauvegarde

# Résultat

## Fonctionnalités implémentées

### Backend — Endpoints API

| Route | Auth | Description |
|---|---|---|
| `GET /api/health` | Public | Retourne `{"status": "ok"}` |
| `GET /api/auth/me` | Session | Retourne `{email, name, role}` de l'utilisateur connecté |
| `GET /auth/login` | Public | Redirige vers Azure AD (OAuth2 Authorization Code flow) |
| `GET /auth/callback` | Public | Reçoit le code Azure AD, échange contre un token, crée la session cookie |
| `GET /auth/logout` | Public | Détruit la session, redirige vers `/` |
| `GET /auth/denied` | Public | Page HTML "accès refusé" (utilisateur authentifié mais non autorisé) |
| `GET /private` | Session | Sert `private.html`, ou redirige vers `/` si non authentifié |

### Frontend — Pages statiques

- `/` (`index.html`) — Page d'accueil avec détection de session : affiche "Se connecter" ou un lien vers `/private`
- `/private` (`private.html`) — Page protégée affichant nom, email, rôle. Placeholder "Application en cours de développement."
- `style.css` — CSS de base

### Auth / sécurité

- OAuth2 Authorization Code Flow via MSAL + Azure AD
- Session signée (cookie HTTP-only, Secure, SameSite=lax, 24h)
- Liste blanche d'utilisateurs avec rôles (`users.yaml`)
- Protection CSRF sur le callback (vérification du `state`)

### Configuration

- `app.yaml` — paramètres Claude, verbosité, OAuth2, session, serveur
- `users.yaml` — liste des emails autorisés + rôles
- `questions.txt` — questions de cadrage (chargées, pas encore utilisées)
- `.env` — secrets (clé Anthropic, client secret Azure, session key)

