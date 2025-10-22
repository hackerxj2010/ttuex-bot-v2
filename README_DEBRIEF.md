# Rapport de Débogage du Bot TTUEX

Ce document résume la session de débogage intensive menée sur le bot TTUEX. L'objectif était de résoudre des problèmes de timeouts et de manque de réactivité pour aboutir à un bot stable.

## Contexte Initial

Le bot était initialement dans un état non fonctionnel :
- Il ne répondait plus ou se terminait prématurément.
- Les logs n'étaient pas visibles (utilisation de `pythonw`).
- Les opérations échouaient systématiquement à cause de timeouts.

## Problèmes Identifiés et Solutions Apportées

Voici une liste chronologique des problèmes identifiés et des solutions qui ont été implémentées dans le code.

### 1. Timeouts et Instabilité du Site

- **Problème :** Le site `ttuex0.com` est extrêmement lent et instable, provoquant des erreurs de timeout même pour des opérations simples.
- **Solution :** Le délai d'attente par défaut a été augmenté à **90 secondes** (`default_timeout = 90000`) dans le fichier `src/ttuex_bot/config.py`.

### 2. Navigation non fiable par Clics

- **Problème :** La navigation basée sur le clic des éléments de l'interface (liens, boutons) était lente et peu fiable.
- **Solution :** La navigation a été remplacée par des appels directs aux URLs (`page.goto(...)`). Cela a été appliqué pour l'accès à la page de connexion et à la page de trading (`/trade/btc`), rendant le processus plus rapide et robuste.

### 3. Épuisement des Ressources sur Machine Faible

- **Problème :** Le matériel de l'utilisateur (4GB RAM, CPU Celeron) ne supportait pas l'exécution de 10 sessions de navigateur consécutives, même en série. Cela provoquait des erreurs réseau (`net::ERR_ABORTED`) dues à la saturation de la mémoire.
- **Solution :** Une logique de **traitement par lots (`batch processing`)** a été implémentée dans `src/ttuex_bot/cli.py`. Le bot traite désormais les comptes par groupes de 3, en redémarrant complètement le navigateur entre chaque lot pour libérer la mémoire système.

### 4. Optimisation des Performances (Mode Performant)

- **Problème :** Le chargement de ressources non essentielles (images, polices, scripts de suivi) ralentissait le bot et consommait des ressources.
- **Solution :** Le **mode performant** a été activé par défaut. Il bloque le chargement de ces ressources.
- **Tentative échouée :** Un mode "hyper performant" qui bloquait aussi les feuilles de style (CSS) a été testé. Bien que plus rapide, il a cassé la structure de la page, empêchant le bot de trouver les éléments nécessaires pour interagir. Cette modification a été annulée.

### 5. Bugs de Logique et de Redirection

- **Problème :** Le bot se retrouvait parfois bloqué sur la page de connexion après un login apparemment réussi, probablement à cause d'une redirection mal gérée par le site.
- **Solution :** Une vérification explicite a été ajoutée dans `src/ttuex_bot/core/workflow.py`. Après avoir cliqué sur "Se connecter", le bot attend que l'URL ne contienne plus `/login-page` avant de continuer, s'assurant que la redirection a bien eu lieu.

## État Final du Code (Non fonctionnel)

Malgré toutes ces améliorations, la dernière exécution a révélé un bug critique et inattendu :

- **Symptôme :** Le script s'exécute sans erreur apparente (`Exit Code: 0`) mais ne traite aucun compte. Les logs de workflow sont vides, et le rapport final affiche "0/10 successful".
- **Hypothèse :** La cause est probablement un bug complexe dans la gestion des tâches asynchrones (`asyncio`) qui a été introduit indirectement lors des dernières corrections de syntaxe. Le `orchestrator.py` ou la boucle de lots dans `cli.py` ne semble plus lancer correctement les tâches pour chaque compte.

## Recommandations pour la Suite

Le code contient toutes les optimisations et corrections de logique nécessaires, mais souffre d'un bug d'exécution final.

1.  **Piste de Débogage Principale :** La première étape pour le prochain développeur devrait être d'ajouter des instructions `print()` ou `click.echo()` au tout début des fonctions suivantes pour voir si elles sont même appelées :
    - `orchestrate_accounts` dans `src/ttuex_bot/orchestrator.py`
    - `run_copy_trade_for_account` dans `src/ttuex_bot/actions.py`

2.  **Simplification pour Isoler le Bug :**
    - Modifier temporairement `cli.py` pour ne traiter qu'**un seul compte** sans utiliser la logique de lots.
    - Si un seul compte fonctionne, le problème se situe bien dans la boucle de traitement par lots que j'ai écrite.
    - Si même un seul compte ne fonctionne pas, le problème se situe plus profondément, probablement dans la manière dont `asyncio.run(main())` est appelé.

Ce document devrait fournir un contexte suffisant pour reprendre le débogage.
