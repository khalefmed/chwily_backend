import uuid

from django.db import migrations


# Quartiers de Nouakchott repris du sélecteur de l'app mobile.
# Coordonnées APPROXIMATIVES — à corriger dans l'admin Django (LocationPoint).
QUARTIERS = [
    ("Aïn Talh", "عين الطلح", 18.0530, -15.9420),
    ("Arafat", "عرفات", 18.0640, -15.9560),
    ("Bawadi", "بوادي", 18.0700, -15.9300),
    ("Bou7dide", "بوحديدة", 18.1450, -15.9250),
    ("Capital", "كبتال", 18.0930, -15.9720),
    ("Carrefour", "كرفور", 18.0660, -15.9540),
    ("Centre émetteur", "سانتر أمتير", 18.1050, -15.9850),
    ("Cinquième", "سينكيم", 18.0800, -15.9450),
    ("Cité plage", "سيت ابلاج", 18.1000, -16.0350),
    ("Dar El Barke", "دار البركة", 18.0900, -15.9200),
    ("Dar Naim", "دار النعيم", 18.1350, -15.9400),
    ("Haysakin", "الحي الساكن", 18.1100, -15.9550),
    ("Goudron chara", "گدروه الشارة", 18.0950, -15.9500),
    ("Ksar", "لكصر", 18.1010, -15.9640),
    ("Lmechrou3", "المشروع", 18.0880, -15.9350),
    ("Mela7", "ملح", 18.0950, -16.0100),
    ("Péka", "بيكا", 18.0850, -15.9750),
    ("Route Nouadhibou", "طريق نواذيبو", 18.1200, -15.9900),
    ("Sahrawi", "صحراوي", 18.0980, -15.9600),
    ("Sixième", "سيزيم", 18.0770, -15.9500),
    ("Soukouk", "صوكوك", 18.0900, -15.9650),
    ("Tevragh zaïne", "تفرغ زينة", 18.0920, -15.9950),
    ("Teyaret", "تيارت", 18.1180, -15.9720),
    ("Tinsweylem", "تنسويليم", 18.1250, -15.9600),
    ("Toujounin", "توجنين", 18.0980, -15.9080),
    ("Velouje", "فلوجة", 18.0830, -15.9400),
    ("Za3tar", "زعتر", 18.0800, -15.9250),
    ("Qandahar", "قندهار", 18.0300, -15.8950),
    ("Tarhil", "الترحيل", 18.0200, -15.8850),
]

# code (== Category.type), name_fr, name_ar, marge, is_scheduled
DELIVERY_TYPES = [
    ("poisson", "Poisson", "سمك", 50, False),
    ("l7am", "Viande", "لحم", 50, False),
    ("sbou7", "Sbou7", "سبوع", 50, False),
    ("mes_plats", "Mes plats", "أطباقي", 50, True),
]


def seed(apps, schema_editor):
    LocationPoint = apps.get_model("api", "LocationPoint")
    DeliveryProvider = apps.get_model("api", "DeliveryProvider")
    DeliveryType = apps.get_model("api", "DeliveryType")

    for name, name_ar, lat, lng in QUARTIERS:
        LocationPoint.objects.get_or_create(
            name=name,
            defaults={"name_ar": name_ar, "lat": lat, "lng": lng},
        )

    origin, _ = LocationPoint.objects.get_or_create(
        name="Point de départ Jemli (à définir)",
        defaults={"name_ar": "", "lat": 18.0858, "lng": -15.9785, "is_active": False},
    )

    jemli, _ = DeliveryProvider.objects.get_or_create(
        code="jemli",
        defaults={
            "name": "Jemli",
            "base_url": "https://api-jemli.oneposts.io/api/third-party/",
            "origin_point": origin,
            "webhook_secret": uuid.uuid4().hex,
        },
    )
    if not jemli.webhook_secret:
        jemli.webhook_secret = uuid.uuid4().hex
        jemli.save(update_fields=["webhook_secret"])

    for code, name_fr, name_ar, margin, is_scheduled in DELIVERY_TYPES:
        DeliveryType.objects.get_or_create(
            code=code,
            defaults={
                "name_fr": name_fr,
                "name_ar": name_ar,
                "delivery_margin": margin,
                "is_scheduled": is_scheduled,
                "provider": jemli,
            },
        )


def unseed(apps, schema_editor):
    DeliveryType = apps.get_model("api", "DeliveryType")
    DeliveryProvider = apps.get_model("api", "DeliveryProvider")
    LocationPoint = apps.get_model("api", "LocationPoint")

    DeliveryType.objects.filter(code__in=[c for c, *_ in DELIVERY_TYPES]).delete()
    DeliveryProvider.objects.filter(code="jemli").delete()
    LocationPoint.objects.filter(name="Point de départ Jemli (à définir)").delete()
    LocationPoint.objects.filter(name__in=[n for n, *_ in QUARTIERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0015_deliveryprovider_locationpoint_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
