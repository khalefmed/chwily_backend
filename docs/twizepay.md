# TwizePay — paiements wallet détectés

TwizePay lit les transactions de nos wallets (Bankily, Masrvi, Sedad…) et les envoie en
webhook. Source : `twizepay-webhooks-fr.pdf` transmis par TwizePay (nov. 2026).

Code : `api/services/payments.py`, vue `TwizePayWebhookView`, modèle `WalletTransaction`.

## Notre endpoint

```
POST /api/payments/webhook/twizepay/
dev : https://dev.194-163-185-253.sslip.io/api/payments/webhook/twizepay/
```

- À enregistrer par un admin de l'organisation dans TwizePay > Webhooks (une seule URL par
  organisation, HTTPS, nom d'hôte public, pas de redirection).
- Secret de signature (`whsec_…`, affiché **une seule fois**) : variable d'env
  `TWIZEPAY_WEBHOOK_SECRET`. Vide = tout est refusé (401). Jamais dans le dépôt.

## Ce que TwizePay envoie

En-têtes `TwizePay-Event-Id` (stable entre tentatives), `TwizePay-Event-Type`
(`transaction.created` | `transaction.updated` | `transaction.test`), `TwizePay-Timestamp`,
`TwizePay-Signature: t=<ts>,v1=<hex>`.

```json
{"id": "8b1e0a2c-…", "occurredAt": "2026-11-07T20:58:00Z", "wallet": "BANKILY",
 "transactionId": "TXN-10001", "direction": "CR", "amount": 150.00,
 "counterpartyNumber": "+22236899900", "counterpartyName": "A Buyer", "balanceAfter": 5000.00}
```

- Signature : HMAC-SHA256(secret, `<ts>.<corps brut>`) en hexa minuscule ; `t` doit égaler
  `TwizePay-Timestamp` et être à moins de 5 min.
- `updated` = même paiement dont le numéro ou le nom était vide : rapprocher sur `id`.
- `test` : montant 0, `TXN-TEST`, ne pas enregistrer.
- Le webhook part quand le téléphone de collecte a remonté la transaction, pas quand la banque
  la comptabilise.
- Réponse 2xx attendue en moins de 10 s, sinon 8 tentatives (1 min → 12 h).

## Ce que fait notre code

| Sujet | Comportement |
| --- | --- |
| Stockage | toute transaction (CR et DR) dans `WalletTransaction`, upsert sur `id` : un renvoi ou un `updated` ne crée jamais un second paiement |
| Numéro payeur | `Commande.payment_phone`, saisi sur le dernier écran (pré-rempli avec le numéro de contact) ; les deux numéros sont normalisés sur 8 chiffres |
| Rapprochement | transaction CR → plus ancienne commande `waiting` de moins de 24 h avec ce `payment_phone` et `prix + livraison` = montant (à 0,01 près) → `paid` |
| Paiement avant commande | à la création de la commande, on cherche une transaction CR non rapprochée (< 24 h) du même numéro et du même montant |
| Après `paid` | même suite qu'un passage manuel : `dispatch_commande` (JEMLI), push au client, push aux admins — en arrière-plan, après la réponse |
| Montant différent | la commande reste `waiting`, push « Paiement à vérifier » aux admins |
| Sans correspondance | transaction gardée `pending`, visible dans l'admin Django |

La validation manuelle par capture d'écran reste en place en secours.
