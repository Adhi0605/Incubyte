"""Deterministic Indian portfolio inventory; prices/specifications are synthetic.

Money returned in the vehicle-input ``price`` field is an exact INR string.
The database adapter in demo.py converts it to integer paise. Photographs are
shared representative model imagery, never evidence of an individual vehicle.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class _Model:
    make: str
    model: str
    category: str
    rupees: int
    fuel: str
    transmission: str
    trims: tuple[str, str]
    info_url: str
    photo: str
    first_year: int = 2017


_MODELS = (
    _Model('Maruti Suzuki', 'Swift', 'Hatchback', 749000, 'Petrol', 'Manual',
           ('VXi', 'ZXi'), 'https://www.marutisuzuki.com/swift', 'swift'),
    _Model('Maruti Suzuki', 'Baleno', 'Hatchback', 875000, 'CNG', 'Manual',
           ('Delta S-CNG', 'Zeta S-CNG'), 'https://www.nexaexperience.com/baleno', 'baleno'),
    _Model('Maruti Suzuki', 'Brezza', 'SUV', 1130000, 'Petrol', 'Automatic',
           ('VXi AT', 'ZXi AT'), 'https://www.marutisuzuki.com/brezza', 'brezza', 2022),
    _Model('Hyundai', 'i20', 'Hatchback', 915000, 'Petrol', 'Manual',
           ('Sportz', 'Asta'), 'https://www.hyundai.com/in/en/find-a-car/i20/highlights', 'i20'),
    _Model('Hyundai', 'Creta', 'SUV', 1690000, 'Diesel', 'Automatic',
           ('S(O) AT', 'SX(O) AT'), 'https://www.hyundai.com/in/en/find-a-car/creta/highlights', 'creta'),
    _Model('Hyundai', 'Venue', 'SUV', 1125000, 'Petrol', 'Manual',
           ('S(O)', 'SX'), 'https://www.hyundai.com/in/en/find-a-car/venue/highlights', 'venue', 2019),
    _Model('Tata', 'Nexon EV', 'SUV', 1575000, 'Electric', 'Automatic',
           ('Fearless', 'Empowered'), 'https://www.tatamotors.com/', 'nexon-ev', 2020),
    _Model('Tata', 'Tiago', 'Hatchback', 635000, 'Petrol', 'Manual',
           ('XT', 'XZ'), 'https://www.tatamotors.com/', 'tiago'),
    _Model('Tata', 'Harrier', 'SUV', 2240000, 'Diesel', 'Automatic',
           ('Adventure AT', 'Fearless AT'), 'https://www.tatamotors.com/', 'harrier', 2019),
    _Model('Mahindra', 'XUV700', 'SUV', 2360000, 'Diesel', 'Automatic',
           ('AX5 AT', 'AX7 AT'), 'https://auto.mahindra.com/suv/xuv700', 'xuv700', 2021),
    _Model('Mahindra', 'Thar', 'SUV', 1580000, 'Petrol', 'Automatic',
           ('LX Hard Top AT', 'LX Convertible AT'), 'https://auto.mahindra.com/suv/thar', 'thar', 2020),
    _Model('Mahindra', 'Scorpio-N', 'SUV', 2150000, 'Diesel', 'Manual',
           ('Z6', 'Z8'), 'https://auto.mahindra.com/suv/scorpio-n', 'scorpio-n', 2022),
    _Model('Kia', 'Seltos', 'SUV', 1820000, 'Petrol', 'Automatic',
           ('HTX IVT', 'GTX DCT'), 'https://www.kia.com/in/our-vehicles/seltos/showroom.html', 'seltos', 2019),
    _Model('Kia', 'Sonet', 'SUV', 1190000, 'Diesel', 'Automatic',
           ('HTX AT', 'GTX+ AT'), 'https://www.kia.com/in/our-vehicles/sonet/showroom.html', 'sonet', 2020),
    _Model('Toyota', 'Innova Hycross', 'MPV', 3150000, 'Hybrid', 'Automatic',
           ('VX Hybrid', 'ZX Hybrid'), 'https://www.toyotabharat.com/showroom/innova/', 'innova-hycross', 2023),
    _Model('Toyota', 'Fortuner', 'SUV', 4150000, 'Diesel', 'Automatic',
           ('4x2 AT', '4x4 AT'), 'https://www.toyotabharat.com/showroom/fortuner/', 'fortuner'),
    _Model('Honda', 'City', 'Sedan', 1475000, 'Petrol', 'Automatic',
           ('V CVT', 'ZX CVT'), 'https://www.hondacarindia.com/honda-city', 'city'),
    _Model('Honda', 'Elevate', 'SUV', 1525000, 'Petrol', 'Manual',
           ('V', 'ZX'), 'https://www.hondacarindia.com/honda-elevate', 'elevate', 2023),
    _Model('Skoda', 'Slavia', 'Sedan', 1675000, 'Petrol', 'Automatic',
           ('Signature AT', 'Prestige AT'), 'https://www.skoda-auto.co.in/models/slavia/slavia', 'slavia', 2022),
    _Model('Skoda', 'Kushaq', 'SUV', 1725000, 'Petrol', 'Manual',
           ('Signature', 'Prestige'), 'https://www.skoda-auto.co.in/models/kushaq/kushaq', 'kushaq', 2021),
    _Model('Volkswagen', 'Virtus', 'Sedan', 1740000, 'Petrol', 'Automatic',
           ('Highline AT', 'Topline AT'), 'https://www.volkswagen.co.in/en/models/virtus.html', 'virtus', 2022),
    _Model('Volkswagen', 'Taigun', 'SUV', 1795000, 'Petrol', 'Manual',
           ('Highline', 'Topline'), 'https://www.volkswagen.co.in/en/models/taigun.html', 'taigun', 2021),
    _Model('Renault', 'Kiger', 'SUV', 975000, 'Petrol', 'Manual',
           ('RXT Turbo', 'RXZ Turbo'), 'https://www.renault.co.in/cars/renault-kiger.html', 'kiger', 2021),
    _Model('MG', 'Hector', 'SUV', 2080000, 'Petrol', 'Automatic',
           ('Smart Pro CVT', 'Sharp Pro CVT'), 'https://www.mgmotor.co.in/vehicles/mghector', 'hector', 2019),
    _Model('Nissan', 'Magnite', 'SUV', 925000, 'Petrol', 'Manual',
           ('N-Connecta Turbo', 'Tekna Turbo'), 'https://www.nissan.in/vehicles/new/magnite.html', 'magnite', 2020),
)

_CITIES = ('Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad', 'Chennai',
           'Pune', 'Ahmedabad', 'Kolkata', 'Kochi', 'Jaipur')
_COLORS = ('Pearl White', 'Steel Grey', 'Midnight Black', 'Silver',
           'Deep Blue', 'Red', 'Bronze', 'Forest Green')
_CREATED = datetime(2025, 10, 1, 9, tzinfo=timezone.utc)


def catalog_vehicles():
    """Return 200 fresh vehicle-input dictionaries, priced in synthetic INR.

    Each of 25 model families has four new and four individual used listings.
    Stock numbers are workspace-local, so each workspace receives identical
    inventory while database IDs remain private. No random/global mutable state.
    """
    vehicles = []
    for model_index, spec in enumerate(_MODELS):
        for variant in range(8):
            index = model_index * 8 + variant
            used = variant >= 4
            year = max(spec.first_year, 2025 - ((model_index + variant) % 8)) if used else 2026
            # Integer arithmetic keeps every price exactly representable in paise.
            rupees = spec.rupees + (variant % 4) * 32000 + model_index * 1250
            if used:
                rupees = rupees * (100 - (2026 - year) * 7) // 100
            created_at = (_CREATED + timedelta(hours=index)).isoformat().replace('+00:00', 'Z')
            photo = _PHOTOS[spec.photo]
            vehicles.append({
                'make': spec.make,
                'model': spec.model,
                'category': spec.category,
                'price': f'{rupees}.00',
                'quantity': (0 if (model_index + variant) % 4 == 0 else 1) if used else
                            (0 if (model_index + variant) % 13 == 0 else 2 + (index % 7)),
                'condition': 'used' if used else 'new',
                'year': year,
                'trim': spec.trims[variant % 2],
                'mileage_km': ((2026 - year) * 9500 + 3500 + index * 83) if used else 0,
                'fuel_type': spec.fuel,
                'transmission': spec.transmission,
                'color': _COLORS[(model_index + variant) % len(_COLORS)],
                'city': _CITIES[(model_index * 3 + variant) % len(_CITIES)],
                'description': (
                    f'{year} {spec.make} {spec.model} {spec.trims[variant % 2]} '
                    f'with {spec.fuel.lower()} power and {spec.transmission.lower()} transmission. '
                    + ('One individual used vehicle; availability is limited to one. ' if used else
                       'New vehicle inventory for a sample Indian dealership. ')
                    + 'Synthetic portfolio listing: price, specifications, mileage and stock are '
                    'illustrative, not a market quote or inspection report. Representative model '
                    'photograph; generation, trim, colour and market may differ from this listing.'
                ),
                'info_url': spec.info_url,
                'images': [{
                    'url': f"/cars/{photo['filename']}",
                    'alt': f'Representative {spec.make} {spec.model} photograph; specification may differ',
                    'credit': photo['credit'],
                    'source_url': photo['source_url'],
                    'license': photo['license'],
                }],
                'stock_number': f'IN-{model_index + 1:02d}-{variant + 1:03d}',
                'vin': '',
                'created_at': created_at,
                'updated_at': created_at,
            })
    return vehicles


# Verified Wikimedia Commons provenance is embedded here so backend-only and
# production builds do not need the frontend source tree or network access.
_PHOTOS = {'swift': {'filename': 'swift.jpg',
           'credit': 'Calreyn88 / Wikimedia Commons',
           'source_url': 'https://commons.wikimedia.org/wiki/File:2024_Suzuki_Swift.jpg',
           'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'baleno': {'filename': 'baleno.jpg',
            'credit': 'Milind Kwatra / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:2022_Maruti_Suzuki_Baleno_Alpha_(India)_front_view.jpg',
            'license': 'CC BY 3.0 (https://creativecommons.org/licenses/by/3.0)'},
 'brezza': {'filename': 'brezza.png',
            'credit': 'DriveSpark / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:2022_Maruti_Suzuki_Brezza_ZXi%2B_(India)_front_view_04.png',
            'license': 'CC BY 3.0 (https://creativecommons.org/licenses/by/3.0)'},
 'i20': {'filename': 'i20.jpg',
         'credit': '© M 93 / Wikimedia Commons',
         'source_url': 'https://commons.wikimedia.org/wiki/File:Hyundai_i20_(III,_Facelift)_%E2%80%93_f_11102025.jpg',
         'license': 'CC BY-SA 3.0 de (https://creativecommons.org/licenses/by-sa/3.0/de/deed.en)'},
 'creta': {'filename': 'creta.jpg',
           'credit': 'Dairokkan9 / Wikimedia Commons',
           'source_url': 'https://commons.wikimedia.org/wiki/File:2021_Hyundai_Creta_SX(O)_CRDi_(India)_front_view.jpg',
           'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'venue': {'filename': 'venue.jpg',
           'credit': 'SsmIntrigue / Wikimedia Commons',
           'source_url': 'https://commons.wikimedia.org/wiki/File:2020_Hyundai_Venue_Ultimate_2019-12-13_2.jpg',
           'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'nexon-ev': {'filename': 'nexon-ev.jpg',
              'credit': 'Rajasekhar1961 / Wikimedia Commons',
              'source_url': 'https://commons.wikimedia.org/wiki/File:Tata_Nexon_EV_in_Hyderabad_02.jpg',
              'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'tiago': {'filename': 'tiago.jpg',
           'credit': 'Dairokkan9 / Wikimedia Commons',
           'source_url': 'https://commons.wikimedia.org/wiki/File:2022_Tata_Tiago_XZA%2B_front_20230512.jpg',
           'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'harrier': {'filename': 'harrier.jpg',
             'credit': 'Matti Blume / Wikimedia Commons',
             'source_url': 'https://commons.wikimedia.org/wiki/File:Tata_Buzzard_Sport,_GIMS_2019,_Le_Grand-Saconnex_(GIMS0651).jpg',
             'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'xuv700': {'filename': 'xuv700.jpg',
            'credit': 'Ank Kumar / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:A_black_Mahindra_XUV700_SUV_in_Ashiana_Brahmananda,_Jamshedpur,_India_(Ank_Kumar,_Infosys_Limited)_01.jpg',
            'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'thar': {'filename': 'thar.jpg',
          'credit': 'Ank Kumar / Wikimedia Commons',
          'source_url': 'https://commons.wikimedia.org/wiki/File:Mahindra_Thar_SUV_in_%22Red_Rage%22_color_at_Ashiana_Brahmanda,_East_Singbhum_India_(Ank_Kumar,_Infosys_limited)_02_(cropped).jpg',
          'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'scorpio-n': {'filename': 'scorpio-n.jpg',
               'credit': 'LuvsMG481 / Wikimedia Commons',
               'source_url': 'https://commons.wikimedia.org/wiki/File:2024_Mahindra_Scorpio_Z8L_front.jpg',
               'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'seltos': {'filename': 'seltos.jpg',
            'credit': 'Alexander-93 / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:Kia_Seltos_IMG_9152.jpg',
            'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'sonet': {'filename': 'sonet.jpg',
           'credit': 'Zotyefan / Wikimedia Commons',
           'source_url': 'https://commons.wikimedia.org/wiki/File:Kia_Sonet_IMG001.jpg',
           'license': 'CC0 (https://creativecommons.org/publicdomain/zero/1.0/deed.en)'},
 'innova-hycross': {'filename': 'innova-hycross.jpg',
                    'credit': 'Ethan Llamas / Wikimedia Commons',
                    'source_url': 'https://commons.wikimedia.org/wiki/File:2023_Toyota_Zenix_2.0_v.jpg',
                    'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'fortuner': {'filename': 'fortuner.jpg',
              'credit': 'Andra Febrian / Wikimedia Commons',
              'source_url': 'https://commons.wikimedia.org/wiki/File:2021_Toyota_Fortuner_SRZ_2.7_4x2_(Indonesia)_front_view_01.jpg',
              'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'city': {'filename': 'city.jpg',
          'credit': '© M 93 / Wikimedia Commons',
          'source_url': 'https://commons.wikimedia.org/wiki/File:Honda_City_1.5_i-VTEC_V_(VIII,_Facelift)_%E2%80%93_f_22032025.jpg',
          'license': 'CC BY-SA 3.0 de (https://creativecommons.org/licenses/by-sa/3.0/de/deed.en)'},
 'elevate': {'filename': 'elevate.jpg',
             'credit': 'Hulchul TV / Wikimedia Commons',
             'source_url': 'https://commons.wikimedia.org/wiki/File:2023_Honda_Elevate_VX_(India)_front_view.jpg',
             'license': 'CC BY 3.0 (https://creativecommons.org/licenses/by/3.0)'},
 'slavia': {'filename': 'slavia.jpg',
            'credit': 'Saiphani02 / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:Skoda_Slavia_Side_view.jpg',
            'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'kushaq': {'filename': 'kushaq.jpg',
            'credit': 'Saiphani02 / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:Skoda_Kushaq_Front.jpg',
            'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'virtus': {'filename': 'virtus.jpg',
            'credit': 'Dairokkan9 / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:2023_Volkswagen_Virtus_Topline_front_20230520.jpg',
            'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'taigun': {'filename': 'taigun.jpg',
            'credit': 'Dairokkan9 / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:Volkswagen_Taigun_front_20230528.jpg',
            'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'kiger': {'filename': 'kiger.jpg',
           'credit': 'Dairokkan9 / Wikimedia Commons',
           'source_url': 'https://commons.wikimedia.org/wiki/File:Renault_Kiger_front_20230602.jpg',
           'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'hector': {'filename': 'hector.jpg',
            'credit': 'Ank Kumar / Wikimedia Commons',
            'source_url': 'https://commons.wikimedia.org/wiki/File:MG(Morris_Garages)_Hector_SUV_in_Jamshedpur,_Jharkhand,_India_(Ank_Kumar,_Infosys_Limited))_02.jpg',
            'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'},
 'magnite': {'filename': 'magnite.jpg',
             'credit': 'Ganesh Mohan T / Wikimedia Commons',
             'source_url': 'https://commons.wikimedia.org/wiki/File:Nissan_Magnite_01.jpg',
             'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0)'}}
