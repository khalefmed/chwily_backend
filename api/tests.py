from unittest import mock

from cloudinary import CloudinaryResource
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import Category, DeliveryProvider, DeliveryType


def _product(pid, name, price, image, discount=None):
    return {'id': pid, 'name': name, 'description': '', 'price': price,
            'discount_price': discount, 'image': image, 'menus': []}


def _fake_upload(url, public_id, **kwargs):
    return {'public_id': public_id, 'format': 'jpg', 'version': 1}


@mock.patch('api.services.catalog.cloudinary.uploader.upload', side_effect=_fake_upload)
@mock.patch('api.services.jemli.JemliClient.list_products')
class PartnerCatalogTests(TestCase):
    def setUp(self):
        cache.clear()
        provider = DeliveryProvider.objects.get(code='jemli')
        self.delivery_type = DeliveryType.objects.get(code='mes_plats')
        self.delivery_type.provider = provider
        self.delivery_type.is_active = True
        self.delivery_type.save()
        self.manual = Category.objects.create(
            name_fr='Manuel', name_ar='يدوي', price1=1, price2=1, price3=1, livraison=0,
            type='mes_plats', type_class='mes_plats',
            image=CloudinaryResource('manual', format='jpg', version=1, type='upload', resource_type='image'),
        )
        self.client = APIClient()

    def test_migration_maps_mes_plats_to_restaurant(self, list_products, upload):
        self.assertEqual(self.delivery_type.catalog_category, 'restaurant')

    def test_view_serves_partner_products(self, list_products, upload):
        list_products.return_value = {'products': [
            _product(7513, 'أظهر', 1000.0, 'https://x/a.jpg'),
            _product(7454, 'الديوك', 300.0, 'https://x/b.jpg', discount=250.0),
        ]}

        data = self.client.get('/api/category/mes_plats/').json()

        list_products.assert_called_once_with('restaurant')
        self.assertEqual([d['name_ar'] for d in data], ['أظهر', 'الديوك'])
        self.assertEqual(data[1]['price1'], 250.0)
        self.assertEqual(data[0]['image'], 'image/upload/v1/jemli/products/7513.jpg')
        self.manual.refresh_from_db()
        self.assertFalse(self.manual.is_active)

    def test_resync_updates_and_deactivates(self, list_products, upload):
        list_products.return_value = {'products': [
            _product(1, 'a', 100.0, 'https://x/1.jpg'), _product(2, 'b', 200.0, 'https://x/2.jpg'),
        ]}
        self.client.get('/api/category/mes_plats/')
        cache.clear()
        list_products.return_value = {'products': [_product(2, 'b', 220.0, 'https://x/2.jpg')]}

        data = self.client.get('/api/category/mes_plats/').json()

        self.assertEqual([(d['external_id'], d['price1']) for d in data], [('2', 220.0)])
        self.assertEqual(upload.call_count, 2)  # image inchangée : pas de re-téléversement
        self.assertFalse(Category.objects.get(external_id='1').is_active)

    def test_partner_error_keeps_last_catalog(self, list_products, upload):
        list_products.return_value = {'products': [_product(1, 'a', 100.0, 'https://x/1.jpg')]}
        self.client.get('/api/category/mes_plats/')
        cache.clear()
        from api.services.jemli import DeliveryPartnerError
        list_products.side_effect = DeliveryPartnerError('404')

        response = self.client.get('/api/category/mes_plats/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([d['external_id'] for d in response.json()], ['1'])

    def test_other_types_do_not_call_partner(self, list_products, upload):
        self.client.get('/api/category/guewda/')
        list_products.assert_not_called()


@mock.patch('api.services.jemli.JemliClient.compute_pricing')
class DeliveryCoordinatesTests(TestCase):
    def setUp(self):
        from api.models import LocationPoint, User
        provider = DeliveryProvider.objects.get(code='jemli')
        provider.origin_point = LocationPoint.objects.first()
        provider.save()
        DeliveryType.objects.filter(code='mes_plats').update(provider=provider, is_active=True)
        self.user = User.objects.create_user(phone=22222222, password='x')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_quote_with_map_point(self, compute_pricing):
        compute_pricing.return_value = {'delivery_fee': 100.0}

        response = self.client.post('/api/commandes/delivery-quote/',
                                    {'lat': 18.09, 'lng': -15.97, 'delivery_type': 'mes_plats'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['delivery_final_price'], 150.0)
        destination = compute_pricing.call_args.args[1]
        self.assertEqual((destination.lat, destination.lng), (18.09, -15.97))

    def test_quote_rejects_bad_coordinates(self, compute_pricing):
        response = self.client.post('/api/commandes/delivery-quote/',
                                    {'lat': 'abc', 'lng': -15.97, 'delivery_type': 'mes_plats'}, format='json')
        self.assertEqual(response.status_code, 400)
        compute_pricing.assert_not_called()

    def test_commande_destination_prefers_map_point(self, compute_pricing):
        from api.models import Commande, LocationPoint
        commande = Commande(location_point=LocationPoint.objects.first(), delivery_lat=18.1, delivery_lng=-15.9)
        self.assertEqual((commande.destination.lat, commande.destination.lng), (18.1, -15.9))
        commande.delivery_lat = None
        self.assertEqual(commande.destination, commande.location_point)


@override_settings(DELIVERY_SANDBOX=False)
@mock.patch('api.services.delivery.notify_client_status')
@mock.patch('api.services.jemli.JemliClient._request', return_value={'id': 555})
class PartnerDispatchTests(TestCase):
    def setUp(self):
        from api.models import Commande, ItemCommande, LocationPoint, User
        self.provider = DeliveryProvider.objects.get(code='jemli')
        self.provider.origin_point = LocationPoint.objects.get(name='Carrefour')
        self.provider.save()
        DeliveryType.objects.filter(code__in=['mes_plats', 'poisson']).update(provider=self.provider)
        user = User.objects.create_user(phone=33333333, password='x', first_name='Ahmed')
        image = CloudinaryResource('x', format='jpg', version=1, type='upload', resource_type='image')
        self.plat = Category.objects.create(
            name_fr='p', name_ar='p', price1=1000, price2=1000, price3=1000, livraison=0,
            type='mes_plats', type_class='mes_plats', image=image, external_id='7513')
        self.poisson = Category.objects.create(
            name_fr='f', name_ar='f', price1=1, price2=1, price3=1, livraison=0,
            type='poisson', type_class='poisson', image=image)
        self.commande = Commande.objects.create(
            prix=2000, location='x', phone='20004200', user=user,
            delivery_provider=self.provider, delivery_lat=18.09, delivery_lng=-15.97)
        self.ItemCommande = ItemCommande

    def _send(self, category, delivery_code):
        from api.services.delivery import send_to_partner
        self.ItemCommande.objects.create(category=category, commande=self.commande, number=2)
        self.commande.delivery_type = DeliveryType.objects.get(code=delivery_code)
        self.assertTrue(send_to_partner(self.commande))
        self.commande.refresh_from_db()

    def test_mes_plats_goes_to_orders(self, request, notify):
        self._send(self.plat, 'mes_plats')

        method, url = request.call_args.args
        body = request.call_args.kwargs['json']
        self.assertEqual(method, 'POST')
        self.assertTrue(url.endswith('/orders/'))
        self.assertEqual(request.call_args.kwargs['params'], {'category': 'restaurant'})
        self.assertEqual(body['items'], [{'product_id': 7513, 'quantity': 2}])
        self.assertEqual(body['destination'], {'lat': 18.09, 'lng': -15.97})
        self.assertEqual((body['phone'], body['full_name']), ('20004200', 'Ahmed'))
        self.assertIn(self.commande.code, body['customer_description'])
        self.assertEqual(self.commande.partner_delivery_ref, '555')

    def test_other_partner_types_go_to_deliveries(self, request, notify):
        self._send(self.poisson, 'poisson')

        method, url = request.call_args.args
        body = request.call_args.kwargs['json']
        self.assertTrue(url.endswith('/deliveries/'))
        self.assertEqual(set(body), {'origin', 'destination', 'custom_description', 'origin_title'})
        self.assertIn('20004200', body['custom_description'])

    def test_status_object_is_mapped(self, request, notify):
        from api.services.delivery import apply_partner_status
        changed = apply_partner_status(self.commande, {'code': 'driver_assigned', 'name': '...'})
        self.assertEqual(changed, 'driver_assigned')


@mock.patch('api.services.delivery.send_notifications_to_admins')
@mock.patch('api.services.delivery.notify_client_status')
class PartnerCallbackTests(TestCase):
    URL = '/api/delivery/webhook/jemli/'

    def setUp(self):
        from api.models import Commande, User
        self.provider = DeliveryProvider.objects.get(code='jemli')
        user = User.objects.create_user(phone=44444444, password='x')
        self.commande = Commande.objects.create(
            prix=1000, location='x', phone='20004200', user=user, status='looking_for_driver',
            delivery_provider=self.provider, partner_delivery_ref='137253', dispatch_status='sent')
        self.client = APIClient()

    def _post(self, body, key=None):
        key = self.provider.webhook_secret if key is None else key
        return self.client.post(self.URL, body, format='json', HTTP_X_API_KEY=key)

    def test_full_lifecycle(self, notify, notify_admins):
        expected = [('driver_assigned', 'driver_assigned'),
                    ('driver_arrived_to_pickup_point', 'loading'),
                    ('driver_arrived_to_drop_point', 'loading'),
                    ('delivered', 'delivered')]
        for code, status in expected:
            response = self._post({'id': 137253, 'status': code, 'driver': {'name': 'Sidi', 'phone': '22123456'}})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'ok': True, 'id': '137253', 'status': code})
            self.commande.refresh_from_db()
            self.assertEqual(self.commande.status, status)
        self.assertEqual(self.commande.driver_phone, '22123456')

    def test_delivered_is_final(self, notify, notify_admins):
        self._post({'id': 137253, 'status': 'delivered'})
        self._post({'id': 137253, 'status': 'driver_arrived_to_drop_point'})
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.status, 'delivered')

    def test_cancelled_keeps_status_and_alerts_admins(self, notify, notify_admins):
        response = self._post({'id': 137253, 'status': 'cancelled'})
        self.assertEqual(response.status_code, 200)
        self.commande.refresh_from_db()
        self.assertEqual((self.commande.status, self.commande.dispatch_status), ('looking_for_driver', 'cancelled'))
        notify_admins.assert_called_once()
        notify.assert_not_called()

    def test_errors(self, notify, notify_admins):
        cases = [
            (self._post({'id': 137253, 'status': 'delivered'}, key='bad'), 401, 'invalid_api_key'),
            (self._post({'status': 'delivered'}), 400, 'missing_fields'),
            (self._post({'id': 137253, 'status': 'paid'}), 400, 'invalid_status'),
            (self._post({'id': 999, 'status': 'delivered'}), 404, 'unknown_id'),
        ]
        for response, http, error in cases:
            self.assertEqual(response.status_code, http)
            self.assertEqual(response.json()['error'], error)


def _run_now(func, *args):
    func(*args)


@override_settings(TWIZEPAY_WEBHOOK_SECRET='whsec_test')
@mock.patch('api.services.payments._in_background', side_effect=_run_now)
@mock.patch('api.services.payments.send_notifications_to_admins')
@mock.patch('api.services.payments.notify_client_status')
class TwizePayWebhookTests(TestCase):
    URL = '/api/payments/webhook/twizepay/'

    def setUp(self):
        from api.models import Commande, User
        self.user = User.objects.create_user(phone=33333333, password='x')
        # Contact 20004200, paiement depuis un autre numéro : 1000 + 150 = 1150 MRU.
        self.commande = Commande.objects.create(
            prix=1000, livraison=150, location='x', phone='20004200', user=self.user, payment_phone='36899900')
        self.client = APIClient()

    def _tx(self, **overrides):
        body = {'id': '8b1e0a2c', 'occurredAt': '2026-11-07T20:58:00Z', 'wallet': 'BANKILY',
                'transactionId': 'TXN-10001', 'direction': 'CR', 'amount': 1150.00,
                'counterpartyNumber': '+22236899900', 'counterpartyName': 'A Buyer', 'balanceAfter': 5000.00}
        body.update(overrides)
        return body

    def _post(self, body, event_type='transaction.created', secret='whsec_test', timestamp=None):
        import hashlib, hmac, json, time
        raw = json.dumps(body).encode()
        ts = str(int(time.time()) if timestamp is None else timestamp)
        sig = hmac.new(secret.encode(), ts.encode() + b'.' + raw, hashlib.sha256).hexdigest()
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.generic('POST', self.URL, raw, content_type='application/json',
                                       HTTP_TWIZEPAY_EVENT_ID='evt-1', HTTP_TWIZEPAY_EVENT_TYPE=event_type,
                                       HTTP_TWIZEPAY_TIMESTAMP=ts, HTTP_TWIZEPAY_SIGNATURE=f't={ts},v1={sig}')

    def test_exact_amount_marks_order_paid(self, notify, notify_admins, _bg):
        from api.models import WalletTransaction
        response = self._post(self._tx())
        self.assertEqual(response.status_code, 200)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.status, 'paid')
        tx = WalletTransaction.objects.get()
        self.assertEqual((tx.match_status, tx.commande, tx.payer_phone), ('matched', self.commande, '36899900'))
        notify.assert_called_once_with(self.commande, 'paid')

    def test_other_amount_or_number_does_not_pay(self, notify, notify_admins, _bg):
        self._post(self._tx(id='a', amount=1000))
        self._post(self._tx(id='b', counterpartyNumber='+22220004200'))
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.status, 'waiting')
        notify_admins.assert_called_once()  # montant différent sur le bon numéro

    def test_replay_and_update_do_not_pay_twice(self, notify, notify_admins, _bg):
        from api.models import Commande, WalletTransaction
        second = Commande.objects.create(prix=1000, livraison=150, location='x', phone='1', user=self.user,
                                         payment_phone='36899900')
        self._post(self._tx())
        self._post(self._tx())
        self._post(self._tx(counterpartyName='Buyer Name'), event_type='transaction.updated')
        second.refresh_from_db()
        self.assertEqual(second.status, 'waiting')
        self.assertEqual(WalletTransaction.objects.count(), 1)
        self.assertEqual(WalletTransaction.objects.get().counterparty_name, 'Buyer Name')

    def test_number_completed_by_update_then_matches(self, notify, notify_admins, _bg):
        self._post(self._tx(counterpartyNumber=None))
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.status, 'waiting')
        self._post(self._tx(), event_type='transaction.updated')
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.status, 'paid')

    def test_payment_before_order(self, notify, notify_admins, _bg):
        from api.models import Commande
        from api.services.payments import match_commande
        self.commande.delete()
        self._post(self._tx())
        commande = Commande.objects.create(prix=1000, livraison=150, location='x', phone='1', user=self.user,
                                           payment_phone='36899900')
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNotNone(match_commande(commande))
        commande.refresh_from_db()
        self.assertEqual(commande.status, 'paid')

    def test_test_event_and_outgoing_are_not_payments(self, notify, notify_admins, _bg):
        from api.models import WalletTransaction
        self.assertEqual(self._post(self._tx(amount=0, transactionId='TXN-TEST'), event_type='transaction.test').status_code, 200)
        self.assertFalse(WalletTransaction.objects.exists())
        self._post(self._tx(direction='DR'))
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.status, 'waiting')
        self.assertEqual(WalletTransaction.objects.get().match_status, 'ignored')

    def test_rejects_bad_signature(self, notify, notify_admins, _bg):
        import time
        self.assertEqual(self._post(self._tx(), secret='wrong').status_code, 401)
        self.assertEqual(self._post(self._tx(), timestamp=int(time.time()) - 600).status_code, 401)
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.status, 'waiting')


@mock.patch('api.services.delivery.send_notifications_to_admins')
@mock.patch('api.services.delivery.send_notification')
class JemliOrderStatusTests(TestCase):
    URL = '/api/delivery/webhook/jemli/'

    def setUp(self):
        from api.models import Commande, User
        self.provider = DeliveryProvider.objects.get(code='jemli')
        user = User.objects.create_user(phone=55555555, password='x', default_lang='fr')
        user.fcm_token = 'token'
        user.save()
        self.commande = Commande.objects.create(
            prix=1000, location='x', phone='20004200', user=user, status='looking_for_driver',
            delivery_provider=self.provider, partner_delivery_ref='9001', dispatch_status='sent')
        self.client = APIClient()

    def _post(self, code):
        return self.client.post(self.URL, {'id': 9001, 'status': code}, format='json',
                                HTTP_X_API_KEY=self.provider.webhook_secret)

    def test_order_lifecycle_notifies_each_step(self, send, notify_admins):
        steps = ['vendor_confirmed', 'vendor_preparing', 'ready_for_pickup', 'driver_collected',
                 'driver_on_way', 'driver_arrived', 'delivered']
        for code in steps:
            self.assertEqual(self._post(code).status_code, 200)
            self.commande.refresh_from_db()
            self.assertEqual(self.commande.partner_status, code)
        self.assertEqual(self.commande.status, 'delivered')
        titles = [c.args[0] for c in send.call_args_list]
        self.assertEqual(titles, ['Vendeur confirmé', 'Préparation de la commande', 'Prêt pour récupérer',
                                  'Commande récupérée', 'En cours de livraison', 'Livreur arrivé', 'Livrée'])

    def test_repeat_and_late_callbacks(self, send, notify_admins):
        self._post('vendor_preparing')
        self._post('vendor_preparing')
        self.assertEqual(send.call_count, 1)
        self._post('driver_assigned')  # arrive en retard : ne fait pas reculer « en cours »
        self.commande.refresh_from_db()
        self.assertEqual(self.commande.status, 'loading')
        self._post('delivered')
        self._post('driver_on_way')
        self.commande.refresh_from_db()
        self.assertEqual((self.commande.status, self.commande.partner_status), ('delivered', 'delivered'))

    def test_vendor_cancelled(self, send, notify_admins):
        self.assertEqual(self._post('vendor_cancelled').status_code, 200)
        self.commande.refresh_from_db()
        self.assertEqual((self.commande.status, self.commande.dispatch_status, self.commande.partner_status),
                         ('looking_for_driver', 'cancelled', 'vendor_cancelled'))
        notify_admins.assert_called_once()
        send.assert_not_called()
