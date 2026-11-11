# API JEMLI (partenaire de livraison) — référence

JEMLI ne fournit pas de documentation formelle. Ce fichier rassemble ce qui a été
**vérifié par appel réel**, ce que JEMLI décrit lui-même (réponse `OPTIONS` de chaque
route, qui renvoie la docstring de la vue Django REST) et les exemples `curl` transmis.
À mettre à jour à chaque nouvelle information.

Code concerné : `api/services/jemli.py` (client HTTP), `api/services/delivery.py`
(devis, envoi, statuts), `api/services/catalog.py` (catalogue `mes_plats`).

Niveau de confiance utilisé ci-dessous :

- ✅ **vérifié** — appelé en réel, réponse observée.
- 📄 **décrit** — docstring renvoyée par `OPTIONS` sur la route, non appelé.
- ⚠️ **exemple seul** — vu dans un `curl` de JEMLI, jamais appelé ni décrit.

## Base et authentification

```
https://api-jemli.oneposts.io/api/third-party/<segment>/
X-Api-Key: <clé>
X-Api-Secret: <secret>
Content-Type: application/json
```

- Clés : dans l'admin Django, `DeliveryProvider` « jemli » (`api_key` / `api_secret`).
  Jamais dans le dépôt. Un seul jeu de clés réelles, partagé par dev et prod.
- Sans les en-têtes : `401 {"detail": "X-Api-Key and X-Api-Secret headers are required"}`.
- **Segment de route** : stocké dans `DeliveryProvider.base_url`, fourni par JEMLI.

  | Période | Segment | État |
  | --- | --- | --- |
  | sept. 2026 | `28/08/2026` | 404 sur toutes les routes depuis oct. 2026 |
  | depuis oct. 2026 | `10/2026` | actif (vérifié le 2026-10-30) |

  Il change sans préavis, et les docstrings et exemples de JEMLI citent encore parfois
  l'ancien. **404 HTML sur toutes les routes = segment à mettre à jour.**
- Astuce : `OPTIONS <route>` (avec les clés) renvoie la description de la route
  (`name`, `description`). Une route inexistante renvoie 404.

## Routes

### `POST compute-pricing/` — devis de livraison ✅

```json
// requête
{"origin": {"lat": 18.0735, "lng": -15.9582}, "destination": {"lat": 18.09, "lng": -15.97}}
// réponse
{"price": 0.0, "delivery_fee": 100.0, "distance_km": 4.13,
 "origin_title": "...", "destination_title": "...", "is_prepaid": true}
```

Le tarif est **`delivery_fee`** (pas `price`). Chez nous :
`delivery_final_price = delivery_fee + DeliveryType.delivery_margin`.

### `GET products/?category=restaurant` — catalogue ✅

```json
{"category": "restaurant", "vendor_id": 472, "products": [
  {"id": 7513, "name": "أظهر", "description": "", "price": 1000.0,
   "discount_price": null, "image": "https://api-jemli.oneposts.io/media/...",
   "menus": [{"id": 1560, "name": "المشويات"}]}
]}
```

- Description JEMLI : *« Active products that belong to an active menu of the category
  vendor. restaurant -> vendor 472. »* Une catégorie correspond donc à **un** vendeur.
- Seule `category=restaurant` est acceptée (sinon 400). `vendor_id` et `page` sont ignorés,
  il n'y a pas de pagination. Les noms sont en arabe uniquement.
- Utilisé par `catalog.py` pour alimenter `mes_plats` (`Category.external_id` = `id`).

### `POST deliveries/` — créer une course 📄

```json
{
  "origin": {"lat": 0, "lng": 0},
  "destination": {"lat": 0, "lng": 0},
  "custom_description": "optionnel",
  "origin_title": "optionnel",
  "destination_title": "optionnel"
}
```

- Course seule (sans produits), pour `sbou7` / `poisson` / `l7am`.
- **Pas de champ téléphone ni nom du destinataire, ni d'heure programmée.**
- Réponse jamais observée : probablement le même objet que `GET deliveries/<id>/`.

### `GET deliveries/<id>/` — suivre une course ✅

```json
{
  "id": 137253,
  "status": {"code": "customer_cancelled", "name": "Annulée par le client",
             "name_ar": "أُلغي من قبل العميل",
             "color": {"text": "#F44336", "background": "#FFEBEE"}},
  "driver": null,
  "vendor": null,
  "created_at": "2026-08-28T04:54:00.472830Z",
  "updated_at": "2026-08-28T04:54:00.472848Z",
  "origin": {"lat": 18.0735, "lng": -15.9582},
  "destination": {"lat": 18.1, "lng": -15.95},
  "origin_title": "كرفور بكار, كرفور",
  "destination_title": "كرفور گاريم, المطار القديم",
  "custom_description": "",
  "delivery_fee": 120.0, "amount": 0.0, "service_fee": 0.0, "distance_km": 4.13,
  "total_amount": 0.0, "discount_amount": 120.0
}
```

- **`status` est un objet** : le code machine est dans `status.code`.
- Codes connus (liste transmise par JEMLI le 2026-10-30 + observés) et correspondance chez nous :

  | `status.code` JEMLI | `Commande.status` |
  | --- | --- |
  | `driver_assigned` | `driver_assigned` |
  | `driver_arrived_to_pickup_point` | `loading` (en cours) |
  | `driver_arrived_to_drop_point` | `loading` (inchangé) |
  | `delivered` | `delivered` |
  | `customer_cancelled` (observé) | `rejected` |

  Commandes restaurant (`orders/`), liste transmise par JEMLI le 2026-11-11 :
  `vendor_confirmed`, `vendor_cancelled`, `vendor_preparing`, `ready_for_pickup`,
  `driver_collected`, `driver_on_way`, `driver_arrived`, `delivered` — correspondance dans
  `jemli-callback.md`. Inconnu : le statut initial d'une course avant affectation.
- Format de `driver` quand il est renseigné : inconnu (probablement nom et téléphone).

### `POST orders/?category=restaurant` — commande restaurant (plats + livraison) 📄 ⚠️

```json
{
  "phone": "22123456",
  "full_name": "optionnel, utilisé seulement à la création du client",
  "destination": {"lat": 18.07, "lng": -15.95},
  "items": [{"product_id": 7513, "quantity": 1}],
  "customer_description": "note optionnelle du client"
}
```

- Pas d'`origin` : le départ est le restaurant (vendeur de la catégorie).
- `product_id` = `id` de `products/` (chez nous `Category.external_id`).
- ⚠️ **Nom du champ note** : la docstring dit `customer_description`, l'exemple `curl` de
  JEMLI dit `custom_description`. À confirmer.
- Réponse, identifiant de commande et suivi : inconnus. `GET orders/<id>/` renvoie 404.
- **Jamais appelée** : elle déclenche une vraie commande chez le restaurant.

### Routes inexistantes (404)

`orders/<id>/`, `categories/`, `vendors/`, `statuses/`, `webhook/`. `GET` sur
`deliveries/` et `orders/` renvoie 405 : pas de liste.

## Webhook (JEMLI → Chwily)

Contrat défini et transmis à JEMLI : voir `jemli-callback.md` (les lignes ci-dessous datent d'avant).

Notre endpoint est `POST /api/delivery/webhook/jemli/`, avec l'en-tête
`X-Webhook-Secret: <DeliveryProvider.webhook_secret>`.

**Le format envoyé par JEMLI est inconnu**, et on ne sait pas s'il est déjà configuré
de leur côté. La vue accepte de façon défensive `delivery_id` | `id` | `reference`,
`status` | `state` et `driver` (`phone` | `phone_number`) ou `driver_phone`.

## Ce que fait notre code (`api/services/`)

| Sujet | Implémentation |
| --- | --- |
| Type avec catalogue (`mes_plats`) | `POST orders/?category=restaurant` : `items` depuis `Category.external_id`, `full_name` = nom du client, note = `customer_description` **et** `custom_description` (champ non tranché) |
| Autres types partenaire | `POST deliveries/` avec `origin`, `destination`, `origin_title` (et `destination_title` si quartier) |
| Référence et téléphone | `custom_description` = `Chwily <code commande> - <téléphone>`, seul moyen de transmettre le téléphone au livreur |
| Destination | point choisi sur la carte (`Commande.delivery_lat/lng`), sinon le quartier |
| Identifiant retourné | lu défensivement (`id`, `delivery_id`, `reference`…, éventuellement sous `data` / `order` / `delivery`) |
| Statut | `status.code` (objet) ou chaîne → `JEMLI_STATUS_MAP` (codes réels ci-dessus ; un code inconnu ne change rien) |
| Sandbox | `DELIVERY_SANDBOX=True` : aucun appel `orders/` ni `deliveries/` réel |

## Questions ouvertes pour JEMLI

1. ~~Liste des statuts~~ reçue le 2026-11-11 pour `orders/` ; reste le statut initial d'une course.
2. Format du webhook, et comment l'enregistrer chez eux (URL + secret).
3. Réponse de `POST orders/` : identifiant, et comment suivre une commande ensuite.
4. `customer_description` ou `custom_description` pour `orders/` ?
5. Comment transmettre au livreur le téléphone du destinataire d'une course `deliveries/` ?
6. Facturation : comment les plats (`orders/`) et les courses sont-ils facturés à Chwily ?
7. Y a-t-il un moyen de tester `orders/` et `deliveries/` sans déclencher de vrai
   livreur ni de vrai restaurant ?
8. Stabilité du segment de route : prévenir avant chaque changement ?
