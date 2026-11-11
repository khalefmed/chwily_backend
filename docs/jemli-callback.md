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

`Commande.status` reste dans la liste connue de l'app ; le code JEMLI reçu est gardé dans
`Commande.partner_status`, et le client reçoit une notification avec le libellé JEMLI (fr/ar)
à chaque nouvelle étape. Un statut ne fait jamais reculer la commande.

Commande restaurant (`orders/`, liste JEMLI du 2026-11-11) :

| `status` | Libellé client | `Commande.status` |
| --- | --- | --- |
| `vendor_confirmed` | Vendeur confirmé | `loading` |
| `vendor_preparing` | Préparation de la commande | `loading` |
| `ready_for_pickup` | Prêt pour récupérer | `loading` |
| `driver_collected` | Commande récupérée | `loading` |
| `driver_on_way` | En cours de livraison | `loading` |
| `driver_arrived` | Livreur arrivé | `loading` |
| `delivered` | Livrée | `delivered` (final) |
| `vendor_cancelled` | — (admins notifiés) | inchangé, `dispatch_status = cancelled` |

Course (`deliveries/`) :

| `status` | `Commande.status` |
| --- | --- |
| `driver_assigned` | `driver_assigned` |
| `driver_arrived_to_pickup_point` | `loading` |
| `driver_arrived_to_drop_point` | `loading` |
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
