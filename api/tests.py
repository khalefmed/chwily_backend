from unittest import mock

from cloudinary import CloudinaryResource
from django.core.cache import cache
from django.test import TestCase
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
