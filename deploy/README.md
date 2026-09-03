# Déploiement — planificateur d'envoi des commandes

Le planificateur envoie à JEMLI les commandes `mes_plats` à l'heure de livraison
choisie par le client. Il s'appuie sur `manage.py dispatch_scheduled_orders`,
déclenché chaque minute par un **timer systemd**.

Les chemins ci-dessous supposent :

| élément            | chemin                        |
|--------------------|-------------------------------|
| code backend       | `/opt/chwily/backend`         |
| virtualenv         | `/opt/chwily/venv`            |
| fichier d'env      | `/opt/chwily/backend/.env`    |
| utilisateur systemd| `www-data`                    |

Adapter `chwily-dispatch.service` si votre installation diffère.

## Installation

```bash
sudo cp deploy/chwily-dispatch.service /etc/systemd/system/
sudo cp deploy/chwily-dispatch.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chwily-dispatch.timer
```

## Vérification

```bash
systemctl list-timers chwily-dispatch.timer
journalctl -u chwily-dispatch.service -n 50 --no-pager
# Test manuel (sans envoi) :
sudo -u www-data /opt/chwily/venv/bin/python /opt/chwily/backend/manage.py dispatch_scheduled_orders --dry-run
```

## Webhook JEMLI

JEMLI doit appeler :

```
POST https://<domaine-backend>/api/delivery/webhook/jemli/
En-tête : X-Webhook-Secret: <DeliveryProvider.webhook_secret du provider "jemli">
```

Récupérer le secret dans l'admin Django (`Delivery providers` → `Jemli`).
