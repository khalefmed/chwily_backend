# Callback JEMLI → Chwily (statuts de livraison)

Contrat destiné à JEMLI (PDF « Chwily x JEMLI - API Callback (test) », 2026-10-30).
Implémentation : `DeliveryWebhookView` (`api/views.py`) et `apply_partner_status`
(`api/services/delivery.py`). Référence générale de l'API JEMLI : `jemli-api.md`.

## Requête

```
POST <base_url>/api/delivery/webhook/jemli/
Content-Type: application/json
X-Api-Key: <DeliveryProvider "jemli".webhook_secret de l'environnement>
```

```json
{"id": 137253, "status": "driver_assigned", "driver": {"name": "Sidi", "phone": "22123456"}}
```

- `id` (obligatoire) : id JEMLI renvoyé à la création, comparé à `Commande.partner_delivery_ref`.
- `status` (obligatoire) : chaîne (un objet `{"code": ...}` est aussi accepté).
- `driver` (optionnel) : `phone` est enregistré dans `Commande.driver_phone`.
- `X-Webhook-Secret` et `?secret=` restent acceptés à la place de `X-Api-Key`.

## Statuts

Depuis le 2026-11-11, les étapes JEMLI sont de vrais statuts `Commande.status` (mêmes noms),
affichés par l'app et notifiés au client. Le dernier code reçu est aussi gardé dans
`Commande.partner_status`. Un statut ne fait jamais reculer la commande (`_STATUS_RANK`).

Commande restaurant (`orders/`) :

| `status` JEMLI | `Commande.status` | Libellé |
| --- | --- | --- |
| `vendor_confirmed` | `vendor_confirmed` | Vendeur confirmé |
| `vendor_preparing` | `vendor_preparing` | Préparation de la commande |
| `ready_for_pickup` | `ready_for_pickup` | Prêt pour récupérer |
| `driver_collected` | `driver_collected` | Commande récupérée |
| `driver_on_way` | `driver_on_way` | En cours de livraison |
| `driver_arrived` | `driver_arrived` | Livreur arrivé |
| `delivered` | `delivered` (final) | Livrée |
| `vendor_cancelled` | inchangé, `dispatch_status = cancelled`, admins notifiés | — |

Course (`deliveries/`) :

| `status` JEMLI | `Commande.status` |
| --- | --- |
| `driver_assigned` | `driver_assigned` |
| `driver_arrived_to_pickup_point` | `loading` |
| `driver_arrived_to_drop_point` | `driver_arrived` |
| `delivered` | `delivered` (final) |
| `cancelled` | inchangé, `dispatch_status = cancelled`, admins notifiés |

`customer_cancelled` (code JEMLI observé) est traité comme `cancelled`.

## Réponses

- `200 {"ok": true, "id": "...", "status": "..."}` (idempotent)
- `401 invalid_api_key`, `400 missing_fields`, `400 invalid_status`, `404 unknown_id`,
  toutes sous la forme `{"ok": false, "error": "<code>", "detail": "..."}`.

## Environnements communiqués à JEMLI

| Environnement | URL | Transmis |
| --- | --- | --- |
| Test (VPS dev) | `https://dev.194-163-185-253.sslip.io/api/delivery/webhook/jemli/` | PDF prêt le 2026-10-30 |
| Production | à définir à la bascule | non |
