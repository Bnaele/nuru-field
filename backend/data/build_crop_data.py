"""Build backend/data/crop_reference.csv from the FAO ECOCROP archive.

Why this exists
---------------
The hackathon build shipped a hand-written crop table that nobody could trace:
`crop_reference` was seeded directly into a Supabase project and the seed script
was never committed. This script replaces it with values derived from a public,
citable source, so anyone can regenerate the file and check it.

Source
------
ECOCROP: FAO Crop Ecological Requirements Database, archived on Zenodo.
    DOI  10.5281/zenodo.13319716
    https://zenodo.org/records/13319716
    Scraped from the original FAO ECOCROP data sheets by supersistence
    (github.com/supersistence/EcoCrop-ScrapeR).

The archive is "measurements or facts" format. For each taxon it carries optimal
growth temperature, optimal annual rainfall and optimal soil pH as a min/max
pair, distinguished by statisticalMethod:

    SIO_001113 -> minimum
    SIO_001114 -> maximum

Coverage
--------
Every taxon in the archive with a usable envelope is included — not a hand-picked
shortlist. Of the 2,567 taxa, 2,071 carry a complete temperature pair; two of
those are rejected as impossible (see PLAUSIBLE), and de-duplication by common
name removes two more, leaving 2,065 rows. That set spans fruit, vegetables,
herbs, spices, nuts, grains, legumes, oilseeds, fodder, fibre, timber, medicinal
and ornamental plants.

The archive only carries scientific names, so common names are supplied for the
species a South African grower is likely to search for (see CURATED_NAMES).
Everything else keeps its scientific name as the display name rather than being
dropped, because "I cannot name this in English" is not a reason to hide a plant
that has a real envelope. A row whose name is still Latin is visible as such.

Source data is not trusted blindly. A handful of values in the archive are
transcription errors — a minimum temperature of 160 C, a 9000 mm rainfall
minimum against a 1300 mm maximum — and those are handled explicitly rather than
passed through or silently repaired.

What is derived vs. what is authored
------------------------------------
- Derived (from ECOCROP): min_temp, max_temp, min_rainfall_mm, max_rainfall_mm,
  min_ph, max_ph.
- Authored here (human judgement, not agronomic data): the species-to-common-name
  mapping and the category label. Common names and groupings are labels, not
  measurements, so they are not something a dataset can supply.

Rainfall and pH are written empty when the archive has no pair for them, rather
than defaulted to a plausible midpoint. The scorer renormalises its weights over
whatever is present and drops its confidence accordingly.

Usage
-----
    python backend/data/build_crop_data.py            # regenerate the CSV
    python backend/data/build_crop_data.py --check    # verify the CSV is current

The raw archive is downloaded into a gitignored scratch directory; only the
derived CSV is committed, because the archive is 10 MB and reproducible from
its DOI in one request.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ZENODO_ZIP = "https://zenodo.org/api/records/13319716/files/archive.zip/content"
SOURCE_NAME = "FAO ECOCROP via Zenodo 10.5281/zenodo.13319716"

HERE = Path(__file__).resolve().parent
OUT_CSV = HERE / "crop_reference.csv"
SCRATCH = HERE / ".ecocrop"
ARCHIVE = SCRATCH / "archive.zip"

# Common names and groupings for species a grower is likely to search for.
# This only overrides the label; it never decides whether a crop is included.
# Grouping is presentational.
CURATED_NAMES: dict[str, tuple[str, str]] = {
    # --- grains and staples ---
    "Zea mays": ("Maize", "Grain"),
    "Triticum aestivum": ("Wheat", "Grain"),
    "Hordeum vulgare": ("Barley", "Grain"),
    "Avena sativa": ("Oats", "Grain"),
    "Secale cereale": ("Rye", "Grain"),
    "Sorghum bicolor": ("Sorghum", "Grain"),
    "Pennisetum glaucum": ("Pearl millet", "Grain"),
    "Eleusine coracana": ("Finger millet", "Grain"),
    "Eragrostis tef": ("Teff", "Grain"),
    "Oryza sativa": ("Rice", "Grain"),
    "Oryza glaberrima": ("African rice", "Grain"),
    "Panicum miliaceum": ("Proso millet", "Grain"),
    "Fagopyrum esculentum": ("Buckwheat", "Grain"),
    "Chenopodium quinoa": ("Quinoa", "Grain"),
    "Amaranthus caudatus": ("Amaranth", "Grain"),
    "Solanum tuberosum": ("Potato", "Staple"),
    "Ipomoea batatas": ("Sweet potato", "Staple"),
    "Manihot esculenta": ("Cassava", "Staple"),
    "Colocasia esculenta": ("Taro", "Staple"),
    "Dioscorea rotundata": ("Yam", "Staple"),
    "Dioscorea alata": ("Greater yam", "Staple"),
    "Xanthosoma sagittifolium": ("Tannia", "Staple"),
    "Canna indica": ("Canna", "Ornamental"),
    # --- legumes ---
    "Phaseolus vulgaris": ("Dry beans", "Legume"),
    "Phaseolus coccineus": ("Runner bean", "Legume"),
    "Phaseolus lunatus": ("Lima bean", "Legume"),
    "Pisum sativum": ("Peas", "Legume"),
    "Cicer arietinum": ("Chickpea", "Legume"),
    "Lens culinaris": ("Lentil", "Legume"),
    "Arachis hypogaea": ("Groundnut", "Legume"),
    "Glycine max": ("Soybean", "Legume"),
    "Vigna unguiculata": ("Cowpea", "Legume"),
    "Vigna radiata": ("Mung bean", "Legume"),
    "Vigna subterranea": ("Bambara groundnut", "Legume"),
    "Vicia faba": ("Faba bean", "Legume"),
    "Cajanus cajan": ("Pigeon pea", "Legume"),
    "Lablab purpureus": ("Lablab", "Legume"),
    "Macrotyloma uniflorum": ("Horse gram", "Legume"),
    "Mucuna pruriens": ("Velvet bean", "Fodder"),
    "Medicago sativa": ("Lucerne", "Fodder"),
    "Trifolium repens": ("White clover", "Fodder"),
    "Trifolium pratense": ("Red clover", "Fodder"),
    "Lupinus albus": ("White lupin", "Legume"),
    # --- oil and fibre ---
    "Helianthus annuus": ("Sunflower", "Oilseed"),
    "Brassica napus": ("Canola", "Oilseed"),
    "Brassica juncea": ("Brown mustard", "Oilseed"),
    "Sesamum indicum": ("Sesame", "Oilseed"),
    "Carthamus tinctorius": ("Safflower", "Oilseed"),
    "Ricinus communis": ("Castor bean", "Industrial"),
    "Olea europaea": ("Olive", "Fruit"),
    "Cocos nucifera": ("Coconut", "Fruit"),
    "Elaeis guineensis": ("Oil palm", "Industrial"),
    "Gossypium hirsutum": ("Cotton", "Fibre"),
    "Gossypium barbadense": ("Sea island cotton", "Fibre"),
    "Agave sisalana": ("Sisal", "Fibre"),
    "Linum usitatissimum": ("Flax", "Fibre"),
    "Boehmeria nivea": ("Ramie", "Fibre"),
    "Hibiscus cannabinus": ("Kenaf", "Fibre"),
    "Saccharum officinarum": ("Sugarcane", "Industrial"),
    "Beta vulgaris var. saccharifera": ("Sugar beet", "Industrial"),
    # --- leafy vegetables ---
    "Spinacia oleracea": ("Spinach", "Vegetable"),
    "Beta vulgaris": ("Beetroot", "Vegetable"),
    "Beta vulgaris var. cicla": ("Swiss chard", "Vegetable"),
    "Lactuca sativa": ("Lettuce", "Vegetable"),
    "Lactuca sativa var. capitata": ("Lettuce", "Vegetable"),
    "Brassica oleracea var. capitata": ("Cabbage", "Vegetable"),
    "Brassica oleracea var. botrytis": ("Cauliflower", "Vegetable"),
    "Brassica oleracea var. italica": ("Broccoli", "Vegetable"),
    "Brassica oleracea var. gemmifera": ("Brussels sprouts", "Vegetable"),
    "Brassica oleracea var. gongylodes": ("Kohlrabi", "Vegetable"),
    "Brassica oleracea var. viridis": ("Kale", "Vegetable"),
    "Brassica rapa": ("Turnip", "Vegetable"),
    "Brassica pekinensis": ("Chinese cabbage", "Vegetable"),
    "Brassica chinensis": ("Pak choi", "Vegetable"),
    "Brassica nigra": ("Black mustard", "Spice"),
    "Eruca vesicaria": ("Rocket", "Vegetable"),
    "Cichorium intybus": ("Chicory", "Vegetable"),
    "Cichorium endivia": ("Endive", "Vegetable"),
    "Apium graveolens": ("Celery", "Vegetable"),
    "Apium graveolens var. dulce": ("Celery", "Vegetable"),
    "Petroselinum crispum": ("Parsley", "Herb"),
    "Coriandrum sativum": ("Coriander", "Herb"),
    "Anethum graveolens": ("Dill", "Herb"),
    "Foeniculum vulgare": ("Fennel", "Herb"),
    "Mentha spicata": ("Spearmint", "Herb"),
    "Mentha x piperita": ("Peppermint", "Herb"),
    "Ocimum basilicum": ("Basil", "Herb"),
    "Thymus vulgaris": ("Thyme", "Herb"),
    "Origanum vulgare": ("Oregano", "Herb"),
    "Rosmarinus officinalis": ("Rosemary", "Herb"),
    "Salvia officinalis": ("Sage", "Herb"),
    "Artemisia dracunculus": ("Tarragon", "Herb"),
    "Lavandula angustifolia": ("Lavender", "Herb"),
    "Amaranthus hybridus": ("Amaranth greens", "Vegetable"),
    "Amaranthus tricolor": ("Leaf amaranth", "Vegetable"),
    "Cleome gynandra": ("Spider plant", "Vegetable"),
    "Corchorus olitorius": ("Jute mallow", "Vegetable"),
    "Solanum nigrum": ("Black nightshade", "Vegetable"),
    "Portulaca oleracea": ("Purslane", "Vegetable"),
    "Urtica dioica": ("Stinging nettle", "Medicinal"),
    # --- root and bulb vegetables ---
    "Daucus carota": ("Carrot", "Vegetable"),
    "Pastinaca sativa": ("Parsnip", "Vegetable"),
    "Raphanus sativus": ("Radish", "Vegetable"),
    "Allium cepa": ("Onion", "Vegetable"),
    "Allium fistulosum": ("Spring onion", "Vegetable"),
    "Allium porrum": ("Leek", "Vegetable"),
    "Allium sativum": ("Garlic", "Vegetable"),
    "Allium schoenoprasum": ("Chives", "Herb"),
    "Apium graveolens var. rapaceum": ("Celeriac", "Vegetable"),
    "Arracacia xanthorrhiza": ("Arracacha", "Vegetable"),
    "Pachyrhizus erosus": ("Jicama", "Vegetable"),
    "Smallanthus sonchifolius": ("Yacon", "Vegetable"),
    "Zingiber officinale": ("Ginger", "Spice"),
    "Curcuma longa": ("Turmeric", "Spice"),
    "Armoracia rusticana": ("Horseradish", "Spice"),
    # --- fruiting vegetables ---
    "Solanum lycopersicum": ("Tomato", "Vegetable"),
    "Lycopersicon esculentum": ("Tomato", "Vegetable"),
    "Solanum melongena": ("Brinjal", "Vegetable"),
    "Capsicum annuum": ("Pepper", "Vegetable"),
    "Capsicum frutescens": ("Chilli", "Vegetable"),
    "Capsicum baccatum": ("Aji", "Vegetable"),
    "Abelmoschus esculentus": ("Okra", "Vegetable"),
    "Abelmoschus manihot": ("Aibika", "Vegetable"),
    "Cucumis sativus": ("Cucumber", "Vegetable"),
    "Cucumis melo": ("Melon", "Vegetable"),
    "Citrullus lanatus": ("Watermelon", "Vegetable"),
    "Cucurbita maxima": ("Pumpkin", "Vegetable"),
    "Cucurbita pepo": ("Squash", "Vegetable"),
    "Cucurbita moschata": ("Butternut", "Vegetable"),
    "Cucurbita ficifolia": ("Fig-leaf gourd", "Vegetable"),
    "Lagenaria siceraria": ("Bottle gourd", "Vegetable"),
    "Luffa acutangula": ("Ridge gourd", "Vegetable"),
    "Momordica charantia": ("Bitter gourd", "Vegetable"),
    "Trichosanthes cucumerina": ("Snake gourd", "Vegetable"),
    "Sechium edule": ("Chayote", "Vegetable"),
    "Physalis peruviana": ("Gooseberry", "Fruit"),
    "Solanum betaceum": ("Tree tomato", "Fruit"),
    # --- deciduous and vine fruit ---
    "Vitis vinifera": ("Grape", "Fruit"),
    "Malus domestica": ("Apple", "Fruit"),
    "Pyrus communis": ("Pear", "Fruit"),
    "Prunus persica": ("Peach", "Fruit"),
    "Prunus armeniaca": ("Apricot", "Fruit"),
    "Prunus domestica": ("Plum", "Fruit"),
    "Prunus salicina": ("Japanese plum", "Fruit"),
    "Prunus avium": ("Cherry", "Fruit"),
    "Prunus dulcis": ("Almond", "Nut"),
    "Cydonia oblonga": ("Quince", "Fruit"),
    "Ficus carica": ("Fig", "Fruit"),
    "Fragaria x ananassa": ("Strawberry", "Fruit"),
    "Fragaria vesca": ("Alpine strawberry", "Fruit"),
    "Rubus idaeus": ("Raspberry", "Fruit"),
    "Rubus fruticosus": ("Blackberry", "Fruit"),
    "Ribes rubrum": ("Red currant", "Fruit"),
    "Ribes nigrum": ("Black currant", "Fruit"),
    "Vaccinium corymbosum": ("Blueberry", "Fruit"),
    "Vaccinium myrtillus": ("Bilberry", "Fruit"),
    "Punica granatum": ("Pomegranate", "Fruit"),
    "Diospyros kaki": ("Persimmon", "Fruit"),
    "Morus alba": ("Mulberry", "Fruit"),
    "Morus nigra": ("Black mulberry", "Fruit"),
    # --- citrus ---
    "Citrus limon": ("Lemon", "Fruit"),
    "Citrus sinensis": ("Orange", "Fruit"),
    "Citrus reticulata": ("Mandarin", "Fruit"),
    "Citrus paradisi": ("Grapefruit", "Fruit"),
    "Citrus aurantium": ("Seville orange", "Fruit"),
    "Citrus aurantifolia": ("Lime", "Fruit"),
    "Citrus latifolia": ("Tahiti lime", "Fruit"),
    "Citrus Clementina": ("Clementine", "Fruit"),
    # --- subtropical and tropical fruit ---
    "Persea americana": ("Avocado", "Fruit"),
    "Mangifera indica": ("Mango", "Fruit"),
    "Musa acuminata": ("Banana", "Fruit"),
    "Musa x paradisiaca": ("Plantain", "Fruit"),
    "Psidium guajava": ("Guava", "Fruit"),
    "Ananas comosus": ("Pineapple", "Fruit"),
    "Passiflora edulis": ("Granadilla", "Fruit"),
    "Passiflora ligularis": ("Sweet granadilla", "Fruit"),
    "Carica papaya": ("Papaya", "Fruit"),
    "Litchi chinensis": ("Litchi", "Fruit"),
    "Dimocarpus longan": ("Longan", "Fruit"),
    "Nephelium lappaceum": ("Rambutan", "Fruit"),
    "Annona cherimola": ("Cherimoya", "Fruit"),
    "Annona squamosa": ("Sugar apple", "Fruit"),
    "Annona muricata": ("Soursop", "Fruit"),
    "Artocarpus heterophyllus": ("Jackfruit", "Fruit"),
    "Artocarpus altilis": ("Breadfruit", "Fruit"),
    "Averrhoa carambola": ("Star fruit", "Fruit"),
    "Syzygium jambos": ("Rose apple", "Fruit"),
    "Syzygium samarangense": ("Wax apple", "Fruit"),
    "Tamarindus indica": ("Tamarind", "Fruit"),
    "Phoenix dactylifera": ("Date palm", "Fruit"),
    "Hylocereus undatus": ("Dragon fruit", "Fruit"),
    "Actinidia deliciosa": ("Kiwifruit", "Fruit"),
    "Opuntia ficus-indica": ("Prickly pear", "Fruit"),
    "Sclerocarya birrea": ("Marula", "Fruit"),
    "Dovyalis caffra": ("Kei apple", "Fruit"),
    "Harpephyllum caffrum": ("Wild plum", "Fruit"),
    "Vangueria infausta": ("Wild medlar", "Fruit"),
    "Ximenia caffra": ("Sour plum", "Fruit"),
    "Adansonia digitata": ("Baobab", "Fruit"),
    "Ziziphus mauritiana": ("Jujube", "Fruit"),
    "Landolphia kirkii": ("Rubber vine", "Fruit"),
    # --- nuts ---
    "Juglans regia": ("Walnut", "Nut"),
    "Corylus avellana": ("Hazelnut", "Nut"),
    "Castanea sativa": ("Chestnut", "Nut"),
    "Pistacia vera": ("Pistachio", "Nut"),
    "Anacardium occidentale": ("Cashew", "Nut"),
    "Macadamia integrifolia": ("Macadamia", "Nut"),
    "Macadamia tetraphylla": ("Macadamia", "Nut"),
    "Bertholletia excelsa": ("Brazil nut", "Nut"),
    # --- beverage and spice ---
    "Coffea arabica": ("Coffee", "Beverage"),
    "Coffea canephora": ("Robusta coffee", "Beverage"),
    "Camellia sinensis": ("Tea", "Beverage"),
    "Theobroma cacao": ("Cocoa", "Beverage"),
    "Humulus lupulus": ("Hops", "Beverage"),
    "Piper nigrum": ("Black pepper", "Spice"),
    "Syzygium aromaticum": ("Clove", "Spice"),
    "Myristica fragrans": ("Nutmeg", "Spice"),
    "Cinnamomum verum": ("Cinnamon", "Spice"),
    "Cinnamomum cassia": ("Cassia", "Spice"),
    "Elettaria cardamomum": ("Cardamom", "Spice"),
    "Vanilla planifolia": ("Vanilla", "Spice"),
    "Crocus sativus": ("Saffron", "Spice"),
    "Pimpinella anisum": ("Anise", "Spice"),
    "Carum carvi": ("Caraway", "Spice"),
    "Nigella sativa": ("Black cumin", "Spice"),
    "Aspalathus linearis": ("Rooibos", "Beverage"),
    "Cyclopia genistoides": ("Honeybush", "Beverage"),
    "Pelargonium sidoides": ("Umckaloabo", "Medicinal"),
    "Sutherlandia frutescens": ("Cancer bush", "Medicinal"),
    "Artemisia afra": ("African wormwood", "Medicinal"),
    "Moringa oleifera": ("Moringa", "Vegetable"),
    "Aloe ferox": ("Bitter aloe", "Medicinal"),
    "Aloe vera": ("Aloe", "Medicinal"),
    "Hoodia gordonii": ("Hoodia", "Medicinal"),
    "Lippia javanica": ("Lemon bush", "Medicinal"),
    # --- fodder and pasture ---
    "Zea mays var. saccharata": ("Sweet corn", "Vegetable"),
    "Sorghum sudanense": ("Sudan grass", "Fodder"),
    "Pennisetum purpureum": ("Elephant grass", "Fodder"),
    "Panicum maximum": ("Guinea grass", "Fodder"),
    "Chloris gayana": ("Rhodes grass", "Fodder"),
    "Digitaria eriantha": ("Smuts finger grass", "Fodder"),
    "Eragrostis curvula": ("Weeping lovegrass", "Fodder"),
    "Cenchrus ciliaris": ("Buffel grass", "Fodder"),
    "Lolium perenne": ("Perennial ryegrass", "Fodder"),
    "Dactylis glomerata": ("Cocksfoot", "Fodder"),
    "Festuca arundinacea": ("Tall fescue", "Fodder"),
    "Avena strigosa": ("Black oats", "Fodder"),
    "Vicia villosa": ("Hairy vetch", "Fodder"),
    "Brassica oleracea": ("Kale", "Fodder"),
    "Opuntia streptacantha": ("Cactus pear", "Fodder"),
    "Atriplex nummularia": ("Old man saltbush", "Fodder"),
    "Leucaena leucocephala": ("Leucaena", "Fodder"),
    "Gliricidia sepium": ("Gliricidia", "Fodder"),
    "Sesbania sesban": ("Sesbania", "Fodder"),
    "Desmodium intortum": ("Greenleaf desmodium", "Fodder"),
    # --- timber and agroforestry ---
    "Eucalyptus grandis": ("Flooded gum", "Timber"),
    "Eucalyptus camaldulensis": ("River red gum", "Timber"),
    "Pinus radiata": ("Radiata pine", "Timber"),
    "Pinus patula": ("Patula pine", "Timber"),
    "Acacia mearnsii": ("Black wattle", "Timber"),
    "Acacia mangium": ("Mangium", "Timber"),
    "Grevillea robusta": ("Grevillea", "Timber"),
    "Casuarina equisetifolia": ("Beefwood", "Timber"),
    "Tectona grandis": ("Teak", "Timber"),
    "Swietenia macrophylla": ("Mahogany", "Timber"),
    "Populus deltoides": ("Eastern cottonwood", "Timber"),
    "Salix babylonica": ("Weeping willow", "Timber"),
    "Azadirachta indica": ("Neem", "Medicinal"),
    "Faidherbia albida": ("Ana tree", "Timber"),
    "Combretum apiculatum": ("Red bushwillow", "Timber"),
    # --- ornamental, cut flower and nursery ---
    "Rosa x hybrida": ("Rose", "Ornamental"),
    "Chrysanthemum indicum": ("Chrysanthemum", "Ornamental"),
    "Dianthus caryophyllus": ("Carnation", "Ornamental"),
    "Gladiolus communis": ("Gladiolus", "Ornamental"),
    "Lilium candidum": ("Lily", "Ornamental"),
    "Tulipa gesneriana": ("Tulip", "Ornamental"),
    "Tagetes erecta": ("Marigold", "Ornamental"),
    "Tagetes patula": ("French marigold", "Ornamental"),
    "Calendula officinalis": ("Calendula", "Ornamental"),
    "Helianthus tuberosus": ("Jerusalem artichoke", "Vegetable"),
    "Zinnia elegans": ("Zinnia", "Ornamental"),
    "Petunia x hybrida": ("Petunia", "Ornamental"),
    "Pelargonium graveolens": ("Rose geranium", "Ornamental"),
    "Gerbera jamesonii": ("Barberton daisy", "Ornamental"),
    "Agapanthus africanus": ("Agapanthus", "Ornamental"),
    "Protea cynaroides": ("King protea", "Ornamental"),
    "Leucospermum cordifolium": ("Pincushion protea", "Ornamental"),
    "Strelitzia reginae": ("Crane flower", "Ornamental"),
    "Clivia miniata": ("Bush lily", "Ornamental"),
    "Kniphofia uvaria": ("Red hot poker", "Ornamental"),
    "Iris germanica": ("Bearded iris", "Ornamental"),
    "Freesia refracta": ("Freesia", "Ornamental"),
    "Ornithogalum thyrsoides": ("Chincherinchee", "Ornamental"),
    "Nerine bowdenii": ("Nerine", "Ornamental"),
    "Hydrangea macrophylla": ("Hydrangea", "Ornamental"),
    "Buxus sempervirens": ("Boxwood", "Ornamental"),
    "Lantana camara": ("Lantana", "Ornamental"),
    "Bougainvillea glabra": ("Bougainvillea", "Ornamental"),
    "Hibiscus rosa-sinensis": ("Hibiscus", "Ornamental"),
    "Jasminum officinale": ("Jasmine", "Ornamental"),
    "Plumeria rubra": ("Frangipani", "Ornamental"),
    "Delonix regia": ("Flamboyant tree", "Ornamental"),
    "Jacaranda mimosifolia": ("Jacaranda", "Ornamental"),
    "Schinus molle": ("Pepper tree", "Ornamental"),
    "Cupressus sempervirens": ("Italian cypress", "Ornamental"),
    "Thuja occidentalis": ("Arborvitae", "Ornamental"),
    "Hedera helix": ("Ivy", "Ornamental"),
    "Vinca minor": ("Periwinkle", "Ornamental"),
    "Cyperus alternifolius": ("Umbrella papyrus", "Ornamental"),
    "Nymphaea nouchali": ("Blue water lily", "Ornamental"),
    # --- industrial and multipurpose ---
    "Jatropha curcas": ("Physic nut", "Industrial"),
    "Parthenium argentatum": ("Guayule", "Industrial"),
    "Simmondsia chinensis": ("Jojoba", "Industrial"),
    "Cymbopogon citratus": ("Lemongrass", "Herb"),
    "Cymbopogon nardus": ("Citronella grass", "Industrial"),
    "Vetiveria zizanioides": ("Vetiver", "Industrial"),
    "Bambusa vulgaris": ("Bamboo", "Timber"),
    "Arundo donax": ("Giant reed", "Industrial"),
    "Miscanthus sinensis": ("Miscanthus", "Industrial"),
    "Nicotiana tabacum": ("Tobacco", "Industrial"),
    "Hevea brasiliensis": ("Rubber tree", "Industrial"),

    # --- archive-name aliases ---
    # ECOCROP indexes several species under an older synonym. These entries exist
    # so the labels still land on the row the archive actually carries; without
    # them the crop is included but shows up under its Latin name.
    "Sclerocarya birrea ssp. caffra": ("Marula", "Fruit"),
    "Sclerocarya caffra": ("Marula", "Fruit"),
    "Protea caffra ssp. caffra": ("Protea", "Ornamental"),
    "Syzygium cordatum": ("Waterberry", "Fruit"),
    "Syzygium guineense": ("Water pear", "Fruit"),
    "Syzygium cumini": ("Java plum", "Fruit"),
    "Rubus idaeus ssp. idaeus": ("Raspberry", "Fruit"),
    "Mentha piperita": ("Peppermint", "Herb"),
    "Mentha spicata var. crispa": ("Spearmint", "Herb"),
    "Allium ampeloprasum": ("Leek", "Vegetable"),
    "Allium cepa var. aggregatum": ("Shallot", "Vegetable"),
    "Eruca sativa": ("Rocket", "Vegetable"),
    "Brassica rapa var. rapifera": ("Turnip", "Vegetable"),
    "Brassica rapa Pak Choi": ("Pak choi", "Vegetable"),
    "Musa sapientum": ("Banana", "Fruit"),
    "Musa balbisiana": ("Plantain", "Fruit"),
    "Citrus medica": ("Citron", "Fruit"),
    "Citrus grandis": ("Pomelo", "Fruit"),
    "Hibiscus sabdariffa": ("Roselle", "Beverage"),
    "Sorghum bicolor var. sweet": ("Sweet sorghum", "Fodder"),
    "Vicia villosa ssp. villosa": ("Hairy vetch", "Fodder"),
}

DERIVED_PROPERTIES = {
    "OptimalGrowthTemperature": ("min_temp", "max_temp"),
    "optimal_rainfall": ("min_rainfall_mm", "max_rainfall_mm"),
    "OptimalGrowthpH": ("min_ph", "max_ph"),
}

# Temperature is the signal the scorer always uses, so a taxon without it cannot
# be scored at all. Rainfall and pH are optional: the archive simply lacks them
# for some species, and inventing a midpoint would be fabrication.
REQUIRED_PROPERTY = "OptimalGrowthTemperature"

FIELDS = [
    "name", "scientific_name", "category",
    "min_temp", "max_temp",
    "min_rainfall_mm", "max_rainfall_mm",
    "min_ph", "max_ph",
    "source",
]

UNCATEGORISED = "Other"


def fetch_archive() -> Path:
    """Download the ECOCROP archive once into a gitignored scratch dir."""
    if ARCHIVE.exists() and ARCHIVE.stat().st_size > 100_000:
        return ARCHIVE
    SCRATCH.mkdir(parents=True, exist_ok=True)
    print(f"downloading {ZENODO_ZIP}", file=sys.stderr)
    with urllib.request.urlopen(ZENODO_ZIP, timeout=120) as response:
        ARCHIVE.write_bytes(response.read())
    return ARCHIVE


def read_archive(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Return (taxonID -> scientificName, measurement rows)."""
    with zipfile.ZipFile(path) as archive:
        taxa_rows = list(csv.DictReader(
            io.TextIOWrapper(archive.open("taxa.txt"), encoding="utf-8", errors="ignore"),
            delimiter="\t",
        ))
        measurements = list(csv.DictReader(
            io.TextIOWrapper(archive.open("measurementsorfacts.txt"), encoding="utf-8", errors="ignore"),
            delimiter="\t",
        ))
    taxa = {row["taxonID"]: row["scientificName"].strip() for row in taxa_rows}
    return taxa, measurements


def _clean_number(value: str) -> str:
    """Normalise an archive number to a plain decimal string, or '' if unusable."""
    text = (value or "").strip().replace(",", ".")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return ""
    if number != number:  # NaN
        return ""
    return f"{number:g}"


# The archive is a scrape of FAO's published sheets and carries a few
# transcription errors. Barringtonia racemosa is recorded with a minimum growth
# temperature of 160 and Eugenia stipitata with 2000-3500, both against a unit of
# degrees Celsius; Carissa edulis carries a 9000 mm rainfall minimum.
#
# These are rejected rather than repaired. Guessing that 160 means 16, or that a
# 9000 came from a stray zero, would be inventing agronomic data in a project
# whose whole point is that every number is traceable.
#
# The windows are deliberately very wide: they exist to catch impossible values,
# not to second-guess unusual but real ones.
PLAUSIBLE = {
    "OptimalGrowthTemperature": (-15.0, 60.0),   # degrees C
    "optimal_rainfall": (0.0, 20000.0),          # mm per year
    "OptimalGrowthpH": (2.0, 11.0),
}


def _is_plausible(prop: str, bounds: dict[str, str]) -> bool:
    """True if the envelope is complete, correctly ordered and physically possible."""
    low_text = bounds.get("min") or ""
    high_text = bounds.get("max") or ""
    if not low_text or not high_text:
        return False
    low, high = float(low_text), float(high_text)
    if low > high:
        return False
    floor, ceiling = PLAUSIBLE[prop]
    return floor <= low and high <= ceiling


def build_rows(
    taxa: dict[str, str],
    measurements: list[dict[str, str]],
    *,
    verbose: bool = False,
) -> list[dict[str, str]]:
    # (taxonID, property) -> {"min": value, "max": value}
    envelopes: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for row in measurements:
        tid = (row.get("occurrenceID") or "").strip()
        if tid not in taxa:
            continue
        prop = (row.get("measurementType") or "").rsplit("/", 1)[-1]
        if prop not in DERIVED_PROPERTIES:
            continue
        method = row.get("statisticalMethod") or ""
        if "SIO_001113" in method:
            bound = "min"
        elif "SIO_001114" in method:
            bound = "max"
        else:
            continue
        number = _clean_number(row.get("measurementValue") or "")
        if number:
            envelopes[(tid, prop)][bound] = number

    rejected: list[str] = []
    dropped: list[str] = []

    candidates: list[dict[str, str]] = []
    for tid, scientific in taxa.items():
        required = envelopes.get((tid, REQUIRED_PROPERTY), {})
        if "min" not in required or "max" not in required:
            continue
        if not _is_plausible(REQUIRED_PROPERTY, required):
            # Without a usable temperature window the species cannot be scored at
            # all, so the row is dropped and the reason is reported.
            rejected.append(f"{scientific} ({required.get('min')}-{required.get('max')} C)")
            continue

        curated = CURATED_NAMES.get(scientific)
        record = {
            "name": curated[0] if curated else scientific,
            "scientific_name": scientific,
            "category": curated[1] if curated else UNCATEGORISED,
            "source": SOURCE_NAME,
        }

        usable = 0
        for prop, (min_field, max_field) in DERIVED_PROPERTIES.items():
            bounds = envelopes.get((tid, prop), {})
            if _is_plausible(prop, bounds):
                usable += 1
                record[min_field] = bounds["min"]
                record[max_field] = bounds["max"]
            else:
                # A broken optional envelope loses the envelope, not the species:
                # the crop can still be scored on its temperature window, and the
                # scorer renormalises over what is present.
                record[min_field] = ""
                record[max_field] = ""
                if bounds:
                    dropped.append(
                        f"{scientific} {prop.replace('OptimalGrowth', '').lower()} "
                        f"{bounds.get('min', '?')}-{bounds.get('max', '?')}"
                    )

        # Completeness is only used to choose between two taxa sharing a common
        # name; it never excludes a crop.
        record["_completeness"] = str(usable)
        candidates.append(record)

    # Lycopersicon esculentum and Solanum lycopersicum are both "Tomato", and two
    # Macadamia species share a name too. Scientific names are unique per taxon,
    # so the only possible collisions are curated common names: keep whichever
    # carries more complete envelope data. Uncurated taxa keep their Latin name
    # and are never dropped.
    by_name: dict[str, dict[str, str]] = {}
    for record in sorted(candidates, key=lambda r: (-int(r["_completeness"]), r["scientific_name"])):
        if record["name"] in by_name:
            continue
        by_name[record["name"]] = record

    rows = []
    for record in sorted(by_name.values(), key=lambda r: (r["category"], r["name"])):
        record.pop("_completeness", None)
        rows.append(record)

    # A row dropped for impossible data is a defect in the source, not something
    # routine, so it is always named. These are the species a reader should know
    # are missing rather than wonder about.
    for line in rejected:
        print(f"warning: dropped {line} - value is not physically possible", file=sys.stderr)

    # A dropped optional envelope is minor: the crop is still listed and scored on
    # temperature. Listed only under --verbose.
    if dropped and verbose:
        for line in dropped:
            print(f"note: blanked impossible envelope {line}", file=sys.stderr)

    # Report curated species the archive does not carry under that exact name,
    # so a typo or a renamed synonym is visible instead of silently missing. The
    # full list is behind --verbose because most of them are ornamental species
    # ECOCROP simply never covered, which is expected rather than a defect.
    present = {row["scientific_name"] for row in rows}
    missing = sorted(set(CURATED_NAMES) - present)
    if missing:
        if verbose:
            print(
                f"warning: {len(missing)} curated species not found in the archive: "
                f"{', '.join(missing)}",
                file=sys.stderr,
            )
        else:
            print(
                f"note: {len(missing)} curated species are not in the archive "
                f"(run with --verbose to list them)",
                file=sys.stderr,
            )

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build crop_reference.csv from ECOCROP.")
    parser.add_argument("--check", action="store_true",
                        help="regenerate in memory and fail if the committed CSV differs")
    parser.add_argument("--verbose", action="store_true",
                        help="list curated species the archive does not carry")
    args = parser.parse_args()

    archive = fetch_archive()
    taxa, measurements = read_archive(archive)
    rows = build_rows(taxa, measurements, verbose=args.verbose)

    if not rows:
        print("error: no crop rows built - the archive format may have changed", file=sys.stderr)
        return 1

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    generated = buffer.getvalue()

    if args.check:
        existing = OUT_CSV.read_text(encoding="utf-8") if OUT_CSV.exists() else ""
        if existing != generated:
            print("error: crop_reference.csv is stale - run build_crop_data.py", file=sys.stderr)
            return 1
        print(f"ok: {len(rows)} crops, CSV is current")
        return 0

    OUT_CSV.write_text(generated, encoding="utf-8")
    print(f"wrote {OUT_CSV.relative_to(HERE.parent.parent)} - {len(rows)} crops from {SOURCE_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
