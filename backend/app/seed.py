"""Reference data + fictional demo scenario.

Usage:
  python -m app.seed reference            # counties, towns, roles, medicine catalog (idempotent)
  python -m app.seed demo                 # reference + fictional demo scenario
  python -m app.seed reset-demo           # remove ONLY demo records and recreate the scenario
  python -m app.seed create-admin EMAIL "Full Name"   # password from ADMIN_PASSWORD or prompt

All demo facilities are fictional, flagged is_demo=True and named "(Demo)". They are not real
facilities, and their stock levels are synthetic.
"""

import getpass
import os
import sys
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.models import (
    Alert,
    AlertType,
    County,
    Facility,
    FacilityMembership,
    FacilityStatus,
    InboundMessage,
    InventoryItem,
    Location,
    Medicine,
    PickupSchedule,
    MovementType,
    NotificationDelivery,
    RippleEvidence,
    Role,
    RolePermission,
    StockMovement,
    StockReport,
    StockReportVerification,
    User,
    UserRole,
    UssdSession,
)
from app.permissions import ROLE_DESCRIPTIONS, ROLE_PERMISSIONS
from app.security import hash_password
from app.services.inventory import create_inventory

COUNTIES = [
    "Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita-Taveta", "Garissa", "Wajir", "Mandera", "Marsabit",
    "Isiolo", "Meru", "Tharaka-Nithi", "Embu", "Kitui", "Machakos", "Makueni", "Nyandarua", "Nyeri", "Kirinyaga",
    "Murang'a", "Kiambu", "Turkana", "West Pokot", "Samburu", "Trans Nzoia", "Uasin Gishu", "Elgeyo-Marakwet",
    "Nandi", "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado", "Kericho", "Bomet", "Kakamega", "Vihiga",
    "Bungoma", "Busia", "Siaya", "Kisumu", "Homa Bay", "Migori", "Kisii", "Nyamira", "Nairobi",
]

# Approximate sub-county / town-centre coordinates (public geographic knowledge).
# Extra names such as Kilimani or Nairobi CBD are kept so demo facilities still resolve.
LOCATIONS = {
    "Mombasa": [
        ("Changamwe", -4.0260, 39.6300), ("Jomvu", -4.0100, 39.6100), ("Kisauni", -4.0000, 39.7000),
        ("Nyali", -4.0225, 39.7139), ("Likoni", -4.0833, 39.6667), ("Mvita", -4.0540, 39.6670),
        ("Mombasa Island", -4.0435, 39.6682),
    ],
    "Kwale": [("Msambweni", -4.4667, 39.4833), ("Lungalunga", -4.5500, 39.1167), ("Matuga", -4.1667, 39.5667),
              ("Kinango", -4.1370, 39.3150)],
    "Kilifi": [
        ("Kilifi North", -3.5100, 39.8500), ("Kilifi South", -3.8000, 39.6700), ("Kaloleni", -3.8200, 39.6200),
        ("Rabai", -3.9200, 39.5700), ("Ganze", -3.5300, 39.6900), ("Malindi", -3.2192, 40.1169),
        ("Magarini", -3.0000, 40.0500), ("Kilifi Town", -3.6305, 39.8499),
    ],
    "Tana River": [("Garsen", -2.2700, 40.1200), ("Galole", -1.5000, 40.0000), ("Bura", -1.1000, 39.9500)],
    "Lamu": [("Lamu East", -2.2700, 40.9000), ("Lamu West", -2.2717, 40.9020)],
    "Taita-Taveta": [("Taveta", -3.4000, 37.6833), ("Wundanyi", -3.4000, 38.3600), ("Mwatate", -3.5000, 38.3800),
                     ("Voi", -3.3961, 38.5561)],
    "Garissa": [
        ("Garissa Township", -0.4536, 39.6461), ("Balambala", -0.0500, 39.0500), ("Lagdera", 0.0500, 39.2000),
        ("Dadaab", 0.0536, 40.3089), ("Fafi", -0.2000, 40.4000), ("Ijara", -1.6000, 40.5000),
        ("Garissa Town", -0.4532, 39.6461),
    ],
    "Wajir": [("Wajir North", 2.3000, 40.0000), ("Wajir East", 1.7500, 40.0600), ("Tarbaj", 2.0000, 40.1000),
              ("Wajir West", 1.7500, 39.6000), ("Eldas", 2.1000, 39.5000), ("Wajir South", 1.2000, 40.2000)],
    "Mandera": [("Mandera West", 3.6000, 40.5000), ("Banissa", 3.9000, 40.3500), ("Mandera North", 3.9500, 41.7000),
                ("Mandera South", 3.2000, 41.2000), ("Mandera East", 3.9366, 41.8670), ("Lafey", 3.1000, 41.7000)],
    "Marsabit": [("Moyale", 3.5270, 39.0560), ("North Horr", 3.3000, 37.0000), ("Saku", 2.3280, 37.9900),
                 ("Laisamis", 1.6000, 37.8000)],
    "Isiolo": [("Isiolo North", 0.3546, 37.5822), ("Isiolo South", 0.0500, 38.0000)],
    "Meru": [
        ("Igembe South", 0.2000, 37.9500), ("Igembe Central", 0.3500, 37.9800), ("Igembe North", 0.5000, 38.0500),
        ("Tigania West", 0.1500, 37.7800), ("Tigania East", 0.1800, 37.9000), ("North Imenti", 0.0800, 37.6500),
        ("Buuri", 0.1000, 37.5500), ("Central Imenti", 0.0200, 37.6500), ("South Imenti", -0.0500, 37.6500),
        ("Meru Town", 0.0470, 37.6490),
    ],
    "Tharaka-Nithi": [("Maara", -0.3000, 37.6500), ("Chuka/Igambang'ombe", -0.3333, 37.6500),
                      ("Tharaka", -0.1800, 37.9300)],
    "Embu": [("Manyatta", -0.5300, 37.4500), ("Runyenjes", -0.4200, 37.5600), ("Mbeere South", -0.7000, 37.5500),
             ("Mbeere North", -0.5800, 37.6500)],
    "Kitui": [
        ("Mwingi North", -0.8500, 38.1500), ("Mwingi West", -0.9300, 38.0000), ("Mwingi Central", -0.9340, 38.0600),
        ("Kitui West", -1.3000, 37.8500), ("Kitui Rural", -1.4000, 38.0000), ("Kitui Central", -1.3670, 38.0100),
        ("Kitui East", -1.4500, 38.2500), ("Kitui South", -1.7000, 38.2000),
    ],
    "Machakos": [
        ("Masinga", -0.9500, 37.6000), ("Yatta", -1.2300, 37.5000), ("Kangundo", -1.3000, 37.3500),
        ("Matungulu", -1.2500, 37.2300), ("Kathiani", -1.4500, 37.3000), ("Mavoko", -1.4500, 36.9800),
        ("Machakos Town", -1.5177, 37.2634), ("Mwala", -1.3500, 37.4500), ("Athi River", -1.4560, 36.9780),
    ],
    "Makueni": [("Mbooni", -1.6700, 37.4700), ("Kilome", -1.8500, 37.3000), ("Kaiti", -1.7800, 37.4700),
                ("Makueni", -1.8040, 37.6240), ("Kibwezi West", -2.3500, 37.8500), ("Kibwezi East", -2.4100, 37.9700)],
    "Nyandarua": [("Kinangop", -0.6500, 36.5700), ("Kipipiri", -0.4500, 36.4800), ("Ol Kalou", -0.2717, 36.3780),
                  ("Ol Jorok", -0.1500, 36.3500), ("Ndaragwa", -0.0500, 36.5200)],
    "Nyeri": [("Tetu", -0.4500, 36.9200), ("Kieni", -0.2500, 37.0000), ("Mathira", -0.3800, 37.0800),
              ("Othaya", -0.5450, 36.9440), ("Mukurweini", -0.5600, 37.0500), ("Nyeri Town", -0.4201, 36.9476)],
    "Kirinyaga": [("Mwea", -0.6800, 37.3700), ("Gichugu", -0.5000, 37.3500), ("Ndia", -0.5500, 37.2500),
                  ("Kirinyaga Central", -0.5000, 37.2800)],
    "Murang'a": [("Kangema", -0.6800, 36.8500), ("Mathioya", -0.7000, 36.9200), ("Kiharu", -0.7210, 37.1530),
                 ("Kigumo", -0.8000, 36.9500), ("Maragwa", -0.8000, 37.1300), ("Kandara", -0.9000, 37.0000),
                 ("Gatanga", -0.9300, 37.0000)],
    "Kiambu": [
        ("Gatundu South", -0.9800, 36.9000), ("Gatundu North", -0.9000, 36.8500), ("Juja", -1.1000, 37.0100),
        ("Thika Town", -1.0388, 37.0834), ("Ruiru", -1.1466, 36.9609), ("Githunguri", -1.0600, 36.7800),
        ("Kiambu", -1.1714, 36.8356), ("Kiambaa", -1.1700, 36.7800), ("Kabete", -1.2500, 36.7300),
        ("Kikuyu", -1.2463, 36.6629), ("Limuru", -1.1100, 36.6500), ("Lari", -1.0000, 36.6000),
        ("Thika", -1.0388, 37.0834), ("Kiambu Town", -1.1714, 36.8356),
    ],
    "Turkana": [("Turkana North", 4.3000, 35.6000), ("Turkana West", 3.5000, 34.8500),
                ("Turkana Central", 3.1191, 35.5973), ("Loima", 2.8000, 35.3000), ("Turkana South", 2.3000, 35.6000),
                ("Turkana East", 2.5000, 36.0000), ("Lodwar", 3.1191, 35.5973)],
    "West Pokot": [("Kapenguria", 1.2389, 35.1119), ("Sigor", 1.5000, 35.4700), ("Kacheliba", 1.4500, 35.0000),
                   ("Pokot South", 1.1500, 35.3500)],
    "Samburu": [("Samburu West", 1.1000, 36.7000), ("Samburu North", 2.0000, 36.9000),
                ("Samburu East", 1.2500, 37.5000)],
    "Trans Nzoia": [("Kwanza", 1.1000, 35.0000), ("Endebess", 1.0700, 34.8500), ("Saboti", 1.0500, 34.9500),
                    ("Kiminini", 0.9500, 35.0500), ("Cherangany", 1.0400, 35.2000)],
    "Uasin Gishu": [("Soy", 0.6500, 35.2000), ("Turbo", 0.6300, 35.1500), ("Moiben", 0.7000, 35.3500),
                    ("Ainabkoi", 0.4000, 35.4500), ("Kapseret", 0.4500, 35.2700), ("Kesses", 0.4000, 35.3200),
                    ("Eldoret", 0.5143, 35.2698)],
    "Elgeyo-Marakwet": [("Marakwet East", 1.0500, 35.6000), ("Marakwet West", 0.9500, 35.5000),
                        ("Keiyo North", 0.6700, 35.5000), ("Keiyo South", 0.4500, 35.5500)],
    "Nandi": [("Tinderet", 0.1500, 35.2500), ("Aldai", 0.2000, 35.1000), ("Nandi Hills", 0.1030, 35.1760),
              ("Chesumei", 0.3500, 35.1500), ("Emgwen", 0.3600, 35.1200), ("Mosop", 0.5000, 35.1000)],
    "Baringo": [("Tiaty", 1.0000, 36.1500), ("Baringo North", 0.7500, 35.8500), ("Baringo Central", 0.4667, 35.9667),
                ("Baringo South", 0.4500, 36.1000), ("Mogotio", 0.1500, 35.9500), ("Eldama Ravine", 0.0500, 35.7200)],
    "Laikipia": [("Laikipia West", 0.2000, 36.4500), ("Laikipia East", 0.0273, 37.0728),
                 ("Laikipia North", 0.6000, 36.8500)],
    "Nakuru": [
        ("Molo", -0.2480, 35.7370), ("Njoro", -0.3440, 35.9440), ("Naivasha", -0.7167, 36.4333),
        ("Gilgil", -0.5000, 36.3200), ("Kuresoi South", -0.4000, 35.6500), ("Kuresoi North", -0.2500, 35.7000),
        ("Subukia", -0.1500, 36.1500), ("Rongai", -0.1700, 35.8600), ("Bahati", -0.1600, 36.1500),
        ("Nakuru Town West", -0.3031, 36.0500), ("Nakuru Town East", -0.2830, 36.0800),
        ("Nakuru Town", -0.3031, 36.0800),
    ],
    "Narok": [("Kilgoris", -1.0000, 34.8833), ("Emurua Dikirr", -0.8500, 35.1500), ("Narok North", -1.0800, 35.8700),
              ("Narok East", -1.2000, 36.0000), ("Narok South", -1.4000, 35.7000), ("Narok West", -1.2500, 35.4000)],
    "Kajiado": [
        ("Kajiado North", -1.3700, 36.7000), ("Kajiado Central", -1.8500, 36.7800), ("Kajiado East", -1.5500, 37.0500),
        ("Kajiado West", -1.8500, 36.4000), ("Kajiado South", -2.1000, 37.0000),
        ("Kitengela", -1.4746, 36.9606), ("Ngong", -1.3524, 36.6600),
    ],
    "Kericho": [("Kipkelion East", -0.2000, 35.4500), ("Kipkelion West", -0.2000, 35.3500),
                ("Ainamoi", -0.3680, 35.2830), ("Bureti", -0.5000, 35.2000), ("Belgut", -0.4000, 35.2000),
                ("Sigowet/Soin", -0.4500, 35.1000)],
    "Bomet": [("Sotik", -0.6833, 35.3500), ("Chepalungu", -0.8500, 35.2500), ("Bomet East", -0.7800, 35.4000),
              ("Bomet Central", -0.7810, 35.3410), ("Konoin", -0.6000, 35.3000)],
    "Kakamega": [
        ("Lugari", 0.6500, 34.8500), ("Likuyani", 0.6200, 35.0200), ("Malava", 0.4500, 34.8500),
        ("Lurambi", 0.2827, 34.7519), ("Navakholo", 0.4000, 34.7000), ("Mumias West", 0.3350, 34.4860),
        ("Mumias East", 0.3360, 34.5200), ("Matungu", 0.4200, 34.4800), ("Butere", 0.2200, 34.4900),
        ("Khwisero", 0.1700, 34.5700), ("Shinyalu", 0.2300, 34.8200), ("Ikolomani", 0.2000, 34.7300),
        ("Kakamega Town", 0.2827, 34.7519),
    ],
    "Vihiga": [("Vihiga", 0.0820, 34.7250), ("Sabatia", 0.1200, 34.8000), ("Hamisi", 0.0800, 34.8500),
               ("Luanda", 0.0300, 34.5800), ("Emuhaya", 0.0600, 34.6300)],
    "Bungoma": [
        ("Mt. Elgon", 0.8800, 34.5800), ("Sirisia", 0.7500, 34.5000), ("Kabuchai", 0.7000, 34.6000),
        ("Bumula", 0.5500, 34.5000), ("Kanduyi", 0.5635, 34.5606), ("Webuye East", 0.6000, 34.7700),
        ("Webuye West", 0.6167, 34.7667), ("Kimilili", 0.7833, 34.7167), ("Tongaren", 0.7500, 34.9000),
    ],
    "Busia": [("Teso North", 0.6500, 34.2500), ("Teso South", 0.5000, 34.2000), ("Nambale", 0.4500, 34.2500),
              ("Matayos", 0.4300, 34.1500), ("Butula", 0.3400, 34.2500), ("Funyula", 0.2800, 34.0200),
              ("Budalangi", 0.1500, 33.9800)],
    "Siaya": [("Ugenya", 0.2000, 34.2000), ("Ugunja", 0.1800, 34.2900), ("Alego Usonga", 0.0607, 34.2881),
              ("Gem", 0.0500, 34.4500), ("Bondo", -0.0980, 34.2690), ("Rarieda", -0.1700, 34.2500)],
    "Kisumu": [
        ("Kisumu East", -0.0917, 34.8000), ("Kisumu West", -0.1000, 34.7000), ("Kisumu Central", -0.0917, 34.7680),
        ("Seme", -0.1500, 34.6000), ("Nyando", -0.1800, 34.9200), ("Muhoroni", -0.1500, 35.2000),
        ("Nyakach", -0.3000, 34.9000), ("Kondele", -0.0868, 34.7750),
    ],
    "Homa Bay": [
        ("Kasipul", -0.4500, 34.6500), ("Kabondo Kasipul", -0.4000, 34.8000), ("Karachuonyo", -0.4500, 34.5000),
        ("Rangwe", -0.5300, 34.5600), ("Homa Bay Town", -0.5273, 34.4571), ("Ndhiwa", -0.7300, 34.3700),
        ("Mbita", -0.4250, 34.2050), ("Suba", -0.5000, 34.1500),
    ],
    "Migori": [
        ("Rongo", -0.7550, 34.6000), ("Awendo", -0.9000, 34.5300), ("Suna East", -1.0634, 34.4731),
        ("Suna West", -1.0700, 34.4300), ("Uriri", -0.9500, 34.4800), ("Nyatike", -0.9000, 34.1500),
        ("Kuria West", -1.2500, 34.4800), ("Kuria East", -1.2500, 34.5800),
    ],
    "Kisii": [
        ("Bonchari", -0.7000, 34.7000), ("South Mugirango", -0.8500, 34.7000), ("Bomachoge Borabu", -0.8500, 34.8500),
        ("Bobasi", -0.9000, 34.8000), ("Bomachoge Chache", -0.8000, 34.8000), ("Nyaribari Masaba", -0.7000, 34.8500),
        ("Nyaribari Chache", -0.6773, 34.7796), ("Kitutu Chache North", -0.6500, 34.7500),
        ("Kitutu Chache South", -0.7000, 34.7700),
    ],
    "Nyamira": [("Kitutu Masaba", -0.5600, 34.9500), ("West Mugirango", -0.5700, 34.9000),
                ("North Mugirango", -0.5000, 35.0000), ("Borabu", -0.7000, 35.0000)],
    "Nairobi": [
        ("Westlands", -1.2676, 36.8108), ("Dagoretti North", -1.2921, 36.7600), ("Dagoretti South", -1.3100, 36.7400),
        ("Langata", -1.3667, 36.7333), ("Kibra", -1.3133, 36.7876), ("Roysambu", -1.2194, 36.8869),
        ("Kasarani", -1.2216, 36.8969), ("Ruaraka", -1.2450, 36.8800), ("Embakasi South", -1.3500, 36.9000),
        ("Embakasi North", -1.2500, 36.9200), ("Embakasi Central", -1.3000, 36.9100),
        ("Embakasi East", -1.3200, 36.9400), ("Embakasi West", -1.3000, 36.8700), ("Makadara", -1.2921, 36.8667),
        ("Kamukunji", -1.2833, 36.8500), ("Starehe", -1.2833, 36.8167), ("Mathare", -1.2597, 36.8581),
        ("Kilimani", -1.2921, 36.7856), ("Embakasi", -1.3197, 36.8947), ("Nairobi CBD", -1.2864, 36.8172),
        ("Kibera", -1.3133, 36.7876), ("Dagoretti", -1.3000, 36.7500),
    ],
}

# Generic names follow the Kenya Essential Medicines List style. Brand names are search aliases only.
# Last flag: is_long_term — typically collected on a repeating schedule. Not a diagnosis.
MEDICINES = [
    ("MED001", "Amoxicillin", "Amoxil", "500 mg", "capsule", "capsule", "Antibiotic", True, False),
    ("MED002", "Paracetamol", "Panadol,Calpol", "500 mg", "tablet", "tablet", "Analgesic", False, False),
    ("MED003", "Metformin", "Glucophage", "500 mg", "tablet", "tablet", "Antidiabetic", True, True),
    ("MED004", "Amlodipine", "Norvasc", "5 mg", "tablet", "tablet", "Antihypertensive", True, True),
    ("MED005", "Artemether + Lumefantrine", "Coartem,AL", "20 mg/120 mg", "tablet", "tablet", "Antimalarial", True, False),
    ("MED006", "Oral Rehydration Salts", "ORS", "20.5 g/L", "sachet", "sachet", "Rehydration", False, False),
    ("MED007", "Zinc sulfate", "", "20 mg", "dispersible tablet", "tablet", "Supplement", False, False),
    ("MED008", "Salbutamol", "Ventolin", "100 mcg/dose", "inhaler", "inhaler", "Respiratory", True, True),
    ("MED009", "Insulin soluble human", "Actrapid", "100 IU/mL 10 mL", "injection", "vial", "Antidiabetic", True, True),
    ("MED010", "Ferrous sulfate + Folic acid", "", "200 mg/0.4 mg", "tablet", "tablet", "Supplement", False, True),
    ("MED011", "Cotrimoxazole", "Septrin", "960 mg", "tablet", "tablet", "Antibiotic", True, False),
    ("MED012", "Losartan", "Cozaar", "50 mg", "tablet", "tablet", "Antihypertensive", True, True),
    ("MED013", "Ibuprofen", "Brufen", "400 mg", "tablet", "tablet", "Analgesic", False, False),
    ("MED014", "Omeprazole", "Losec", "20 mg", "capsule", "capsule", "Gastrointestinal", True, False),
    ("MED015", "Medroxyprogesterone acetate", "Depo-Provera", "150 mg/mL", "injection", "vial",
     "Family planning", True, True),
    ("MED016", "Tenofovir + Lamivudine + Dolutegravir", "TLD", "300/300/50 mg", "tablet", "tablet",
     "Antiretroviral", True, True),
    ("MED017", "Hydrochlorothiazide", "", "25 mg", "tablet", "tablet", "Antihypertensive", True, True),
    ("MED018", "Ceftriaxone", "Rocephin", "1 g", "powder for injection", "vial", "Antibiotic", True, False),
    ("MED019", "Rifampicin + Isoniazid + Pyrazinamide + Ethambutol", "RHZE", "150/75/400/275 mg",
     "tablet", "tablet", "Antitubercular", True, True),
    ("MED020", "Rifampicin + Isoniazid", "RH", "150/75 mg", "tablet", "tablet", "Antitubercular", True, True),
    ("MED021", "Isoniazid", "", "300 mg", "tablet", "tablet", "Antitubercular", True, True),
]

DEMO_EMAIL_DOMAIN = "demo.stockout.example"


def seed_reference(db: Session) -> None:
    for role, desc in ROLE_DESCRIPTIONS.items():
        if not db.get(Role, role.value):
            db.add(Role(name=role.value, description=desc))
    db.flush()
    db.execute(delete(RolePermission))
    for role, perms in ROLE_PERMISSIONS.items():
        for p in sorted(perms):
            db.add(RolePermission(role_name=str(role), permission=p))
    missing_areas = [n for n in COUNTIES if n not in LOCATIONS]
    if missing_areas:
        raise RuntimeError(f"LOCATIONS is missing counties: {', '.join(missing_areas)}")
    for i, name in enumerate(COUNTIES, start=1):
        if not db.query(County).filter_by(name=name).first():
            db.add(County(code=f"{i:03d}", name=name))
    db.flush()
    for county_name, towns in LOCATIONS.items():
        c = db.query(County).filter_by(name=county_name).one()
        for town, lat, lng in towns:
            if not db.query(Location).filter_by(county_id=c.id, name=town).first():
                db.add(Location(county_id=c.id, name=town, latitude=lat, longitude=lng))
    for code, gen, brands, strength, form, unit, cat, rx, long_term in MEDICINES:
        row = db.query(Medicine).filter_by(code=code).first()
        if row is None:
            db.add(Medicine(code=code, generic_name=gen, brand_names=brands, strength=strength, dosage_form=form,
                            base_unit=unit, category=cat, requires_prescription=rx, is_long_term=long_term))
        else:
            row.is_long_term = long_term
            row.category = cat
    db.commit()


def _user(db: Session, email: str, name: str, role: str, phone: str | None) -> User:
    u = db.query(User).filter_by(email=email).one_or_none()
    pw = hash_password(get_settings().demo_password)
    if u is None:
        u = User(email=email, full_name=name, role=role, phone=phone, password_hash=pw, is_demo=True)
        db.add(u)
        db.flush()
    else:
        u.full_name, u.role, u.phone, u.password_hash, u.is_active = name, role, phone, pw, True
    return u


def _loc(db: Session, county: str, town: str) -> tuple[County, Location]:
    c = db.query(County).filter_by(name=county).one()
    return c, db.query(Location).filter_by(county_id=c.id, name=town).one()


DEMO_FACILITIES = [
    # code, name, type, county, town, lat, lng, status, show_qty
    ("FAC-D001", "Mwangaza Community Pharmacy (Demo)", "pharmacy", "Nairobi", "Westlands", -1.2649, 36.8031,
     "approved", True),
    ("FAC-D002", "Tumaini Health Centre (Demo)", "health_centre", "Nairobi", "Kilimani", -1.2897, 36.7869,
     "approved", False),
    ("FAC-D003", "Baraka Medical Clinic (Demo)", "clinic", "Nairobi", "Westlands", -1.2712, 36.8125,
     "approved", True),
    ("FAC-D004", "Upendo Chemist (Demo)", "pharmacy", "Nairobi", "Kilimani", -1.2950, 36.7820, "approved", True),
    ("FAC-D005", "Jamii Dispensary (Demo)", "dispensary", "Kiambu", "Ruiru", -1.1450, 36.9580, "approved", True),
    ("FAC-D006", "Neema Pharmacy (Demo)", "pharmacy", "Nairobi", "Embakasi", -1.3180, 36.8920, "pending", False),
]

# facility code -> [(medicine code, quantity, min threshold)]
DEMO_STOCK = {
    "FAC-D001": [("MED001", 400, 100), ("MED002", 2500, 500), ("MED003", 900, 300), ("MED005", 240, 72),
                 ("MED006", 150, 40), ("MED008", 12, 5), ("MED016", 240, 80), ("MED019", 120, 40)],
    "FAC-D002": [("MED001", 60, 100), ("MED002", 1800, 500), ("MED005", 30, 72), ("MED006", 300, 60),
                 ("MED010", 1200, 300), ("MED015", 40, 10), ("MED016", 18, 80), ("MED019", 0, 40)],
    "FAC-D003": [("MED001", 250, 80), ("MED002", 900, 300), ("MED004", 600, 150), ("MED013", 700, 200),
                 ("MED016", 400, 80), ("MED019", 600, 40)],
    "FAC-D004": [("MED001", 300, 50), ("MED002", 1000, 200), ("MED003", 500, 100)],
    "FAC-D005": [("MED001", 500, 100), ("MED002", 1500, 300), ("MED005", 180, 72), ("MED006", 200, 50),
                 ("MED016", 200, 80), ("MED019", 180, 40)],
}

DEMO_STAFF = [
    # email local part, name, role, facility code, sms phone
    ("pharmacist.mwangaza", "Demo Pharmacist (Mwangaza)", UserRole.FACILITY_ADMIN, "FAC-D001", "+254700000011"),
    ("staff.mwangaza", "Demo Stock Clerk (Mwangaza)", UserRole.FACILITY_STAFF, "FAC-D001", "+254700000012"),
    ("admin.tumaini", "Demo Facility Admin (Tumaini)", UserRole.FACILITY_ADMIN, "FAC-D002", "+254700000021"),
    ("admin.baraka", "Demo Facility Admin (Baraka)", UserRole.FACILITY_ADMIN, "FAC-D003", "+254700000031"),
    ("admin.upendo", "Demo Facility Admin (Upendo)", UserRole.FACILITY_ADMIN, "FAC-D004", "+254700000041"),
    ("admin.jamii", "Demo Facility Admin (Jamii)", UserRole.FACILITY_ADMIN, "FAC-D005", "+254700000051"),
    ("admin.neema", "Demo Facility Admin (Neema)", UserRole.FACILITY_ADMIN, "FAC-D006", "+254700000061"),
]


def _backfill_history(db: Session, item: InventoryItem, days: int, daily: int) -> None:
    """Rewrite the item's history as `days` of daily dispensing ending at the current quantity."""
    now = utcnow()
    final = item.quantity
    start = final + days * daily
    db.query(StockMovement).filter_by(inventory_id=item.id).delete()
    t0 = now - timedelta(days=days, hours=2)
    db.add(StockMovement(inventory_id=item.id, movement_type=MovementType.INITIAL, quantity_delta=start,
                         quantity_before=0, quantity_after=start, reason="Initial stock record (demo)",
                         source="demo", created_at=t0))
    q = start
    for d in range(days):
        db.add(StockMovement(inventory_id=item.id, movement_type=MovementType.DISPENSE, quantity_delta=-daily,
                             quantity_before=q, quantity_after=q - daily, reason="Daily dispensing (demo)",
                             source="demo", created_at=t0 + timedelta(days=d + 1)))
        q -= daily


def seed_demo(db: Session) -> dict:
    seed_reference(db)
    s = get_settings()
    staff_phone = s.demo_staff_phone or None
    _user(db, f"admin@{DEMO_EMAIL_DOMAIN}", "Demo System Administrator", UserRole.SYSTEM_ADMIN,
          staff_phone or "+254700000001")
    facilities = {}
    for code, name, ftype, county, town, lat, lng, status, show in DEMO_FACILITIES:
        c, loc = _loc(db, county, town)
        f = Facility(code=code, name=name, facility_type=ftype, county_id=c.id, location_id=loc.id,
                     address=f"Fictional demo address, {town}", phone=None, latitude=lat, longitude=lng,
                     status=status, public_show_quantity=show, is_demo=True,
                     approved_at=utcnow() if status == "approved" else None)
        db.add(f)
        facilities[code] = f
    db.flush()
    for local, name, role, fcode, phone in DEMO_STAFF:
        if staff_phone and local == "pharmacist.mwangaza":
            phone = staff_phone
        u = _user(db, f"{local}@{DEMO_EMAIL_DOMAIN}", name, role, phone)
        db.add(FacilityMembership(user_id=u.id, facility_id=facilities[fcode].id, role=role, can_update_stock=True,
                                  sms_phone=phone))
    db.flush()

    meds = {m.code: m for m in db.query(Medicine)}
    admin = db.query(User).filter_by(email=f"admin@{DEMO_EMAIL_DOMAIN}").one()
    items = {}
    for fcode, rows in DEMO_STOCK.items():
        for mcode, qty, minimum in rows:
            out = create_inventory(db, facilities[fcode], meds[mcode], qty, minimum, admin, source="demo",
                                   internal_notes="Synthetic demo stock")
            items[(fcode, mcode)] = out.item
    db.flush()

    # Consumption history so days-remaining estimates are meaningful for some items.
    _backfill_history(db, items[("FAC-D001", "MED001")], 21, 25)
    _backfill_history(db, items[("FAC-D002", "MED001")], 14, 12)
    _backfill_history(db, items[("FAC-D001", "MED003")], 14, 30)

    # Upendo's records are 10 days old -> shown as "stale" publicly.
    old = utcnow() - timedelta(days=10)
    for (fcode, _), it in items.items():
        if fcode == "FAC-D004":
            it.last_updated_at = old
            db.query(StockMovement).filter_by(inventory_id=it.id).update({"created_at": old})
    # An expiring batch for the expiry warning.
    items[("FAC-D003", "MED004")].batch_number = "DEMO-B17"
    items[("FAC-D003", "MED004")].expiry_date = (utcnow() + timedelta(days=25)).date()

    # Alerts raised by create_inventory reflect the seeded state; backdate them to look realistic.
    for a in db.query(Alert).filter(Alert.facility_id.in_([f.id for f in facilities.values()])):
        a.created_at = utcnow() - timedelta(hours=3)
    # Seeded alerts should not trigger SMS on reset.
    db.query(NotificationDelivery).filter(NotificationDelivery.is_demo.is_(True),
                                          NotificationDelivery.status == "queued").delete()

    # Fictional patient reminder: usual clinic is low on TLD so the refill finder shows alternatives.
    from app.services.pickup import today_ke, upsert_schedule
    upsert_schedule(
        db, phone="+254700000088", medicine=meds["MED016"], county_id=facilities["FAC-D002"].county_id,
        next_pickup_on=today_ke() + timedelta(days=2), interval_days=30, remind_days_before=3,
        preferred_facility=facilities["FAC-D002"], consent_source="demo", is_demo=True,
    )
    db.commit()
    return {"facilities": len(facilities), "inventory_items": len(items), "users": len(DEMO_STAFF) + 1}


def clear_demo(db: Session) -> dict:
    ids = [f for (f,) in db.query(Facility.id).filter(Facility.is_demo.is_(True))]
    ripple_ids = []
    for a in db.query(Alert).filter(Alert.alert_type == AlertType.RIPPLE):
        facs = {e.facility_id for e in a.ripple_evidence}
        if (facs and facs <= set(ids)) or (not facs and a.evidence.get("is_demo")):
            ripple_ids.append(a.id)
    inv_ids = select(InventoryItem.id).where(InventoryItem.facility_id.in_(ids))
    report_ids = select(StockReport.id).where(StockReport.facility_id.in_(ids))
    db.execute(delete(RippleEvidence).where(RippleEvidence.facility_id.in_(ids)))
    db.execute(delete(RippleEvidence).where(RippleEvidence.alert_id.in_(ripple_ids)))
    db.execute(delete(NotificationDelivery).where(
        NotificationDelivery.facility_id.in_(ids) | NotificationDelivery.is_demo.is_(True)
        | NotificationDelivery.alert_id.in_(ripple_ids)))
    db.execute(delete(Alert).where(Alert.facility_id.in_(ids) | Alert.id.in_(ripple_ids)))
    db.execute(delete(StockReportVerification).where(StockReportVerification.report_id.in_(report_ids)))
    db.execute(delete(StockReport).where(StockReport.facility_id.in_(ids)))
    db.execute(delete(StockMovement).where(StockMovement.inventory_id.in_(inv_ids)))
    db.execute(delete(InventoryItem).where(InventoryItem.facility_id.in_(ids)))
    db.execute(delete(FacilityMembership).where(FacilityMembership.facility_id.in_(ids)))
    db.execute(delete(Facility).where(Facility.id.in_(ids)))
    db.execute(delete(PickupSchedule).where(PickupSchedule.is_demo.is_(True)))
    db.execute(delete(UssdSession).where(UssdSession.is_simulated.is_(True)))
    db.execute(delete(InboundMessage).where(InboundMessage.provider_message_id.like("SIM-%")))
    db.commit()
    return {"removed_facilities": len(ids), "removed_ripple_alerts": len(ripple_ids)}


def reset_demo(db: Session, keep_user_id: str | None = None) -> dict:
    """Removes demo-flagged records only. Real facilities, users and audit logs are untouched;
    demo user accounts are kept (passwords reset) so active demo sessions stay valid."""
    removed = clear_demo(db)
    created = seed_demo(db)
    return {**removed, **created}


def create_admin(db: Session, email: str, name: str, password: str) -> User:
    seed_reference(db)
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters")
    u = db.query(User).filter_by(email=email.lower()).one_or_none()
    if u:
        raise SystemExit("User already exists")
    u = User(email=email.lower(), full_name=name, role=UserRole.SYSTEM_ADMIN, password_hash=hash_password(password))
    db.add(u)
    db.commit()
    return u


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "demo"
    db = SessionLocal()
    try:
        if cmd == "reference":
            seed_reference(db)
            print("Reference data seeded.")
        elif cmd == "demo":
            if db.query(Facility).filter(Facility.is_demo.is_(True)).first():
                print("Demo data already present. Use 'reset-demo' to restore the scenario.")
                seed_reference(db)
            else:
                print("Demo seeded:", seed_demo(db))
        elif cmd == "reset-demo":
            print("Demo reset:", reset_demo(db))
        elif cmd == "create-admin":
            email, name = argv[2], argv[3]
            pw = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
            create_admin(db, email, name, pw)
            print("Administrator created.")
        else:
            print(__doc__)
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv)
